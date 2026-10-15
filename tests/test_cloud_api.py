from __future__ import annotations

import importlib
import json

from fastapi.testclient import TestClient


def test_cloud_ingest_is_idempotent_and_computes_online_result(tmp_path, monkeypatch):
    monkeypatch.setenv("CLOUD_DB_PATH", str(tmp_path / "cloud.db"))
    monkeypatch.setenv("CLOUD_API_TOKEN", "unit-test-token")
    import pipeline.config as config_module
    import pipeline.cloud_app as cloud_module
    importlib.reload(config_module)
    cloud_module = importlib.reload(cloud_module)
    client = TestClient(cloud_module.app)
    headers = {"Authorization": "Bearer unit-test-token"}
    samples = []
    for i in range(401):
        samples.append({"session_id": "cloud-test", "sensor": 1, "index": i, "values": [60, 100, 130]})
    for i in range(400):
        samples.append({"session_id": "cloud-test", "sensor": 2, "index": i, "values": [3, 4]})
    payload = {"samples": samples, "window_modes": [{"session_id": "cloud-test", "window_index": 0,
                "mode": "online", "prior_peak_index": None, "assigned_at": 1.0}]}
    first = client.post("/v1/ingest", headers=headers, json=payload)
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["samples_inserted"] == 801
    assert body["results_created"] == 1
    result = client.get("/v1/sessions/cloud-test/results", headers=headers)
    assert result.status_code == 200
    assert result.json()[0]["mode"] == "online"
    assert result.json()[0]["missing_1"] == 0
    assert result.json()[0]["missing_2"] == 0

    repeated = client.post("/v1/ingest", headers=headers, json=payload)
    assert repeated.status_code == 200
    assert repeated.json()["samples_inserted"] == 0
    assert repeated.json()["samples_duplicate"] == 801
    assert len(client.get("/v1/sessions/cloud-test/results", headers=headers).json()) == 1


def test_cloud_token_is_enforced(tmp_path, monkeypatch):
    monkeypatch.setenv("CLOUD_DB_PATH", str(tmp_path / "secure.db"))
    monkeypatch.setenv("CLOUD_API_TOKEN", "required-token")
    import pipeline.config as config_module
    import pipeline.cloud_app as cloud_module
    importlib.reload(config_module)
    cloud_module = importlib.reload(cloud_module)
    client = TestClient(cloud_module.app)
    assert client.get("/v1/status").status_code == 401
    assert client.get("/v1/status", headers={"Authorization": "Bearer required-token"}).status_code == 200


def test_offline_result_is_not_uploaded_as_a_second_result_when_online_result_exists(tmp_path, monkeypatch):
    monkeypatch.setenv("CLOUD_DB_PATH", str(tmp_path / "conflict.db"))
    monkeypatch.setenv("CLOUD_API_TOKEN", "token")
    import pipeline.config as config_module
    import pipeline.cloud_app as cloud_module
    importlib.reload(config_module)
    cloud_module = importlib.reload(cloud_module)
    db = cloud_module.db
    online = {"session_id": "s", "window_index": 1, "start_index": 400, "end_index": 799,
              "missing_1": 0, "missing_2": 0, "complete": True, "mean": {}, "min": {}, "max": {},
              "magnitude": 1.0, "heart_rate": None, "mode": "online"}
    offline = {**online, "mode": "offline"}
    db.insert_result("s", 1, "online", online)
    db.insert_offline_results([{"session_id": "s", "window_index": 1, "mode": "offline", "result": offline}])
    assert len(db.results_for_session("s")) == 1
    assert db.results_for_session("s")[0]["mode"] == "online"
