# Public read-only portfolio demo mode

Use this option only for the Render portfolio deployment that contains synthetic demonstration data. It is intended to let recruiters browse the dashboard without asking for a username and password. Do not enable it for real or private data.

## Render environment variables

Set:

- `DASHBOARD_PUBLIC_READ_ONLY=true`
- `ENABLE_SYNTHETIC_DEMO_SEED=true`
- Keep `CLOUD_API_TOKEN` set to a strong, private value.

Keep `DASHBOARD_USERNAME`, `DASHBOARD_PASSWORD`, and `DASHBOARD_SESSION_SECRET` configured as administrator credentials if you may later return to protected dashboard mode. Do not put any secret values in GitHub or in the README.

## Behavior

- The fixed bundled synthetic fixture is materialized at application startup, including after a free-instance restart.
- Anonymous users can read dashboard data for the portfolio demonstration. The UI identifies itself as a public read-only demo and hides controls that seed or reset demo data.
- Dashboard POST/other write actions are rejected in this mode. Device `/v1/*` operations are rejected after bearer-token validation while public demo mode is enabled, preventing operational samples from entering databases served through anonymous reads. Admin file imports use the separate `ADMIN_DB_PATH` store.
- The mode is not a general public production setting. The dashboard GET endpoints can display database-backed records on the service, so the instance must contain synthetic showcase data only.
- Render free filesystems are ephemeral; the fixture is recreated on startup, but data durability is not proven.

## Enable on Render

1. Open the Render service and select **Environment**.
2. Add `DASHBOARD_PUBLIC_READ_ONLY` with value `true`; verify `ENABLE_SYNTHETIC_DEMO_SEED` is also `true`.
3. Save changes and wait for the new deployment to become **Live**.
4. Open the public dashboard URL in a private/incognito browser window. The dashboard should open without a sign-in form and show the seeded synthetic fixture.
5. Verify that POST requests to demo seed/reset routes return HTTP 403 and that `/v1/*` device API requests are rejected in public demo mode even with a valid bearer token. Admin uploads are available only after administrator sign-in and are stored separately.

To return to protected access, set `DASHBOARD_PUBLIC_READ_ONLY=false` or remove the variable and redeploy.


## Separate administrator workspace

The public demo stays read-only and uses only the fixed synthetic fixture. The site provides an **Admin** route at `/#/admin`; administrator sign-in uses `DASHBOARD_USERNAME`, `DASHBOARD_PASSWORD`, and `DASHBOARD_SESSION_SECRET`. These credentials remain server-side. A valid signed administrator session can use the `/api/admin/*` endpoints even while public demo reads remain enabled.

After signing in, an administrator can import CSV or JSONL/NDJSON sample datasets, inspect sample rows and derived processing windows, and delete an import. Imports use a separate SQLite database configured with `ADMIN_DB_PATH`, for example `/tmp/mayacardio/admin.db` on the portfolio host. This separation prevents administrator imports from appearing in the public synthetic demo.

### Supported input schema

CSV requires `session_id,sensor,index,value_1,value_2,value_3` columns. Sensor 1 rows must have exactly three signed 24-bit integer values; Sensor 2 rows must have exactly two. The optional third value is blank for Sensor 2. An optional `type` column can label rows as `sample`, `loss`, or `manifest`.

JSONL/NDJSON accepts one JSON object per line with `type: "sample"` and fields `session_id`, `sensor`, `index`, `values`, or `type: "loss"` with `session_id`, `sensor`, `from_index`, `to_index`, and `reason`. A `type: "manifest"` object is optional and ignored during import. Repeated sample keys and conflicting session IDs are rejected. Files are limited to 5 MiB and 50,000 sample rows.

The selected source label is a statement supplied by the administrator. Schema checking does not independently prove the data came from a physical sensor or verify clinical accuracy. Do not upload patient-identifying or sensitive real medical data to Render's free service. The free filesystem is ephemeral; persistent storage and a separate security/privacy review are required before use with sensitive or operational data.
