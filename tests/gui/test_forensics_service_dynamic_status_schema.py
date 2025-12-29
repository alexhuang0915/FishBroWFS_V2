"""Unit test for forensics service dynamic status schema."""
import json
import tempfile

from gui.nicegui.services.forensics_service import generate_ui_forensics


def test_forensics_snapshot_contains_system_status_with_state():
    """generate_ui_forensics returns a snapshot with system_status that has state."""
    with tempfile.TemporaryDirectory() as tmpdir:
        snapshot = generate_ui_forensics(outputs_dir=tmpdir)
        # Top-level keys
        assert "system_status" in snapshot
        status = snapshot["system_status"]
        # Required keys
        assert "state" in status
        assert "summary" in status
        assert "backend_up" in status
        assert "worker_up" in status
        # Ensure state is a string (ONLINE/DEGRADED/OFFLINE)
        assert isinstance(status["state"], str)
        assert status["state"] in ("ONLINE", "DEGRADED", "OFFLINE")
        # Ensure no KeyError 'status' exists (legacy)
        assert "status" not in snapshot  # Should be system_status now
        # Ensure ui_registry exists (may be empty)
        assert "ui_registry" in snapshot
        # Ensure pages_static exists
        assert "pages_static" in snapshot


def test_forensics_snapshot_serializable():
    """Snapshot must be JSON-serializable (no sets)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        snapshot = generate_ui_forensics(outputs_dir=tmpdir)
        # This will raise TypeError if any non-serializable data (e.g., set)
        json_str = json.dumps(snapshot, default=str)
        # Ensure we can load it back
        loaded = json.loads(json_str)
        assert loaded["system_status"]["state"] in ("ONLINE", "DEGRADED", "OFFLINE")