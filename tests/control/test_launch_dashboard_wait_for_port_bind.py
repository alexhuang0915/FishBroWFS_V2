#!/usr/bin/env python3
"""
Unit tests for launch_dashboard.py bind-wait logic.

Tests the improved process supervision and port binding detection:
1. is_port_bound() function with mocked ss/lsof
2. wait_for_port_bind() timeout behavior
3. start_nicegui_ui() crash detection
4. start_control_api() crash detection
"""

import time
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock, Mock, call
import pytest

# We'll import the functions we need to test
# Note: conftest.py already adds src/ to sys.path
try:
    from scripts.launch_dashboard import (
        is_port_bound,
        wait_for_port_bind,
        start_nicegui_ui,
        start_control_api,
    )
    IMPORT_SUCCESS = True
except ImportError as e:
    print(f"Warning: Could not import launch_dashboard functions: {e}")
    IMPORT_SUCCESS = False


@pytest.mark.skipif(not IMPORT_SUCCESS, reason="launch_dashboard module not available")
class TestIsPortBound:
    """Test is_port_bound() function."""
    
    def test_is_port_bound_ss_success(self, monkeypatch):
        """Test is_port_bound returns True when ss shows port bound."""
        mock_output = "tcp   LISTEN 0  128  *:8080  *:*  users:((\"python3\",pid=12345,fd=3))"
        
        def mock_check_output(cmd, **kwargs):
            if "ss" in " ".join(cmd):
                return mock_output
            else:
                return ""
        
        monkeypatch.setattr(subprocess, "check_output", mock_check_output)
        
        result = is_port_bound(8080)
        assert result is True
    
    def test_is_port_bound_ss_failure_lsof_success(self, monkeypatch):
        """Test is_port_bound uses lsof when ss fails."""
        call_count = 0
        
        def mock_check_output(cmd, **kwargs):
            nonlocal call_count
            call_count += 1
            if "ss" in " ".join(cmd):
                raise subprocess.CalledProcessError(1, cmd, b"")
            elif "lsof" in " ".join(cmd):
                return "COMMAND   PID USER   FD   TYPE DEVICE SIZE/OFF NODE NAME\npython3  12345  user  3u  IPv4  12345  0t0  TCP *:8080 (LISTEN)"
            return ""
        
        monkeypatch.setattr(subprocess, "check_output", mock_check_output)
        
        result = is_port_bound(8080)
        assert result is True
        assert call_count == 2  # ss then lsof
    
    def test_is_port_bound_both_fail(self, monkeypatch):
        """Test is_port_bound returns False when both ss and lsof fail."""
        def mock_check_output(cmd, **kwargs):
            raise subprocess.CalledProcessError(1, cmd, b"")
        
        monkeypatch.setattr(subprocess, "check_output", mock_check_output)
        
        result = is_port_bound(8080)
        assert result is False
    
    def test_is_port_bound_not_listening(self, monkeypatch):
        """Test is_port_bound returns False when port not in LISTEN state."""
        mock_output = "tcp   ESTAB 0  128  *:8080  *:*  users:((\"python3\",pid=12345,fd=3))"
        
        def mock_check_output(cmd, **kwargs):
            if "ss" in " ".join(cmd):
                return mock_output
            else:
                return ""
        
        monkeypatch.setattr(subprocess, "check_output", mock_check_output)
        
        result = is_port_bound(8080)
        assert result is False  # Not LISTEN state
    
    def test_is_port_bound_wrong_port(self, monkeypatch):
        """Test is_port_bound returns False for different port."""
        mock_output = "tcp   LISTEN 0  128  *:8000  *:*  users:((\"python3\",pid=12345,fd=3))"
        
        def mock_check_output(cmd, **kwargs):
            if "ss" in " ".join(cmd):
                return mock_output
            else:
                return ""
        
        monkeypatch.setattr(subprocess, "check_output", mock_check_output)
        
        result = is_port_bound(8080)  # Check 8080 but output shows 8000
        assert result is False


