# Verification evidence and open acceptance tests

**Status:** local software verification completed; official assessment-environment verification remains outstanding.

## Tests executed in the package environment

Command:

```bash
pytest -q
```

Latest local Python run after dashboard API/security changes: **31 tests passed** (Python 3.13.5, pytest 9.0.2). Coverage includes:

- exact-wire CRC verification (including whitespace-sensitive JSON array text);
- protocol-compatible development fixture response shape;
- recovery from CRC-corrupt replies, duplicate replies, and a mock session restart with an unknown old tail;
- collection of both sensors into the device database;
- idempotent sample insertion, conflict detection, and preservation of the first received value;
- contiguous watermark behavior and finite loss ranges;
- recovered samples being removed from a prior loss range;
- overlapping loss reports being reduced to non-overlapping index ranges;
- reporting unknown tails with `to_index: null`;
- first-window statistics, missing counts, and sensor-2 magnitude;
- specified five-second heart-rate rule for a deterministic synthetic trace;
- null heart rate when the five-second sensor-1 range contains a missing sample;
- offline result assignment and recovery of unacknowledged online windows during an outage;
- final-window outputs after a known session end without a lookahead sample; and
- authenticated, idempotent cloud ingestion and online result production.

## Local end-to-end smoke test

Environment: local non-ARM development container; development-only synthetic mock; FastAPI cloud service; five-second run with development mock speed set to 4×. This is reproducible integration evidence, not final acceptance evidence.

Latest local smoke run observation:

| Check | Observation |
|---|---:|
| Device sample rows | 13,894 |
| Cloud sample rows | 13,894 |
| Explicit loss records | 0 |
| Online window results in cloud | 17 |
| Runtime mode at stop | online |
| Device/cloud sample row equality | Exact match on `(session_id, sensor, index, values)` for all 13,894 rows |
| Device SQLite `integrity_check` | `ok` |
| Cloud SQLite `integrity_check` | `ok` |
| CLI status | `{"mode":"online","samples_saved":13894,"samples_in_cloud":13894,"backlog":0,"sessions":1}` |

Counts can vary with timing and do not establish the assessment's throughput or deadline requirements. The run did not use MayaCardio's official mock, a Raspberry Pi 4, a production free-tier cloud account, or a physical power cut.

## Local online/offline recovery smoke test

Environment: local non-ARM development container; development-only mock running at 4× synthetic time; cloud API process stopped for approximately two seconds and then restarted. This confirms basic functional recovery, but the transition times were not instrumented against the assessment clock and therefore are not formal deadline evidence.

| Check | Observation |
|---|---:|
| Device sample rows after recovery | 27,162 |
| Cloud sample rows after recovery | 27,162 |
| Exact device/cloud `(session_id, sensor, index, values)` equality | Yes |
| Device/cloud loss rows | 0 / 0 |
| Device results during/after offline interval | 16 offline results |
| Cloud results | 17 online and 16 offline results |
| Sample backlog after recovery | 0 |
| Device/cloud SQLite `integrity_check` | `ok` / `ok` |
| Mode observation | Offline while cloud was unavailable; online after restart |

This is evidence of local offline processing and catch-up only. It does not establish the 10-second switching bound, 5-second online-result bound, two-hour outage performance, or resource limits on ARM64.

## Required tests still to run on the official environment

| Assessment item | Required evidence | State |
|---|---|---|
| Every received sample exists exactly once on device | Official `check_ground_truth` comparison against `pipeline export --from device` | Not run: official checker/mock not in uploaded files |
| No silent loss / unchanged values | Official ground-truth export comparison | Not run |
| Process kill and restart | Before/after exports, SQLite integrity check, logs | Unit/smoke tests only; real Pi test outstanding |
| Physical power cut | Real Raspberry Pi power interruption; exact lost ranges and actual bound | Not run |
| Cloud result visible within five seconds | Recorded timestamps for consecutive online windows against live cloud | Not yet timed formally |
| Mode switch within ten seconds | Timestamped network cut/restore and mode log | Not yet timed formally |
| Two-hour outage catch-up within 15 minutes | Recorded outage/restoration times and cloud ground-truth comparison | Not run |
| ARM64 <= 4 CPU cores / 2 GB RAM | Device-side resource cap and one-hour resource report | Not run |
| One-hour metrics | `scripts/measure_resources.py` CSV, average CPU, peak RSS, disk writes, network sent | Not run |
| Five-minute demo video | Video showing network cut, process kill, and physical power cut | Not recorded |

