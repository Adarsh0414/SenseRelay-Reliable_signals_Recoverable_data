# MayaCardio Software Systems Engineer - Step-by-Step Run and GitHub Guide

**Project:** Never Lose a Heartbeat
**Scope:** Local synthetic demo, automated tests, GitHub publishing, and the remaining official-assessment checks.

> **Important:** This guide distinguishes a local development demo from final assessment evidence. The included `pipeline/demo_mock.py` is a development-only simulator. The assignment's final validation requires MayaCardio's official `biosignal-mock` and `check_ground_truth` tool, plus ARM64 device and real free-cloud testing.

## 1. What you need - and what is optional

| Item | Needed now? | Why |
|---|---|---|
| Python 3.11 or newer (your Python 3.13 is supported; Python 3.12 is used only inside the Docker image) | Yes | Runs the pipeline, simulator, API, and tests. |
| Git for Windows | Yes, to push using Git commands | Tracks code and publishes it to GitHub. GitHub Desktop is an optional graphical alternative. |
| Internet access | Yes, for initial dependency installation and GitHub | Downloads Python packages and pushes the repository. |
| Docker Desktop | **Optional** | Only needed if you choose the Docker Compose demo. Do not install Docker inside the source project. |
| Static JSON dataset | **No for this role** | The Software Systems assessment describes a live synthetic TCP service named `biosignal-mock`, not a static JSON dataset. |
| Official `biosignal-mock` and `check_ground_truth` | Required for final acceptance testing | They were not included in the assessment files available when this project was prepared. Request them from PAT/MayaCardio. |
| ARM64 Linux / Raspberry Pi-class environment (maximum 4 CPU cores and 2 GB RAM for device side) | Required for final acceptance evidence | A Windows laptop-only demo cannot prove this criterion. |
| Real free-tier cloud deployment with persistent storage | Required for final acceptance | A local FastAPI service is only a development demo. Paid cloud resources disqualify the submission. |

## 2. Download and extract the project correctly

1. Download `mayacardio_never_lose_a_heartbeat.zip`.
2. In File Explorer, right-click the ZIP and select **Extract All**.
3. Open the extracted project folder. Depending on your extraction settings, there may be two nested folders with the same name. Use the **inner folder** that contains all of these items:
  - `README.md`
  - `pyproject.toml`
  - `requirements.txt`
  - `pipeline/`
  - `tests/`
  - `docs/`
  - `scripts/`
  - `Dockerfile` and `compose.demo.yml`
4. Do not run commands from the Downloads folder above the project root. All commands below should be run from the directory containing `pyproject.toml`.

In PowerShell, verify the folder with:

```powershell
Get-ChildItem
```

## 3. Install the basic tools on Windows

### 3.1 Install Python

You already have Python 3.13, so you do not need to install Python 3.12. The project metadata requires Python 3.11 or newer. The README mentioning Python 3.12 refers to the Docker image, not a requirement for your Windows installation.

Open a **new** PowerShell window and check:

```powershell
py -3.13 --version
```

Expected: Python 3.13.x. If `py -3.13` is not recognized, try `python --version`; as long as it reports Python 3.11 or newer, you can create the virtual environment with `python -m venv .venv`.

### 3.2 Install Git

Install Git for Windows from <https://git-scm.com/download/win>. Open a new PowerShell window and verify:

```powershell
git --version
```

Docker is not needed for the native-Python steps below.

## 4. Create the project environment and install dependencies

Open PowerShell in the project root. Replace the path in the first line with the actual path on your computer:

```powershell
Set-Location "C:\path\to\mayacardio_never_lose_a_heartbeat"
py -3.13 -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[test]"
```

The execution-policy command applies only to that PowerShell process. If activation still fails, use the virtual-environment Python directly, for example:

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
```

Do not install these dependencies globally and do not commit the `.venv` folder to GitHub.

## 5. Run the automated tests first

From the same project root, with the virtual environment activated:

```powershell
python -m pytest
```

The project currently has 22 local automated tests. All 22 passed in the prepared development environment. Your computer should run the tests again after installation; retain the actual output you see. If any test fails, do not continue as if the tests passed - copy the complete error and investigate it first.

## 6. Run the local demo without Docker

This starts three separate processes. Keep three PowerShell windows open. In **each** window, navigate to the project root and activate `.venv`.

### Terminal 1 - development-only mock

```powershell
python -m pipeline.demo_mock --mode signal --seed 7 --duration 300 --port 7100 --speed 4
```

It prints a line containing `DEVELOPMENT MOCK ONLY` and a `session=...` identifier. Copy the full session ID somewhere; you will need it for the export/result commands. This mock is only for local development, not final ground-truth evidence.

### Terminal 2 - local cloud API

```powershell
New-Item -ItemType Directory -Force .\data | Out-Null
$env:CLOUD_DB_PATH = ".\data\cloud.db"
$env:CLOUD_API_TOKEN = "demo-only-change-me"
python -m uvicorn pipeline.cloud_app:app --host 127.0.0.1 --port 8000
```

Keep the token exactly the same in Terminal 3. It is a demo-only local token; never use it on a public cloud deployment.

In another PowerShell window, verify the API health endpoint:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
```

