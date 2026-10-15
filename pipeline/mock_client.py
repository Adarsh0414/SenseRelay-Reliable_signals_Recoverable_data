"""TCP client for the provided biosignal-mock newline-delimited JSON protocol."""
from __future__ import annotations

import json
import re
import socket
import zlib
from dataclasses import dataclass
from typing import Any


class MockProtocolError(RuntimeError):
    pass


def _json_array_bounds(raw: bytes, key: bytes = b'"data"') -> tuple[int, int]:
    """Return the exact byte range of the JSON array value, preserving wire whitespace."""
    match = re.search(key + rb"\s*:\s*", raw)
    if not match:
        raise MockProtocolError("response has no data field")
    start = match.end()
    while start < len(raw) and raw[start] in b" \t\r\n":
        start += 1
    if start >= len(raw) or raw[start:start + 1] != b"[":
        raise MockProtocolError("data field is not an array")
    depth = 0
    in_string = False
    escaped = False
    for pos in range(start, len(raw)):
        byte = raw[pos]
        if in_string:
            if escaped:
                escaped = False
            elif byte == 0x5C:
                escaped = True
            elif byte == 0x22:
                in_string = False
            continue
        if byte == 0x22:
            in_string = True
        elif byte == 0x5B:
            depth += 1
        elif byte == 0x5D:
            depth -= 1
            if depth == 0:
                return start, pos + 1
    raise MockProtocolError("unterminated data array")


def verify_data_crc(raw: bytes, payload: dict[str, Any]) -> bool:
    try:
        start, end = _json_array_bounds(raw)
        actual = f"{zlib.crc32(raw[start:end]) & 0xffffffff:08x}"
        supplied = str(payload.get("crc32", "")).strip().lower().removeprefix("0x")
        return actual == supplied.zfill(8)
    except (MockProtocolError, TypeError, ValueError):
        return False


@dataclass
class MockReply:
    payload: dict[str, Any]
    raw: bytes
    crc_valid: bool


class MockTcpClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 7100, timeout: float = 1.5):
        self.host, self.port, self.timeout = host, int(port), float(timeout)
        self.sock: socket.socket | None = None
        self.reader = None

    def close(self) -> None:
        try:
            if self.reader:
                self.reader.close()
        except OSError:
            pass
        try:
            if self.sock:
                self.sock.close()
        except OSError:
            pass
        self.reader = None
        self.sock = None

    def _connect(self) -> None:
        self.close()
        self.sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        self.sock.settimeout(self.timeout)
        self.reader = self.sock.makefile("rb")

    def read(self, sensor: int, from_index: int | None = None) -> MockReply:
        if sensor not in (1, 2):
            raise ValueError("sensor must be 1 or 2")
        command: dict[str, Any] = {"cmd": "read", "sensor": sensor}
        if from_index is not None:
            command["from_index"] = int(from_index)
        wire = json.dumps(command, separators=(",", ":")).encode("utf-8") + b"\n"
        for attempt in range(2):
            try:
                if self.sock is None or self.reader is None:
                    self._connect()
                assert self.sock is not None and self.reader is not None
                self.sock.sendall(wire)
                raw = self.reader.readline()
                if not raw:
                    raise ConnectionError("mock service closed the TCP stream")
                if not raw.endswith(b"\n"):
                    raise MockProtocolError("response was not newline terminated")
                payload = json.loads(raw.decode("utf-8"))
                if not isinstance(payload, dict):
                    raise MockProtocolError("response must be a JSON object")
                return MockReply(payload=payload, raw=raw.rstrip(b"\r\n"), crc_valid=verify_data_crc(raw.rstrip(b"\r\n"), payload))
            except (OSError, ValueError, json.JSONDecodeError, MockProtocolError):
                self.close()
                if attempt:
                    raise
        raise MockProtocolError("unreachable TCP read failure")
