"""DEVELOPMENT FIXTURE ONLY: protocol-compatible synthetic mock for local tests.

It does not replace, patch, or modify MayaCardio's supplied biosignal-mock. The
final validation must use the official executable exactly as provided.
"""
from __future__ import annotations

import argparse
import json
import math
import socketserver
import time
import zlib
from typing import Any

SAMPLE_RATE = 400
BUFFER_SAMPLES = 10 * SAMPLE_RATE
MODULUS = 8_388_608


class DemoState:
    def __init__(self, mode: str, seed: int, duration: int, speed: float, fault_every_crc: int = 0,
                 duplicate_every: int = 0, restart_after_requests: int = 0):
        self.mode = mode
        self.seed = seed
        self.duration = duration
        self.speed = max(0.01, speed)
        self.started = time.monotonic()
        self.session_number = 0
        self.session_id = f"demo-{seed}-{int(time.time())}"
        self.next_index = {1: 0, 2: 0}
        self.request_count = 0
        self.fault_every_crc = max(0, fault_every_crc)
        self.duplicate_every = max(0, duplicate_every)
        self.restart_after_requests = max(0, restart_after_requests)
        self.last_wire: dict[int, bytes] = {}
        self.restart_pending_sensors: set[int] = set()

    def available_end(self) -> int:
        elapsed = int((time.monotonic() - self.started) * SAMPLE_RATE * self.speed)
        return min(self.duration * SAMPLE_RATE, elapsed)

    def _noise(self, idx: int, salt: int = 0) -> int:
        x = (idx * 1103515245 + (self.seed + salt) * 12345 + 1013904223) & 0x7fffffff
        return (x % 2001) - 1000

    def values(self, sensor: int, idx: int) -> list[int]:
        if self.mode == "ramp":
            if sensor == 1:
                return [int((3 * idx + c) % MODULUS) for c in (1, 2, 3)]
            return [int((2 * idx + c) % MODULUS) for c in (1, 2)]
        if sensor == 1:
            seconds = idx / SAMPLE_RATE
            phase_seconds = seconds % 360.0
            if phase_seconds < 120:
                bpm, segment_start, beats_before = 60.0, 0.0, 0.0
            elif phase_seconds < 240:
                bpm, segment_start, beats_before = 90.0, 120.0, 120.0
            else:
                bpm, segment_start, beats_before = 72.0, 240.0, 300.0
            rate_phase = ((phase_seconds - segment_start) * bpm / 60.0) % 1.0
            distance = min(rate_phase, 1.0 - rate_phase)
            pulse = 1_100_000.0 * math.exp(-distance * 700.0)
            channel2 = int(90_000 + self._noise(idx) * 6 + pulse)
            return [int(round(channel2 * 0.6)), channel2, int(round(channel2 * 1.3))]
        ch1 = int(400_000 + 25_000 * math.sin(idx / 610.0) + self._noise(idx, 17) * 8)
        ch2 = int(150_000 + 12_000 * math.cos(idx / 830.0) + self._noise(idx, 29) * 5)
        return [ch1, ch2]

    def new_session(self) -> None:
        self.session_number += 1
        self.session_id = f"demo-{self.seed}-{int(time.time())}-{self.session_number}"
        self.next_index = {1: 0, 2: 0}
        self.started = time.monotonic()

    def make_reply(self, request: dict[str, Any]) -> bytes:
        self.request_count += 1
        if self.restart_after_requests and self.request_count == self.restart_after_requests:
            self.new_session()
        sensor = int(request["sensor"])
        if sensor not in (1, 2):
            raise ValueError("sensor must be 1 or 2")
        available = self.available_end()
        requested = request.get("from_index")
        if sensor in self.restart_pending_sensors:
            # A restarted mock starts a new session at index 0 even if the client asks for its old cursor.
            start = 0
            self.restart_pending_sensors.discard(sensor)
        else:
            start = self.next_index[sensor] if requested is None else int(requested)
        lost: list[dict[str, Any]] = []
        oldest = max(0, available - BUFFER_SAMPLES)
        if start < oldest:
            lost.append({"from_index": start, "to_index": oldest - 1, "reason": "buffer_overflow"})
            start = oldest
        start = min(max(0, start), self.duration * SAMPLE_RATE)
        count = max(0, min(SAMPLE_RATE, available - start))
        rows = [self.values(sensor, idx) for idx in range(start, start + count)]
        self.next_index[sensor] = max(self.next_index[sensor], start + count)
        session_end = available >= self.duration * SAMPLE_RATE and start + count >= self.duration * SAMPLE_RATE
        data_text = json.dumps(rows, separators=(",", ":"))
        crc = f"{zlib.crc32(data_text.encode('utf-8')) & 0xffffffff:08x}"
        if self.fault_every_crc and self.request_count % self.fault_every_crc == 0:
            crc = "00000000" if crc != "00000000" else "ffffffff"
        prefix = {
            "session_id": self.session_id, "sensor": sensor, "first_index": start, "count": count,
            "lost": lost, "session_end": session_end, "crc32": crc,
        }
        wire = (json.dumps(prefix, separators=(",", ":"))[:-1] + ',"data":' + data_text + '}\n').encode("utf-8")
        if self.duplicate_every and self.request_count % self.duplicate_every == 0 and sensor in self.last_wire:
            wire = self.last_wire[sensor]
        self.last_wire[sensor] = wire
        return wire


class Handler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        state: DemoState = self.server.state  # type: ignore[attr-defined]
        for raw in self.rfile:
            try:
                request = json.loads(raw.decode("utf-8"))
                if request.get("cmd") != "read":
                    raise ValueError("unsupported command")
                response = state.make_reply(request)
                self.wfile.write(response)
                self.wfile.flush()
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                self.wfile.write((json.dumps({"error": str(exc)}) + "\n").encode("utf-8"))
                self.wfile.flush()


class DemoServer(socketserver.TCPServer):
    allow_reuse_address = True
    def __init__(self, address: tuple[str, int], state: DemoState):
        self.state = state
        super().__init__(address, Handler)


def main() -> None:
    parser = argparse.ArgumentParser(description="Development-only mock implementing the assignment's TCP JSON protocol")
    parser.add_argument("--mode", choices=("signal", "ramp"), default="signal")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--duration", type=int, default=3600)
    parser.add_argument("--port", type=int, default=7100)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--speed", type=float, default=1.0, help="1.0 is real-time; >1 accelerates synthetic time for tests")
    parser.add_argument("--fault-every-crc", type=int, default=0, help="test-only: send an incorrect CRC every Nth reply")
    parser.add_argument("--duplicate-every", type=int, default=0, help="test-only: repeat a previous reply every Nth request")
    parser.add_argument("--restart-after-requests", type=int, default=0, help="test-only: change session after N requests")
    args = parser.parse_args()
    state = DemoState(args.mode, args.seed, args.duration, args.speed, args.fault_every_crc,
                      args.duplicate_every, args.restart_after_requests)
    with DemoServer((args.host, args.port), state) as server:
        print(f"DEVELOPMENT MOCK ONLY - {args.host}:{args.port}, mode={args.mode}, speed={args.speed}x, session={state.session_id}")
        print("Final validation must use the official biosignal-mock binary, not this fixture.")
        try:
            server.serve_forever(poll_interval=0.1)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
