from __future__ import annotations

import importlib

import pytest
from fastapi import HTTPException
from starlette.requests import Request
from fastapi.testclient import TestClient


def _reload_app(monkeypatch, tmp_path, *, dashboard_auth: bool):
    monkeypatch.setenv("CLOUD_DB_PATH", str(tmp_path / "cloud.db"))
    monkeypatch.setenv("PIPELINE_DB_PATH", str(tmp_path / "missing-device.db"))
    monkeypatch.setenv("DASHBOARD_DEVICE_DB_PATH", str(tmp_path / "missing-device.db"))
    monkeypatch.setenv("DEMO_DATASET_PATH", str(tmp_path / "synthetic_demo_dataset.jsonl"))
    monkeypatch.delenv("CLOUD_API_TOKEN", raising=False)
    if dashboard_auth:
        monkeypatch.setenv("DASHBOARD_USERNAME", "reviewer")
        monkeypatch.setenv("DASHBOARD_PASSWORD", "a-long-test-only-password")
        monkeypatch.setenv("DASHBOARD_SESSION_SECRET", "unit-test-secret-32-characters-minimum")
    else:
        monkeypatch.delenv("DASHBOARD_USERNAME", raising=False)
        monkeypatch.delenv("DASHBOARD_PASSWORD", raising=False)
        monkeypatch.delenv("DASHBOARD_SESSION_SECRET", raising=False)
    import pipeline.config as config_module
    import pipeline.cloud_app as cloud_module
    importlib.reload(config_module)
    return importlib.reload(cloud_module)


def test_dashboard_local_development_mode_only_reports_available_data(monkeypatch, tmp_path):
    cloud_module = _reload_app(monkeypatch, tmp_path, dashboard_auth=False)
    client = TestClient(cloud_module.app)

    auth = client.get("/api/auth/session")
    assert auth.status_code == 200
    assert auth.json()["authenticated"] is True
    assert auth.json()["username"] == "local-development"

    summary = client.get("/api/dashboard/summary")
    assert summary.status_code == 200, summary.text
    body = summary.json()
    assert body["cloud"]["samples"] == 0
    assert body["device"]["available"] is False
    assert body["device"]["samples"] is None
    assert "Synthetic" in body["data_notice"]
    assert summary.headers["x-content-type-options"] == "nosniff"
    assert summary.headers["x-frame-options"] == "DENY"


def test_dashboard_login_uses_separate_signed_http_only_cookie(monkeypatch, tmp_path):
    cloud_module = _reload_app(monkeypatch, tmp_path, dashboard_auth=True)
    client = TestClient(cloud_module.app, base_url="http://127.0.0.1:8000")

    session = client.get("/api/auth/session").json()
    assert session["configured"] is True
    assert session["authenticated"] is False
    assert client.get("/api/dashboard/summary").status_code == 401

    failed = client.post("/api/auth/login", json={"username": "reviewer", "password": "wrong"})
    assert failed.status_code == 401

    cross_origin = client.post("/api/auth/login", headers={"Origin": "https://attacker.example"}, json={"username": "reviewer", "password": "a-long-test-only-password"})
    assert cross_origin.status_code == 403

    response = client.post("/api/auth/login", headers={"Origin": "http://127.0.0.1:5173"}, json={"username": "reviewer", "password": "a-long-test-only-password"})
    assert response.status_code == 200, response.text
    cookie = response.headers.get("set-cookie", "").lower()
    assert "httponly" in cookie
    assert "samesite=strict" in cookie
    assert "bearer" not in cookie

    assert client.get("/api/auth/session").json()["authenticated"] is True
    assert client.get("/api/dashboard/summary").status_code == 200
    logout = client.post("/api/auth/logout")
    assert logout.status_code == 200
    assert client.get("/api/auth/session").json()["authenticated"] is False


