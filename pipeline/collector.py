"""Fault-tolerant acquisition from the official mock service."""
from __future__ import annotations

import json
import time
from typing import Any

from .db import Database, CHANNELS
from .mock_client import MockProtocolError, MockReply, MockTcpClient


class Collector:
    def __init__(self, db: Database, client: MockTcpClient):
        self.db = db
        self.client = client
        self.discovered_sensors: set[int] = set()
        self.active_session_id = db.get_meta("active_session_id")

    def close(self) -> None:
        self.client.close()

    def _declare_old_session_tail_lost(self, old_session: str, new_session: str) -> None:
        if not old_session or old_session == new_session or not self.db.session_exists(old_session):
            return
        # The assignment explicitly requires to_index:null when a restarted mock's old tail is unknown.
        losses = []
        for sensor in (1, 2):
            cursor = self.db.get_watermark(old_session, sensor)
            losses.append({
                "session_id": old_session, "sensor": sensor, "from_index": cursor, "to_index": None,
                "reason": f"mock_session_restart_to_{new_session}_old_end_unknown",
            })
        self.db.add_losses(losses)
        self.db.mark_session_ended(old_session)
        self.db.add_event("mock_session_restart", f"Session changed from {old_session} to {new_session}; old tail recorded as unknown")

    def _accept_session_id(self, session_id: str) -> None:
        if not session_id:
            raise MockProtocolError("mock response has an empty session_id")
        if self.active_session_id is None:
            self.active_session_id = session_id
            self.db.ensure_session(session_id)
            self.db.set_meta("active_session_id", session_id)
        elif session_id != self.active_session_id:
            old = self.active_session_id
            self._declare_old_session_tail_lost(old, session_id)
            self.active_session_id = session_id
            self.db.ensure_session(session_id)
            self.db.set_meta("active_session_id", session_id)
            self.discovered_sensors.clear()

    def _validate_reply(self, reply: MockReply, expected_sensor: int) -> tuple[dict[str, Any], bool]:
        data = reply.payload
        required = ("session_id", "sensor", "first_index", "count", "lost", "data", "session_end", "crc32")
        if any(key not in data for key in required):
            raise MockProtocolError(f"reply missing one of required fields: {required}")
        if int(data["sensor"]) != expected_sensor:
            raise MockProtocolError(f"asked for sensor {expected_sensor}, received sensor {data['sensor']}")
        if int(data["first_index"]) < 0 or int(data["count"]) < 0:
            raise MockProtocolError("negative first_index or count")
        if not isinstance(data["data"], list) or int(data["count"]) != len(data["data"]):
            raise MockProtocolError("count does not equal data array length")
        if not isinstance(data["lost"], list):
            raise MockProtocolError("lost must be an array")
        for row in data["data"]:
            if not isinstance(row, list) or len(row) != CHANNELS[expected_sensor] or any(not isinstance(v, int) for v in row):
                raise MockProtocolError("invalid sample row shape or type")
        return data, reply.crc_valid

    def _report_declared_losses(self, session_id: str, sensor: int, records: list[dict[str, Any]]) -> None:
        normalised = []
        for loss in records:
            if not isinstance(loss, dict) or "from_index" not in loss:
                self.db.add_event("malformed_mock_loss", json.dumps(loss), session_id, sensor)
                continue
            normalised.append({
                "session_id": session_id, "sensor": sensor,
                "from_index": int(loss["from_index"]),
                "to_index": None if loss.get("to_index") is None else int(loss["to_index"]),
                "reason": str(loss.get("reason") or "reported_by_mock"),
            })
        if normalised:
            self.db.add_losses(normalised)

    def _insert_reply_samples(self, session_id: str, sensor: int, first_index: int, rows: list[list[int]]) -> None:
        samples = []
        invalid_losses = []
        for offset, values in enumerate(rows):
            index = first_index + offset
            if any(int(v) < -8_388_608 or int(v) > 8_388_607 for v in values):
                invalid_losses.append({"session_id": session_id, "sensor": sensor, "from_index": index,
                                      "to_index": index, "reason": "invalid_signed_24_bit_sample_value"})
                self.db.add_event("out_of_range_value", "Rejected mock sample outside signed 24-bit range", session_id, sensor, index)
                continue
            samples.append({"session_id": session_id, "sensor": sensor, "index": index, "values": values})
        if samples:
            stats = self.db.add_samples(samples)
            if stats["conflicts"]:
                self.db.add_event("mock_duplicate_conflict", f"{stats['conflicts']} repeated sample keys carried different values", session_id, sensor, first_index)
        if invalid_losses:
            self.db.add_losses(invalid_losses)

    def _read_at(self, sensor: int, index: int) -> tuple[dict[str, Any], bool] | None:
        """Try a bounded number of exact re-reads; bad CRC data is never inserted."""
        for attempt in range(3):
            try:
                reply = self.client.read(sensor, from_index=index)
                payload, crc_valid = self._validate_reply(reply, sensor)
                session_id = str(payload["session_id"])
                self._accept_session_id(session_id)
                if not crc_valid:
                    self.db.add_event("crc32_mismatch", f"Rejected reply at index {payload['first_index']}; retry={attempt + 1}", session_id, sensor, int(payload["first_index"]))
                    time.sleep(0.03 * (attempt + 1))
                    continue
                return payload, True
            except (OSError, ValueError, MockProtocolError) as exc:
                self.db.add_event("mock_read_error", repr(exc), self.active_session_id, sensor, index)
                time.sleep(0.05 * (attempt + 1))
        return None

    def poll_sensor(self, sensor: int) -> int:
        """Read a sensor once, recovering a gap via the mock's from_index feature."""
        known_session = self.active_session_id
        requested_index = None
        if sensor in self.discovered_sensors and known_session:
            requested_index = self.db.get_watermark(known_session, sensor)
        try:
            reply = self.client.read(sensor, from_index=requested_index)
            payload, crc_valid = self._validate_reply(reply, sensor)
            self._accept_session_id(str(payload["session_id"]))
        except (OSError, ValueError, MockProtocolError) as exc:
            self.db.add_event("mock_read_error", repr(exc), self.active_session_id, sensor, requested_index)
            return 0
        session_id = str(payload["session_id"])
        if not crc_valid:
            self.db.add_event("crc32_mismatch", f"Rejected response at index {payload['first_index']}; will re-read", session_id, sensor, int(payload["first_index"]))
            recovered = self._read_at(sensor, int(payload["first_index"]))
            if recovered is None:
                return 0
            payload, _ = recovered
            session_id = str(payload["session_id"])
            self._report_declared_losses(session_id, sensor, payload["lost"])
            self._insert_reply_samples(session_id, sensor, int(payload["first_index"]), payload["data"])
            self.discovered_sensors.add(sensor)
            if payload.get("session_end"):
                self.db.mark_session_ended(session_id)
            return int(payload["count"])

        self.discovered_sensors.add(sensor)
        self._report_declared_losses(session_id, sensor, payload["lost"])
        first_index = int(payload["first_index"])
        expected = self.db.get_watermark(session_id, sensor)

        # When a mock read advances before our previous transaction committed, re-read the gap first.
        for _ in range(4):
            expected = self.db.get_watermark(session_id, sensor)
            if first_index <= expected:
                break
            recovered = self._read_at(sensor, expected)
            if recovered is None:
                self.db.add_event("gap_recovery_pending", f"Could not yet recover indexes {expected}..{first_index - 1}; no later data accepted", session_id, sensor, expected)
                return 0
            gap_payload, _ = recovered
            if str(gap_payload["session_id"]) != session_id:
                self._accept_session_id(str(gap_payload["session_id"]))
                return 0
            self._report_declared_losses(session_id, sensor, gap_payload["lost"])
            gap_first = int(gap_payload["first_index"])
            gap_expected = self.db.get_watermark(session_id, sensor)
            if gap_first > gap_expected:
                self.db.add_event("gap_recovery_still_missing", f"Requested index {gap_expected}; mock began at {gap_first}", session_id, sensor, gap_expected)
                return 0
            self._insert_reply_samples(session_id, sensor, gap_first, gap_payload["data"])
            if gap_payload.get("session_end"):
                self.db.mark_session_ended(session_id)
            # Continue while the original later response remains beyond the contiguous cursor.
        expected = self.db.get_watermark(session_id, sensor)
        if first_index > expected:
            self.db.add_event("gap_recovery_pending", f"Unresolved indexes {expected}..{first_index - 1}", session_id, sensor, expected)
            return 0
        self._insert_reply_samples(session_id, sensor, first_index, payload["data"])
        if payload.get("session_end"):
            self.db.mark_session_ended(session_id)
        return int(payload["count"])

    def poll_both(self) -> dict[int, int]:
        return {sensor: self.poll_sensor(sensor) for sensor in (1, 2)}