It should return JSON indicating `ok: true`.

### Terminal 3 - device pipeline

```powershell
New-Item -ItemType Directory -Force .\data | Out-Null
$env:PIPELINE_DB_PATH = ".\data\device.db"
$env:MOCK_HOST = "127.0.0.1"
$env:MOCK_PORT = "7100"
$env:CLOUD_URL = "http://127.0.0.1:8000"
$env:CLOUD_API_TOKEN = "demo-only-change-me"
$env:POLL_INTERVAL_SECONDS = "0.05"
python -m pipeline.cli run
```

Let it run for about 15-30 seconds. Then stop the pipeline with **Ctrl+C in Terminal 3**. Stop the mock and API with Ctrl+C in Terminals 1 and 2 when you have finished checking the results.

### Terminal 4 - inspect the run

Open a fourth PowerShell window. Navigate to the project root, activate `.venv`, and set the device/cloud environment variables again because environment variables set in one terminal are not automatically shared with other terminals:

```powershell
$env:PIPELINE_DB_PATH = ".\data\device.db"
$env:MOCK_HOST = "127.0.0.1"
$env:MOCK_PORT = "7100"
$env:CLOUD_URL = "http://127.0.0.1:8000"
$env:CLOUD_API_TOKEN = "demo-only-change-me"
python -m pipeline.cli status
python -m pipeline.cli db-check
```

`status` should report sample counts and a backlog value. `db-check` should return JSON with `"ok": true` if the local database integrity check passes.

Use the session ID copied from Terminal 1:

```powershell
python -m pipeline.cli results --session "PASTE_SESSION_ID_HERE"
python -m pipeline.cli export --session "PASTE_SESSION_ID_HERE" --from device
python -m pipeline.cli export --session "PASTE_SESSION_ID_HERE" --from cloud
```

Exports are one JSON object per line and may be very long. For the first run, `status`, `db-check`, and `results` are enough to confirm that the pipeline is running; only export full sample files when needed. Keep generated database files and large local exports out of the GitHub source repository.

### What this local demo proves - and does not prove

It demonstrates basic integration between the development simulator, local SQLite database, and local cloud API. It does **not** prove the official mock's compatibility, ARM64 resource compliance, a physical power-cut bound, the five-second/ten-second deadlines, or two-hour outage recovery. Those tests require the official test resources and environment.

## 7. Alternative local demo with Docker Compose (optional)

Choose this section **instead of** the manual three-terminal run only if you want to use Docker. Docker Desktop is a separate Windows application; it is not something installed into the Python source code. Official installation guide: <https://docs.docker.com/desktop/setup/install/windows-install/>.

After Docker Desktop is installed and running, open PowerShell in the project root and execute:

```powershell
docker compose -f compose.demo.yml up --build
```

In a second PowerShell window in the same project root, check the device service:

```powershell
docker compose -f compose.demo.yml exec device pipeline status
docker compose -f compose.demo.yml exec device pipeline db-check
docker compose -f compose.demo.yml logs mock
```

The included Compose file is marked **local demo only** and uses the development mock. It starts with a one-hour, real-time mock configuration, so it is not the fastest option for a short demo. Stop with Ctrl+C. If you want to remove containers afterward, use:

```powershell
docker compose -f compose.demo.yml down
```

Do **not** add `-v` unless you intentionally want to delete the Compose database volumes and their stored data.

## 8. Publish the project to GitHub

### 8.1 Check what will be published

First stop the three local processes. Make sure you are in the project root that contains `pyproject.toml`. Then run:

```powershell
git status
```

The included `.gitignore` excludes `.venv/`, `.env`, Python caches, and SQLite database files. Never publish access tokens, passwords, `.env` files, database files, or virtual-environment folders. The demo token shown in this guide is only for local development.

If Git has never been configured on your computer, set your commit identity (use your own details):

```powershell
git config --global user.name "YOUR NAME"
git config --global user.email "YOUR_GITHUB_EMAIL"
```

### 8.2 Initialize and commit locally

Run these commands from the project root:

