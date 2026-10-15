# Start the MayaCardio Website on Windows

This guide starts the **website UI** and the **FastAPI API** in VS Code. Docker is optional. The first `npm install` requires npm registry access and generates `frontend/package-lock.json`; commit that lockfile to GitHub after a successful install.

## 1. One-time prerequisites

- Python 3.11+ and a working project virtual environment (Python 3.13 is supported).
- Node.js 22.12+ and npm. Check with `node --version` and `npm --version`.
- Open the repository root in VS Code. It is the folder containing `pyproject.toml` and `frontend/`.

## 2. Terminal 1 - start FastAPI

From the repository root:

```powershell
.\.venv\Scripts\Activate.ps1
New-Item -ItemType Directory -Force .\data | Out-Null
$env:APP_ENV = "development"
$env:CLOUD_DB_PATH = ".\data\cloud.db"
$env:CLOUD_API_TOKEN = "demo-only-change-me"
python -m uvicorn pipeline.cloud_app:app --host 127.0.0.1 --port 8000
```

Keep this terminal running. `demo-only-change-me` is for local loopback use only. Do not use it in a public deployment.

## 3. Terminal 2 - install and start the website

Open another terminal:

```powershell
Set-Location .\frontend
npm install
npm run dev
```

If npm says it cannot reach the registry, check your internet/proxy configuration and retry. Do not delete project files to fix a network timeout.

Open the URL printed by Vite, normally:

`http://127.0.0.1:5173/#/`

The public landing page should load. Select **Open dashboard** to inspect the live API-backed workspace. Keep Terminal 1 and Terminal 2 running while using the page.

### Populate the dashboard with one saved synthetic session

A new clone starts with empty runtime databases; the UI should not make up counters. For a professional walkthrough, open **Open dashboard**, then use **Load demo dataset** in the Overview notice. This loads the bundled deterministic seed-7 source at `data/fixtures/synthetic_demo_seed7.jsonl`, creates the runtime JSONL copy at `data/synthetic_demo_dataset.jsonl`, and persists the same sample records/results into `data/device.db` and `data/cloud.db`. You should then see sample counts, 30 processing windows, a documented Sensor 2 gap at indexes 4,800-4,839, and three windows marked offline. The same session appears in Sessions, Processing results, and Data integrity. In Settings & help you can download the JSONL file or reset only the fixed demo session.

This dashboard fixture is for a repeatable website/interview demo. It is not the assessment's official mock and must not be presented as evidence that the real collector, switching deadlines, ARM64 limits, or power-cut acceptance tests passed. Do not add the runtime JSONL or SQLite database files to Git; the seed implementation is what reproduces them.


## 4. Run frontend checks

From `frontend/`:

```powershell
npm run lint
npm run typecheck
npm test
npm run audit
npm run build
```

If a command fails, copy the complete output and diagnose it before committing a claimed passing result. The build writes `frontend/dist/`. If that directory exists, the FastAPI app serves the built website from `/` when started from the repository.

## 5. Optional: populate the dashboard with a local synthetic demo

This is for development only and is **not a substitute** for MayaCardio's official mock or acceptance checker.

Start Terminal 3 from the repository root and run the development sensor simulator. Start the simulator immediately before the pipeline so its limited unread-data buffer does not fill while no collector is reading it:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pipeline.demo_mock --mode signal --seed 7 --duration 1800 --port 7100 --speed 1
```

Copy the session ID from the output and leave the simulator running. In Terminal 4, from the repository root:

```powershell
.\.venv\Scripts\Activate.ps1
New-Item -ItemType Directory -Force .\data | Out-Null
$env:PIPELINE_DB_PATH = ".\data\device.db"
$env:MOCK_HOST = "127.0.0.1"
$env:MOCK_PORT = "7100"
$env:CLOUD_URL = "http://127.0.0.1:8000"
$env:CLOUD_API_TOKEN = "demo-only-change-me"
python -m pipeline.cli run
```

When the dashboard is open, samples that have reached the backend should appear as sessions/results. If it reports unavailable device metrics, check that the API can access `data/device.db`; use the same repository root and make sure the pipeline has started. Do not treat zero displayed loss records as proof that all official acceptance checks passed.

To stop the demo, press `Ctrl+C` in Terminal 4, Terminal 3, and then the API terminal. You can leave the Vite process running while you inspect the UI.

## 6. Production requirements

Do not expose the Vite development server publicly. Before a public build, set the real origin and build with API docs disabled unless they have deliberately been reviewed for exposure:

```powershell
Set-Location .\frontend
$env:PUBLIC_SITE_URL = "https://YOUR-REAL-HOSTNAME"
$env:VITE_PUBLIC_SITE_URL = "https://YOUR-REAL-HOSTNAME"
$env:VITE_API_DOCS_ENABLED = "false"
npm run build
```

On the backend host, set server-only values using a secure environment/secret manager:

```text
APP_ENV=production
ENABLE_API_DOCS=false
CLOUD_API_TOKEN=<unique-long-random-token>
DASHBOARD_USERNAME=<administrator-name>
DASHBOARD_PASSWORD=<unique-password-at-least-12-characters>
DASHBOARD_SESSION_SECRET=<random-secret-at-least-32-characters>
DASHBOARD_COOKIE_SECURE=true
```

Serve the API behind HTTPS, keep the database on persistent protected storage, and restrict network access. Never put these credentials in `VITE_*` variables or frontend files.

## What this guide does not prove

A successful local website run does not prove official `biosignal-mock` compatibility, the ground-truth comparison, ARM64/Raspberry Pi resource limits, power-cut durability, the five-second/ten-second timing targets, two-hour outage recovery, or the required physical demonstration video. Those remain separate MayaCardio assessment requirements.
