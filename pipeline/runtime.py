"""Long-running device coordinator: collection, mode switching, processing, and sync."""
from __future__ import annotations

import logging
import signal
import time
from threading import Event

from .cloud_client import CloudClient
from .collector import Collector
from .config import DeviceConfig, ensure_parent
from .db import Database
from .mock_client import MockTcpClient
from .processing import process_offline_results

log = logging.getLogger("mayacardio.pipeline")


class PipelineRuntime:
    def __init__(self, config: DeviceConfig | None = None):
        self.config = config or DeviceConfig()
        ensure_parent(self.config.db_path)
        self.db = Database(self.config.db_path)
        self.cloud = CloudClient(self.config)
        self.collector = Collector(
            self.db,
            MockTcpClient(self.config.mock_host, self.config.mock_port, timeout=max(0.5, self.config.read_timeout)),
        )
        self.stop_event = Event()
        self.mode = self.db.get_meta("current_mode", "offline") or "offline"
        self.last_health_check = 0.0
        self.cloud_is_healthy: bool | None = None

    def stop(self) -> None:
        self.stop_event.set()

    def _switch_mode(self, new_mode: str) -> None:
        if new_mode == self.mode:
            return
        log.warning("Mode switch: %s -> %s", self.mode, new_mode)
        self.mode = new_mode
        self.db.set_meta("current_mode", new_mode)
        self.db.add_event("mode_switch", f"Device mode changed to {new_mode}", self.collector.active_session_id)

    def _check_cloud(self, force: bool = False) -> bool:
        now = time.monotonic()
        if not force and now - self.last_health_check < self.config.health_interval:
            return bool(self.cloud_is_healthy)
        self.last_health_check = now
        healthy = self.cloud.health()
        self.cloud_is_healthy = healthy
        return healthy

    def _process_sessions(self) -> None:
        active = self.collector.active_session_id
        if self.mode == "offline":
            # A network failure can occur after an online mode marker was persisted locally
            # but before the cloud acknowledged it. Reclassify those unacknowledged windows
            # so they are processed locally during the outage, including after a restart.
            changed = self.db.reclassify_unuploaded_online_to_offline()
            if changed:
                log.info("Reclassified %s unacknowledged online windows for offline processing", changed)
        if active:
            # Assign modes before processing, so the cloud never mistakes an offline backlog for live online data.
            if self.mode == "offline":
                self.db.assign_ready_windows(active, "offline")
                created = process_offline_results(self.db, active)
                if created:
                    log.info("Created %s offline window results for %s", created, active)
            else:
                self.db.assign_ready_windows(active, "online")
        # Finish any locally assigned offline windows after a restart as well.
        for session_id in self.db.get_sessions():
            if session_id == active:
                continue
            created = process_offline_results(self.db, session_id)
            if created:
                log.info("Recovered %s offline result windows for prior session %s", created, session_id)

    def run(self) -> None:
        """Run until Ctrl+C / stop_event. Every sample batch is committed before cloud upload."""
        log.info("Pipeline starting; mock=%s:%s cloud=%s", self.config.mock_host, self.config.mock_port, self.config.cloud_url)
        # Startup starts in offline-safe mode. If cloud is reachable, any ready backlog is first finalized locally.
        previous_mode = self.mode
        self.collector.poll_both()
        healthy = self._check_cloud(force=True)
        if healthy and previous_mode == "offline":
            if self.collector.active_session_id:
                self.db.assign_ready_windows(self.collector.active_session_id, "offline")
                process_offline_results(self.db, self.collector.active_session_id)
            self._switch_mode("online")
        elif not healthy:
            self._switch_mode("offline")
        try:
            while not self.stop_event.is_set():
                try:
                    self.collector.poll_both()
                except Exception as exc:  # keep acquisition loop alive; always preserve a diagnostic.
                    self.db.add_event("collector_cycle_error", repr(exc), self.collector.active_session_id)
                    log.exception("Collector cycle failed")

                healthy = self._check_cloud()
                if not healthy:
                    self._switch_mode("offline")
                elif self.mode == "offline":
                    # Finalize any closed outage windows locally before going back online.
                    if self.collector.active_session_id:
                        self.db.assign_ready_windows(self.collector.active_session_id, "offline")
                        process_offline_results(self.db, self.collector.active_session_id)
                    self._switch_mode("online")

                self._process_sessions()
                if self.mode == "online":
                    synced = self.cloud.sync_once(self.db)
                    if synced is None:
                        log.warning("Cloud ingestion failed; entering offline mode")
                        self.cloud_is_healthy = False
                        self.db.reclassify_unuploaded_online_to_offline(self.collector.active_session_id)
                        self._switch_mode("offline")
                        self._process_sessions()
                    elif synced.get("samples", 0) or synced.get("results", 0) or synced.get("modes", 0):
                        log.debug("Sync batch: %s", synced)
                time.sleep(max(0.005, self.config.poll_interval))
        finally:
            self.collector.close()
            self.db.set_meta("current_mode", self.mode)
            log.info("Pipeline stopped in %s mode", self.mode)


def configure_logging(verbose: bool = False) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
