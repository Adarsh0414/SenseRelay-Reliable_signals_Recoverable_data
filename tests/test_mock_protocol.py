from __future__ import annotations

import json
import socketserver
import threading
import time
import zlib

from pipeline.demo_mock import DemoServer, DemoState
from pipeline.mock_client import MockTcpClient, verify_data_crc


def test_crc_is_checked_against_exact_wire_array_text():
    data_text = '[ [1, 2, 3] , [4,5,6] ]'
    crc = f"{zlib.crc32(data_text.encode()) & 0xffffffff:08x}"
    raw = ('{"session_id":"s","sensor":1,"first_index":0,"count":2,"lost":[],"session_end":false,"crc32":"'
           + crc + '","data":' + data_text + '}').encode()
    assert verify_data_crc(raw, json.loads(raw))
    altered = raw.replace(b"[4,5,6]", b"[4,5,7]")
    assert not verify_data_crc(altered, json.loads(altered))


def test_demo_mock_speaks_official_newline_json_protocol():
    state = DemoState("ramp", seed=7, duration=10, speed=100)
    with DemoServer(("127.0.0.1", 0), state) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        time.sleep(0.02)
        host, port = server.server_address
        client = MockTcpClient(host, port, timeout=1)
        try:
            # Simulated time is accelerated enough to have data immediately.
            reply = client.read(1, from_index=0)
            assert reply.crc_valid
            assert reply.payload["sensor"] == 1
            assert reply.payload["count"] == len(reply.payload["data"])
            assert reply.payload["data"][0] == [1, 2, 3]
        finally:
            client.close()
            server.shutdown()
            thread.join(timeout=2)
