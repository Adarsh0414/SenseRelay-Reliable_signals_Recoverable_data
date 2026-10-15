"""Environment-backed configuration for the device and cloud services."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc


@dataclass(frozen=True)
class DeviceConfig:
    db_path: str = os.getenv("PIPELINE_DB_PATH", "./data/device.db")
    mock_host: str = os.getenv("MOCK_HOST", "127.0.0.1")
    mock_port: int = _int("MOCK_PORT", 7100)
    cloud_url: str = os.getenv("CLOUD_URL", "http://127.0.0.1:8000").rstrip("/")
    cloud_token: str = os.getenv("CLOUD_API_TOKEN", "")
    poll_interval: float = _float("POLL_INTERVAL_SECONDS", 0.05)
    health_interval: float = _float("HEALTH_INTERVAL_SECONDS", 1.0)
    connect_timeout: float = _float("HTTP_CONNECT_TIMEOUT_SECONDS", 0.7)
    read_timeout: float = _float("HTTP_READ_TIMEOUT_SECONDS", 2.0)
    upload_live_limit: int = _int("UPLOAD_LIVE_LIMIT", 8000)
    upload_backlog_limit: int = _int("UPLOAD_BACKLOG_LIMIT", 4000)


@dataclass(frozen=True)
class CloudConfig:
    db_path: str = os.getenv("CLOUD_DB_PATH", "./data/cloud.db")
    api_token: str = os.getenv("CLOUD_API_TOKEN", "")


def ensure_parent(path: str) -> None:
    Path(path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