def test_dashboard_rejects_partial_auth_configuration(monkeypatch, tmp_path):
    monkeypatch.setenv("CLOUD_DB_PATH", str(tmp_path / "partial.db"))
    monkeypatch.delenv("CLOUD_API_TOKEN", raising=False)
    monkeypatch.setenv("DASHBOARD_USERNAME", "reviewer")
    monkeypatch.delenv("DASHBOARD_PASSWORD", raising=False)
    monkeypatch.delenv("DASHBOARD_SESSION_SECRET", raising=False)
    monkeypatch.setenv("DASHBOARD_DEVICE_DB_PATH", str(tmp_path / "missing-device.db"))
    import pipeline.config as config_module
    import pipeline.cloud_app as cloud_module
    importlib.reload(config_module)
    cloud_module = importlib.reload(cloud_module)
    client = TestClient(cloud_module.app)
    assert client.get("/api/dashboard/summary").status_code == 503
    assert client.get("/api/auth/session").json()["needs_configuration"] is True


def test_remote_ingestion_fails_closed_when_cloud_token_is_missing(monkeypatch, tmp_path):
    cloud_module = _reload_app(monkeypatch, tmp_path, dashboard_auth=False)
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
        "method": "POST", "scheme": "http", "path": "/v1/ingest", "raw_path": b"/v1/ingest",
        "query_string": b"", "headers": [], "client": ("198.51.100.8", 12345), "server": ("api.example", 8000),
    }
    request = Request(scope)
    with pytest.raises(HTTPException) as raised:
        cloud_module.verify_token(request, None)
    assert raised.value.status_code == 503

