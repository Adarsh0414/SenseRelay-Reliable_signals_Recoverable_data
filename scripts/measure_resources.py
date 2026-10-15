#!/usr/bin/env python3
"""Measure a running Linux device process for the assessment's one-hour report.

CPU and RSS are for the pipeline process. Disk bytes are the process's OS-reported
write_bytes. Network bytes sent are interface counters for non-loopback/non-container
interfaces, so run on a dedicated device to minimize unrelated traffic.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

try:
    import psutil
except ImportError:
    print("Install the measurement dependency first: pip install psutil", file=sys.stderr)
    raise SystemExit(2)


def net_sent_bytes(interface: str | None = None) -> int:
    counters = psutil.net_io_counters(pernic=True)
    total = 0
    for name, counter in counters.items():
        if interface:
            if name != interface:
                continue
        elif name == "lo" or name.startswith(("docker", "br-", "veth", "virbr")):
            continue
        total += int(counter.bytes_sent)
    return total


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=int, required=True, help="PID of the pipeline process")
    parser.add_argument("--duration", type=float, default=3600, help="measurement duration in seconds")
    parser.add_argument("--interval", type=float, default=1.0, help="sample interval in seconds")
    parser.add_argument("--output", default="docs/resource_measurements.csv")
    parser.add_argument("--interface", default=None, help="optional network interface name, e.g. eth0 or wlan0")
    args = parser.parse_args()
    if args.duration <= 0 or args.interval <= 0:
        parser.error("duration and interval must be positive")

    try:
        proc = psutil.Process(args.pid)
        proc.cpu_percent(interval=None)  # warm-up baseline
        baseline_io = proc.io_counters()
        baseline_write = int(getattr(baseline_io, "write_bytes", 0))
        baseline_net = net_sent_bytes(args.interface)
    except (psutil.NoSuchProcess, psutil.AccessDenied) as exc:
        print(f"Cannot inspect PID {args.pid}: {exc}", file=sys.stderr)
        raise SystemExit(2)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    cpu_values: list[float] = []
    peak_rss = 0
    last_write = baseline_write
    last_net = baseline_net
    records = 0
    cores = max(1, psutil.cpu_count(logical=True) or 1)

    try:
        with output.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=[
                "elapsed_seconds", "process_cpu_pct_one_core", "process_cpu_pct_device_capacity",
                "rss_bytes", "process_write_bytes_cumulative", "non_loopback_network_sent_bytes_cumulative",
            ])
            writer.writeheader()
            while True:
                elapsed = time.monotonic() - start
                if elapsed >= args.duration:
                    break
                time.sleep(min(args.interval, max(0, args.duration - elapsed)))
                try:
                    cpu_one_core = float(proc.cpu_percent(interval=None))
                    memory = int(proc.memory_info().rss)
                    io = proc.io_counters()
                    last_write = int(getattr(io, "write_bytes", 0))
                    last_net = net_sent_bytes(args.interface)
                except (psutil.NoSuchProcess, psutil.AccessDenied) as exc:
                    print(f"Measurement stopped because PID {args.pid} is no longer readable: {exc}", file=sys.stderr)
                    break
                cpu_values.append(cpu_one_core / cores * 100.0)
                peak_rss = max(peak_rss, memory)
                records += 1
                writer.writerow({
                    "elapsed_seconds": round(time.monotonic() - start, 3),
                    "process_cpu_pct_one_core": round(cpu_one_core, 3),
                    "process_cpu_pct_device_capacity": round(cpu_one_core / cores * 100.0, 3),
                    "rss_bytes": memory,
                    "process_write_bytes_cumulative": last_write,
                    "non_loopback_network_sent_bytes_cumulative": last_net,
                })
                file.flush()
    except KeyboardInterrupt:
        print("Measurement interrupted early; summary represents only the recorded interval.", file=sys.stderr)

    elapsed_seconds = time.monotonic() - start
    summary = {
        "pid": args.pid,
        "measurement_seconds": round(elapsed_seconds, 2),
        "samples": records,
        "average_cpu_pct_device_capacity": round(sum(cpu_values) / len(cpu_values), 3) if cpu_values else None,
        "peak_rss_mb": round(peak_rss / 1024 / 1024, 3),
        "process_disk_bytes_written_mb": round(max(0, last_write - baseline_write) / 1024 / 1024, 3),
        "non_loopback_network_sent_mb": round(max(0, last_net - baseline_net) / 1024 / 1024, 3),
        "network_interface": args.interface or "all non-loopback/non-container interfaces",
        "csv": str(output),
        "note": "Network counters are system interface counters; run on a dedicated device for clean measurements.",
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
