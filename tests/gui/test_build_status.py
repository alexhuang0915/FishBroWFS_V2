from datetime import datetime, timedelta

from gui.desktop.utils.build_status import (
    derive_overall_status,
    extract_status_message,
    compute_stall_warning,
)
from gui.desktop.utils.artifact_manifest import select_build_manifest_filename, parse_build_manifest


def test_derive_overall_status():
    assert derive_overall_status([]) == "UNKNOWN"
    assert derive_overall_status(["RUNNING"]) == "RUNNING"
    assert derive_overall_status(["QUEUED", "RUNNING"]) == "RUNNING"
    assert derive_overall_status(["SUCCEEDED"]) == "DONE"
    assert derive_overall_status(["COMPLETED", "SUCCEEDED"]) == "DONE"
    assert derive_overall_status(["FAILED"]) == "FAILED"
    assert derive_overall_status(["FAILED", "RUNNING"]) == "FAILED"


def test_extract_status_message():
    assert extract_status_message({}) == ""
    assert extract_status_message({"phase": "building"}) == "building"
    assert extract_status_message({"message": "ok", "phase": "ignored"}) == "ok"
    assert extract_status_message({"status_message": "submitting"}) == "submitting"


def test_compute_stall_warning():
    now = datetime(2025, 1, 1, 12, 0, 0)
    assert compute_stall_warning(None, now, 20) == ""
    assert compute_stall_warning(now - timedelta(seconds=10), now, 20) == ""
    assert "STALL WARNING" in compute_stall_warning(now - timedelta(seconds=25), now, 20)


def test_manifest_selection_and_parse():
    artifact_index = {
        "artifacts": [
            {"filename": "other.txt"},
            {"filename": "build_data_manifest.json"},
        ]
    }
    assert select_build_manifest_filename(artifact_index) == "build_data_manifest.json"
    rows, produced_path = parse_build_manifest({})
    assert rows == []
    assert produced_path is None
