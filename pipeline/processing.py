"""Deterministic one-second statistics and heartbeat processing per assessment rules."""
from __future__ import annotations

import math
from collections import deque
from statistics import mean
from typing import Any

from .db import Database, SAMPLE_RATE

WINDOW_SIZE = 400
HEART_WINDOW_SECONDS = 5
HEART_WINDOW_SAMPLES = WINDOW_SIZE * HEART_WINDOW_SECONDS
PEAK_LOOKBACK = 800


def _round1(value: float | None) -> float | None:
    return None if value is None else round(float(value), 1)


def _channel_stats(samples: dict[int, list[int]], channels: int) -> tuple[list[float | None], list[int | None], list[int | None]]:
    means: list[float | None] = []
    mins: list[int | None] = []
    maxs: list[int | None] = []
    for channel in range(channels):
        values = [row[channel] for row in samples.values()]
        if not values:
            means.append(None)
            mins.append(None)
            maxs.append(None)
        else:
            means.append(_round1(mean(values)))
            mins.append(min(values))
            maxs.append(max(values))
    return means, mins, maxs


def _find_segment_peaks(
    db: Database,
    session_id: str,
    candidate_start: int,
    candidate_end: int,
    prior_peak_index: int | None,
) -> list[int]:
    """Find peaks in a bounded interval, using the preceding 800 samples for each candidate.

    prior_peak_index is a checkpoint from the device's incremental detector. It is
    necessary to keep the 100-sample refractory rule correct while the cloud is
    receiving a new live window ahead of an older synchronization backlog.
    """
    if candidate_end < candidate_start:
        return []
    context_start = candidate_start - PEAK_LOOKBACK
    values_by_index = db.get_samples(session_id, 1, context_start, candidate_end + 1)
    values: list[int | None] = []
    for idx in range(context_start, candidate_end + 2):
        values.append(values_by_index[idx][1] if idx in values_by_index else None)

    # Initialize a monotonic maximum deque and missing counter over candidate_start-800..candidate_start-1.
    maxq: deque[tuple[int, int]] = deque()
    missing = 0
    for idx in range(context_start, candidate_start):
        value = values[idx - context_start]
        if value is None:
            missing += 1
        else:
            while maxq and maxq[-1][1] <= value:
                maxq.pop()
            maxq.append((idx, value))

    last_peak = prior_peak_index
    found: list[int] = []
    for idx in range(candidate_start, candidate_end + 1):
        current = values[idx - context_start]
        previous = values[idx - 1 - context_start]
        following = values[idx + 1 - context_start]
        if (
            missing == 0 and current is not None and previous is not None and following is not None
            and maxq and current > previous and current > following and current > maxq[0][1] / 2
            and (last_peak is None or idx - last_peak >= 100)
        ):
            found.append(idx)
            last_peak = idx
        outgoing_idx = idx - PEAK_LOOKBACK
        outgoing = values[outgoing_idx - context_start]
        if outgoing is None:
            missing -= 1
        if maxq and maxq[0][0] == outgoing_idx:
            maxq.popleft()
        if current is None:
            missing += 1
        else:
            while maxq and maxq[-1][1] <= current:
                maxq.pop()
            maxq.append((idx, current))
    return found


def window_inputs_are_covered(db: Database, session_id: str, window_index: int) -> bool:
    start = WINDOW_SIZE * window_index
    end = start + WINDOW_SIZE - 1
    # One-second statistics only need the samples inside the window. While a live
    # session is running, wait for the next sensor-1 sample so a peak at the final
    # index can be evaluated. At a known session end there is no following sample;
    # the final sample simply cannot qualify as a peak.
    if not db.range_is_covered(session_id, 1, start, end):
        return False
    if not db.is_session_ended(session_id) and not db.range_is_covered(session_id, 1, end + 1, end + 1):
        return False
    if not db.range_is_covered(session_id, 2, start, end):
        return False
    if window_index >= 4:
        heart_start = WINDOW_SIZE * (window_index - 4)
        candidate_start = max(PEAK_LOOKBACK, heart_start - 100)
        context_start = candidate_start - PEAK_LOOKBACK
        heart_end = WINDOW_SIZE * (window_index + 1) - 1
        context_end = heart_end if db.is_session_ended(session_id) else heart_end + 1
        if not db.range_is_covered(session_id, 1, context_start, context_end):
            return False
    return True


