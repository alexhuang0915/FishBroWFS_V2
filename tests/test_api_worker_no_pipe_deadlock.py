
"""Test that worker spawn does not use PIPE (prevents deadlock)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from FishBroWFS_V2.control.api import _ensure_worker_running


def test_worker_spawn_not_using_pipes(monkeypatch, tmp_path):
    """Test that _ensure_worker_running does not use subprocess.PIPE."""
    called = {}
    
    def fake_popen(args, **kwargs):
        called["args"] = args
        called["kwargs"] = kwargs
        # Create a mock process object
        p = MagicMock()
        p.pid = 123
        return p
    
    monkeypatch.setattr("FishBroWFS_V2.control.api.subprocess.Popen", fake_popen)
    monkeypatch.setattr("FishBroWFS_V2.control.api.os.kill", lambda pid, sig: None)
    
    db_path = tmp_path / "jobs.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Create pidfile that doesn't exist (so worker will start)
    pidfile = db_path.parent / "worker.pid"
    assert not pidfile.exists()
    
    # Mock init_db to avoid actual DB creation
    monkeypatch.setattr("FishBroWFS_V2.control.api.init_db", lambda _: None)
    
    _ensure_worker_running(db_path)
    
    kw = called["kwargs"]
    
    # Critical: must not use PIPE
    assert kw["stdout"] is not subprocess.PIPE, "stdout must not be PIPE (deadlock risk)"
    assert kw["stderr"] is not subprocess.PIPE, "stderr must not be PIPE (deadlock risk)"
    
    # Should use file handle (opened file object)
    assert kw["stdout"] is not None, "stdout must be set (file handle)"
    assert kw["stderr"] is not None, "stderr must be set (file handle)"
    # Both stdout and stderr should be the same file handle
    assert kw["stdout"] is kw["stderr"], "stdout and stderr should point to same file"
    
    # Should have stdin=DEVNULL
    assert kw.get("stdin") == subprocess.DEVNULL, "stdin should be DEVNULL"
    
    # Should have start_new_session=True
    assert kw.get("start_new_session") is True, "start_new_session should be True"
    
    # Should have close_fds=True
    assert kw.get("close_fds") is True, "close_fds should be True"


