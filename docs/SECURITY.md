# Security Notes - MayaCardio Signal Operations

## Scope

This project is an engineering demonstration using synthetic sensor data. It is not a medical device and is not intended for diagnosis, treatment, patient care, or emergency monitoring. No regulatory or privacy-compliance certification is claimed.

## Credential boundaries

- `CLOUD_API_TOKEN` authenticates device-to-cloud ingestion. React never reads or embeds this token.
- `DASHBOARD_USERNAME`, `DASHBOARD_PASSWORD`, and `DASHBOARD_SESSION_SECRET` protect browser sessions for normal remote deployments.
- `DASHBOARD_PUBLIC_READ_ONLY=true` is an optional portfolio-only mode for a deployment containing synthetic demo data only. It permits anonymous GET access to dashboard routes, rejects dashboard write actions, and requires `ENABLE_SYNTHETIC_DEMO_SEED=true`; do not enable it if real or private records can enter the dashboard databases.
- Dashboard sessions use an HMAC-signed cookie with an eight-hour expiry, `HttpOnly`, `SameSite=Strict`, and `Secure` when HTTPS is used or explicitly configured.
- Credentials are read by the backend from environment variables. Partial configuration fails closed. If dashboard credentials are entirely absent, dashboard data routes allow loopback clients only for local development.
- If `CLOUD_API_TOKEN` is absent, ingestion is allowed only from loopback clients; remote ingestion fails closed with a configuration error.

Generate a session secret using:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Use a distinct random value for `CLOUD_API_TOKEN`. Never commit actual secret values.

## Browser/API protections implemented

- Dashboard data routes use a dedicated dashboard-access dependency.
- Device-to-cloud bearer credentials and browser dashboard cookies are separate.
- Login validates the browser origin when an `Origin` header is present and failed login attempts are rate-limited in process memory.
- Dashboard session cookies are HttpOnly and SameSite Strict. Set `DASHBOARD_COOKIE_SECURE=true` for public HTTPS deployments.
- API responses receive Content Security Policy, `X-Content-Type-Options`, `X-Frame-Options`, Referrer Policy, and Permissions Policy headers. HSTS is emitted when FastAPI sees an HTTPS request.
- Query parameters are constrained; SQL queries use bound parameters; session results and sample outputs have bounded result sizes.
- React renders API-supplied text as text and does not inject it as raw HTML.
- Remote cloud ingestion fails closed if `CLOUD_API_TOKEN` is missing.

## Required production controls

Before exposing an instance publicly:

1. For a protected deployment, configure all dashboard credentials. For a portfolio demo, enable `DASHBOARD_PUBLIC_READ_ONLY=true` only when all dashboard data is synthetic and set `ENABLE_SYNTHETIC_DEMO_SEED=true`; do not share dashboard credentials in the public README. In both modes use a strong, independent cloud-ingestion token.
2. Terminate HTTPS at a trusted reverse proxy and set `DASHBOARD_COOKIE_SECURE=true`.
3. Restrict inbound ports to the reverse proxy and required administration channels.
4. Keep SQLite files and backups outside public web roots, on persistent storage with controlled permissions.
5. Configure backups, retention, monitoring, dependency updates, secret scanning, and incident response.
6. Add a proxy/shared rate limiter if running multiple workers. The built-in login limiter is process-local and is not shared between instances.
7. Review trusted proxy and forwarded-header configuration before relying on scheme detection.
8. Run dependency vulnerability scanning and a formal security review before production use.
9. Set `APP_ENV=production` before a public deployment. API docs, ReDoc, and the OpenAPI schema are disabled in production by default; set `ENABLE_API_DOCS=true` only after an intentional exposure review.
10. Do not ingest real patient data into this student demonstration.

## Known limitations

- The built-in login rate limiter is process-local.
- A production secrets manager is preferable to environment variables.
- The project has not undergone an independent penetration test or formal security certification.
- Host metrics describe the API process host, not necessarily the Raspberry Pi.
- The Vite development server is for localhost use and must not be exposed publicly.


## Frontend dependency handling

- Direct frontend dependencies are version-pinned in `frontend/package.json` to make the first install predictable. Generate and commit `frontend/package-lock.json` after a successful `npm install`; use `npm ci` for later clean installs and CI.
- Run `npm run audit` from `frontend/` and review remediation rather than blindly applying dependency overrides.
- The Vite development server binds to `127.0.0.1` and is not a production web server. Production deployments should serve the generated static build from FastAPI or a trusted static host behind the intended security boundary.
- Frontend source maps are disabled for production builds. Verify that no environment variable prefixed with `VITE_` contains any secret, because Vite embeds such variables into browser code.


## Synthetic demo fixture endpoint safety

The dashboard-only fixture creates a predictable synthetic session and is useful for presentation. In normal mode, its seed, reset, status, and download endpoints require dashboard access; mutating POST requests validate origin. In `DASHBOARD_PUBLIC_READ_ONLY=true` mode, startup seeds the deterministic fixture, anonymous dashboard GET routes are allowed, and dashboard write requests are rejected. This mode requires `ENABLE_SYNTHETIC_DEMO_SEED=true` and is safe only while the deployment contains synthetic demonstration records exclusively. Device ingestion continues to require `CLOUD_API_TOKEN`. Generated JSONL and SQLite files are runtime data and should not be committed to Git.
