from __future__ import annotations

from pipeline.db import Database


def test_samples_are_idempotent_and_conflicts_are_not_overwritten(tmp_path):
    db = Database(str(tmp_path / "device.db"))
    sample = {"session_id": "s", "sensor": 1, "index": 0, "values": [1, 2, 3]}
    assert db.add_samples([sample])["inserted"] == 1
    assert db.add_samples([sample])["duplicates"] == 1
    conflicting = {**sample, "values": [4, 5, 6]}
    stats = db.add_samples([conflicting])
    assert stats["conflicts"] == 1
    assert db.get_samples("s", 1, 0, 0)[0] == [1, 2, 3]
    assert db.get_watermark("s", 1) == 1


def test_watermark_stops_at_unknown_gap_then_advances_after_loss_ledger(tmp_path):
    db = Database(str(tmp_path / "device.db"))
    rows = [{"session_id": "s", "sensor": 1, "index": i, "values": [i, i, i]} for i in [0, 1, 3, 4]]
    db.add_samples(rows)
    assert db.get_watermark("s", 1) == 2
    db.add_losses([{"session_id": "s", "sensor": 1, "from_index": 2, "to_index": 2, "reason": "test_gap"}])
    assert db.get_watermark("s", 1) == 5


def test_recovered_sample_is_removed_from_loss_range(tmp_path):
    db = Database(str(tmp_path / "device.db"))
    db.add_losses([{"session_id": "s", "sensor": 2, "from_index": 10, "to_index": 14, "reason": "reported"}])
    db.add_samples([{"session_id": "s", "sensor": 2, "index": i, "values": [i, i]} for i in range(10)])
    db.add_samples([{"session_id": "s", "sensor": 2, "index": 12, "values": [5, 6]}])
    rows = list(db.export_samples("s"))
    loss_rows = [r for r in rows if "from_index" in r]
    assert { (r["from_index"], r["to_index"]) for r in loss_rows } == {(10, 11), (13, 14)}
    assert db.get_watermark("s", 2) == 15


def test_unknown_tail_loss_is_exported_with_null_to_index(tmp_path):
    db = Database(str(tmp_path / "device.db"))
    db.add_samples([{"session_id": "old", "sensor": 1, "index": 0, "values": [0, 0, 0]}])
    db.add_losses([{"session_id": "old", "sensor": 1, "from_index": 1, "to_index": None, "reason": "restart"}])
    exported = list(db.export_samples("old"))
    assert {"sensor": 1, "from_index": 1, "to_index": None, "reason": "restart"} in exported


def test_failed_upload_can_reclassify_unacknowledged_windows_as_offline(tmp_path):
    db = Database(str(tmp_path / "device.db"))
    db.insert_window_modes([{"session_id": "s", "window_index": 3, "mode": "online", "prior_peak_index": 900, "assigned_at": 1.0}])
    assert db.reclassify_unuploaded_online_to_offline("s") == 1
    assert db.unprocessed_offline_modes("s")[0]["window_index"] == 3
    assert db.pending_mode_windows()[0]["mode"] == "offline"


def test_overlapping_loss_reports_are_subtracted_from_existing_ledger(tmp_path):
    db = Database(str(tmp_path / "device.db"))
    db.add_losses([{"session_id": "s", "sensor": 1, "from_index": 10, "to_index": 20, "reason": "first_report"}])
    db.add_losses([{"session_id": "s", "sensor": 1, "from_index": 15, "to_index": 25, "reason": "expanded_report"}])
    exported = [row for row in db.export_samples("s") if "from_index" in row]
    assert [(r["from_index"], r["to_index"], r["reason"]) for r in exported] == [
        (10, 20, "first_report"),
        (21, 25, "expanded_report"),
    ]
