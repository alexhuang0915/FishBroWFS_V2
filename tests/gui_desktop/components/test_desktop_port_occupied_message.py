"""
Test desktop shows proper PORT_OCCUPIED message with PID/cmdline.

Simulate non-fishbro process on port 8000 and assert PORT_OCCUPIED
status with detailed diagnostic information in the message.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../src"))

from gui.desktop.supervisor_lifecycle import (
    ensure_supervisor_running,
    SupervisorStatus,
)

# Skip Qt tests if PySide6 is not available
try:
    from PySide6.QtWidgets import QMessageBox
    QT_AVAILABLE = True
except ImportError:
    QT_AVAILABLE = False


def test_port_occupied_detection_includes_pid_and_cmdline():
    """Test that PORT_OCCUPIED details include PID and cmdline."""
    with patch("gui.desktop.supervisor_lifecycle.detect_port_occupant_8000") as mock_detect:
        
        # Mock port occupied by non-fishbro process with detailed info
        mock_detect.return_value = {
            "occupied": True,
            "pid": 54321,
            "process_name": "node",
            "cmdline": ["/usr/bin/node", "/home/user/app/server.js", "--port", "8000"],
            "is_fishbro_supervisor": False,
        }
        
        status, details = ensure_supervisor_running()
        
        # Verify status and details
        assert status == SupervisorStatus.PORT_OCCUPIED
        assert details["pid"] == 54321
        assert details["process_name"] == "node"
        assert details["cmdline"] == ["/usr/bin/node", "/home/user/app/server.js", "--port", "8000"]
        assert "port_occupied" in details["error"]
        
        # Verify message includes diagnostic info
        message = details["message"]
        assert "Port 8000 occupied" in message
        assert "54321" in message  # PID
        assert "node" in message  # process name


@pytest.mark.skipif(not QT_AVAILABLE, reason="PySide6 not available")
def test_control_station_shows_port_occupied_dialog():
    """Test that ControlStation shows QMessageBox for PORT_OCCUPIED."""
    # Import here to avoid Qt import errors when skipped
    from gui.desktop.control_station import ControlStation
    
    with patch("gui.desktop.control_station.ensure_supervisor_running") as mock_ensure, \
         patch("PySide6.QtWidgets.QMessageBox.critical") as mock_msgbox:
        
        # Mock PORT_OCCUPIED status
        mock_ensure.return_value = (
            SupervisorStatus.PORT_OCCUPIED,
            {
                "pid": 9999,
                "process_name": "nginx",
                "cmdline": ["nginx", "-g", "daemon off;"],
                "error": "port_occupied",
                "message": "Port 8000 occupied by PID 9999 (nginx)",
            }
        )
        
        # Create a minimal ControlStation instance without full Qt initialization
        # We'll patch the __init__ to skip the parent initialization and setup
        with patch("PySide6.QtWidgets.QMainWindow.__init__", return_value=None):
            # Create instance with minimal setup
            station = ControlStation.__new__(ControlStation)
            
            # Set up minimal attributes needed by start_supervisor
            station.status_indicator = Mock()
            station.status_indicator.setText = Mock()
            station.status_indicator.setStyleSheet = Mock()
            
            # Call start_supervisor directly
            station.start_supervisor()
            
            # Verify QMessageBox was shown
            mock_msgbox.assert_called_once()
            
            # Check dialog content
            call_args = mock_msgbox.call_args
            assert call_args[0][1] == "Port Conflict"  # title
            
            # Message should contain PID and process name
            message = call_args[0][2]
            assert "9999" in message  # PID
            assert "nginx" in message  # process name
            assert "Port 8000" in message


def test_port_occupied_message_formats_cmdline_truncated():
    """Test that cmdline is included in details (not necessarily in message)."""
    with patch("gui.desktop.supervisor_lifecycle.detect_port_occupant_8000") as mock_detect:
        
        # Mock with long cmdline
        long_cmdline = ["python", "-m", "very_long_module_name",
                       "--very-long-argument", "value",
                       "--another-argument", "another-value",
                       "--yet-another", "more-values"]
        
        mock_detect.return_value = {
            "occupied": True,
            "pid": 12345,
            "process_name": "python",
            "cmdline": long_cmdline,
            "is_fishbro_supervisor": False,
        }
        
        status, details = ensure_supervisor_running()
        
        # Verify status and basic details
        assert status == SupervisorStatus.PORT_OCCUPIED
        assert details["pid"] == 12345
        assert details["process_name"] == "python"
        assert details["cmdline"] == long_cmdline
        
        # Message should contain PID and process name
        message = details["message"]
        assert "12345" in message
        assert "python" in message
        assert "Port 8000 occupied" in message


def test_different_non_fishbro_processes_identified():
    """Test various non-fishbro processes are correctly identified."""
    test_cases = [
        {
            "pid": 1111,
            "process_name": "nginx",
            "cmdline": ["nginx"],
            "expected_in_message": ["1111", "nginx"]
        },
        {
            "pid": 2222,
            "process_name": "python",
            "cmdline": ["python", "-m", "http.server", "8000"],
            "expected_in_message": ["2222", "python"]  # Only PID and process name in message
        },
        {
            "pid": 3333,
            "process_name": "node",
            "cmdline": ["node", "app.js"],
            "expected_in_message": ["3333", "node"]
        },
        {
            "pid": 4444,
            "process_name": "java",
            "cmdline": ["java", "-jar", "jetty.jar"],
            "expected_in_message": ["4444", "java"]
        },
    ]
    
    for test_case in test_cases:
        with patch("gui.desktop.supervisor_lifecycle.detect_port_occupant_8000") as mock_detect:
            mock_detect.return_value = {
                "occupied": True,
                "pid": test_case["pid"],
                "process_name": test_case["process_name"],
                "cmdline": test_case["cmdline"],
                "is_fishbro_supervisor": False,
            }
            
            status, details = ensure_supervisor_running()
            
            assert status == SupervisorStatus.PORT_OCCUPIED
            
            # Check message contains PID and process name
            message = details["message"].lower()
            for expected in test_case["expected_in_message"]:
                assert str(expected).lower() in message, \
                    f"Expected '{expected}' in message: {message}"
            
            # Verify cmdline is preserved in details
            assert details["cmdline"] == test_case["cmdline"]


def test_no_auto_kill_on_port_occupied():
    """Verify that desktop NEVER auto-kills port occupants."""
    with patch("gui.desktop.supervisor_lifecycle.detect_port_occupant_8000") as mock_detect, \
         patch("os.kill") as mock_kill, \
         patch("psutil.Process") as mock_process:
        
        # Mock port occupied by non-fishbro (include all required keys)
        mock_detect.return_value = {
            "occupied": True,
            "pid": 9999,
            "process_name": "other_app",
            "cmdline": ["other_app", "--port", "8000"],
            "is_fishbro_supervisor": False,
        }
        
        status, _ = ensure_supervisor_running()
        
        # Verify no kill attempts were made
        mock_kill.assert_not_called()
        
        # Status should be PORT_OCCUPIED, not ERROR
        assert status == SupervisorStatus.PORT_OCCUPIED


if __name__ == "__main__":
    pytest.main([__file__, "-v"])