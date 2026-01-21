"""
Test that supervisor binds to 127.0.0.1:8000 (loopback only).

Ensures Supervisor server:
- Listens on 127.0.0.1:8000
- NOT bound to 0.0.0.0
- Respects explicit host/port flags
"""

import subprocess
import time
import socket
import psutil
import pytest
import os
import sys
from pathlib import Path


@pytest.mark.integration
@pytest.mark.slow
def test_supervisor_binds_loopback_only():
    """Start supervisor in test mode and verify it binds to 127.0.0.1:8000 only."""
    # Start supervisor with explicit loopback bind
    cmd = [
        sys.executable, "-m", "uvicorn", "control.api:app",
        "--host", "127.0.0.1",
        "--port", "8000",
    ]
    repo_root = Path(__file__).resolve().parents[3]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")
    
    proc = subprocess.Popen(
        cmd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True
    )
    
    try:
        # Wait for startup
        for _ in range(30):
            if any(
                conn.status == psutil.CONN_LISTEN and conn.laddr.port == 8000
                for conn in psutil.net_connections(kind="inet")
            ):
                break
            time.sleep(0.1)
        
        # Check listening connections
        loopback_found = False
        wildcard_found = False
        
        for conn in psutil.net_connections(kind="inet"):
            if conn.status == psutil.CONN_LISTEN and conn.laddr.port == 8000:
                if conn.laddr.ip == "127.0.0.1":
                    loopback_found = True
                elif conn.laddr.ip == "0.0.0.0":
                    wildcard_found = True
        
        # Verify loopback binding
        assert loopback_found, "Supervisor should be listening on 127.0.0.1:8000"
        assert not wildcard_found, "Supervisor should NOT be listening on 0.0.0.0:8000"
        
        # Test socket connection to loopback
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(("127.0.0.1", 8000))
        sock.close()
        assert result == 0, "Should be able to connect to 127.0.0.1:8000"
        
        # Test socket connection to localhost (should also work)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(("localhost", 8000))
        sock.close()
        assert result == 0, "Should be able to connect to localhost:8000"
        
    finally:
        # Clean up
        proc.terminate()
        proc.wait(timeout=5)


@pytest.mark.integration
@pytest.mark.slow
def test_supervisor_rejects_wildcard_bind():
    """Ensure supervisor with explicit 127.0.0.1 flag doesn't bind to 0.0.0.0."""
    # This test is essentially covered by the first test,
    # but we make the assertion explicit
    cmd = [
        sys.executable, "-m", "uvicorn", "control.api:app",
        "--host", "127.0.0.1",
        "--port", "8000",
    ]
    repo_root = Path(__file__).resolve().parents[3]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root / "src")
    
    proc = subprocess.Popen(
        cmd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True
    )
    
    try:
        for _ in range(30):
            if any(
                conn.status == psutil.CONN_LISTEN and conn.laddr.port == 8000
                for conn in psutil.net_connections(kind="inet")
            ):
                break
            time.sleep(0.1)
        
        # Check for any 0.0.0.0 bindings on port 8000
        for conn in psutil.net_connections(kind="inet"):
            if (conn.status == psutil.CONN_LISTEN and 
                conn.laddr.port == 8000 and 
                conn.laddr.ip == "0.0.0.0"):
                pytest.fail(f"Supervisor bound to 0.0.0.0:8000 (PID: {conn.pid})")
                
    finally:
        proc.terminate()
        proc.wait(timeout=5)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])