"""Tests for worker spawn policy (Phase B)."""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch, mock_open, MagicMock

import pytest

from FishBroWFS_V2.control.worker_spawn_policy import can_spawn_worker, validate_pidfile


class TestCanSpawnWorker:
    """Test can_spawn_worker decision logic."""

    def test_allowed_normal(self, tmp_path, monkeypatch):
        """No pytest env, not /tmp -> allowed."""
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        # Use a path not under /tmp
        db_path = Path.cwd() / "test.db"
        allowed, reason = can_spawn_worker(db_path)
        assert allowed is True
        assert reason == "ok"

    def test_deny_pytest_no_override(self, tmp_path, monkeypatch):
        """PYTEST_CURRENT_TEST set, no override -> deny."""
        monkeypatch.setenv("PYTEST_CURRENT_TEST", "test_foo")
        monkeypatch.delenv("FISHBRO_ALLOW_SPAWN_IN_TESTS", raising=False)
        db_path = tmp_path / "jobs.db"
        allowed, reason = can_spawn_worker(db_path)
        assert allowed is False
        assert "pytest" in reason
        assert "FISHBRO_ALLOW_SPAWN_IN_TESTS" in reason

    def test_allow_pytest_with_override(self, tmp_path, monkeypatch):
        """PYTEST_CURRENT_TEST set but override present -> allow."""
        monkeypatch.setenv("PYTEST_CURRENT_TEST", "test_foo")
        monkeypatch.setenv("FISHBRO_ALLOW_SPAWN_IN_TESTS", "1")
        # Also allow tmp because tmp_path is under /tmp
        monkeypatch.setenv("FISHBRO_ALLOW_TMP_DB", "1")
        db_path = tmp_path / "jobs.db"
        allowed, reason = can_spawn_worker(db_path)
        assert allowed is True
        assert reason == "ok"

    def test_deny_tmp_db_no_override(self, monkeypatch):
        """DB path under /tmp, no override -> deny."""
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        with tempfile.NamedTemporaryFile(suffix=".db", dir="/tmp") as f:
            db_path = Path(f.name)
            allowed, reason = can_spawn_worker(db_path)
            assert allowed is False
            assert "/tmp" in reason
            assert "FISHBRO_ALLOW_TMP_DB" in reason

    def test_allow_tmp_db_with_override(self, monkeypatch):
        """DB path under /tmp but override present -> allow."""
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        monkeypatch.setenv("FISHBRO_ALLOW_TMP_DB", "1")
        with tempfile.NamedTemporaryFile(suffix=".db", dir="/tmp") as f:
            db_path = Path(f.name)
            allowed, reason = can_spawn_worker(db_path)
            assert allowed is True
            assert reason == "ok"

    def test_pytest_and_tmp_both_deny(self, monkeypatch):
        """Both conditions, deny with pytest reason first."""
        monkeypatch.setenv("PYTEST_CURRENT_TEST", "test_foo")
        with tempfile.NamedTemporaryFile(suffix=".db", dir="/tmp") as f:
            db_path = Path(f.name)
            allowed, reason = can_spawn_worker(db_path)
            assert allowed is False
            # Should be pytest reason (first check)
            assert "pytest" in reason

    def test_pytest_override_tmp_deny(self, monkeypatch):
        """Pytest overridden, tmp still denied."""
        monkeypatch.setenv("PYTEST_CURRENT_TEST", "test_foo")
        monkeypatch.setenv("FISHBRO_ALLOW_SPAWN_IN_TESTS", "1")
        with tempfile.NamedTemporaryFile(suffix=".db", dir="/tmp") as f:
            db_path = Path(f.name)
            allowed, reason = can_spawn_worker(db_path)
            assert allowed is False
            assert "/tmp" in reason

    def test_expanduser_resolve(self, tmp_path, monkeypatch):
        """Ensure path expansion and resolution works."""
        monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
        # Allow /tmp because tmp_path is under /tmp
        monkeypatch.setenv("FISHBRO_ALLOW_TMP_DB", "1")
        # Mock home directory
        fake_home = tmp_path / "home" / "user"
        fake_home.mkdir(parents=True)
        monkeypatch.setenv("HOME", str(fake_home))
        # Create a symlink to test resolution
        link = tmp_path / "link.db"
        target = tmp_path / "real.db"
        target.touch()
        link.symlink_to(target)
        allowed, reason = can_spawn_worker(link)
        assert allowed is True


