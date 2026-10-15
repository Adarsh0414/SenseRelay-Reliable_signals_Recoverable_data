"""Small persistent cloud ingestion and processing API.

Run with: uvicorn pipeline.cloud_app:app --host 0.0.0.0 --port 8000
Set CLOUD_DB_PATH to a persistent volume and CLOUD_API_TOKEN for deployment.
"""
from __future__ import annotations

import base64
import hmac
import ipaddress
import json
import os
import time
from collections import defaultdict, deque
from pathlib import Path
from threading import Lock
from typing import Any, Literal
from urllib.parse import urlsplit

import psutil
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from .config import CloudConfig, ensure_parent
from .db import Database
from .processing import process_online_results

config = CloudConfig()
ensure_parent(config.db_path)
db = Database(config.db_path)
_APP_ENV = os.getenv("APP_ENV", "development").strip().lower()
_docs_setting = os.getenv("ENABLE_API_DOCS")
if _docs_setting is None:
    _API_DOCS_ENABLED = _APP_ENV not in {"prod", "production"}
else:
    _API_DOCS_ENABLED = _docs_setting.strip().lower() in {"1", "true", "yes", "on"}

app = FastAPI(
    title="MayaCardio Synthetic Biosignal Pipeline",
    version="0.2.0",
    description="Synthetic biosignal collection, processing, and synchronization API.",
    docs_url="/docs" if _API_DOCS_ENABLED else None,
    redoc_url="/redoc" if _API_DOCS_ENABLED else None,
    openapi_url="/openapi.json" if _API_DOCS_ENABLED else None,
)

# The device-to-cloud bearer token and browser dashboard session are separate credentials.
# Browser code never receives CLOUD_API_TOKEN. With no dashboard credentials configured,
# dashboard endpoints are available only to loopback clients for local development.
_DASHBOARD_USERNAME = os.getenv("DASHBOARD_USERNAME", "")
_DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "")
_DASHBOARD_SESSION_SECRET = os.getenv("DASHBOARD_SESSION_SECRET", "")
_DASHBOARD_COOKIE_NAME = "mayacardio_dashboard_session"
_DASHBOARD_SESSION_SECONDS = 8 * 60 * 60
_DASHBOARD_AUTH_PARTIAL = any((_DASHBOARD_USERNAME, _DASHBOARD_PASSWORD, _DASHBOARD_SESSION_SECRET)) and not (
    _DASHBOARD_USERNAME and _DASHBOARD_PASSWORD and len(_DASHBOARD_SESSION_SECRET) >= 32 and len(_DASHBOARD_PASSWORD) >= 12
)
_DASHBOARD_AUTH_CONFIGURED = bool(
    _DASHBOARD_USERNAME and _DASHBOARD_PASSWORD and len(_DASHBOARD_SESSION_SECRET) >= 32 and len(_DASHBOARD_PASSWORD) >= 12
)
_login_failures: dict[str, deque[float]] = defaultdict(deque)
_login_lock = Lock()


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if request.url.path in {"/docs", "/redoc"}:
        # FastAPI's optional Swagger/ReDoc page uses its configured static assets and an inline bootstrap.
        csp = ("default-src 'self'; script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
               "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; img-src 'self' data:; "
               "font-src 'self' data: https://cdn.jsdelivr.net; connect-src 'self'; object-src 'none'; "
               "base-uri 'self'; frame-ancestors 'none'; form-action 'self'")
    else:
        csp = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
               "img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; "
               "object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'")
    response.headers.setdefault("Content-Security-Policy", csp)
    response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    if request.url.path.startswith(("/api/auth", "/api/dashboard", "/v1/")):
        response.headers.setdefault("Cache-Control", "no-store")
    if request.url.scheme == "https":
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


def _is_loopback_request(request: Request) -> bool:
    if request.client is None:
        return False
    host = request.client.host
    if host == "testclient":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host.lower() == "localhost"


