"""
Test PING handler contract v1.
"""
import json
import time
import subprocess
import threading
from pathlib import Path
import pytest

from src.control.supervisor.db import SupervisorDB
from src.control.supervisor.models import JobSpec
from src.control.supervisor.supervisor import Supervisor


def test_ping_handler_registered():
    """Test that PING handler is registered."""
    from src.control.supervisor.job_handler import get_handler
    handler = get_handler("PING")
    assert handler is not None
    assert handler.__class__.__name__ == "PingHandler"


def test_ping_validate_params():
    """Test PING parameter validation."""
    from src.control.supervisor.handlers.ping import PingHandler
    handler = PingHandler()
    
    # Valid params
    handler.validate_params({"sleep_sec": 0.1})
    handler.validate_params({"sleep_sec": 0})
    handler.validate_params({"sleep_sec": 3600})
    handler.validate_params({})  # default sleep_sec
    
    # Invalid params
    with pytest.raises(ValueError, match="must be numeric"):
        handler.validate_params({"sleep_sec": "not a number"})
    
    with pytest.raises(ValueError, match="must be non-negative"):
        handler.validate_params({"sleep_sec": -1})
    
    with pytest.raises(ValueError, match="too large"):
        handler.validate_params({"sleep_sec": 3601})


def test_ping_execute_quick(tmp_path: Path):
    """Test PING execution with minimal sleep."""
    from src.control.supervisor.handlers.ping import PingHandler
    from src.control.supervisor.job_handler import JobContext
    
    handler = PingHandler()
    
    # Mock DB
    class MockDB:
        def update_heartbeat(self, job_id, progress=None, phase=None):
            pass
        def is_abort_requested(self, job_id):
            return False
    
    mock_db = MockDB()
    context = JobContext("test_job", mock_db, str(tmp_path))
    
    # Execute with tiny sleep
    start = time.time()
    result = handler.execute({"sleep_sec": 0.01}, context)
    elapsed = time.time() - start
    
    assert result["ok"] is True
    assert result["elapsed"] >= 0.01
    assert elapsed < 0.5  # Should be quick


def test_ping_execute_with_abort(tmp_path: Path):
    """Test PING execution with abort request."""
    from src.control.supervisor.handlers.ping import PingHandler
    from src.control.supervisor.job_handler import JobContext
    
    handler = PingHandler()
    
    abort_called = [False]
    
    class MockDB:
        def update_heartbeat(self, job_id, progress=None, phase=None):
            pass
        def is_abort_requested(self, job_id):
            # Return True after first check to simulate abort
            if not abort_called[0]:
                abort_called[0] = True
                return False
            return True
    
    mock_db = MockDB()
    context = JobContext("test_job", mock_db, str(tmp_path))
    
    # Execute with longer sleep but should abort quickly
    result = handler.execute({"sleep_sec": 10.0}, context)
    
    assert "aborted" in result
    assert result["aborted"] is True
    assert result["elapsed"] < 1.0  # Should abort quickly


def test_ping_integration_smoke(tmp_path: Path):
    """Smoke test: submit PING job and run supervisor."""
    db_path = tmp_path / "jobs_v2.db"
    db = SupervisorDB(db_path)
    
    # Submit PING job
    spec = JobSpec(job_type="PING", params={"sleep_sec": 0.1})
    job_id = db.submit_job(spec)
    
    # Create supervisor with max_workers=1
    supervisor = Supervisor(
        db_path=db_path,
        max_workers=1,
        tick_interval=0.1,
        artifacts_root=tmp_path / "artifacts"
    )
    
    # Run a few ticks
    for _ in range(10):
        supervisor.tick()
        time.sleep(0.1)
        
        # Check job state
        job = db.get_job_row(job_id)
        if job and job.state == "SUCCEEDED":
            break
    
    # Verify job succeeded
    job = db.get_job_row(job_id)
    assert job is not None
    assert job.state == "SUCCEEDED"
    
    # Verify result
    result = json.loads(job.result_json)
    assert result["ok"] is True
    assert result["elapsed"] >= 0.1
    
    # Clean up
    supervisor.shutdown()


def test_ping_cli_submit(tmp_path: Path):
    """Test CLI submission of PING job."""
    db_path = tmp_path / "jobs_v2.db"
    
    # Use python -m to submit
    import sys
    cmd = [
        sys.executable, "-m", "src.control.supervisor.cli",
        "--db", str(db_path),
        "submit",
        "--job-type", "PING",
        "--params-json", '{"sleep_sec": 0.05}'
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    assert result.returncode == 0
    assert "Submitted job:" in result.stdout
    
    # Extract job ID
    lines = result.stdout.strip().split("\n")
    job_line = [l for l in lines if "Submitted job:" in l][0]
    job_id = job_line.split(":")[1].strip()
    
    # Verify job exists in DB
    db = SupervisorDB(db_path)
    job = db.get_job_row(job_id)
    assert job is not None
    assert job.job_type == "PING"