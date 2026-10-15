from pipeline.config import DeviceConfig
from pipeline.db import Database
from pipeline.runtime import PipelineRuntime


def test_offline_runtime_reclassifies_unacknowledged_online_windows(tmp_path):
    db_path = str(tmp_path / "device.db")
    db = Database(db_path)
    db.insert_window_modes([
        {"session_id": "s", "window_index": 0, "mode": "online", "prior_peak_index": None, "assigned_at": 1.0}
    ])
    runtime = PipelineRuntime(DeviceConfig(db_path=db_path, mock_host="127.0.0.1", mock_port=65500,
                                           cloud_url="http://127.0.0.1:65501", cloud_token=""))
    runtime.mode = "offline"
    runtime.collector.active_session_id = "s"
    runtime._process_sessions()
    assert db.pending_mode_windows()[0]["mode"] == "offline"
    runtime.collector.close()