def _check_same_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    host = request.headers.get("host")
    if origin and host:
        try:
            parsed = urlsplit(origin)
            request_host = urlsplit(f"//{host}")
        except ValueError:
            raise HTTPException(status_code=403, detail="Invalid request origin") from None
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or not request_host.hostname:
            raise HTTPException(status_code=403, detail="Invalid request origin")
        same_host = parsed.netloc.lower() == host.lower()
        # Vite development serves the browser from :5173 and proxies same-machine API requests
        # to :8000. Permit that explicit loopback-only case, never arbitrary remote origins.
        local_dev_origin = False
        if _is_loopback_request(request) and request.url.hostname:
            try:
                local_dev_origin = ipaddress.ip_address(parsed.hostname).is_loopback and ipaddress.ip_address(request.url.hostname).is_loopback
            except ValueError:
                local_dev_origin = parsed.hostname.lower() == "localhost" and request.url.hostname.lower() == "localhost"
        if not same_host and not local_dev_origin:
            raise HTTPException(status_code=403, detail="Cross-origin request rejected")


def _sign_dashboard_session(username: str, expires_at: int) -> str:
    payload = base64.urlsafe_b64encode(
        json.dumps({"u": username, "e": expires_at}, separators=(",", ":")).encode("utf-8")
    ).rstrip(b"=").decode("ascii")
    signature = hmac.new(_DASHBOARD_SESSION_SECRET.encode("utf-8"), payload.encode("ascii"), "sha256").hexdigest()
    return f"{payload}.{signature}"


def _read_dashboard_session(request: Request) -> str | None:
    if not _DASHBOARD_AUTH_CONFIGURED:
        return None
    raw = request.cookies.get(_DASHBOARD_COOKIE_NAME, "")
    if not raw or "." not in raw:
        return None
    payload, supplied_signature = raw.rsplit(".", 1)
    expected_signature = hmac.new(
        _DASHBOARD_SESSION_SECRET.encode("utf-8"), payload.encode("ascii", errors="ignore"), "sha256"
    ).hexdigest()
    if not hmac.compare_digest(supplied_signature, expected_signature):
        return None
    try:
        encoded = payload.encode("ascii")
        decoded = base64.urlsafe_b64decode(encoded + b"=" * (-len(encoded) % 4))
        details = json.loads(decoded)
        if details.get("e", 0) <= int(time.time()):
            return None
        username = details.get("u")
        if username != _DASHBOARD_USERNAME:
            return None
        return str(username)
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


def require_dashboard_access(request: Request) -> str:
    if _DASHBOARD_AUTH_PARTIAL:
        raise HTTPException(status_code=503, detail="Dashboard authentication is partially configured; set all dashboard credentials")
    if not _DASHBOARD_AUTH_CONFIGURED:
        if _is_loopback_request(request):
            return "local-development"
        raise HTTPException(status_code=503, detail="Dashboard authentication must be configured before remote access")
    username = _read_dashboard_session(request)
    if username is None:
        raise HTTPException(status_code=401, detail="Dashboard sign-in required")
    return username


class DashboardLogin(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=1, max_length=1024)


_device_db_cache: dict[str, Database] = {}
_device_db_cache_lock = Lock()


def _device_database() -> Database | None:
    configured_path = os.getenv("DASHBOARD_DEVICE_DB_PATH") or os.getenv("PIPELINE_DB_PATH", "./data/device.db")
    device_path = Path(configured_path).expanduser().resolve()
    cloud_path = Path(config.db_path).expanduser().resolve()
    if device_path == cloud_path or not device_path.is_file():
        return None
    cache_key = str(device_path)
    with _device_db_cache_lock:
        if cache_key not in _device_db_cache:
            _device_db_cache[cache_key] = Database(cache_key)
        return _device_db_cache[cache_key]


def _database_summary(database: Database, *, include_device_metrics: bool = False) -> dict[str, Any]:
    with database.connect() as conn:
        samples = int(conn.execute("SELECT COUNT(*) FROM samples").fetchone()[0])
        losses = int(conn.execute("SELECT COUNT(*) FROM losses").fetchone()[0])
        sessions = int(conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0])
        results = int(conn.execute("SELECT COUNT(*) FROM results").fetchone()[0])
        events = int(conn.execute("SELECT COUNT(*) FROM integrity_events").fetchone()[0])
        last_sample = conn.execute("SELECT MAX(received_at) FROM samples").fetchone()[0]
        last_event = conn.execute("SELECT MAX(created_at) FROM integrity_events").fetchone()[0]
        session_row = conn.execute("SELECT session_id FROM sessions ORDER BY last_seen_at DESC LIMIT 1").fetchone()
        backlog = int(conn.execute("SELECT COUNT(*) FROM samples WHERE uploaded=0").fetchone()[0]) if include_device_metrics else None
    summary: dict[str, Any] = {
        "samples": samples,
        "losses": losses,
        "sessions": sessions,
        "results": results,
        "events": events,
        "last_sample_at": float(last_sample) if last_sample is not None else None,
        "last_event_at": float(last_event) if last_event is not None else None,
        "latest_session_id": str(session_row[0]) if session_row else None,
    }
    if include_device_metrics:
        summary["backlog"] = backlog
        summary["mode"] = database.get_meta("current_mode", "unknown") or "unknown"
    return summary


class SampleIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    session_id: str = Field(min_length=1, max_length=200)
    sensor: Literal[1, 2]
    index: int = Field(ge=0)
    values: list[int] = Field(min_length=2, max_length=3)


class LossIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    session_id: str = Field(min_length=1, max_length=200)
    sensor: Literal[1, 2]
    from_index: int = Field(ge=0)
    to_index: int | None = Field(default=None, ge=0)
    reason: str = Field(min_length=1, max_length=500)


class ModeIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    session_id: str = Field(min_length=1, max_length=200)
    window_index: int = Field(ge=0)
    mode: Literal["online", "offline"]
    prior_peak_index: int | None = Field(default=None, ge=0)
    assigned_at: float | None = None


class ResultIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    session_id: str = Field(min_length=1, max_length=200)
    window_index: int = Field(ge=0)
    mode: Literal["offline"]
    result: dict[str, Any]


class IngestRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    samples: list[SampleIn] = Field(default_factory=list, max_length=15000)
    losses: list[LossIn] = Field(default_factory=list, max_length=3000)
    window_modes: list[ModeIn] = Field(default_factory=list, max_length=2000)
    offline_results: list[ResultIn] = Field(default_factory=list, max_length=2000)


def verify_token(request: Request, authorization: str | None = Header(default=None)) -> None:
    token = config.api_token
    if not token:
        if _is_loopback_request(request):
            return  # Local development only; remote ingestion fails closed without a token.
        raise HTTPException(status_code=503, detail="CLOUD_API_TOKEN must be configured before remote ingestion is enabled")
    expected = f"Bearer {token}"
    if authorization is None or not hmac.compare_digest(authorization, expected):
        raise HTTPException(status_code=401, detail="Invalid or missing bearer token")


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "service": "mayacardio-pipeline", "version": "0.2.0"}


@app.post("/v1/ingest", dependencies=[Depends(verify_token)])
def ingest(body: IngestRequest) -> dict[str, Any]:
    sample_rows = [s.model_dump() for s in body.samples]
    loss_rows = [l.model_dump() for l in body.losses]
    mode_rows = [m.model_dump(exclude_none=False) for m in body.window_modes]
    offline_rows = [r.model_dump() for r in body.offline_results]
    sample_stats = db.add_samples(sample_rows, uploaded=True)
    loss_inserted = db.add_losses(loss_rows, uploaded=True)
    db.insert_window_modes(mode_rows, uploaded=True)
    db.insert_offline_results(offline_rows, uploaded=True)
    results_created = process_online_results(db)
    return {
        "ok": True,
        "samples_inserted": sample_stats["inserted"],
        "samples_duplicate": sample_stats["duplicates"],
        "sample_conflicts": sample_stats["conflicts"],
        "losses_inserted": loss_inserted,
        "results_created": results_created,
        "sample_count": db.sample_count(),
    }


@app.get("/v1/status", dependencies=[Depends(verify_token)])
def status(session_id: str | None = Query(default=None)) -> dict[str, Any]:
    return {"ok": True, "samples": db.sample_count(session_id), "losses": db.loss_count(session_id),
            "sessions": db.get_sessions() if session_id is None else [session_id] if db.session_exists(session_id) else [],
            "results": len(db.results_for_session(session_id)) if session_id else sum(len(db.results_for_session(s)) for s in db.get_sessions())}


@app.get("/v1/sessions/{session_id}/results", dependencies=[Depends(verify_token)])
def results(session_id: str) -> list[dict[str, Any]]:
    return db.results_for_session(session_id)


