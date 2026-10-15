# MayaCardio Dashboard Presentation Walkthrough (3-5 minutes)

This script demonstrates the **website presentation fixture** and the relationship between the same stored data across the dashboard. It is not the assessment's official five-minute failure-test video, which must separately show a network cut, process kill, and physical power interruption on the required environment.

## Before recording

1. Open the project in VS Code.
2. Start FastAPI in a terminal from the repository root using the local development configuration from `docs/START_WEBSITE_ON_WINDOWS.md`.
3. Start Vite in a second terminal from `frontend/` with `npm run dev`.
4. Open the printed localhost URL and choose **Open dashboard**.
5. Start with the deterministic fixture not yet loaded, if you want to show the empty state honestly.

## Suggested timeline

### 0:00-0:30 - Explain the scope

Say: “This is a synthetic-data engineering demonstration. The dashboard never uses hardcoded counts. I will load one reproducible fixture, persist it, and then inspect the same session in each page.” Point out the visible synthetic environment notice.

### 0:30-1:10 - Create and persist the dataset

Click **Load demo dataset**. Wait for the successful feedback message and refreshed counts. Explain that the checked-in `data/fixtures/synthetic_demo_seed7.jsonl` source uses seed 7 for reproducibility; the API creates `data/synthetic_demo_dataset.jsonl` as the runtime copy and stores matching rows in both `data/device.db` and `data/cloud.db`. Do not say that this simulates a real cloud deployment: the dashboard's “cloud” store is the local FastAPI cloud-service database in this laptop demo, not a remote cloud account.

### 1:10-1:50 - Overview and sessions

Show device/cloud sample counts, no pending backlog for the seeded fixture, and the processing chart. Open **Sessions** and select `maya-demo-seed7-v1`. Explain that the views derive from the stored session rather than separate card values.

### 1:50-2:40 - Processing results

Open **Processing results**. Show the one-second windows and point out the means/minima/maxima, magnitude, heart-rate estimate when valid, completeness, and online/offline mode. Point out the intentionally incomplete window near the documented sensor-2 gap; do not hide it.

### 2:40-3:20 - Integrity and data provenance

Open **Data integrity** and show the explicit Sensor 2 gap from sample index 4,800 through 4,839. Explain that no values are invented for this interval. Show the seed, sample rate, duration, number of stored sample rows, loss count, and dataset file in **Settings & help**.

### 3:20-4:00 - Export and repeatability

Use **Download JSONL**. Explain that the first line is the manifest and remaining lines contain the actual sample/loss records. If useful, open the downloaded file briefly and show the manifest count and SHA-256. Reloading the dashboard should preserve the session, and loading again should reuse it rather than append duplicate samples.

### 4:00-4:30 - Scope and next verification

State clearly: “This proves the dashboard can display one persisted, deterministic synthetic dataset. It does not prove official biosignal-mock compatibility, Raspberry Pi resource limits, physical power-cut durability, five/ten-second deadlines, or two-hour backlog recovery. Those require separate assessment tests.”

## Do not claim

- That the dashboard fixture is MayaCardio's official input dataset.
- That the local FastAPI SQLite database is a deployed remote cloud account.
- That a zero fixture backlog proves live synchronization timing.
- That this dashboard walkthrough replaces the assessment's required failure-demo video.
- That any unperformed hardware, official checker, or performance test passed.
