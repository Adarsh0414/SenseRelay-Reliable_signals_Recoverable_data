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
- Dashboard POST/other write actions are rejected in this mode. The `/v1/ingest` API remains protected by `CLOUD_API_TOKEN`.
- The mode is not a general public production setting. The dashboard GET endpoints can display database-backed records on the service, so the instance must contain synthetic showcase data only.
- Render free filesystems are ephemeral; the fixture is recreated on startup, but data durability is not proven.

## Enable on Render

1. Open the Render service and select **Environment**.
2. Add `DASHBOARD_PUBLIC_READ_ONLY` with value `true`; verify `ENABLE_SYNTHETIC_DEMO_SEED` is also `true`.
3. Save changes and wait for the new deployment to become **Live**.
4. Open the public dashboard URL in a private/incognito browser window. The dashboard should open without a sign-in form and show the seeded synthetic fixture.
5. Verify that POST requests to the demo seed/reset routes return HTTP 403 and that ingestion still requires its bearer token.

To return to protected access, set `DASHBOARD_PUBLIC_READ_ONLY=false` or remove the variable and redeploy.