@app.get("/v1/sessions/{session_id}/samples", dependencies=[Depends(verify_token)])
def samples(session_id: str, sensor: int | None = Query(default=None, ge=1, le=2),
            start: int = Query(default=0, ge=0), limit: int = Query(default=1000, ge=1, le=10000)) -> list[dict[str, Any]]:
    with db.connect() as conn:
        if sensor is None:
            rows = conn.execute(
                "SELECT sensor,sample_index,values_json FROM samples WHERE session_id=? AND sample_index>=? ORDER BY sample_index,sensor LIMIT ?",
                (session_id, start, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT sensor,sample_index,values_json FROM samples WHERE session_id=? AND sensor=? AND sample_index>=? ORDER BY sample_index LIMIT ?",
                (session_id, sensor, start, limit),
            ).fetchall()
    import json
    return [{"sensor": int(r["sensor"]), "index": int(r["sample_index"]), "values": json.loads(r["values_json"])} for r in rows]


@app.get("/v1/sessions/{session_id}/losses", dependencies=[Depends(verify_token)])
def losses(session_id: str) -> list[dict[str, Any]]:
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT sensor,from_index,to_index,reason FROM losses WHERE session_id=? ORDER BY sensor,from_index", (session_id,)
        ).fetchall()
    return [{"sensor": int(r["sensor"]), "from_index": int(r["from_index"]),
             "to_index": None if r["to_index"] is None else int(r["to_index"]), "reason": r["reason"]} for r in rows]


@app.get("/v1/events", dependencies=[Depends(verify_token)])
def events(limit: int = Query(default=100, ge=1, le=1000)) -> list[dict[str, Any]]:
    with db.connect() as conn:
        rows = conn.execute("SELECT * FROM integrity_events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/auth/session")
def dashboard_auth_session(request: Request) -> dict[str, Any]:
    if _DASHBOARD_AUTH_PARTIAL:
        return {"authenticated": False, "login_required": True, "configured": False, "needs_configuration": True}
    if _DASHBOARD_AUTH_CONFIGURED:
        username = _read_dashboard_session(request)
        return {"authenticated": username is not None, "login_required": True, "configured": True,
                "needs_configuration": False, "username": username}
    local_access = _is_loopback_request(request)
    return {"authenticated": local_access, "login_required": not local_access, "configured": False,
            "needs_configuration": not local_access, "username": "local-development" if local_access else None}


@app.post("/api/auth/login")
def dashboard_login(payload: DashboardLogin, request: Request, response: Response) -> dict[str, Any]:
    _check_same_origin(request)
    if _DASHBOARD_AUTH_PARTIAL:
        raise HTTPException(status_code=503, detail="Dashboard authentication is partially configured")
    if not _DASHBOARD_AUTH_CONFIGURED:
        raise HTTPException(status_code=503, detail="Set DASHBOARD_USERNAME, DASHBOARD_PASSWORD (at least 12 characters), and a DASHBOARD_SESSION_SECRET of at least 32 characters")
    ip = request.client.host if request.client else "unknown"
    now = time.time()
    with _login_lock:
        attempts = _login_failures[ip]
        while attempts and now - attempts[0] > 900:
            attempts.popleft()
        if len(attempts) >= 8:
            raise HTTPException(status_code=429, detail="Too many sign-in attempts. Wait 15 minutes and try again.", headers={"Retry-After": "900"})
    valid_user = hmac.compare_digest(payload.username.encode("utf-8"), _DASHBOARD_USERNAME.encode("utf-8"))
    valid_password = hmac.compare_digest(payload.password.encode("utf-8"), _DASHBOARD_PASSWORD.encode("utf-8"))
    if not (valid_user and valid_password):
        with _login_lock:
            _login_failures[ip].append(now)
        raise HTTPException(status_code=401, detail="Invalid username or password")
    with _login_lock:
        _login_failures.pop(ip, None)
    expires_at = int(now) + _DASHBOARD_SESSION_SECONDS
    token = _sign_dashboard_session(_DASHBOARD_USERNAME, expires_at)
    secure_setting = os.getenv("DASHBOARD_COOKIE_SECURE")
    secure_cookie = (secure_setting.lower() in {"1", "true", "yes"}) if secure_setting is not None else request.url.scheme == "https"
    response.set_cookie(
        key=_DASHBOARD_COOKIE_NAME, value=token, max_age=_DASHBOARD_SESSION_SECONDS,
        httponly=True, secure=secure_cookie, samesite="strict", path="/",
    )
    return {"ok": True, "username": _DASHBOARD_USERNAME, "expires_at": expires_at}