def test_api_docs_are_disabled_by_default_in_production(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("ENABLE_API_DOCS", raising=False)
    cloud_module = _reload_app(monkeypatch, tmp_path, dashboard_auth=True)
    assert cloud_module.app.docs_url is None
    assert cloud_module.app.redoc_url is None
    assert cloud_module.app.openapi_url is None
    client = TestClient(cloud_module.app)
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_api_docs_can_be_explicitly_enabled(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ENABLE_API_DOCS", "true")
    cloud_module = _reload_app(monkeypatch, tmp_path, dashboard_auth=True)
    assert cloud_module.app.docs_url == "/docs"
    assert cloud_module.app.openapi_url == "/openapi.json"
    client = TestClient(cloud_module.app)
    assert client.get("/openapi.json").status_code == 200



def test_deterministic_demo_dataset_is_persisted_reused_and_reset_safely(monkeypatch, tmp_path):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("ENABLE_SYNTHETIC_DEMO_SEED", raising=False)
    cloud_module = _reload_app(monkeypatch, tmp_path, dashboard_auth=False)
    client = TestClient(cloud_module.app, base_url="http://127.0.0.1:8000")

    before = client.get("/api/dashboard/demo/status")
    assert before.status_code == 200
    assert before.json()["enabled"] is True
    assert before.json()["seeded"] is False
    assert before.json()["bundled_fixture_available"] is True
    assert before.json()["seed"] == 7
    assert before.json()["sample_rate_hz"] == 400
    assert before.json()["duration_seconds"] == 30
    assert before.json()["sample_rows"] == 23960
    assert before.json()["controlled_gap"] == {"sensor": 2, "from_index": 4800, "to_index": 4839}
    assert before.json()["offline_windows"] == [15, 16, 17]

    bad_origin = client.post("/api/dashboard/demo/seed", headers={"Origin": "https://attacker.example"})
    assert bad_origin.status_code == 403

    seeded = client.post("/api/dashboard/demo/seed")
    assert seeded.status_code == 200, seeded.text
    body = seeded.json()
    assert body["ok"] is True
    assert body["already_present"] is False
    assert body["seed"] == 7
    assert body["sample_rate_hz"] == 400
    assert body["duration_seconds"] == 30
    assert body["sample_rows"] == 23960
    assert body["sensor_1_sample_count"] == 12000
    assert body["sensor_2_sample_count"] == 11960
    assert body["loss_records"] == 1
    assert body["window_count"] == 30
    assert body["online_windows"] == 27
    assert body["offline_windows"] == 3
    assert body["cloud"]["sample_rows"] == body["device"]["sample_rows"] == 23960
    assert body["cloud"]["pending_samples"] == body["device"]["pending_samples"] == 0
    assert body["cloud"]["results"] == 30
    assert body["device"]["results"] == 3

    status = client.get("/api/dashboard/demo/status").json()
    assert status["seeded"] is True
    assert status["dataset_file_exists"] is True

    dataset_path = tmp_path / "synthetic_demo_dataset.jsonl"
    lines = dataset_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1 + 23960 + 1
    import json
    manifest = json.loads(lines[0])
    assert manifest["dataset_id"] == body["session_id"]
    assert manifest["sha256"] == body["sha256"]

    # The JSONL source and both databases must preserve the same sample keys and values.
    source_samples = []
    for line in lines[1:]:
        record = json.loads(line)
        if record["type"] == "sample":
            source_samples.append((int(record["sensor"]), int(record["index"]), record["values"]))
    expected_sorted = sorted(source_samples, key=lambda row: (row[1], row[0]))
    with cloud_module.db.connect() as conn:
        cloud_samples = [(int(row[0]), int(row[1]), json.loads(row[2])) for row in conn.execute(
            "SELECT sensor,sample_index,values_json FROM samples WHERE session_id=? ORDER BY sample_index,sensor", (body["session_id"],)
        ).fetchall()]
    device_db = cloud_module._device_database()
    assert device_db is not None
    with device_db.connect() as conn:
        device_samples = [(int(row[0]), int(row[1]), json.loads(row[2])) for row in conn.execute(
            "SELECT sensor,sample_index,values_json FROM samples WHERE session_id=? ORDER BY sample_index,sensor", (body["session_id"],)
        ).fetchall()]
    assert cloud_samples == device_samples == expected_sorted

    sessions = client.get("/api/dashboard/sessions").json()
    demo_session = next(row for row in sessions["items"] if row["session_id"] == body["session_id"])
    assert demo_session["samples_cloud"] == 23960
    assert demo_session["samples_device"] == 23960
    assert demo_session["losses"] == 1  # mirrored stores are deduplicated in the session summary
    assert demo_session["results"] == 30  # online/offline copies are counted by unique window/mode

    results = client.get(f"/api/dashboard/sessions/{body['session_id']}/results?limit=100").json()
    assert results["total"] == 30
    window_12 = next(row for row in results["items"] if row["window_index"] == 12)
    assert window_12["missing_2"] == 40
    assert window_12["complete"] is False
    assert window_12["magnitude"] is not None
    window_4 = next(row for row in results["items"] if row["window_index"] == 4)
    assert window_4["heart_rate"] == 60.0
    assert sum(row["mode"] == "offline" for row in results["items"]) == 3

    download = client.get("/api/dashboard/demo/download")
    assert download.status_code == 200
    assert "application/x-ndjson" in download.headers["content-type"]

    # Repeated clicks read the stored fixture and do not duplicate database rows.
    second = client.post("/api/dashboard/demo/seed")
    assert second.status_code == 200
    assert second.json()["already_present"] is True
    assert second.json()["sample_rows"] == 23960
    assert cloud_module.db.sample_count(body["session_id"]) == 23960

    # If the JSONL export is removed but both stores remain complete, the next
    # idempotent seed reconstructs the export from the same persisted sample rows.
    dataset_path.unlink()
    assert client.get("/api/dashboard/demo/status").json()["seeded"] is False
    repaired = client.post("/api/dashboard/demo/seed")
    assert repaired.status_code == 200, repaired.text
    assert repaired.json()["already_present"] is True
    assert dataset_path.is_file()
    assert client.get("/api/dashboard/demo/status").json()["seeded"] is True

    # Reset is constrained to the fixed demo session and preserves unrelated records.
    cloud_module.db.ensure_session("assessment-session-to-keep")
    reset = client.post("/api/dashboard/demo/reset")
    assert reset.status_code == 200
    assert cloud_module.db.session_exists("assessment-session-to-keep") is True
    assert cloud_module.db.session_exists(body["session_id"]) is False
    assert dataset_path.exists() is False
    assert client.get("/api/dashboard/demo/status").json()["seeded"] is False


@pytest.mark.parametrize("app_env", ["production", "staging"])
def test_demo_dataset_seeding_is_disabled_by_default_outside_dev(monkeypatch, tmp_path, app_env):
    monkeypatch.setenv("APP_ENV", app_env)
    monkeypatch.delenv("ENABLE_SYNTHETIC_DEMO_SEED", raising=False)
    cloud_module = _reload_app(monkeypatch, tmp_path, dashboard_auth=False)
    client = TestClient(cloud_module.app, base_url="http://127.0.0.1:8000")
    assert client.get("/api/dashboard/demo/status").json()["enabled"] is False
    assert client.post("/api/dashboard/demo/seed").status_code == 404
    assert client.post("/api/dashboard/demo/reset").status_code == 404
