from __future__ import annotations

import threading
import time

from pipeline.collector import Collector
from pipeline.db import Database
from pipeline.demo_mock import DemoServer, DemoState
from pipeline.mock_client import MockTcpClient


def test_collector_persists_both_sensors_from_demo_mock(tmp_path):
    state = DemoState("ramp", seed=7, duration=10, speed=100)
    with DemoServer(("127.0.0.1", 0), state) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        time.sleep(0.02)
        host, port = server.server_address
        db = Database(str(tmp_path / "device.db"))
        collector = Collector(db, MockTcpClient(host, port, timeout=1))
        try:
            for _ in range(3):
                collector.poll_both()
            session = collector.active_session_id
            assert session is not None
            assert db.sample_count(session) >= 800
            assert db.get_watermark(session, 1) > 0
            assert db.get_watermark(session, 2) > 0
            assert db.get_samples(session, 1, 0, 0)[0] == [1, 2, 3]
        finally:
            collector.close()
            server.shutdown()
            thread.join(timeout=2)


def test_collector_retries_crc_corruption_and_never_accepts_corrupt_reply(tmp_path):
    state = DemoState("ramp", seed=7, duration=10, speed=100, fault_every_crc=2)
    with DemoServer(("127.0.0.1", 0), state) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        time.sleep(0.02)
        host, port = server.server_address
        db = Database(str(tmp_path / "device.db"))
        collector = Collector(db, MockTcpClient(host, port, timeout=1))
        try:
            for _ in range(3):
                collector.poll_both()
            session = collector.active_session_id
            assert session is not None
            assert db.get_watermark(session, 1) > 0
            assert db.get_watermark(session, 2) > 0
            with db.connect() as conn:
                assert conn.execute("SELECT COUNT(*) FROM integrity_events WHERE event_type='crc32_mismatch'").fetchone()[0] > 0
            # All persisted sample values still follow the deterministic ramp generator.
            assert db.get_samples(session, 1, 0, 0)[0] == [1, 2, 3]
        finally:
            collector.close()
            server.shutdown()
            thread.join(timeout=2)


def test_collector_deduplicates_repeated_mock_replies(tmp_path):
    state = DemoState("ramp", seed=7, duration=10, speed=100, duplicate_every=3)
    with DemoServer(("127.0.0.1", 0), state) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        time.sleep(0.02)
        host, port = server.server_address
        db = Database(str(tmp_path / "device.db"))
        collector = Collector(db, MockTcpClient(host, port, timeout=1))
        try:
            for _ in range(5):
                collector.poll_both()
            session = collector.active_session_id
            assert session is not None
            with db.connect() as conn:
                rows = conn.execute(
                    "SELECT sensor, sample_index, COUNT(*) FROM samples WHERE session_id=? GROUP BY sensor,sample_index HAVING COUNT(*) > 1",
                    (session,),
                ).fetchall()
            assert rows == []
            assert db.get_watermark(session, 1) > 0
            assert db.get_watermark(session, 2) > 0
        finally:
            collector.close()
            server.shutdown()
            thread.join(timeout=2)


def test_collector_records_unknown_old_session_tail_when_mock_restarts(tmp_path):
    state = DemoState("ramp", seed=7, duration=10, speed=100, restart_after_requests=2)
    with DemoServer(("127.0.0.1", 0), state) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        time.sleep(0.02)
        host, port = server.server_address
        db = Database(str(tmp_path / "device.db"))
        collector = Collector(db, MockTcpClient(host, port, timeout=1))
        try:
            collector.poll_both()
            active = collector.active_session_id
            assert active is not None
            old_sessions = [sid for sid in db.get_sessions() if sid != active]
            assert len(old_sessions) == 1
            old = old_sessions[0]
            exports = list(db.export_samples(old))
            losses = [row for row in exports if "from_index" in row]
            assert any(row["sensor"] == 1 and row["to_index"] is None for row in losses)
            assert any(row["sensor"] == 2 and row["to_index"] is None for row in losses)
        finally:
            collector.close()
            server.shutdown()
            thread.join(timeout=2)
