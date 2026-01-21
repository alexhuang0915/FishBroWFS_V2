"""
Test that desktop uses psutil for port detection (no shell parsing).

Monkeypatch psutil.net_connections to verify desktop code path uses psutil
and doesn't fall back to shell commands (ss/lsof/netstat).
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../src"))

from gui.desktop.supervisor_lifecycle import (
    is_port_listening_8000,
    detect_port_occupant_8000,
)


def test_port_detection_uses_psutil():
    """Verify is_port_listening_8000 calls psutil.net_connections."""
    with patch("psutil.net_connections") as mock_net_connections:
        # Mock psutil to return a listening connection on port 8000
        mock_conn = Mock()
        mock_conn.status = "LISTEN"
        mock_conn.laddr.port = 8000
        mock_conn.laddr.ip = "127.0.0.1"
        mock_net_connections.return_value = [mock_conn]
        
        result = is_port_listening_8000()
        
        # Verify psutil was called
        mock_net_connections.assert_called_once_with(kind="inet")
        assert result is True


def test_port_detection_no_shell_commands():
    """Ensure no subprocess calls are made for port detection."""
    with patch("psutil.net_connections") as mock_psutil, \
         patch("subprocess.run") as mock_subprocess, \
         patch("socket.socket") as mock_socket:
        
        # Make psutil raise AccessDenied to trigger fallback
        from psutil import AccessDenied
        mock_psutil.side_effect = AccessDenied()
        
        # Mock socket connect for fallback
        mock_sock_instance = Mock()
        mock_sock_instance.connect_ex.return_value = 0
        mock_sock_instance.settimeout = Mock()
        mock_socket.return_value = mock_sock_instance
        
        result = is_port_listening_8000()
        
        # Verify subprocess was NOT called (no shell parsing)
        mock_subprocess.assert_not_called()
        
        # Socket fallback is allowed when psutil fails
        assert result is True


def test_detect_port_occupant_uses_psutil():
    """Verify detect_port_occupant_8000 uses psutil Process API."""
    with patch("psutil.net_connections") as mock_net_connections, \
         patch("psutil.Process") as mock_process:
        
        # Mock a listening connection
        mock_conn = Mock()
        mock_conn.status = "LISTEN"
        mock_conn.laddr.port = 8000
        mock_conn.laddr.ip = "127.0.0.1"
        mock_conn.pid = 12345
        mock_net_connections.return_value = [mock_conn]
        
        # Mock process details
        mock_proc = Mock()
        mock_proc.name.return_value = "uvicorn"
        mock_proc.cmdline.return_value = ["python", "-m", "uvicorn", "control.api:app"]
        mock_process.return_value = mock_proc
        
        result = detect_port_occupant_8000()
        
        # Verify psutil APIs were called
        mock_net_connections.assert_called_once_with(kind="inet")
        mock_process.assert_called_once_with(12345)
        
        # Verify result structure
        assert result["occupied"] is True
        assert result["pid"] == 12345
        assert result["process_name"] == "uvicorn"
        assert result["is_fishbro_supervisor"] is True


def test_no_shell_parsing_in_occupant_detection():
    """Ensure detect_port_occupant_8000 doesn't use shell commands."""
    with patch("psutil.net_connections") as mock_psutil, \
         patch("subprocess.run") as mock_subprocess, \
         patch("subprocess.Popen") as mock_popen:
        
        # Make psutil fail
        from psutil import AccessDenied
        mock_psutil.side_effect = AccessDenied()
        
        # Mock socket for fallback
        with patch("socket.socket") as mock_socket:
            mock_sock_instance = Mock()
            mock_sock_instance.connect_ex.return_value = 0
            mock_sock_instance.settimeout = Mock()
            mock_socket.return_value = mock_sock_instance
            
            result = detect_port_occupant_8000()
            
            # Verify no shell commands were executed
            mock_subprocess.assert_not_called()
            mock_popen.assert_not_called()
            
            # Should still detect port as occupied via socket
            assert result["occupied"] is True
            assert result["pid"] is None  # Can't get PID via socket


def test_fishbro_supervisor_detection_logic():
    """Test the logic that identifies fishbro supervisor processes."""
    test_cases = [
        # (cmdline, expected_is_fishbro)
        (["python", "-m", "uvicorn", "control.api:app"], True),
        (["python", "-m", "uvicorn", "control.api:app", "--host", "127.0.0.1"], True),
        (["/usr/bin/python3", "src/control/api.py"], True),
        (["python", "some_other_app.py"], False),
        (["node", "server.js"], False),
        (["python", "-m", "http.server", "8000"], False),
    ]
    
    with patch("psutil.net_connections") as mock_net_connections, \
         patch("psutil.Process") as mock_process:
        
        mock_conn = Mock()
        mock_conn.status = "LISTEN"
        mock_conn.laddr.port = 8000
        mock_conn.pid = 12345
        mock_net_connections.return_value = [mock_conn]
        
        for cmdline, expected in test_cases:
            mock_proc = Mock()
            mock_proc.name.return_value = "python"
            mock_proc.cmdline.return_value = cmdline
            mock_process.return_value = mock_proc
            
            result = detect_port_occupant_8000()
            assert result["is_fishbro_supervisor"] == expected, \
                f"Failed for cmdline: {cmdline}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])