@pytest.mark.skipif(not IMPORT_SUCCESS, reason="launch_dashboard module not available")
class TestWaitForPortBind:
    """Test wait_for_port_bind() function."""
    
    def test_wait_for_port_bind_success(self, monkeypatch):
        """Test wait_for_port_bind returns True when port becomes bound."""
        call_count = 0
        
        def mock_is_port_bound(port, host):
            nonlocal call_count
            call_count += 1
            # Return True on third call
            return call_count >= 3
        
        monkeypatch.setattr("scripts.launch_dashboard.is_port_bound", mock_is_port_bound)
        
        start_time = time.time()
        result = wait_for_port_bind(8080, timeout_seconds=5, check_interval=0.1)
        elapsed = time.time() - start_time
        
        assert result is True
        assert call_count >= 3
        assert elapsed < 5  # Should finish before timeout
    
    def test_wait_for_port_bind_timeout(self, monkeypatch):
        """Test wait_for_port_bind returns False on timeout."""
        def mock_is_port_bound(port, host):
            return False  # Never bound
        
        monkeypatch.setattr("scripts.launch_dashboard.is_port_bound", mock_is_port_bound)
        
        start_time = time.time()
        result = wait_for_port_bind(8080, timeout_seconds=1, check_interval=0.2)
        elapsed = time.time() - start_time
        
        assert result is False
        assert elapsed >= 1  # Should wait at least timeout
    
    def test_wait_for_port_bind_immediate_success(self, monkeypatch):
        """Test wait_for_port_bind returns immediately if already bound."""
        def mock_is_port_bound(port, host):
            return True  # Already bound
        
        monkeypatch.setattr("scripts.launch_dashboard.is_port_bound", mock_is_port_bound)
        
        start_time = time.time()
        result = wait_for_port_bind(8080, timeout_seconds=10, check_interval=1)
        elapsed = time.time() - start_time
        
        assert result is True
        assert elapsed < 1  # Should return immediately


