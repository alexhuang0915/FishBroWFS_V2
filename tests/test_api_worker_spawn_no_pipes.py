"""Test that API worker spawn does not use PIPE (prevents deadlock)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from FishBroWFS_V2.control.api import _ensure_worker_running


def test_api_worker_spawn_no_pipes(monkeypatch, tmp_path: Path) -> None:
    """Test that _ensure_worker_running does not use subprocess.PIPE."""
    seen: dict[str, object] = {}

    def fake_popen(args, **kwargs):  # noqa: ANN001
        seen.update(kwargs)
        class P:
            pid = 123
        return P()

    monkeypatch.setattr("FishBroWFS_V2.control.api.subprocess.Popen", fake_popen)
    monkeypatch.setattr("FishBroWFS_V2.control.api.os.kill", lambda pid, sig: None)
    monkeypatch.setattr("FishBroWFS_V2.control.api.init_db", lambda _: None)

    db_path = tmp_path / "jobs.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)

    _ensure_worker_running(db_path)

    assert seen["stdout"] is not subprocess.PIPE
    assert seen["stderr"] is not subprocess.PIPE
    assert seen.get("stdin") is subprocess.DEVNULL
