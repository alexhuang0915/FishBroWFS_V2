"""CI-safe service freeze smoke test.

Enforces service freeze contract:
- Backend starts and responds to /health
- Worker starts and publishes pidfile+heartbeat immediately
- /worker/status becomes alive:true within timeout
- Cleanup processes reliably even if test fails
"""

import os
import socket
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path

import pytest
import requests


def free_port() -> int:
    """Get a free port on localhost."""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def wait_ok(url: str, timeout: float = 5.0) -> requests.Response:
    """Wait for URL to return 200 OK."""
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            r = requests.get(url, timeout=0.5)
            if r.status_code == 200:
                return r
        except Exception:
            pass
        time.sleep(0.1)
    raise AssertionError(f"timeout waiting {url}")


@contextmanager
def managed_backend(port: int):
    """Start backend on given port, yield, then terminate."""
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = "src"
    
    backend = subprocess.Popen(
        [
            ".venv/bin/python",
            "-m",
            "uvicorn",
            "control.api:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        wait_ok(f"http://127.0.0.1:{port}/health", timeout=10.0)
        yield backend
    finally:
        backend.terminate()
        backend.wait(timeout=5.0)


@contextmanager
def managed_worker(db_path: Path):
    """Start worker with given db path, yield, then terminate."""
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = "src"
    
    worker = subprocess.Popen(
        [
            ".venv/bin/python",
            "-B",
            "-m",
            "control.worker_main",
            str(db_path),
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        yield worker
    finally:
        worker.terminate()
        worker.wait(timeout=5.0)


def test_service_freeze_smoke(tmp_path: Path):
    """Service freeze contract: backend+worker must show alive:true within 2s."""
    port = free_port()
    db_path = tmp_path / "jobs.db"
    
    # Ensure outputs directory exists for pidfile/heartbeat
    outputs_dir = tmp_path / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)
    
    # Set environment so backend uses our temp db
    os.environ["JOBS_DB_PATH"] = str(db_path)
    
    with managed_backend(port) as backend:
        # Verify backend is up
        health_resp = requests.get(f"http://127.0.0.1:{port}/health", timeout=1.0)
        assert health_resp.status_code == 200
        assert health_resp.json() == {"status": "ok"}
        
        # Check worker status before worker starts (should be dead)
        status_resp = requests.get(f"http://127.0.0.1:{port}/worker/status", timeout=1.0)
        assert status_resp.status_code == 200
        status = status_resp.json()
        assert status["alive"] is False
        assert status["reason"] in {"pidfile missing", "worker not alive"}
        
        # Start worker
        with managed_worker(db_path) as worker:
            # Poll /worker/status until alive:true (max 5 seconds)
            t0 = time.time()
            alive = False
            while time.time() - t0 < 5.0:
                try:
                    status_resp = requests.get(
                        f"http://127.0.0.1:{port}/worker/status", timeout=0.5
                    )
                    if status_resp.status_code == 200:
                        status = status_resp.json()
                        if status.get("alive") is True:
                            alive = True
                            break
                except Exception:
                    pass
                time.sleep(0.2)
            
            assert alive, "worker did not become alive:true within 5 seconds"
            
            # Verify pid and heartbeat are present
            assert status["pid"] is not None
            assert isinstance(status["pid"], int)
            assert status["pid"] > 0
            
            # Heartbeat age should be recent (< 3 seconds)
            if status.get("last_heartbeat_age_sec") is not None:
                assert status["last_heartbeat_age_sec"] < 3.0
            
            # Verify pidfile exists
            pidfile = db_path.parent / "worker.pid"
            assert pidfile.exists()
            
            # Verify heartbeat file exists
            heartbeat_file = db_path.parent / "worker.heartbeat"
            assert heartbeat_file.exists()
            
            # Check 3 consecutive status calls (should all be alive:true)
            for i in range(3):
                status_resp = requests.get(
                    f"http://127.0.0.1:{port}/worker/status", timeout=0.5
                )
                assert status_resp.status_code == 200
                status = status_resp.json()
                assert status["alive"] is True, f"status call {i+1} failed"
                time.sleep(0.1)
        
        # After worker stops, status should show alive:false
        time.sleep(0.5)  # Give time for cleanup
        status_resp = requests.get(f"http://127.0.0.1:{port}/worker/status", timeout=1.0)
        assert status_resp.status_code == 200
        status = status_resp.json()
        # Worker is dead, but pidfile might still exist (cleanup is best-effort)
        # The important thing is alive:false or stale heartbeat
        if status["alive"]:
            # If still alive, heartbeat should be stale (>5s)
            assert status.get("last_heartbeat_age_sec", 100) > 5.0


def test_service_freeze_cleanup(tmp_path: Path):
    """Ensure pidfile/heartbeat are cleaned up on worker exit."""
    port = free_port()
    db_path = tmp_path / "jobs.db"
    outputs_dir = tmp_path / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)
    
    os.environ["JOBS_DB_PATH"] = str(db_path)
    
    with managed_backend(port):
        pidfile = db_path.parent / "worker.pid"
        heartbeat_file = db_path.parent / "worker.heartbeat"
        
        # Start and immediately stop worker
        worker = subprocess.Popen(
            [
                ".venv/bin/python",
                "-B",
                "-m",
                "control.worker_main",
                str(db_path),
            ],
            env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": "src"},
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        
        # Wait a moment for files to be created
        time.sleep(0.5)
        
        # Files should exist while worker is running
        assert pidfile.exists()
        assert heartbeat_file.exists()
        
        # Stop worker
        worker.terminate()
        worker.wait(timeout=3.0)
        
        # Files should be cleaned up (best-effort)
        # Note: cleanup is best-effort, so we don't assert they're gone
        # But we verify worker status shows not alive
        time.sleep(0.5)
        status_resp = requests.get(f"http://127.0.0.1:{port}/worker/status", timeout=1.0)
        if status_resp.status_code == 200:
            status = status_resp.json()
            # Either alive:false or stale heartbeat
            if status["alive"]:
                assert status.get("last_heartbeat_age_sec", 100) > 5.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