Before submission, replace this status with the exact date, device model/architecture, kernel, cloud tier, mock command, session ID, duration, result, checker summary, and evidence filenames. Do not mark a row as passed without logs or a reproducible artifact.


## Website and dashboard verification status

Additional backend security regression tests verify that API docs, ReDoc, and the OpenAPI schema are disabled by default in production and can be explicitly enabled with `ENABLE_API_DOCS=true`. Dashboard API tests cover local-only development access, signed browser sessions, invalid credentials, origin rejection, fail-closed partial configuration, cloud-token requirements, and synthetic-fixture access controls.

Implemented website source includes a React/TypeScript/Vite landing page and dashboard, session/result/integrity/resource views, favicon SVG/ICO/PNG assets, Apple touch icon, manifest, Open Graph image, page metadata, robots/sitemap generation, and API-backed data states. Python dashboard API tests cover local-only development mode, the separate signed dashboard cookie, invalid credentials, origin rejection, partial-auth fail-closed behavior, baseline security headers, and remote ingestion rejection when the cloud token is not configured.

**Frontend build verification is outstanding in this authoring environment.** `npm install` could not finish because the environment could not resolve `registry.npmjs.org`. TypeScript sources were syntax-transpiled for parse errors, but that is not a substitute for `npm run typecheck`, `npm test`, or `npm run build`. Run those commands from `frontend/` on a machine with npm registry access before calling the website build complete. The project ZIP does not contain a generated `frontend/dist/` or an npm lockfile; `npm install` and `npm run build` generate these on the target machine.


## Persistent dashboard fixture verification

The deterministic presentation fixture is loaded only when the operator explicitly selects the dashboard's **Load demo dataset** action (or the Settings & help equivalent). The checked-in source is `data/fixtures/synthetic_demo_seed7.jsonl`; the API validates it, writes the runtime JSONL copy, and stores the same records in both SQLite databases. It is separate from the official sensor-mock collector path.

Validated by `tests/test_dashboard_api.py`:

- Fixed session ID `maya-demo-seed7-v1` and seed `7`;
- a checked-in JSONL source with a manifest containing counts, parameters, controlled gap details, notice, and SHA-256 of the data records;
- 23,960 sample rows persisted to both device and cloud stores: 12,000 Sensor 1 and 11,960 Sensor 2;
- one explicitly recorded Sensor 2 loss range, indexes 4,800-4,839;
- 30 processed one-second windows, with 27 online and 3 offline results in the cloud result ledger; the device stores the three offline results;
- window 12 is incomplete and reports `missing_2=40`, and window 4 produces the expected seeded-trace heart-rate result of 60.0 bpm;
- the JSONL source samples match every `(sensor, index, values)` tuple stored in both SQLite databases;
- repeating the seed operation is idempotent, the stored JSONL SHA-256 is checked before reuse, and a missing source file can be reconstructed from the complete persisted cloud rows;
- JSONL download works and reset removes only the fixed synthetic demo session, preserving an unrelated session;
- demo fixture operations are enabled by default only in development/test environments and unavailable by default in production or staging.

Latest test run after adding the fixture tests: `python -m pytest -q` - **31 passed**. This is Python/backend evidence only. The frontend dependencies could not be installed in the authoring container due to an npm registry timeout, so a complete frontend typecheck, lint, Vitest run, audit, production build, and browser-level verification remain to be run on the Windows workstation. The fixture does not substitute for official assessment validation.


## Website polish pass

- The Python suite was rerun after the shared theme, fixed viewport shell, draggable PWA install control, service worker, and dash-normalization changes: `python -m pytest -q` reported 31 passing tests.
- `frontend/public/sw.js` passes Node's JavaScript syntax check. The web manifest and required favicon/PWA image assets are present. A recursive UTF-8 text scan found no em dash or en dash characters.
- The full frontend dependency install, type-check, lint, Vitest run, vulnerability audit, production bundle, and browser-level interaction checks could not be completed in the authoring environment because `npm install` timed out while reaching the npm registry. Run these from the frontend folder on the Windows workstation before publishing this revision.
- PWA install prompting remains browser-dependent. The homepage control opens the native prompt when available and otherwise explains the browser's install menu. Service-worker caching intentionally excludes API responses.
