"""Required JSON-lines command-line interface and the runtime launcher."""
from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import sys
import time
from typing import Any

import requests

from .cloud_client import CloudClient
from .config import DeviceConfig, ensure_parent
from .db import Database
from .runtime import PipelineRuntime, configure_logging


def _json_line(value: Any) -> None:
    print(json.dumps(value, separators=(",", ":"), ensure_ascii=False))


def _cloud_session(config: DeviceConfig) -> requests.Session:
    session = requests.Session()
    if config.cloud_token:
        session.headers["Authorization"] = f"Bearer {config.cloud_token}"
    return session


def _cloud_export(config: DeviceConfig, session_id: str):
    client = _cloud_session(config)
    samples: list[dict[str, Any]] = []
    for sensor in (1, 2):
        start = 0
        while True:
            response = client.get(
                f"{config.cloud_url}/v1/sessions/{session_id}/samples",
                params={"sensor": sensor, "start": start, "limit": 10000}, timeout=(config.connect_timeout, config.read_timeout),
            )
            response.raise_for_status()
            rows = response.json()
            if not rows:
                break
            samples.extend(rows)
            latest = max(int(row["index"]) for row in rows)
            if latest < start:
                break
            start = latest + 1
            if len(rows) < 10000:
                break
    # Required export format: all sample lines, then all explicit loss lines.
    for row in sorted(samples, key=lambda r: (int(r["sensor"]), int(r["index"]))):
        yield {"sensor": int(row["sensor"]), "index": int(row["index"]), "values": row["values"]}
    response = client.get(f"{config.cloud_url}/v1/sessions/{session_id}/losses", timeout=(config.connect_timeout, config.read_timeout))
    response.raise_for_status()
    for row in sorted(response.json(), key=lambda r: (int(r["sensor"]), int(r["from_index"]))):
        yield {"sensor": int(row["sensor"]), "from_index": int(row["from_index"]),
               "to_index": row.get("to_index"), "reason": row["reason"]}


def main() -> None:
    parser = argparse.ArgumentParser(prog="pipeline", description="MayaCardio synthetic biosignal pipeline")
    parser.add_argument("--verbose", action="store_true", help="enable detailed logs (for run command)")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("run", help="start continuous acquisition, processing, and cloud synchronization")
    sub.add_parser("status", help="print current mode, saved/cloud samples, and backlog as one JSON line")
    exp = sub.add_parser("export", help="export samples and explicit loss records as JSON lines")
    exp.add_argument("--session", required=True)
    exp.add_argument("--from", dest="source", choices=("device", "cloud"), required=True)
    res = sub.add_parser("results", help="print one JSON line per processed window and mode")
    res.add_argument("--session", required=True)
    sub.add_parser("db-check", help="run SQLite integrity_check and report the result")

    args = parser.parse_args()
    config = DeviceConfig()
    ensure_parent(config.db_path)
    db = Database(config.db_path)

    if args.command == "run":
        configure_logging(args.verbose)
        runtime = PipelineRuntime(config)
        def stop(_signum, _frame):
            runtime.stop()
        signal.signal(signal.SIGINT, stop)
        signal.signal(signal.SIGTERM, stop)
        runtime.run()
        return

    if args.command == "status":
        mode = db.get_meta("current_mode", "offline") or "offline"
        cloud_status = CloudClient(config).status()
        cloud_count = int(cloud_status["samples"]) if cloud_status is not None and "samples" in cloud_status else None
        _json_line(db.status(mode, cloud_count))
        return

    if args.command == "export":
        if args.source == "device":
            for row in db.export_samples(args.session):
                _json_line(row)
        else:
            try:
                for row in _cloud_export(config, args.session):
                    _json_line(row)
            except requests.RequestException as exc:
                print(f"cloud export failed: {exc}", file=sys.stderr)
                raise SystemExit(2)
        return

    if args.command == "results":
        rows: dict[tuple[str, int, str], dict[str, Any]] = {}
        for row in db.results_for_session(args.session):
            rows[(row["session_id"], int(row["window_index"]), row["mode"])] = row
        cloud_rows = CloudClient(config).results(args.session)
        if cloud_rows is not None:
            for row in cloud_rows:
                rows[(row["session_id"], int(row["window_index"]), row["mode"])] = row
        for key in sorted(rows, key=lambda k: (k[1], k[2])):
            _json_line(rows[key])
        return

    if args.command == "db-check":
        with db.connect() as conn:
            rows = [r[0] for r in conn.execute("PRAGMA integrity_check").fetchall()]
        _json_line({"ok": rows == ["ok"], "integrity_check": rows})
        if rows != ["ok"]:
            raise SystemExit(1)
        return


if __name__ == "__main__":
    main()
