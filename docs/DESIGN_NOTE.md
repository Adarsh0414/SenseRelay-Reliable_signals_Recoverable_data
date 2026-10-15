# Design note - Never Lose a Heartbeat

## Architecture

The device runs the unmodified `biosignal-mock` and a Python collector on ARM64 Linux. The collector alternates requests for sensors 1 and 2 over the mock's newline-delimited JSON/TCP interface. It verifies the supplied CRC-32 against the exact wire text for the `data` array and validates the sample count, sensor identity, channel count, integer types, and signed 24-bit range. The collector requests a specific starting index, making an uncommitted reply re-readable after a process restart while it remains in the mock's buffer.

Accepted rows are written to a local SQLite database with WAL journaling, `synchronous=FULL`, primary keys `(session_id, sensor, sample_index)`, and explicit transactions. The device is authoritative for received samples; cloud connectivity does not gate acquisition. The cloud API stores each sample under the same idempotency key. An acknowledged local upload is marked only after an HTTP success response; a timeout can cause a replay, which is handled idempotently.

When connected, the device marks ready windows `online` and synchronizes samples, loss records, and window markers to a persistent cloud service. Cloud code calculates the online result. When disconnected or an upload fails, the device marks ready windows `offline`, computes the same result locally, and retains all unacknowledged data. Synchronization gives recent samples high priority to meet live-result deadlines and also advances the oldest backlog every cycle. Explicit finite loss intervals can advance a contiguous watermark; an unknown session tail (`to_index: null`) is recorded but does not imply an infinite sequence of known-missing samples.

## Processing

Window `w` is the sample interval `[400w, 400w+399]`. Missing counts are 400 minus the number of stored sample rows in that sensor/window. `complete` is true only when both counts are zero. Means, minima, and maxima are computed channel-by-channel over available rows; empty channel input produces `null`. Sensor-2 magnitude is the mean of `sqrt(ch1^2 + ch2^2)` over available sensor-2 rows. Decimal outputs are rounded to one decimal place.

For heart rate, the implementation first requires `w >= 4` and all 2,000 sensor-1 samples in the defined five-second window. A peak requires the previous 800 samples and following sample to be available, a strict local maximum, a value greater than half the preceding-800 maximum, and at least 100 samples since the previous accepted peak. Two or more peaks produce `60 * 400 / mean_peak_gap_samples`; otherwise heart rate is `null`.

## Guarantees and limitations

- **Application-level duplicate protection:** one stored row per sensor/index/session; conflicting repeated values are logged and never overwrite the first value.
- **Process-crash recovery:** previously committed local transactions survive a process kill. Restarted collection resumes from the durable contiguous watermark and asks the mock to re-read that index.
- **Power interruption:** the declared target is **no more than 10 seconds of sample-index loss per sensor**, based on the mock's ten-second unread buffer, assuming acquisition stops at the power cut, the device resumes promptly, and the platform honors SQLite sync requests. The exact tail of an old mock session may be unknowable after restart; the program reports that honestly with `to_index: null`. This bound is an engineering target and **has not yet been validated by pulling power on a Raspberry Pi 4**.
- **Cloud synchronization:** when the free cloud endpoint is reachable and has sufficient throughput/storage, acknowledged rows are durable in its persistent database. A two-hour catch-up within 15 minutes requires measured throughput of roughly 6,400 sample rows per second on average (2 sensors × 400 samples/second × 7,200 seconds = 5,760,000 rows; divided by 900 seconds = 6,400 rows/second), plus losses, modes, and processing. The target must be verified with the actual cloud allocation.
- **Known limitation:** if the official mock loses an unread range and its report does not identify a finite range, exact end boundaries may be unavailable; no synthetic values are invented to fill that gap. Any samples rejected due to invalid CRC remain unaccepted until re-read; persistent unavailability is logged and must become an explicit reported loss.

## Resource use

The device service itself is pure Python plus SQLite and has no mandatory numerical-library dependency. The collector commits small batches and the peak detector advances incrementally. One-hour average CPU, peak RSS, storage writes, and outbound network bytes must be measured on the ARM64 environment used for judging; the repository includes `scripts/measure_resources.py` to collect these figures. Local x86 demo measurements are not evidence of Raspberry Pi resource compliance.
