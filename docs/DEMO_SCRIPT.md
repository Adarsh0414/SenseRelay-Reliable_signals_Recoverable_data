# Five-minute failure-demo script

Use the **official** `biosignal-mock` and a real, persistent cloud deployment for the final recording. The development fixture can help rehearse the commands but does not count as official acceptance evidence. Video limit: five minutes.

## Before recording

- Confirm that the device is ARM64 Linux and stays within 4 CPU cores / 2 GB RAM for the mock + pipeline.
- Start the cloud API on a separate free-tier service/VM with persistent storage and an authenticated HTTPS endpoint.
- Start the official mock exactly as specified in the assessment.
- Start `pipeline run`, and have a second terminal ready for the CLI commands.
- Keep the assessment's `check_ground_truth` tool available. Its command line was not present in the uploaded document, so use the instructions distributed with that tool.

## Timeline

### 0:00-0:40 - Show normal online acquisition

```bash
pipeline status
pipeline db-check
```

Explain that rows are committed to the device database before synchronization. Show cloud health and one or two online result lines:

```bash
pipeline results --session '<SESSION_ID>' | head -n 3
```

### 0:40-1:45 - Cut the network to the cloud

For a local Compose rehearsal, from another terminal run:

```bash
docker compose -f compose.demo.yml pause cloud
```

On the real device, use the approved network-disconnection method for your environment; do not block the mock connection, only the cloud route. Show that `pipeline status` changes to `offline`, collection continues, backlog rises, and offline window results appear locally. Keep the outage brief in the video; perform the separate two-hour test for the evidence log.

### 1:45-2:35 - Restore the cloud connection

For the local Compose rehearsal:

```bash
docker compose -f compose.demo.yml unpause cloud
```

On the real setup, remove the network block. Show mode returning to `online`, backlog decreasing, and cloud status/results catching up. Save the status output and cloud result timestamps.

### 2:35-3:25 - Kill the pipeline process

Stop the pipeline forcefully with `kill -9 <PIPELINE_PID>` on Linux (or the equivalent process-kill command), then restart `pipeline run` using the **same database path**. Show that old sample keys remain present and collection resumes from the saved watermark. Run `pipeline db-check` and compare the export/checker output before and after.

### 3:25-4:25 - Demonstrate a physical power interruption

This step must be performed on the Raspberry Pi hardware used for final validation. With the mock and pipeline running, disconnect power as the assessment requires, restore power, restart the mock/pipeline per the test setup, and show the integrity check and loss ledger. Do not substitute a process kill for this step or label an unperformed test as passed. Preserve logs, exported data, and the stated loss bound.

### 4:25-5:00 - Final evidence snapshot

Show these artifacts in the repository:

- `device-export.jsonl` and `cloud-export.jsonl`;
- `results.jsonl` and `pipeline db-check` output;
- `docs/TEST_EVIDENCE.md` updated with the exact test date, environment, result, and checker output;
- `docs/resource_measurements.csv` from the full one-hour run;
- the official ground-truth comparison summary.

## Do not claim in the video unless verified

Do not claim a successful physical power-cut test, ARM64 resource compliance, zero loss under all possible failures, or a two-hour recovery within 15 minutes until the corresponding measured test has actually passed.