class TestValidatePidfile:
    """Test pidfile validation."""

    def test_missing_pidfile(self, tmp_path):
        """pidfile does not exist -> invalid."""
        pidfile = tmp_path / "worker.pid"
        db_path = tmp_path / "jobs.db"
        valid, reason = validate_pidfile(pidfile, db_path)
        assert valid is False
        assert "missing" in reason

    def test_corrupted_pidfile(self, tmp_path):
        """pidfile contains non-integer -> invalid."""
        pidfile = tmp_path / "worker.pid"
        pidfile.write_text("not-a-number")
        db_path = tmp_path / "jobs.db"
        valid, reason = validate_pidfile(pidfile, db_path)
        assert valid is False
        assert "corrupted" in reason

    def test_dead_process(self, tmp_path):
        """pid exists but process dead -> invalid."""
        # Use a high PID unlikely to exist
        pidfile = tmp_path / "worker.pid"
        pidfile.write_text("999999")
        db_path = tmp_path / "jobs.db"
        valid, reason = validate_pidfile(pidfile, db_path)
        assert valid is False
        assert "dead" in reason

    @pytest.mark.skipif(not Path("/proc/self/cmdline").exists(), reason="requires Linux /proc")
    def test_live_process_wrong_cmdline(self, tmp_path):
        """Process alive but not worker_main -> invalid."""
        pid = os.getpid()
        pidfile = tmp_path / "worker.pid"
        pidfile.write_text(str(pid))
        db_path = tmp_path / "jobs.db"
        valid, reason = validate_pidfile(pidfile, db_path)
        # Our own process is not a worker_main
        assert valid is False
        assert "not a worker_main" in reason

    @pytest.mark.skipif(not Path("/proc/self/cmdline").exists(), reason="requires Linux /proc")
    def test_live_process_mismatch_db(self, tmp_path):
        """Process is worker_main but db_path mismatch -> invalid."""
        # We'll mock cmdline to contain worker_main but different db_path
        pid = os.getpid()
        pidfile = tmp_path / "worker.pid"
        pidfile.write_text(str(pid))
        db_path = tmp_path / "jobs.db"
        fake_cmdline = f"python -m FishBroWFS_V2.control.worker_main /some/other.db"
        with patch("pathlib.Path.read_bytes", return_value=fake_cmdline.encode() + b"\x00"):
            valid, reason = validate_pidfile(pidfile, db_path)
            assert valid is False
            assert "db_path mismatch" in reason

    @pytest.mark.skipif(not Path("/proc/self/cmdline").exists(), reason="requires Linux /proc")
    def test_valid_worker(self, tmp_path):
        """Process matches worker_main and db_path -> valid."""
        pid = os.getpid()
        pidfile = tmp_path / "worker.pid"
        pidfile.write_text(str(pid))
        db_path = tmp_path / "jobs.db"
        fake_cmdline = f"python -m FishBroWFS_V2.control.worker_main {db_path}"
        with patch("pathlib.Path.read_bytes", return_value=fake_cmdline.encode() + b"\x00"):
            valid, reason = validate_pidfile(pidfile, db_path)
            assert valid is True
            assert "alive and matching" in reason

    def test_no_proc_fallback(self, tmp_path):
        """When /proc/{pid}/cmdline missing, fallback returns True."""
        pid = os.getpid()
        pidfile = tmp_path / "worker.pid"
        pidfile.write_text(str(pid))
        db_path = tmp_path / "jobs.db"
        # Mock Path constructor to return a mock for /proc/{pid}/cmdline
        with patch("FishBroWFS_V2.control.worker_spawn_policy.Path") as MockPath:
            # For other Path calls (pidfile, etc.) we need to return real Path objects
            # We'll use side_effect to differentiate
            def path_side(*args, **kwargs):
                # args[0] is the path string
                path_str = args[0] if args else ""
                if path_str.startswith("/proc/"):
                    # Return a mock with exists returning False
                    mock = MagicMock()
                    mock.exists.return_value = False
                    return mock
                # Return a real Path for everything else
                from pathlib import Path as RealPath
                return RealPath(*args, **kwargs)
            MockPath.side_effect = path_side
            valid, reason = validate_pidfile(pidfile, db_path)
            assert valid is True
            assert "unverifiable" in reason

    def test_cmdline_read_error(self, tmp_path):
        """If reading cmdline raises exception, fallback to unverifiable."""
        pid = os.getpid()
        pidfile = tmp_path / "worker.pid"
        pidfile.write_text(str(pid))
        db_path = tmp_path / "jobs.db"
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.read_bytes", side_effect=PermissionError):
                valid, reason = validate_pidfile(pidfile, db_path)
                # Should fallback to unverifiable (since exception caught)
                assert valid is True
                assert "unverifiable" in reason

    def test_cmdline_decode_error(self, tmp_path):
        """If cmdline bytes cannot be decoded, treat as empty."""
        pid = os.getpid()
        pidfile = tmp_path / "worker.pid"
        pidfile.write_text(str(pid))
        db_path = tmp_path / "jobs.db"
        with patch("pathlib.Path.exists", return_value=True):
            with patch("pathlib.Path.read_bytes", return_value=b"\xff\xfe"):
                valid, reason = validate_pidfile(pidfile, db_path)
                # cmdline empty, so worker_main not found -> invalid
                assert valid is False
                assert "not a worker_main" in reason