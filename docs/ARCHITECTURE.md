# Architecture and invariants

## Components

1. **TCP collector (`pipeline.collector`, `pipeline.mock_client`)** talks to `biosignal-mock` using newline-delimited JSON. It checks the CRC against the exact on-wire bytes of the `data` array, validates channel shape and signed 24-bit values, and uses the requested sample index to re-read uncommitted/gap data.
2. **Device SQLite store (`pipeline.db`)** is authoritative for data received by the device. A sample is keyed by `(session_id, sensor, sample_index)`. Identical duplicates are ignored; conflicting values are logged and the original is retained. Explicit gaps are recorded in `losses`; the contiguous watermark advances only through a stored sample or a finite loss interval.
3. **Incremental peak detector** uses a sliding maximum over the previous 800 samples, tracks missing samples, and persists its cursor and most recent valid peak so restarts do not require scanning the session from the beginning.
4. **Window-mode ledger** records whether a ready one-second window is to be processed online or offline. The device finalizes offline windows locally and sends them on reconnect. A small previous-peak checkpoint lets the cloud evaluate recent live windows even while old offline backlog data is being synchronized.
5. **Cloud ingestion API (`pipeline.cloud_app`)** is an idempotent FastAPI service with a persistent SQLite database. It stores samples and losses before computing online-mode results. In production, set a high-entropy `CLOUD_API_TOKEN`, use HTTPS, and store the cloud DB on persistent storage.
6. **CLI (`pipeline.cli`)** implements the required commands and prints JSON Lines for machine-checkable exports and results.

## Invariants

- A committed sample row is never overwritten by a duplicate key.
- Cloud upload happens only after a local transaction commits. A lost HTTP acknowledgement may cause a replay, which is safe because cloud insertion is idempotent.
- A result is not computed until every required input index is either present in `samples` or explicitly accounted for by a finite `losses` range.
- An unbounded loss (`to_index: null`) documents an unknown tail after a mock restart but does not falsely advance the contiguous watermark.
- Device offline results are uploaded separately from samples; the cloud retains a valid existing online result if an ambiguous retry later presents a conflicting offline result.
- Wall-clock time is observational metadata only. Sample index is the ordering source of truth.

## Important distinction for live results during catch-up

After a long outage, cloud ingestion must prioritize recent live data while also sending the oldest backlog. Otherwise the cloud might have to ingest millions of older rows before seeing a current window. Recent online windows carry a checkpoint (the last previously detected peak before the required local detection segment); cloud code still checks the samples, availability, 800-sample threshold, neighbouring samples, refractory interval, and five-second heart-rate formula. This supports current result deadlines while backlog synchronization proceeds. When all older data is synchronized, the local peak ledger and cloud outputs can be cross-checked.

## Durability boundary

SQLite is opened in WAL mode with `synchronous=FULL`; the collector commits each received batch before proceeding to cloud upload. This protects committed transactions only if the filesystem, storage device, and platform correctly honor synchronization requests. No software can guarantee persistence if storage lies about `fsync`, the disk fails, or the database volume is lost. We do not describe untested power-loss behavior as proven.

## Website and dashboard boundary

The React/TypeScript website in `frontend/` is a read-only observer for operational state. During development, Vite runs on loopback port 5173 and proxies `/api`, `/health`, `/docs`, and `/openapi.json` to FastAPI. In a production build, `npm run build` produces `frontend/dist/`; FastAPI mounts that static build when its `index.html` exists. Hash-based client routing keeps client views separate from FastAPI's `/docs` development API-reference path.

The browser calls `/api/dashboard/*` endpoints for bounded summaries, sessions, window results, loss records, integrity events, and API-host resource snapshots. If the API cannot access the device database, those device-side values remain unavailable rather than being inferred from cloud counts. Resource snapshots describe the API host, not automatically the Raspberry Pi.

Dashboard browser access is deliberately distinct from device ingestion. `CLOUD_API_TOKEN` is used by device-to-cloud ingestion and is never embedded in the frontend. When remote dashboard authentication is configured, the backend issues an expiring HMAC-signed `HttpOnly`, `SameSite=Strict` cookie. With no dashboard credentials, the dashboard endpoints permit loopback development access only. A partial dashboard-auth configuration fails closed. Public deployments require HTTPS, strong server-side credentials, a persistent protected database location, restricted inbound ports, and review of proxy/header configuration.

The default development environment exposes FastAPI's interactive docs. Set `APP_ENV=production` to disable `/docs`, `/redoc`, and `/openapi.json` unless `ENABLE_API_DOCS=true` is intentionally configured. The frontend's `VITE_API_DOCS_ENABLED` build flag should be set to `false` when using that production default, so the UI does not show an unavailable API-reference link.


## Persistent deterministic website fixture

The monitoring UI can be populated without leaving placeholder counters in the frontend. When explicitly requested in local development, `pipeline.demo_dataset` creates a fixed seed-7 synthetic session and persists its JSONL source to `data/synthetic_demo_dataset.jsonl`. The same sample and loss rows are inserted into the local device SQLite and cloud SQLite stores; the shared processing engine creates window results based on those records. Later dashboard requests read session counts, results, and loss events through the normal FastAPI read endpoints. The seed operation is idempotent, checks the JSONL manifest hash, and has a reset operation limited to its fixed demo session. This is only a dashboard presentation fixture, separate from live collection and not official acceptance evidence; fixture mutation is enabled by default only in development/test environments.
