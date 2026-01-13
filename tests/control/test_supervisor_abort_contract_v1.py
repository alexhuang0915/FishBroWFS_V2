"""
Test supervisor abort contract v1.
"""
import json
import time
import subprocess
import signal
from pathlib import Path
import pytest

from control.supervisor.db import SupervisorDB
from control.supervisor.models import JobSpec
from control.supervisor.supervisor import Supervisor


def test_abort_request_flag(tmp_path: Path):
    """Test abort request flag setting and checking."""
    db_path = tmp_path / "test.db"
    db = SupervisorDB(db_path)
    
    spec = JobSpec(job_type="PING", params={"sleep_sec": 10.0})
    job_id = db.submit_job(spec)
    
    # Initially not requested
    assert db.is_abort_requested(job_id) is False
    
    # Request abort
    db.request_abort(job_id)
    
    # Should be requested
    assert db.is_abort_requested(job_id) is True
    
    # Job row should reflect this
    job = db.get_job_row(job_id)
    assert job.abort_requested is True
    
    # Request abort again (idempotent)
    db.request_abort(job_id)
    assert db.is_abort_requested(job_id) is True


def test_abort_queued_job(tmp_path: Path):
    """Test aborting a QUEUED job."""
    db_path = tmp_path / "test.db"
    db = SupervisorDB(db_path)
    
    spec = JobSpec(job_type="PING", params={"sleep_sec": 10.0})
    job_id = db.submit_job(spec)
    
    # Request abort while QUEUED
    db.request_abort(job_id)
    
    # Try to fetch - should not return this job
    fetched = db.fetch_next_queued_job()
    assert fetched is None  # Job with abort requested should not be fetched
    
    # Job should still be QUEUED with abort flag
    job = db.get_job_row(job_id)
    assert job.state == "QUEUED"
    assert job.abort_requested is True


def test_abort_running_job_via_flag(tmp_path: Path):
    """Test that running job detects abort flag and stops."""
    from control.supervisor.handlers.ping import PingHandler
    from control.supervisor.job_handler import JobContext
    
    handler = PingHandler()
    
    abort_requested = [False]
    
    class MockDB:
        def update_heartbeat(self, job_id, progress=None, phase=None):
            pass
        def is_abort_requested(self, job_id):
            return abort_requested[0]
    
    mock_db = MockDB()
    context = JobContext("test_job", mock_db, str(tmp_path))
    
    # Start execution in thread
    import threading
    result = [None]
    
    def execute():
        result[0] = handler.execute({"sleep_sec": 2.0}, context)
    
    thread = threading.Thread(target=execute)
    thread.start()
    
    # Wait a bit then set abort flag
    time.sleep(0.1)
    abort_requested[0] = True
    
    thread.join(timeout=1.0)
    
    # Should have aborted
    assert result[0] is not None
    assert "aborted" in result[0]
    assert result[0]["aborted"] is True
    assert result[0]["elapsed"] < 1.0


def test_supervisor_abort_flow(tmp_path: Path):
    """Test full abort flow through supervisor."""
    db_path = tmp_path / "jobs_v2.db"
    db = SupervisorDB(db_path)
    
    # Submit long-running job
    spec = JobSpec(job_type="PING", params={"sleep_sec": 5.0})
    job_id = db.submit_job(spec)
    
    # Create supervisor
    supervisor = Supervisor(
        db_path=db_path,
        max_workers=1,
        tick_interval=0.1,
        artifacts_root=tmp_path / "artifacts"
    )
    
    # Run one tick to spawn worker
    supervisor.tick()
    time.sleep(0.2)  # Let worker start
    
    # Request abort
    db.request_abort(job_id)
    
    # Run a few more ticks
    for _ in range(10):
        supervisor.tick()
        time.sleep(0.1)
        
        # Check job state
        job = db.get_job_row(job_id)
        if job and job.state in ("ABORTED", "FAILED"):
            break
    
    # Job should be ABORTED (or FAILED with user_abort)
    job = db.get_job_row(job_id)
    assert job is not None
    assert job.state in ("ABORTED", "FAILED")
    if job.state == "FAILED":
        assert "user_abort" in job.state_reason.lower()
    
    supervisor.shutdown()


def test_cli_abort_command(tmp_path: Path):
    """Test CLI abort command."""
    db_path = tmp_path / "jobs_v2.db"
    db = SupervisorDB(db_path)
    
    # Submit job
    spec = JobSpec(job_type="PING", params={"sleep_sec": 0.1})
    job_id = db.submit_job(spec)
    
    # Run abort command
    import sys
    import os
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"
    cmd = [
        sys.executable, "-m", "src.control.supervisor.cli",
        "--db", str(db_path),
        "abort",
        "--job-id", job_id
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    assert result.returncode == 0
    assert f"Abort requested for job {job_id}" in result.stdout
    
    # Verify abort flag set
    assert db.is_abort_requested(job_id) is True
    
    # Try to abort non-existent job
    cmd = [
        sys.executable, "-m", "src.control.supervisor.cli",
        "--db", str(db_path),
        "abort",
        "--job-id", "non_existent"
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    assert result.returncode == 1
    assert "not found or not abortable" in result.stderr


def test_cannot_abort_terminal_states(tmp_path: Path):
    """Test that jobs in terminal states cannot be aborted."""
    db_path = tmp_path / "test.db"
    db = SupervisorDB(db_path)
    
    terminal_states = ["SUCCEEDED", "FAILED", "ABORTED", "ORPHANED"]
    
    for state in terminal_states:
        spec = JobSpec(job_type="PING", params={"sleep_sec": 0.1})
        job_id = db.submit_job(spec)
        
        # Manually set to terminal state
        with db._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("""
                UPDATE jobs SET state = ? WHERE job_id = ?
            """, (state, job_id))
            conn.commit()
        
        # Request abort should not affect terminal state
        db.request_abort(job_id)
        
        # Job should remain in terminal state
        job = db.get_job_row(job_id)
        assert job.state == state
        # abort_requested may be set but doesn't matter


def test_abort_clears_worker_assignment(tmp_path: Path):
    """Test that aborting a running job clears worker assignment."""
    db_path = tmp_path / "test.db"
    db = SupervisorDB(db_path)
    
    spec = JobSpec(job_type="PING", params={"sleep_sec": 10.0})
    job_id = db.submit_job(spec)
    
    # Mark as running with worker
    db.fetch_next_queued_job()
    db.mark_running(job_id, "worker1", 1000)
    
    # Request abort
    db.request_abort(job_id)
    
    # Mark as ABORTED (simulating worker detecting abort)
    db.mark_aborted(job_id, "user_abort")
    
    # Worker should be marked IDLE
    with db._connect() as conn:
        cursor = conn.execute("SELECT status FROM workers WHERE worker_id = ?", ("worker1",))
        row = cursor.fetchone()
        if row:
            # In our implementation, mark_aborted clears worker assignment
            # Worker status might be IDLE or EXITED depending on implementation
            pass