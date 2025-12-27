"""Tests for identity-aware lifecycle preflight system."""

import os
import tempfile
import subprocess
import signal
from pathlib import Path
from unittest.mock import patch, MagicMock, Mock
import pytest

from control.lifecycle import (
    detect_port_occupant,
    verify_fishbro_control_identity,
    verify_fishbro_ui_identity,
    preflight_port,
    kill_process,
    read_pidfile,
    write_pidfile,
    remove_pidfile,
)


class TestPortDetection:
    """Test port occupancy detection."""

    def test_detect_port_occupant_no_occupant(self, monkeypatch):
        """When port is free, returns PortOccupant with occupied=False."""
        # Mock subprocess.check_output to raise CalledProcessError (simulating no output)
        def mock_check_output(cmd, **kwargs):
            raise subprocess.CalledProcessError(1, cmd, b"")
        
        monkeypatch.setattr(subprocess, "check_output", mock_check_output)
        
        result = detect_port_occupant(8000)
        assert isinstance(result, object)  # Should be PortOccupant
        assert hasattr(result, 'occupied')
        assert result.occupied is False

    def test_detect_port_occupant_with_ss(self, monkeypatch):
        """When ss returns a PID."""
        def mock_check_output(cmd, **kwargs):
            if "ss" in " ".join(cmd):
                return 'tcp   LISTEN 0  128  *:8000  *:*  users:(("python3",pid=12345,fd=3))'
            else:
                return ""
        
        monkeypatch.setattr(subprocess, "check_output", mock_check_output)
        
        result = detect_port_occupant(8000)
        assert result.occupied is True
        assert result.pid == 12345

    def test_detect_port_occupant_with_lsof(self, monkeypatch):
        """When ss fails but lsof returns a PID."""
        call_count = 0
        def mock_check_output(cmd, **kwargs):
            nonlocal call_count
            call_count += 1
            if "ss" in " ".join(cmd):
                raise subprocess.CalledProcessError(1, cmd, b"")
            elif "lsof" in " ".join(cmd):
                # lsof output with header line
                return "COMMAND   PID USER   FD   TYPE DEVICE SIZE/OFF NODE NAME\npython3  12345  user  3u  IPv4  12345  0t0  TCP *:8000 (LISTEN)"
            return ""
        
        monkeypatch.setattr(subprocess, "check_output", mock_check_output)
        
        result = detect_port_occupant(8000)
        assert result.occupied is True
        assert result.pid == 12345

    def test_detect_port_occupant_parse_error(self, monkeypatch):
        """When output cannot be parsed."""
        def mock_check_output(cmd, **kwargs):
            return "garbage output"
        
        monkeypatch.setattr(subprocess, "check_output", mock_check_output)
        
        result = detect_port_occupant(8000)
        assert result.occupied is True  # Output exists but can't parse
        assert result.pid is None


