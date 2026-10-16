# Admin dataset workspace

The site has two deliberately separate experiences:

- **Public portfolio demo** (`/#/dashboard`): anonymous, read-only, and populated with the deterministic synthetic fixture.
- **Administrator workspace** (`/#/admin`): requires the configured dashboard username/password and a valid server-signed session. It imports datasets into a separate `ADMIN_DB_PATH` SQLite database.

This admin workspace is for schema-conforming engineering dataset inspection. It is not a live sensor console, a clinical tool, or proof of sensor provenance. The source category is self-reported in the upload form and is not independently verified.

## Render settings

For the portfolio deployment, set the following environment variables in Render:

```text
DASHBOARD_PUBLIC_READ_ONLY=true
ENABLE_SYNTHETIC_DEMO_SEED=true
ADMIN_DB_PATH=/tmp/mayacardio/admin.db
DASHBOARD_USERNAME=<private administrator username>
DASHBOARD_PASSWORD=<unique password of at least 12 characters>
DASHBOARD_SESSION_SECRET=<independent random secret of at least 32 characters>
DASHBOARD_COOKIE_SECURE=true
CLOUD_API_TOKEN=<independent private ingestion token>
```

Generate secrets locally if needed:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Use a distinct random value for each secret. Never commit real values to Git, add them to the README, or share them in screenshots. If a secret has appeared in an image or chat, rotate it.

In public-demo mode, `/v1/*` device API operations are intentionally rejected even when a valid bearer token is presented. This stops operational records entering database tables that anonymous dashboard reads can expose. Administrator file imports are stored separately. For an actual device-to-cloud system, use a separate protected deployment with public-demo mode disabled and durable storage rather than weakening this safety boundary.

## Uploading a dataset

1. Open `/#/admin` and sign in using the administrator credentials above.
2. Enter a dataset name and optional context description.
3. Choose an honest source label: hardware/collector export, external dataset mapped to the schema, or synthetic test dataset.
4. Download the CSV template or select a supported `.csv`, `.jsonl`, or `.ndjson` file.
5. Import it, then inspect the listed sessions to preview sample rows and results.

Limits: 5 MiB per file and 50,000 sample rows. Files with unsupported schemas, duplicate `(session_id, sensor, index)` keys, conflicting session IDs, non-integer values, or out-of-range channel values are rejected. An administrator can delete an imported dataset from the workspace.

### CSV format

Required columns are `session_id,sensor,index` and either a JSON-array `values` column or individual `value_1,value_2` columns. `value_3` is required for Sensor 1 and should be blank for Sensor 2. The downloadable template uses:

```csv
session_id,sensor,index,value_1,value_2,value_3
bench-session-001,1,0,100,101,102
bench-session-001,2,0,200,201,
```

Sensor 1 rows require exactly three signed 24-bit integer values; Sensor 2 rows require exactly two. Sample indexes are non-negative integers. A CSV `type` column can optionally identify `sample`, `loss`, or `manifest` rows.

### JSONL / NDJSON format

Store one JSON object per line. A sample object can look like:

```json
{"type":"sample","session_id":"bench-session-001","sensor":1,"index":0,"values":[100,101,102]}
{"type":"sample","session_id":"bench-session-001","sensor":2,"index":0,"values":[200,201]}
```

Loss objects use `type: "loss"`, `session_id`, `sensor`, `from_index`, `to_index` (nullable), and `reason`. An optional `type: "manifest"` record is accepted and ignored for sample processing.

## Storage and safety limits

- Admin imports are isolated from the public demo fixture and public dashboard database.
- The app validates the schema and calculates results using the existing processing engine; it does not verify whether a file truly came from hardware or whether resulting values are clinically accurate.
- Do not upload patient-identifying or sensitive medical data to this portfolio service.
- Render Free has an ephemeral filesystem. `/tmp/mayacardio/admin.db` can be lost on restart or redeploy. This feature demonstrates upload and inspection, not durable production data storage.
- Do not claim uploaded data is live sensor data unless its origin and acquisition path are established separately.