```powershell
git init -b main
git add .
git status
git commit -m "Build fault-tolerant synthetic biosignal pipeline"
```

Before `git commit`, inspect `git status` and confirm that `.venv`, `.env`, `data/device.db`, `data/cloud.db`, and large generated sample exports are not staged. If they are staged, stop and unstage them; do not push secrets or generated databases.

If Git reports that the branch already exists because you initialized the repository earlier, do not repeatedly run `git init`; inspect `git status` and continue with the existing repository.

### 8.3 Create an empty GitHub repository

1. Sign in to <https://github.com/>.
2. Click **New repository**.
3. Suggested repository name: `mayacardio-never-lose-a-heartbeat`.
4. Choose **Public** if PAT/company reviewers need to open the link without special access, unless your placement instructions require a private repository.
5. Because the full project already exists locally, leave **Add a README**, **Add .gitignore**, and **Choose a license** unchecked. This avoids creating a separate initial commit on GitHub that can conflict with the local history.
6. Create the repository and copy its HTTPS URL from the GitHub page.

### 8.4 Connect and push

Replace `YOUR_GITHUB_USERNAME` with your actual GitHub username:

```powershell
git remote add origin https://github.com/YOUR_GITHUB_USERNAME/mayacardio-never-lose-a-heartbeat.git
git remote -v
git push -u origin main
```

Follow the sign-in prompt if Git asks you to authenticate. Do not place passwords or personal access tokens directly into the Git remote URL.

If `origin` already exists, inspect it with `git remote -v` instead of adding it again. If the branch is not named `main`, check `git branch` and use the actual branch name.

### 8.5 Verify the online repository

Refresh the GitHub repository page and confirm that it shows:

- `README.md` at the top of the repository;
- `pipeline/`, `tests/`, `scripts/`, and `docs/`;
- `pyproject.toml`, `requirements.txt`, `.gitignore`, `Dockerfile`, and `compose.demo.yml`;
- no `.venv/`, `.env`, SQLite databases, or secret keys.

Open the README using a signed-out/private browser window if possible to confirm that the reviewer can access a public repository.

## 9. What remains for final assessment submission

Do not mark these as complete merely because the local tests pass:

1. Obtain MayaCardio's **official** ARM64 `biosignal-mock` and `check_ground_truth` utility. The uploaded assessment copy has a blank download placeholder, so their exact command line cannot be inferred safely. Ask PAT using the placement office's designated query address.
2. Run the pipeline on ARM64 Linux / Raspberry Pi-class hardware and prove the device-side limit of at most 4 CPU cores and 2 GB RAM.
3. Compare `pipeline export --session SESSION_ID --from device` against the official ground truth with the checker instructions supplied by MayaCardio.
4. Run and record process-kill/restart, physical power-cut, network-cut/restore, and disk-full tests. State the actual observed power-loss bound; do not claim zero loss without evidence.
5. Measure one full hour with the included helper, using the actual pipeline PID:

   ```bash
   python scripts/measure_resources.py --pid <PIPELINE_PID> --duration 3600 --interval 1 --output docs/resource_measurements.csv
   ```

6. Verify and record the actual five-second online-result deadline, ten-second mode-switch deadline, and catch-up after an outage of up to two hours (complete cloud copy within 15 minutes).
7. Record the required five-minute demo video showing a network cut, process kill, and physical power cut.
8. Update `docs/TEST_EVIDENCE.md` only with measurements and results actually obtained. Keep commands, timestamps, logs, checker output, and evidence filenames.

The project documentation already labels these acceptance tests as outstanding. Do not edit it to claim they passed until you have evidence.

## 10. Submit the correct link and follow placement instructions

- Paste the public GitHub repository URL into the placement Google Form wherever it requests the project/repository link. Submit before the deadline stated in the placement email.
- The Software Systems Engineer JD also says to email the CV or short project summary and completed assessment to `BuildWithUS@mayacardio.io`, with subject `2026 Oct: Software Systems Engineer - [Your Name]`. Follow any more specific instruction from PAT and do not treat an email as a substitute for the placement-office form unless PAT confirms it.
- For missing official mock/checker downloads or submission questions, use the placement-office query address specified in the email: `patqueries.bhopal@vitbhopal.ac.in`.
- The placement email says shortlisted students who have completed the assignment must report to LC103 at 3:00 PM on 16 October 2026 in PAT formals. Follow the latest PAT instructions if they have sent an update.

## Official references

- GitHub: Add locally hosted code to GitHub - <https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github>
- Docker Desktop for Windows (only if using Docker) - <https://docs.docker.com/desktop/setup/install/windows-install/>
- Python for Windows - <https://www.python.org/downloads/windows/>