@pytest.mark.skipif(not IMPORT_SUCCESS, reason="launch_dashboard module not available")
class TestStartNiceguiUi:
    """Test start_nicegui_ui() function with crash detection."""
    
    def test_start_nicegui_ui_success(self, monkeypatch, tmp_path):
        """Test successful UI start with port binding."""
        # Mock subprocess.Popen
        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_proc.poll.return_value = None  # Process is running
        mock_proc.stdout.readline.return_value = ""  # No output
        
        # Mock is_port_bound to return True after a few calls
        bound_call_count = 0
        def mock_is_port_bound(port, host):
            nonlocal bound_call_count
            bound_call_count += 1
            return bound_call_count >= 2  # Bound on second check
        
        # Mock write_pidfile and write_metadata
        mock_write_pidfile = MagicMock()
        mock_write_metadata = MagicMock()
        
        monkeypatch.setattr(subprocess, "Popen", MagicMock(return_value=mock_proc))
        monkeypatch.setattr("scripts.launch_dashboard.is_port_bound", mock_is_port_bound)
        monkeypatch.setattr("scripts.launch_dashboard.write_pidfile", mock_write_pidfile)
        monkeypatch.setattr("scripts.launch_dashboard.write_metadata", mock_write_metadata)
        
        pid_dir = tmp_path / "pids"
        pid_dir.mkdir()
        
        result = start_nicegui_ui(
            host="127.0.0.1",
            port=8080,
            control_host="127.0.0.1",
            control_port=8000,
            pid_dir=pid_dir,
        )
        
        assert result == 12345
        assert bound_call_count >= 2
        mock_write_pidfile.assert_called_once_with(12345, "ui", pid_dir)
        mock_write_metadata.assert_called_once()
    
    def test_start_nicegui_ui_crash_before_bind(self, monkeypatch, tmp_path):
        """Test UI process crashes before binding."""
        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_proc.poll.return_value = 1  # Process exited
        mock_proc.returncode = 1
        mock_proc.communicate.return_value = ("Error: Module not found\n", "")
        
        # Mock is_port_bound to never return True
        def mock_is_port_bound(port, host):
            return False
        
        monkeypatch.setattr(subprocess, "Popen", MagicMock(return_value=mock_proc))
        monkeypatch.setattr("scripts.launch_dashboard.is_port_bound", mock_is_port_bound)
        
        pid_dir = tmp_path / "pids"
        pid_dir.mkdir()
        
        result = start_nicegui_ui(
            host="127.0.0.1",
            port=8080,
            control_host="127.0.0.1",
            control_port=8000,
            pid_dir=pid_dir,
        )
        
        assert result is None
        mock_proc.communicate.assert_called_once()
    
    def test_start_nicegui_ui_bind_timeout(self, monkeypatch, tmp_path):
        """Test UI process runs but never binds to port."""
        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_proc.poll.return_value = None  # Process is running
        mock_proc.stdout.readline.return_value = ""  # No output
        mock_proc.terminate.return_value = None
        mock_proc.wait.return_value = None
        mock_proc.kill.return_value = None
        
        # Mock is_port_bound to always return False
        def mock_is_port_bound(port, host):
            return False
        
        monkeypatch.setattr(subprocess, "Popen", MagicMock(return_value=mock_proc))
        monkeypatch.setattr("scripts.launch_dashboard.is_port_bound", mock_is_port_bound)
        
        pid_dir = tmp_path / "pids"
        pid_dir.mkdir()
        
        result = start_nicegui_ui(
            host="127.0.0.1",
            port=8080,
            control_host="127.0.0.1",
            control_port=8000,
            pid_dir=pid_dir,
        )
        
        assert result is None
        mock_proc.terminate.assert_called_once()
        # Should have tried to kill after timeout
    
    def test_start_nicegui_ui_exception(self, monkeypatch, tmp_path):
        """Test UI start raises exception."""
        monkeypatch.setattr(subprocess, "Popen", MagicMock(side_effect=Exception("Failed to start")))
        
        pid_dir = tmp_path / "pids"
        pid_dir.mkdir()
        
        result = start_nicegui_ui(
            host="127.0.0.1",
            port=8080,
            control_host="127.0.0.1",
            control_port=8000,
            pid_dir=pid_dir,
        )
        
        assert result is None


@pytest.mark.skipif(not IMPORT_SUCCESS, reason="launch_dashboard module not available")
class TestStartControlApi:
    """Test start_control_api() function with crash detection."""
    
    def test_start_control_api_success(self, monkeypatch, tmp_path):
        """Test successful Control API start with port binding."""
        mock_proc = MagicMock()
        mock_proc.pid = 54321
        mock_proc.poll.return_value = None
        mock_proc.stdout.readline.return_value = ""
        
        bound_call_count = 0
        def mock_is_port_bound(port, host):
            nonlocal bound_call_count
            bound_call_count += 1
            return bound_call_count >= 2
        
        mock_write_pidfile = MagicMock()
        mock_write_metadata = MagicMock()
        
        monkeypatch.setattr(subprocess, "Popen", MagicMock(return_value=mock_proc))
        monkeypatch.setattr("scripts.launch_dashboard.is_port_bound", mock_is_port_bound)
        monkeypatch.setattr("scripts.launch_dashboard.write_pidfile", mock_write_pidfile)
        monkeypatch.setattr("scripts.launch_dashboard.write_metadata", mock_write_metadata)
        
        pid_dir = tmp_path / "pids"
        pid_dir.mkdir()
        
        result = start_control_api(
            host="127.0.0.1",
            port=8000,
            pid_dir=pid_dir,
        )
        
        assert result == 54321
        assert bound_call_count >= 2
        mock_write_pidfile.assert_called_once_with(54321, "control", pid_dir)
        mock_write_metadata.assert_called_once()
    
    def test_start_control_api_crash_before_bind(self, monkeypatch, tmp_path):
        """Test Control API process crashes before binding."""
        mock_proc = MagicMock()
        mock_proc.pid = 54321
        mock_proc.poll.return_value = 1
        mock_proc.returncode = 1
        mock_proc.communicate.return_value = ("Error: Import failed\n", "")
        
        def mock_is_port_bound(port, host):
            return False
        
        monkeypatch.setattr(subprocess, "Popen", MagicMock(return_value=mock_proc))
        monkeypatch.setattr("scripts.launch_dashboard.is_port_bound", mock_is_port_bound)
        
        pid_dir = tmp_path / "pids"
        pid_dir.mkdir()
        
        result = start_control_api(
            host="127.0.0.1",
            port=8000,
            pid_dir=pid_dir,
        )
        
        assert result is None
        mock_proc.communicate.assert_called_once()


