"""
Test desktop auto-starts supervisor when not running.

Mock ensure_supervisor_running path and assert start_supervisor_subprocess
is invoked when supervisor is not running.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock, call
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../src"))

from gui.desktop.supervisor_lifecycle import (
    ensure_supervisor_running,
    SupervisorStatus,
    start_supervisor_subprocess,
)
from gui.desktop.supervisor_lifecycle import detect_port_occupant_8000


def test_ensure_supervisor_running_starts_when_port_free():
    """Test that supervisor is started when port 8000 is free."""
    with patch("gui.desktop.supervisor_lifecycle.detect_port_occupant_8000") as mock_detect, \
         patch("gui.desktop.supervisor_lifecycle.start_supervisor_subprocess") as mock_start, \
         patch("gui.desktop.supervisor_lifecycle.wait_for_health") as mock_health:
        
        # Mock port as free
        mock_detect.return_value = {
            "occupied": False,
            "pid": None,
            "process_name": None,
            "cmdline": None,
            "is_fishbro_supervisor": None,
        }
        
        # Mock successful startup
        mock_proc = Mock()
        mock_proc.pid = 9999
        mock_start.return_value = mock_proc
        mock_health.return_value = True
        
        status, details = ensure_supervisor_running()
        
        # Verify supervisor was started
        mock_start.assert_called_once()
        
        # Verify status is RUNNING
        assert status == SupervisorStatus.RUNNING
        assert details["pid"] == 9999
        assert details["action"] == "started"


def test_ensure_supervisor_running_when_already_running():
    """Test that supervisor is not started when already running."""
    with patch("gui.desktop.supervisor_lifecycle.detect_port_occupant_8000") as mock_detect, \
         patch("gui.desktop.supervisor_lifecycle.start_supervisor_subprocess") as mock_start:
        
        # Mock port occupied by fishbro supervisor
        mock_detect.return_value = {
            "occupied": True,
            "pid": 12345,
            "process_name": "uvicorn",
            "cmdline": ["python", "-m", "uvicorn", "control.api:app"],
            "is_fishbro_supervisor": True,
        }
        
        status, details = ensure_supervisor_running()
        
        # Verify supervisor was NOT started
        mock_start.assert_not_called()
        
        # Verify status is RUNNING (already running)
        assert status == SupervisorStatus.RUNNING
        assert details["pid"] == 12345
        assert details["action"] == "already_running"


def test_ensure_supervisor_running_port_occupied_by_other():
    """Test PORT_OCCUPIED status when port occupied by non-fishbro process."""
    with patch("gui.desktop.supervisor_lifecycle.detect_port_occupant_8000") as mock_detect, \
         patch("gui.desktop.supervisor_lifecycle.start_supervisor_subprocess") as mock_start:
        
        # Mock port occupied by non-fishbro process
        mock_detect.return_value = {
            "occupied": True,
            "pid": 9999,
            "process_name": "node",
            "cmdline": ["node", "server.js"],
            "is_fishbro_supervisor": False,
        }
        
        status, details = ensure_supervisor_running()
        
        # Verify supervisor was NOT started (never auto-kill)
        mock_start.assert_not_called()
        
        # Verify status is PORT_OCCUPIED
        assert status == SupervisorStatus.PORT_OCCUPIED
        assert details["pid"] == 9999
        assert details["process_name"] == "node"
        assert "port_occupied" in details["error"]


def test_ensure_supervisor_running_health_check_fails():
    """Test ERROR status when supervisor starts but health check fails."""
    with patch("gui.desktop.supervisor_lifecycle.detect_port_occupant_8000") as mock_detect, \
         patch("gui.desktop.supervisor_lifecycle.start_supervisor_subprocess") as mock_start, \
         patch("gui.desktop.supervisor_lifecycle.wait_for_health") as mock_health:
        
        # Mock port as free
        mock_detect.return_value = {"occupied": False}
        
        # Mock successful process start but health check fails
        mock_proc = Mock()
        mock_proc.pid = 9999
        mock_start.return_value = mock_proc
        mock_health.return_value = False  # Health check fails
        
        status, details = ensure_supervisor_running()
        
        # Verify supervisor was started
        mock_start.assert_called_once()
        
        # Verify status is ERROR due to health check failure
        assert status == SupervisorStatus.ERROR
        assert "health_check_failed" in details["error"]


def test_start_supervisor_subprocess_includes_explicit_bind_flags():
    """Test that start_supervisor_subprocess includes explicit host/port flags."""
    with patch("gui.desktop.supervisor_lifecycle.discover_supervisor_command") as mock_discover, \
         patch("subprocess.Popen") as mock_popen, \
         patch("pathlib.Path.mkdir"), \
         patch("builtins.open"), \
         patch("gui.desktop.supervisor_lifecycle.log_entrypoint"):
        
        # Mock discovered command (may or may not have host/port)
        test_cases = [
            # (discovered_cmd, expected_cmd_contains)
            (
                ["python", "-m", "uvicorn", "control.api:app"],
                ["--host", "127.0.0.1", "--port", "8000"]
            ),
            (
                ["python", "-m", "uvicorn", "control.api:app", "--host", "0.0.0.0"],
                ["--host", "127.0.0.1", "--port", "8000"]  # Should override host
            ),
            (
                ["python", "-m", "uvicorn", "control.api:app", "--port", "9000"],
                ["--host", "127.0.0.1", "--port", "8000"]  # Should override port
            ),
        ]
        
        for discovered_cmd, expected_contains in test_cases:
            mock_discover.return_value = discovered_cmd
            mock_popen.reset_mock()
            
            start_supervisor_subprocess()
            
            # Get the actual command passed to Popen
            call_args = mock_popen.call_args
            actual_cmd = call_args[0][0] if call_args else None
            
            # Verify command contains explicit bind flags
            assert actual_cmd is not None
            cmd_str = " ".join(actual_cmd)
            for expected in expected_contains:
                assert expected in cmd_str, f"Expected '{expected}' in command: {cmd_str}"


def test_no_double_spawn_guard():
    """Test that ensure_supervisor_running doesn't spawn multiple supervisors."""
    # This would be tested by integration tests in practice
    # For unit test, we verify the logic path doesn't call start when already running
    with patch("gui.desktop.supervisor_lifecycle.detect_port_occupant_8000") as mock_detect, \
         patch("gui.desktop.supervisor_lifecycle.start_supervisor_subprocess") as mock_start:
        
        # First call: port free, start supervisor
        mock_detect.return_value = {"occupied": False}
        mock_proc = Mock()
        mock_proc.pid = 9999
        mock_start.return_value = mock_proc
        
        with patch("gui.desktop.supervisor_lifecycle.wait_for_health") as mock_health:
            mock_health.return_value = True
            status1, _ = ensure_supervisor_running()
        
        # Reset mock to track second call
        mock_start.reset_mock()
        
        # Second call: port now occupied by our supervisor
        mock_detect.return_value = {
            "occupied": True,
            "pid": 9999,
            "process_name": "uvicorn",
            "cmdline": ["python", "-m", "uvicorn", "control.api:app"],
            "is_fishbro_supervisor": True,
        }
        
        status2, _ = ensure_supervisor_running()
        
        # Verify supervisor was NOT started again
        mock_start.assert_not_called()
        assert status1 == SupervisorStatus.RUNNING
        assert status2 == SupervisorStatus.RUNNING


if __name__ == "__main__":
    pytest.main([__file__, "-v"])