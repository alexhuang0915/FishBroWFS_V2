"""
Test supervisor handling of unknown job types v1.
"""
import json
import subprocess
from pathlib import Path
import pytest

from src.control.supervisor.db import SupervisorDB
from src.control.supervisor.models import JobSpec
from src.control.supervisor.job_handler import validate_job_spec, get_handler


def test_unknown_job_type_rejection():
    """Test that unknown job types are rejected during validation."""
    spec = JobSpec(job_type="NON_EXISTENT_TYPE", params={})
    
    with pytest.raises(ValueError, match="Unknown job_type"):
        validate_job_spec(spec)


def test_get_handler_unknown():
    """Test get_handler returns None for unknown types."""
    handler = get_handler("NON_EXISTENT_TYPE")
    assert handler is None


def test_submit_unknown_job_type(tmp_path: Path):
    """Test submitting unknown job type via DB (should still be allowed)."""
    db_path = tmp_path / "test.db"
    db = SupervisorDB(db_path)
    
    # DB submission doesn't validate handler existence
    spec = JobSpec(job_type="NON_EXISTENT_TYPE", params={"foo": "bar"})
    job_id = db.submit_job(spec)
    
    # Job should be QUEUED
    job = db.get_job_row(job_id)
    assert job is not None
    assert job.job_type == "NON_EXISTENT_TYPE"
    assert job.state == "QUEUED"


def test_bootstrap_unknown_job_type(tmp_path: Path):
    """Test bootstrap fails for unknown job type."""
    db_path = tmp_path / "jobs_v2.db"
    db = SupervisorDB(db_path)
    
    # Submit unknown job type
    spec = JobSpec(job_type="NON_EXISTENT_TYPE", params={"foo": "bar"})
    job_id = db.submit_job(spec)
    
    # Mark as RUNNING (simulating supervisor fetching it)
    with db._connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("""
            UPDATE jobs
            SET state = 'RUNNING', updated_at = ?
            WHERE job_id = ?
        """, ("2026-01-01T00:00:00+00:00", job_id))
        conn.commit()
    
    # Try to run bootstrap
    import sys
    import os
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"
    cmd = [
        sys.executable, "-m", "src.control.supervisor.bootstrap",
        "--db", str(db_path),
        "--job-id", job_id,
        "--artifacts-root", str(tmp_path / "artifacts")
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    
    # Should fail with error about unknown job type
    assert result.returncode == 1
    assert "unknown_job_type" in result.stderr or "ERROR" in result.stderr
    
    # Job should be marked FAILED
    job = db.get_job_row(job_id)
    assert job.state == "FAILED"
    assert "unknown_job_type" in job.state_reason.lower()


def test_supervisor_handles_unknown_job_type(tmp_path: Path):
    """Test supervisor workflow with unknown job type."""
    db_path = tmp_path / "jobs_v2.db"
    db = SupervisorDB(db_path)
    
    # Submit unknown job type
    spec = JobSpec(job_type="NON_EXISTENT_TYPE", params={"foo": "bar"})
    job_id = db.submit_job(spec)
    
    # Create supervisor
    from src.control.supervisor.supervisor import Supervisor
    supervisor = Supervisor(
        db_path=db_path,
        max_workers=1,
        tick_interval=0.1,
        artifacts_root=tmp_path / "artifacts"
    )
    
    # Run ticks - supervisor will fetch and spawn worker
    for _ in range(5):
        supervisor.tick()
        import time
        time.sleep(0.1)
        
        # Check job state
        job = db.get_job_row(job_id)
        if job and job.state == "FAILED":
            break
    
    # Job should be FAILED due to unknown job type
    job = db.get_job_row(job_id)
    assert job is not None
    assert job.state == "FAILED"
    assert "unknown_job_type" in job.state_reason.lower()
    
    supervisor.shutdown()


def test_cli_submit_unknown_job_type(tmp_path: Path):
    """Test CLI rejects unknown job type on submission."""
    db_path = tmp_path / "jobs_v2.db"
    
    import sys
    cmd = [
        sys.executable, "-m", "src.control.supervisor.cli",
        "--db", str(db_path),
        "submit",
        "--job-type", "NON_EXISTENT_TYPE",
        "--params-json", '{"foo": "bar"}'
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    # Should fail during validation
    assert result.returncode == 1
    assert "Unknown job_type" in result.stderr or "unknown_job_type" in result.stderr


def test_validation_error_marking(tmp_path: Path):
    """Test that validation errors mark job as FAILED."""
    db_path = tmp_path / "test.db"
    db = SupervisorDB(db_path)
    
    # Submit PING job with invalid params
    spec = JobSpec(job_type="PING", params={"sleep_sec": -1})  # Invalid negative sleep
    job_id = db.submit_job(spec)
    
    # Mark as RUNNING
    with db._connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("""
            UPDATE jobs
            SET state = 'RUNNING', updated_at = ?
            WHERE job_id = ?
        """, ("2026-01-01T00:00:00+00:00", job_id))
        conn.commit()
    
    # Try to run bootstrap
    import sys
    import os
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"
    cmd = [
        sys.executable, "-m", "src.control.supervisor.bootstrap",
        "--db", str(db_path),
        "--job-id", job_id,
        "--artifacts-root", str(tmp_path / "artifacts")
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    
    # Should fail with validation error
    assert result.returncode == 1
    assert "validation_error" in result.stderr or "ERROR" in result.stderr
    
    # Job should be marked FAILED with validation error
    job = db.get_job_row(job_id)
    assert job.state == "FAILED"
    assert "validation_error" in job.state_reason.lower()


def test_handler_registry_isolation():
    """Test that handler registry is isolated to this module."""
    from src.control.supervisor.job_handler import HANDLER_REGISTRY
    
    # PING should be registered
    assert "PING" in HANDLER_REGISTRY
    
    # Unknown type should not be there
    assert "NON_EXISTENT_TYPE" not in HANDLER_REGISTRY
    
    # Can't register empty string
    from src.control.supervisor.job_handler import register_handler
    from src.control.supervisor.handlers.ping import ping_handler
    
    with pytest.raises(ValueError, match="non-empty str"):
        register_handler("", ping_handler)
    
    with pytest.raises(ValueError, match="non-empty str"):
        register_handler(None, ping_handler)  # type: ignore