@app.post("/api/auth/logout")
def dashboard_logout(request: Request, response: Response) -> dict[str, bool]:
    _check_same_origin(request)
    response.delete_cookie(key=_DASHBOARD_COOKIE_NAME, path="/", httponly=True, samesite="strict")
    return {"ok": True}


def _demo_seed_enabled() -> bool:
    setting = os.getenv("ENABLE_SYNTHETIC_DEMO_SEED")
    if setting is not None:
        return setting.strip().lower() in {"1", "true", "yes", "on"}
    return _APP_ENV in {"dev", "development", "test", "testing"}


def _demo_dataset_path() -> Path:
    default_path = Path(__file__).resolve().parent.parent / "data" / "synthetic_demo_dataset.jsonl"
    return Path(os.getenv("DEMO_DATASET_PATH", str(default_path))).expanduser().resolve()


def _device_database_for_demo_seed() -> Database:
    configured_path = os.getenv("DASHBOARD_DEVICE_DB_PATH") or os.getenv("PIPELINE_DB_PATH", "./data/device.db")
    device_path = Path(configured_path).expanduser().resolve()
    cloud_path = Path(config.db_path).expanduser().resolve()
    if device_path == cloud_path:
        raise HTTPException(status_code=409, detail="Device and cloud databases must use different files for a demo seed")
    cache_key = str(device_path)
    with _device_db_cache_lock:
        if cache_key not in _device_db_cache:
            _device_db_cache[cache_key] = Database(cache_key)
        return _device_db_cache[cache_key]


def _demo_store_status(database: Database, session_id: str) -> dict[str, int | bool]:
    with database.connect() as conn:
        session_exists = conn.execute("SELECT 1 FROM sessions WHERE session_id=?", (session_id,)).fetchone() is not None
        samples_count = int(conn.execute("SELECT COUNT(*) FROM samples WHERE session_id=?", (session_id,)).fetchone()[0])
        losses_count = int(conn.execute("SELECT COUNT(*) FROM losses WHERE session_id=?", (session_id,)).fetchone()[0])
        results_count = int(conn.execute("SELECT COUNT(*) FROM results WHERE session_id=?", (session_id,)).fetchone()[0])
        pending_samples = int(conn.execute("SELECT COUNT(*) FROM samples WHERE session_id=? AND uploaded=0", (session_id,)).fetchone()[0])
    return {"session_exists": session_exists, "sample_rows": samples_count, "loss_records": losses_count,
            "results": results_count, "pending_samples": pending_samples}


@app.get("/api/dashboard/demo/status", dependencies=[Depends(require_dashboard_access)])
def dashboard_demo_status() -> dict[str, Any]:
    from .demo_dataset import (
        BUNDLED_DEMO_DATASET_PATH, DEMO_DURATION_SECONDS, DEMO_GAP_END, DEMO_GAP_START, DEMO_GAP_SENSOR,
        DEMO_NOTICE, DEMO_OFFLINE_WINDOWS, DEMO_SEED, DEMO_SESSION_ID,
    )
    from .db import SAMPLE_RATE

    device_db = _device_database()
    cloud_status = _demo_store_status(db, DEMO_SESSION_ID)
    device_status = _demo_store_status(device_db, DEMO_SESSION_ID) if device_db else {
        "session_exists": False, "sample_rows": 0, "loss_records": 0, "results": 0, "pending_samples": 0,
    }
    path = _demo_dataset_path()
    expected_rows = DEMO_DURATION_SECONDS * SAMPLE_RATE * 2 - (DEMO_GAP_END - DEMO_GAP_START + 1)
    # Treat the fixture as loaded only when its source file and both persisted stores
    # contain the complete expected session. A partial write remains recoverable by
    # calling the idempotent seed endpoint again.
    cloud_complete = (
        cloud_status["session_exists"] and cloud_status["sample_rows"] == expected_rows
        and cloud_status["loss_records"] == 1 and cloud_status["results"] == DEMO_DURATION_SECONDS
        and cloud_status["pending_samples"] == 0
    )
    device_complete = (
        device_status["session_exists"] and device_status["sample_rows"] == expected_rows
        and device_status["loss_records"] == 1 and device_status["results"] == len(DEMO_OFFLINE_WINDOWS)
        and device_status["pending_samples"] == 0
    )
    return {
        "enabled": _demo_seed_enabled(),
        "seeded": bool(path.is_file() and cloud_complete and device_complete),
        "session_id": DEMO_SESSION_ID,
        "seed": DEMO_SEED,
        "sample_rate_hz": SAMPLE_RATE,
        "duration_seconds": DEMO_DURATION_SECONDS,
        "sample_rows": expected_rows,
        "sensor_1_sample_count": DEMO_DURATION_SECONDS * SAMPLE_RATE,
        "sensor_2_sample_count": DEMO_DURATION_SECONDS * SAMPLE_RATE - (DEMO_GAP_END - DEMO_GAP_START + 1),
        "window_count": DEMO_DURATION_SECONDS,
        "controlled_gap": {"sensor": DEMO_GAP_SENSOR, "from_index": DEMO_GAP_START, "to_index": DEMO_GAP_END},
        "offline_windows": list(DEMO_OFFLINE_WINDOWS),
        "dataset_file": path.name,
        "dataset_file_exists": path.is_file(),
        "bundled_fixture_available": BUNDLED_DEMO_DATASET_PATH.is_file(),
        "cloud": cloud_status,
        "device": device_status,
        "notice": DEMO_NOTICE,
    }


