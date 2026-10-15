"""HTTP client and prioritized, idempotent synchronization."""
from __future__ import annotations

from typing import Any
import requests

from .config import DeviceConfig
from .db import Database


class CloudClient:
    def __init__(self, config: DeviceConfig):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "mayacardio-pipeline/0.1.0"})
        if config.cloud_token:
            self.session.headers["Authorization"] = f"Bearer {config.cloud_token}"

    def health(self) -> bool:
        try:
            r = self.session.get(f"{self.config.cloud_url}/health", timeout=(self.config.connect_timeout, self.config.read_timeout))
            r.raise_for_status()
            return bool(r.json().get("ok"))
        except (requests.RequestException, ValueError):
            return False

    def status(self, session_id: str | None = None) -> dict[str, Any] | None:
        try:
            r = self.session.get(f"{self.config.cloud_url}/v1/status", params={"session_id": session_id} if session_id else None,
                                 timeout=(self.config.connect_timeout, self.config.read_timeout))
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError):
            return None

    def results(self, session_id: str) -> list[dict[str, Any]] | None:
        try:
            r = self.session.get(f"{self.config.cloud_url}/v1/sessions/{session_id}/results",
                                 timeout=(self.config.connect_timeout, self.config.read_timeout))
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError):
            return None

    def sync_once(self, db: Database) -> dict[str, int] | None:
        """Send new live context and old backlog together; cloud ingestion is idempotent.

        Recent data is prioritized so a new online window can be processed within its
        deadline even when older offline samples are being caught up. Oldest backlog is
        also advanced every cycle so a two-hour outage can fully reconcile.
        """
        samples = db.pending_samples(self.config.upload_live_limit, self.config.upload_backlog_limit)
        losses = db.pending_losses(1000, 1000)
        modes = db.pending_mode_windows(500, 500)
        offline_results = db.pending_offline_results(500, 500)
        if not samples and not losses and not modes and not offline_results:
            return {"samples": 0, "losses": 0, "modes": 0, "results": 0}
        payload = {
            "samples": samples,
            "losses": [{k: v for k, v in row.items() if k != "id"} for row in losses],
            "window_modes": modes,
            "offline_results": offline_results,
        }
        try:
            response = self.session.post(
                f"{self.config.cloud_url}/v1/ingest", json=payload,
                timeout=(self.config.connect_timeout, max(self.config.read_timeout, 4.0)),
            )
            response.raise_for_status()
            response.json()
        except (requests.RequestException, ValueError):
            return None
        db.mark_uploaded(samples=samples, losses=losses, window_modes=modes, offline_results=offline_results)
        return {"samples": len(samples), "losses": len(losses), "modes": len(modes), "results": len(offline_results)}