@pytest.mark.skipif(not IMPORT_SUCCESS, reason="launch_dashboard module not available")
class TestIntegrationScenarios:
    """Integration scenarios for bind-wait logic."""
    
    def test_restart_ui_scenario_crash_recovery(self, monkeypatch):
        """Simulate restart-ui scenario where UI crashes and is detected."""
        # This is a high-level test to ensure the logic works together
        # We'll mock the key functions and verify behavior
        
        # Track calls
        calls = []
        
        def mock_is_port_bound(port, host):
            calls.append(("is_port_bound", port, host))
            return False  # Never binds (simulating crash)
        
        def mock_popen(cmd, **kwargs):
            calls.append(("Popen", cmd))
            mock_proc = MagicMock()
            mock_proc.pid = 99999
            mock_proc.poll.return_value = 1  # Crashed immediately
            mock_proc.returncode = 1
            mock_proc.communicate.return_value = ("UI crashed on startup\n", "")
            return mock_proc
        
        monkeypatch.setattr("scripts.launch_dashboard.is_port_bound", mock_is_port_bound)
        monkeypatch.setattr(subprocess, "Popen", mock_popen)
        
        # Import and test
        from scripts.launch_dashboard import start_nicegui_ui
        
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            pid_dir = Path(tmpdir) / "pids"
            pid_dir.mkdir()
            
            result = start_nicegui_ui(
                host="127.0.0.1",
                port=8080,
                control_host="127.0.0.1",
                control_port=8000,
                pid_dir=pid_dir,
            )
        
        assert result is None
        # Should have detected crash and returned None
        assert any("Popen" in str(call) for call in calls)
    
    def test_successful_bind_with_output_capture(self, monkeypatch):
        """Test that output is captured during bind wait."""
        output_lines = [
            "Starting NiceGUI...",
            "Loading modules...",
            "Server ready on port 8080",
        ]
        output_index = 0
        
        def mock_stdout_readline():
            nonlocal output_index
            if output_index < len(output_lines):
                line = output_lines[output_index]
                output_index += 1
                return line + "\n"
            return ""
        
        mock_proc = MagicMock()
        mock_proc.pid = 12345
        mock_proc.poll.return_value = None
        mock_proc.stdout.readline = mock_stdout_readline
        
        bound_call_count = 0
        def mock_is_port_bound(port, host):
            nonlocal bound_call_count
            bound_call_count += 1
            return bound_call_count >= 3  # Bind on third check
        
        monkeypatch.setattr(subprocess, "Popen", MagicMock(return_value=mock_proc))
        monkeypatch.setattr("scripts.launch_dashboard.is_port_bound", mock_is_port_bound)
        monkeypatch.setattr("scripts.launch_dashboard.write_pidfile", MagicMock())
        monkeypatch.setattr("scripts.launch_dashboard.write_metadata", MagicMock())
        
        from scripts.launch_dashboard import start_nicegui_ui
        
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            pid_dir = Path(tmpdir) / "pids"
            pid_dir.mkdir()
            
            result = start_nicegui_ui(
                host="127.0.0.1",
                port=8080,
                control_host="127.0.0.1",
                control_port=8000,
                pid_dir=pid_dir,
            )