@app.post("/api/dashboard/demo/seed", dependencies=[Depends(require_dashboard_access)])
def dashboard_seed_demo(request: Request) -> dict[str, Any]:
    _check_same_origin(request)
    if not _demo_seed_enabled():
        raise HTTPException(status_code=404, detail="Synthetic demo seeding is disabled for this deployment")
    from .demo_dataset import DEMO_SESSION_ID, seed_persistent_demo

    device_db = _device_database_for_demo_seed()
    path = _demo_dataset_path()
    try:
        result = seed_persistent_demo(db, device_db, path)
    except (ValueError, OSError) as exc:
        # Return only a bounded operational message; do not expose filesystem paths or tracebacks.
        raise HTTPException(status_code=409, detail=f"Unable to seed the stored synthetic demo dataset: {exc}") from None
    result["enabled"] = True
    result["dataset_file"] = path.name
    result["session_id"] = DEMO_SESSION_ID
    return result


@app.post("/api/dashboard/demo/reset", dependencies=[Depends(require_dashboard_access)])
def dashboard_reset_demo(request: Request) -> dict[str, Any]:
    _check_same_origin(request)
    if not _demo_seed_enabled():
        raise HTTPException(status_code=404, detail="Synthetic demo reset is disabled for this deployment")
    from .demo_dataset import DEMO_SESSION_ID

    cloud_deleted = db.delete_session(DEMO_SESSION_ID)
    device_db = _device_database()
    device_deleted = device_db.delete_session(DEMO_SESSION_ID) if device_db else False
    path = _demo_dataset_path()
    if path.is_file():
        path.unlink()
    return {"ok": True, "cloud_session_removed": cloud_deleted, "device_session_removed": device_deleted,
            "session_id": DEMO_SESSION_ID, "dataset_file_removed": True,
            "notice": "Only the fixed synthetic demo session was removed; other sessions were not changed."}


@app.get("/api/dashboard/demo/download", dependencies=[Depends(require_dashboard_access)])
def dashboard_download_demo_dataset() -> FileResponse:
    if not _demo_seed_enabled():
        raise HTTPException(status_code=404, detail="Synthetic demo export is disabled for this deployment")
    path = _demo_dataset_path()
    if not path.is_file():
        raise HTTPException(status_code=404, detail="No stored demo dataset yet. Load the deterministic demo session first.")
    return FileResponse(path, media_type="application/x-ndjson", filename="mayacardio_synthetic_demo_dataset.jsonl")


@app.get("/api/dashboard/summary", dependencies=[Depends(require_dashboard_access)])
def dashboard_summary() -> dict[str, Any]:
    cloud_summary = _database_summary(db)
    device_db = _device_database()
    device_summary = _database_summary(device_db, include_device_metrics=True) if device_db else {
        "available": False, "mode": "unavailable", "samples": None, "losses": None,
        "sessions": None, "results": None, "backlog": None, "events": None,
        "last_sample_at": None, "last_event_at": None, "latest_session_id": None,
    }
    if device_db:
        device_summary["available"] = True
    return {
        "generated_at": time.time(),
        "service": {"name": "MayaCardio Synthetic Biosignal Pipeline", "version": "0.2.0"},
        "device": device_summary,
        "cloud": cloud_summary,
        "data_notice": "Synthetic demonstration data only; not for clinical use.",
    }


