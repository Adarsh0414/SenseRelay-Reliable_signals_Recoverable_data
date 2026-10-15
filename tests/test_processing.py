from __future__ import annotations

from pipeline.db import Database
from pipeline.processing import compute_window, process_offline_results


def _sample_rows(session: str, sensor: int, start: int, end: int, missing: set[int] | None = None):
    missing = missing or set()
    out = []
    for i in range(start, end + 1):
        if i in missing:
            continue
        if sensor == 1:
            v = 1000 if i in (800, 1200, 1600, 2000) else 10
            # Make neighboring samples around the peak lower, avoiding a plateau.
            out.append({"session_id": session, "sensor": 1, "index": i, "values": [int(v * 0.6), v, int(v * 1.3)]})
        else:
            out.append({"session_id": session, "sensor": 2, "index": i, "values": [3, 4]})
    return out


def test_first_window_stats_and_missing_counts(tmp_path):
    db = Database(str(tmp_path / "device.db"))
    db.add_samples(_sample_rows("s", 1, 0, 400))
    db.add_samples(_sample_rows("s", 2, 0, 399, missing={2, 3, 4}))
    db.add_losses([{"session_id": "s", "sensor": 2, "from_index": 2, "to_index": 4, "reason": "test_missing"}])
    result = compute_window(db, "s", 0, "offline")
    assert result is not None
    assert result["missing_1"] == 0
    assert result["missing_2"] == 3
    assert result["complete"] is False
    assert result["magnitude"] == 5.0
    assert result["heart_rate"] is None
    assert result["mean"]["sensor_2"] == [3.0, 4.0]


def test_heart_rate_uses_the_specified_five_second_peak_rule(tmp_path):
    db = Database(str(tmp_path / "device.db"))
    db.add_samples(_sample_rows("s", 1, 0, 2000))
    db.add_samples(_sample_rows("s", 2, 0, 1999))
    result = compute_window(db, "s", 4, "offline")
    assert result is not None
    assert result["heart_rate"] == 60.0
    assert result["complete"] is True


def test_heart_rate_is_null_if_any_sensor1_sample_in_five_second_range_is_missing(tmp_path):
    db = Database(str(tmp_path / "device.db"))
    db.add_samples(_sample_rows("s", 1, 0, 2000, missing={1000}))
    db.add_losses([{"session_id": "s", "sensor": 1, "from_index": 1000, "to_index": 1000, "reason": "corrupt_packet"}])
    db.add_samples(_sample_rows("s", 2, 0, 1999))
    result = compute_window(db, "s", 4, "offline")
    assert result is not None
    assert result["heart_rate"] is None
    assert result["complete"] is True  # complete describes the one-second window only.


def test_ready_offline_windows_are_saved_with_mode(tmp_path):
    db = Database(str(tmp_path / "device.db"))
    db.add_samples(_sample_rows("s", 1, 0, 800))
    db.add_samples(_sample_rows("s", 2, 0, 799))
    assert db.assign_ready_windows("s", "offline") == 2
    assert process_offline_results(db, "s") == 2
    results = db.results_for_session("s")
    assert len(results) == 2
    assert {r["mode"] for r in results} == {"offline"}


def test_final_complete_window_is_emitted_when_session_ends_without_lookahead(tmp_path):
    db = Database(str(tmp_path / "device.db"))
    db.add_samples(_sample_rows("s", 1, 0, 399))
    db.add_samples(_sample_rows("s", 2, 0, 399))
    db.mark_session_ended("s")
    assert db.assign_ready_windows("s", "offline") == 1
    assert process_offline_results(db, "s") == 1
    result = db.results_for_session("s")[0]
    assert result["window_index"] == 0
    assert result["complete"] is True
    assert result["heart_rate"] is None


def test_final_five_second_window_can_compute_heart_rate_without_a_post_session_sample(tmp_path):
    db = Database(str(tmp_path / "device.db"))
    db.add_samples(_sample_rows("s", 1, 0, 1999))
    db.add_samples(_sample_rows("s", 2, 0, 1999))
    db.mark_session_ended("s")
    assert db.assign_ready_windows("s", "offline") == 5
    assert process_offline_results(db, "s") == 5
    results = db.results_for_session("s")
    final = next(row for row in results if row["window_index"] == 4)
    assert final["heart_rate"] == 60.0
    assert final["complete"] is True