def compute_window(
    db: Database,
    session_id: str,
    window_index: int,
    mode: str,
    prior_peak_index: int | None = None,
) -> dict[str, Any] | None:
    """Compute one result only after all relevant indexes are stored or explicitly lost."""
    if mode not in ("online", "offline"):
        raise ValueError("mode must be 'online' or 'offline'")
    if not window_inputs_are_covered(db, session_id, window_index):
        return None

    start = WINDOW_SIZE * window_index
    end = start + WINDOW_SIZE - 1
    samples_1 = db.get_samples(session_id, 1, start, end)
    samples_2 = db.get_samples(session_id, 2, start, end)
    missing_1 = WINDOW_SIZE - len(samples_1)
    missing_2 = WINDOW_SIZE - len(samples_2)

    mean_1, min_1, max_1 = _channel_stats(samples_1, 3)
    mean_2, min_2, max_2 = _channel_stats(samples_2, 2)
    magnitudes = [math.sqrt(row[0] * row[0] + row[1] * row[1]) for row in samples_2.values()]
    magnitude = _round1(mean(magnitudes)) if magnitudes else None

    heart_rate: float | None = None
    if window_index >= 4:
        heart_start = WINDOW_SIZE * (window_index - 4)
        heart_end = WINDOW_SIZE * (window_index + 1) - 1
        heart_samples = db.get_samples(session_id, 1, heart_start, heart_end)
        if len(heart_samples) == HEART_WINDOW_SAMPLES:
            candidate_start = max(PEAK_LOOKBACK, heart_start - 100)
            # If not supplied (e.g. an offline call before a window marker exists), use the local peak ledger.
            if prior_peak_index is None:
                prior_peak_index = db.get_prior_peak(session_id, candidate_start)
            peaks = _find_segment_peaks(db, session_id, candidate_start, heart_end, prior_peak_index)
            # Peaks below heart_start are only refractory context; the formula uses peaks inside the 5 s interval.
            in_window = [p for p in peaks if heart_start <= p <= heart_end]
            if len(in_window) >= 2:
                gaps = [in_window[i] - in_window[i - 1] for i in range(1, len(in_window))]
                mean_gap_samples = mean(gaps)
                if mean_gap_samples > 0:
                    heart_rate = _round1(60.0 * SAMPLE_RATE / mean_gap_samples)

    return {
        "session_id": session_id,
        "window_index": window_index,
        "start_index": start,
        "end_index": end,
        "missing_1": missing_1,
        "missing_2": missing_2,
        "complete": missing_1 == 0 and missing_2 == 0,
        "mean": {"sensor_1": mean_1, "sensor_2": mean_2},
        "min": {"sensor_1": min_1, "sensor_2": min_2},
        "max": {"sensor_1": max_1, "sensor_2": max_2},
        "magnitude": magnitude,
        "heart_rate": heart_rate,
        "mode": mode,
    }


def process_offline_results(db: Database, session_id: str) -> int:
    count = 0
    # Running this incremental detector after sample ingestion preserves global peak state across restarts.
    db.advance_peak_detector(session_id)
    for row in db.unprocessed_offline_modes(session_id):
        result = compute_window(db, session_id, row["window_index"], "offline", row.get("prior_peak_index"))
        if result is not None:
            db.insert_result(session_id, row["window_index"], "offline", result)
            count += 1
    return count


def process_online_results(db: Database, session_id: str | None = None) -> int:
    """Cloud-side calculation for windows explicitly marked online by the device."""
    count = 0
    sessions = [session_id] if session_id else db.get_sessions()
    for current_session in sessions:
        db.advance_peak_detector(current_session)
        for row in db.unprocessed_online_modes(current_session):
            result = compute_window(db, current_session, row["window_index"], "online", row.get("prior_peak_index"))
            if result is not None:
                db.insert_result(current_session, row["window_index"], "online", result)
                count += 1
    return count
