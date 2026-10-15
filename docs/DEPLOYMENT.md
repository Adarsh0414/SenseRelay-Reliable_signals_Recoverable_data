# Deployment Guide - Website and API

## Local development

Use separate processes for the cloud API, React/Vite UI, and development sensor/pipeline. Docker remains optional.

### Terminal 1 - backend

From repository root:

```powershell
.\.venv\Scripts\Activate.ps1
New-Item -ItemType Directory -Force .\data | Out-Null
$env:CLOUD_DB_PATH = ".\data\cloud.db"
$env:CLOUD_API_TOKEN = "demo-only-change-me"
python -m uvicorn pipeline.cloud_app:app --host 127.0.0.1 --port 8000
```

### Terminal 2 - frontend

```powershell
Set-Location .\frontend
npm install
npm run dev
```

Open the local Vite URL printed in the terminal (normally `http://127.0.0.1:5173/#/`). The API proxy routes dashboard calls to FastAPI on port 8000, so keep FastAPI running. Vite 8 requires Node.js 20.19+ or 22.12+; Node.js 22.12+ is recommended.

### Tests

From repository root:

```powershell
python -m pytest -q
```

From `frontend/`:

```powershell
npm run lint
npm run typecheck
npm test
npm run audit
npm run build
```

## Production build and static serving

Set the actual public origin before building:

```powershell
Set-Location .\frontend
$env:PUBLIC_SITE_URL = "https://YOUR-REAL-HOSTNAME"
$env:VITE_PUBLIC_SITE_URL = "https://YOUR-REAL-HOSTNAME"
$env:VITE_API_DOCS_ENABLED = "false"
npm run build
```

Replace the placeholder. The first `npm install` generates `package-lock.json`; commit it before using `npm ci` in CI or on a clean machine. The build output is `frontend/dist/`. If this directory exists, FastAPI serves the generated website at `/`; hash-based routing is used so individual frontend views do not require separate server routes.

## Production environment

Set these variables on the server only:

```text
CLOUD_DB_PATH=/persistent/path/cloud.db
CLOUD_API_TOKEN=<long-random-device-to-cloud-secret>
DASHBOARD_USERNAME=<administrator-username>
DASHBOARD_PASSWORD=<unique-password-at-least-12-characters>
DASHBOARD_SESSION_SECRET=<random-secret-at-least-32-characters>
DASHBOARD_COOKIE_SECURE=true
APP_ENV=production
ENABLE_API_DOCS=false
```

API docs, ReDoc, and the OpenAPI schema are enabled automatically in development. In production, set `APP_ENV=production`; docs are then disabled unless `ENABLE_API_DOCS=true` is explicitly configured. For a matching frontend build, set `VITE_API_DOCS_ENABLED=false` so the interface does not offer an API reference link that the backend has disabled. Only enable docs publicly after reviewing whether that disclosure is appropriate.

Set `DASHBOARD_DEVICE_DB_PATH` only when the API host is intentionally expected to have access to a local/device database. On a separate cloud VM that database usually does not exist, so device metrics should display as unavailable. Do not copy a device database to cloud merely to populate the UI unless that is part of the chosen, secure architecture.

Run FastAPI behind an HTTPS reverse proxy. Keep SQLite on persistent storage with restricted file permissions, restrict inbound ports, configure backups, and verify that cloud billing/free-tier settings meet the assessment's constraints. Do not expose port 8000 directly to the public internet without an appropriate security boundary.

The health endpoint is `/health`. The FastAPI API reference is `/docs` in development. In production, it is disabled by default when `APP_ENV=production`, unless deliberately enabled with `ENABLE_API_DOCS=true`.

## Rollback

Keep the previous code revision and a tested backup of persistent databases. Roll back code if new-build smoke tests fail. Do not delete SQLite databases or WAL files while the service is running. Stop the service gracefully before moving or restoring database files.

## Not automatically performed

This guide does not provision a cloud provider or domain, create accounts, approve billing, install TLS certificates, configure actual secrets, or prove the Raspberry Pi/official-checker criteria. Those tasks require your hosting account and independent verification.