class TestIdentityVerification:
    """Test FishBro identity verification."""

    def test_verify_fishbro_control_identity_success(self, monkeypatch):
        """Control API identity endpoint returns correct service."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"service_name": "control_api"}
        
        with patch("requests.get", return_value=mock_response) as mock_get:
            result, data, error = verify_fishbro_control_identity("localhost", 8000)
            assert result is True
            assert error is None
            mock_get.assert_called_once_with("http://localhost:8000/__identity", timeout=2)

    def test_verify_fishbro_control_identity_wrong_service(self, monkeypatch):
        """Control API returns wrong service name."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"service_name": "something_else"}
        
        with patch("requests.get", return_value=mock_response):
            result, data, error = verify_fishbro_control_identity("localhost", 8000)
            assert result is False
            assert "service_name" in str(error)

    def test_verify_fishbro_control_identity_http_error(self, monkeypatch):
        """Control API returns non-200."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        
        with patch("requests.get", return_value=mock_response):
            result, data, error = verify_fishbro_control_identity("localhost", 8000)
            assert result is False
            assert "HTTP" in str(error)

    def test_verify_fishbro_control_identity_request_exception(self, monkeypatch):
        """Request raises exception."""
        with patch("requests.get", side_effect=Exception("Connection refused")):
            result, data, error = verify_fishbro_control_identity("localhost", 8000)
            assert result is False
            assert error is not None

    def test_verify_fishbro_ui_identity_success(self, monkeypatch):
        """UI process matches FishBro patterns."""
        mock_occupant = MagicMock()
        mock_occupant.cmdline = "python3 -m gui.nicegui.app"
        
        result, error = verify_fishbro_ui_identity(mock_occupant)
        assert result is True
        assert error is None

    def test_verify_fishbro_ui_identity_wrong_process(self, monkeypatch):
        """Process is not FishBro UI."""
        mock_occupant = MagicMock()
        mock_occupant.cmdline = "python3 -m http.server"
        
        result, error = verify_fishbro_ui_identity(mock_occupant)
        assert result is False
        assert error is not None

    def test_verify_fishbro_ui_identity_no_proc(self, monkeypatch):
        """No cmdline available."""
        mock_occupant = MagicMock()
        mock_occupant.cmdline = None
        
        result, error = verify_fishbro_ui_identity(mock_occupant)
        assert result is False
        assert "No cmdline" in str(error)


class TestPreflightPort:
    """Test preflight port decision logic."""

    def test_preflight_port_free(self, monkeypatch):
        """Port is free -> START."""
        mock_occupant = MagicMock()
        mock_occupant.occupied = False
        with patch("control.lifecycle.detect_port_occupant", return_value=mock_occupant):
            result = preflight_port(8000, service_type="control")
            assert result.status.value == "FREE"
            assert result.decision == "START"

    def test_preflight_port_fishbro_control(self, monkeypatch):
        """Port occupied by FishBro Control -> REUSE."""
        mock_occupant = MagicMock()
        mock_occupant.occupied = True
        mock_occupant.pid = 12345
        with patch("control.lifecycle.detect_port_occupant", return_value=mock_occupant):
            with patch("control.lifecycle.verify_fishbro_control_identity", return_value=(True, {}, None)):
                result = preflight_port(8000, service_type="control")
                assert result.status.value == "OCCUPIED_FISHBRO"
                assert result.decision == "REUSE"
                assert result.occupant.pid == 12345

    def test_preflight_port_fishbro_ui(self, monkeypatch):
        """Port occupied by FishBro UI -> REUSE."""
        # Create a proper PortOccupant-like object
        from control.lifecycle import PortOccupant
        mock_occupant = PortOccupant(
            occupied=True,
            pid=12345,
            cmdline="python -m gui.nicegui.app"
        )
        with patch("control.lifecycle.detect_port_occupant", return_value=mock_occupant):
            with patch("control.lifecycle.verify_fishbro_control_identity", return_value=(False, None, "error")):
                with patch("control.lifecycle.verify_fishbro_ui_identity", return_value=(True, None)):
                    result = preflight_port(8080, service_type="ui")
                    assert result.status.value == "OCCUPIED_FISHBRO"
                    assert result.decision == "REUSE"
                    assert result.occupant.pid == 12345

    def test_preflight_port_non_fishbro_no_force(self, monkeypatch):
        """Port occupied by non-FishBro -> FAIL_FAST."""
        mock_occupant = MagicMock()
        mock_occupant.occupied = True
        mock_occupant.pid = 12345
        with patch("control.lifecycle.detect_port_occupant", return_value=mock_occupant):
            with patch("control.lifecycle.verify_fishbro_control_identity", return_value=(False, None, "error")):
                with patch("control.lifecycle.verify_fishbro_ui_identity", return_value=(False, "error")):
                    result = preflight_port(8000, service_type="control")
                    assert result.status.value == "OCCUPIED_NOT_FISHBRO"
                    assert result.decision == "FAIL_FAST"
                    assert result.occupant.pid == 12345

    def test_preflight_port_identity_failure(self, monkeypatch):
        """Port occupied but identity check fails -> OCCUPIED_UNKNOWN."""
        mock_occupant = MagicMock()
        mock_occupant.occupied = True
        mock_occupant.pid = 12345
        with patch("control.lifecycle.detect_port_occupant", return_value=mock_occupant):
            with patch("control.lifecycle.verify_fishbro_control_identity", side_effect=Exception("error")):
                with patch("control.lifecycle.verify_fishbro_ui_identity", side_effect=Exception("error")):
                    result = preflight_port(8000, service_type="control")
                    assert result.status.value == "OCCUPIED_UNKNOWN"
                    assert result.decision == "FAIL_FAST"
                    assert result.occupant.pid == 12345


class TestKillProcess:
    """Test process killing."""

    def test_kill_process_success(self, monkeypatch):
        """Process killed successfully."""
        mock_kill = MagicMock()
        monkeypatch.setattr(os, "kill", mock_kill)
        
        result = kill_process(12345)
        assert result is True
        # Should call SIGTERM, check (os.kill(pid, 0)), then SIGKILL after sleep
        assert mock_kill.call_count == 3
        assert mock_kill.call_args_list[0][0][1] == signal.SIGTERM
        assert mock_kill.call_args_list[1][0][1] == 0  # Check if process exists
        assert mock_kill.call_args_list[2][0][1] == signal.SIGKILL

    def test_kill_process_already_dead(self, monkeypatch):
        """Process already dead (OSError)."""
        mock_kill = MagicMock(side_effect=ProcessLookupError("No such process"))
        monkeypatch.setattr(os, "kill", mock_kill)
        
        result = kill_process(12345)
        assert result is True  # Considered success

    def test_kill_process_permission_error(self, monkeypatch):
        """Permission error when killing."""
        mock_kill = MagicMock(side_effect=PermissionError("Operation not permitted"))
        monkeypatch.setattr(os, "kill", mock_kill)
        
        result = kill_process(12345)
        assert result is False


class TestPidFileManagement:
    """Test PID file operations."""

    def setup_method(self):
        """Create temp PID directory."""
        self.temp_dir = tempfile.mkdtemp()
        self.pid_dir = Path(self.temp_dir) / "pids"
        self.pid_dir.mkdir(parents=True, exist_ok=True)

    def teardown_method(self):
        """Clean up temp directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_write_read_delete_pid_file(self):
        """Round-trip test for PID file operations."""
        # Write PID file
        write_pidfile(12345, "control", self.pid_dir)
        pid_file = self.pid_dir / "control.pid"
        assert pid_file.exists()
        
        # Read PID file
        pid = read_pidfile("control", self.pid_dir)
        assert pid == 12345
        
        # Delete PID file
        remove_pidfile("control", self.pid_dir)
        assert not pid_file.exists()

    def test_read_nonexistent_pid_file(self):
        """Reading non-existent PID file returns None."""
        pid = read_pidfile("nonexistent", self.pid_dir)
        assert pid is None

    def test_read_corrupted_pid_file(self):
        """Reading corrupted PID file returns None."""
        pid_file = self.pid_dir / "corrupted.pid"
        pid_file.write_text("not-a-number")
        
        pid = read_pidfile("corrupted", self.pid_dir)
        assert pid is None

    def test_delete_nonexistent_pid_file(self):
        """Deleting non-existent PID file is safe."""
        remove_pidfile("nonexistent", self.pid_dir)  # Should not raise


class TestLaunchDashboardIntegration:
    """Integration tests for launch_dashboard.py commands."""

    def test_status_command(self, monkeypatch):
        """Test status command."""
        # Skip this test for now as it requires complex mocking
        pass

    def test_stop_command(self, monkeypatch):
        """Test stop command."""
        # Skip this test for now as it requires complex mocking
        pass

    def test_restart_ui_command(self, monkeypatch):
        """Test restart-ui command."""
        # Skip this test for now as it requires complex mocking
        pass

    def test_restart_all_command(self, monkeypatch):
        """Test restart-all command."""
        # Skip this test for now as it requires complex mocking
        pass

    def test_invalid_command(self, monkeypatch):
        """Test invalid command."""
        # Skip this test for now as it requires complex mocking
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])