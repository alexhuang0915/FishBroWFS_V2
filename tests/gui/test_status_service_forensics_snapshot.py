"""Unit test for status_service forensics snapshot."""
import pytest

from gui.nicegui.services.status_service import get_forensics_snapshot


def test_get_forensics_snapshot_has_stable_keys():
    """get_forensics_snapshot() returns a dict with the required keys."""
    snap = get_forensics_snapshot()
    assert isinstance(snap, dict)
    expected_keys = {
        "state",
        "summary",
        "backend_up",
        "worker_up",
        "backend_error",
        "worker_error",
        "last_checked_ts",
        "polling_started",
        "poll_interval_s",
    }
    for key in expected_keys:
        assert key in snap


def test_get_forensics_snapshot_no_exception_when_backend_offline():
    """Snapshot must not raise even if backend is offline."""
    # The service should already be in whatever state (maybe offline).
    # We just ensure the call succeeds.
    snap = get_forensics_snapshot()
    assert isinstance(snap, dict)
    # At minimum state and summary should be strings
    assert isinstance(snap["state"], str)
    assert isinstance(snap["summary"], str)
    # backend_up and worker_up are bool
    assert isinstance(snap["backend_up"], bool)
    assert isinstance(snap["worker_up"], bool)
    # polling_started is bool
    assert isinstance(snap["polling_started"], bool)
    # poll_interval_s is float
    assert isinstance(snap["poll_interval_s"], float)
    # errors may be None or str
    if snap["backend_error"] is not None:
        assert isinstance(snap["backend_error"], str)
    if snap["worker_error"] is not None:
        assert isinstance(snap["worker_error"], str)
    # last_checked_ts is float or None
    assert snap["last_checked_ts"] is None or isinstance(snap["last_checked_ts"], float)