@app.get("/api/dashboard/sessions", dependencies=[Depends(require_dashboard_access)])
def dashboard_sessions(
    search: str = Query(default="", max_length=200),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=100000),
) -> dict[str, Any]:
    device_db = _device_database()
    id_set = set(db.get_sessions())
    if device_db:
        id_set.update(device_db.get_sessions())
    needle = search.casefold().strip()
    all_ids = sorted(id_set, reverse=True)
    if needle:
        all_ids = [sid for sid in all_ids if needle in sid.casefold()]
    page_ids = all_ids[offset:offset + limit]
    sessions: list[dict[str, Any]] = []
    for session_id in page_ids:
        sources = [("cloud", db)]
        if device_db:
            sources.append(("device", device_db))
        samples = {"cloud": 0, "device": None}
        loss_keys: set[tuple[int, int, int | None, str]] = set()
        result_keys: set[tuple[int, str]] = set()
        max_index: int | None = None
        created_at: float | None = None
        last_seen_at: float | None = None
        ended = False
        for source_name, source_db in sources:
            with source_db.connect() as conn:
                sample_row = conn.execute("SELECT COUNT(*),MAX(sample_index) FROM samples WHERE session_id=?", (session_id,)).fetchone()
                if source_name == "cloud":
                    samples["cloud"] = int(sample_row[0])
                else:
                    samples["device"] = int(sample_row[0])
                if sample_row[1] is not None:
                    max_index = max(max_index or 0, int(sample_row[1]))
                for loss_row in conn.execute("SELECT sensor,from_index,to_index,reason FROM losses WHERE session_id=?", (session_id,)).fetchall():
                    loss_keys.add((int(loss_row["sensor"]), int(loss_row["from_index"]),
                                   None if loss_row["to_index"] is None else int(loss_row["to_index"]), str(loss_row["reason"])))
                for result_row in conn.execute("SELECT window_index,mode FROM results WHERE session_id=?", (session_id,)).fetchall():
                    result_keys.add((int(result_row["window_index"]), str(result_row["mode"])))
                session_row = conn.execute("SELECT created_at,last_seen_at,ended FROM sessions WHERE session_id=?", (session_id,)).fetchone()
                if session_row:
                    created_at = min(created_at, float(session_row[0])) if created_at is not None else float(session_row[0])
                    last_seen_at = max(last_seen_at or 0.0, float(session_row[1]))
                    ended = ended or bool(session_row[2])
        sessions.append({"session_id": session_id, "samples_cloud": samples["cloud"], "samples_device": samples["device"],
                         "losses": len(loss_keys), "results": len(result_keys), "latest_sample_index": max_index,
                         "created_at": created_at, "last_seen_at": last_seen_at, "ended": ended})
    return {"items": sessions, "total": len(all_ids), "limit": limit, "offset": offset}


@app.get("/api/dashboard/sessions/{session_id}/results", dependencies=[Depends(require_dashboard_access)])
def dashboard_session_results(
    session_id: str, limit: int = Query(default=500, ge=1, le=5000), offset: int = Query(default=0, ge=0, le=100000),
) -> dict[str, Any]:
    rows: dict[tuple[str, int, str], dict[str, Any]] = {}
    for source_db in (db, _device_database()):
        if source_db is None:
            continue
        for row in source_db.results_for_session(session_id):
            key = (str(row.get("session_id", session_id)), int(row["window_index"]), str(row["mode"]))
            rows[key] = row
    ordered = sorted(rows.values(), key=lambda row: (int(row["window_index"]), str(row["mode"])))
    return {"items": ordered[offset:offset + limit], "total": len(ordered), "limit": limit, "offset": offset}


@app.get("/api/dashboard/sessions/{session_id}/samples", dependencies=[Depends(require_dashboard_access)])
def dashboard_session_samples(
    session_id: str, source: Literal["cloud", "device"] = Query(default="cloud"),
    sensor: int | None = Query(default=None, ge=1, le=2), start: int = Query(default=0, ge=0),
    limit: int = Query(default=500, ge=1, le=1000),
) -> dict[str, Any]:
    source_db = db if source == "cloud" else _device_database()
    if source_db is None:
        raise HTTPException(status_code=404, detail="Device database is not available on this host")
    with source_db.connect() as conn:
        if sensor is None:
            rows = conn.execute(
                "SELECT sensor,sample_index,values_json,received_at FROM samples WHERE session_id=? AND sample_index>=? ORDER BY sample_index,sensor LIMIT ?",
                (session_id, start, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT sensor,sample_index,values_json,received_at FROM samples WHERE session_id=? AND sensor=? AND sample_index>=? ORDER BY sample_index LIMIT ?",
                (session_id, sensor, start, limit),
            ).fetchall()
    return {"items": [{"sensor": int(row["sensor"]), "index": int(row["sample_index"]), "values": json.loads(row["values_json"]),
                       "received_at": float(row["received_at"])} for row in rows], "limit": limit, "start": start, "source": source}


@app.get("/api/dashboard/sessions/{session_id}/losses", dependencies=[Depends(require_dashboard_access)])
def dashboard_session_losses(session_id: str) -> list[dict[str, Any]]:
    combined: dict[tuple[Any, ...], dict[str, Any]] = {}
    for source_name, source_db in (("cloud", db), ("device", _device_database())):
        if source_db is None:
            continue
        with source_db.connect() as conn:
            rows = conn.execute(
                "SELECT sensor,from_index,to_index,reason,recorded_at FROM losses WHERE session_id=? ORDER BY sensor,from_index", (session_id,)
            ).fetchall()
        for row in rows:
            item = {"sensor": int(row["sensor"]), "from_index": int(row["from_index"]),
                    "to_index": None if row["to_index"] is None else int(row["to_index"]),
                    "reason": str(row["reason"]), "recorded_at": float(row["recorded_at"]), "source": source_name}
            key = (item["sensor"], item["from_index"], item["to_index"], item["reason"])
            # Prefer the cloud copy if a loss record has been synchronized.
            if key not in combined or source_name == "cloud":
                combined[key] = item
    return sorted(combined.values(), key=lambda item: (item["sensor"], item["from_index"]))


@app.get("/api/dashboard/events", dependencies=[Depends(require_dashboard_access)])
def dashboard_events(limit: int = Query(default=100, ge=1, le=500)) -> list[dict[str, Any]]:
    device_db = _device_database()
    combined: list[dict[str, Any]] = []
    for source_name, source_db in (("cloud", db), ("device", device_db)):
        if source_db is None:
            continue
        with source_db.connect() as conn:
            rows = conn.execute("SELECT id,session_id,sensor,sample_index,event_type,detail,created_at FROM integrity_events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        combined.extend({"id": f"{source_name}-{row['id']}", "session_id": row["session_id"], "sensor": row["sensor"],
                         "sample_index": row["sample_index"], "event_type": row["event_type"], "detail": row["detail"],
                         "created_at": float(row["created_at"]), "source": source_name} for row in rows)
    return sorted(combined, key=lambda item: item["created_at"], reverse=True)[:limit]


@app.get("/api/dashboard/resources", dependencies=[Depends(require_dashboard_access)])
def dashboard_resources() -> dict[str, Any]:
    try:
        disk = psutil.disk_usage(str(Path(config.db_path).expanduser().resolve().parent))
        memory = psutil.virtual_memory()
        return {
            "observed_at": time.time(),
            "scope": "API service host; these figures are not Raspberry Pi device measurements unless this API runs on that device",
            "cpu_percent": psutil.cpu_percent(interval=None),
            "memory": {"total_bytes": memory.total, "used_bytes": memory.used, "percent": memory.percent},
            "disk": {"total_bytes": disk.total, "used_bytes": disk.used, "free_bytes": disk.free, "percent": disk.percent},
            "pid": os.getpid(),
        }
    except (OSError, RuntimeError) as exc:
        raise HTTPException(status_code=503, detail="Host resource metrics are currently unavailable") from exc


# Serve a production frontend build when present. In development, Vite serves the UI and
# proxies /api to this FastAPI process. Hash-based frontend routing avoids SPA deep-link ambiguity.
_frontend_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if (_frontend_dist / "index.html").is_file():
    app.mount("/", StaticFiles(directory=str(_frontend_dist), html=True), name="website")
