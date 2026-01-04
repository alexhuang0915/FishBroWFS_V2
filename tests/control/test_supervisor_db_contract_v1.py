"""
Test supervisor DB contract v1.
"""
import json
import tempfile
from pathlib import Path
import pytest

from src.control.supervisor.db import SupervisorDB
from src.control.supervisor.models import JobSpec


def test_init_schema(tmp_path: Path):
    """Test DB schema initialization."""
    db_path = tmp_path / "test.db"
    db = SupervisorDB(db_path)
    
    # Should create tables
    assert db_path.exists()
    
    with db._connect() as conn:
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = {row["name"] for row in cursor.fetchall()}
        assert "jobs" in tables
        assert "workers" in tables


def test_submit_job(tmp_path: Path):
    """Test job submission."""
    db_path = tmp_path / "test.db"
    db = SupervisorDB(db_path)
    
    spec = JobSpec(job_type="PING", params={"sleep_sec": 1.0})
    job_id = db.submit_job(spec)
    
    assert isinstance(job_id, str)
    assert len(job_id) > 0
    
    job = db.get_job_row(job_id)
    assert job is not None
    assert job.job_id == job_id
    assert job.job_type == "PING"
    assert job.state == "QUEUED"
    assert job.created_at == job.updated_at


def test_mark_running(tmp_path: Path):
    """Test marking job as RUNNING with worker assignment."""
    db_path = tmp_path / "test.db"
    db = SupervisorDB(db_path)
    
    spec = JobSpec(job_type="PING", params={"sleep_sec": 0.1})
    job_id = db.submit_job(spec)
    
    # First fetch as queued
    fetched = db.fetch_next_queued_job()
    assert fetched == job_id
    
    # Mark as running with worker
    worker_id = "test_worker_123"
    pid = 9999
    db.mark_running(job_id, worker_id, pid)
    
    job = db.get_job_row(job_id)
    assert job.state == "RUNNING"
    assert job.worker_id == worker_id
    assert job.worker_pid == pid
    assert job.last_heartbeat is not None


def test_update_heartbeat(tmp_path: Path):
    """Test heartbeat updates."""
    db_path = tmp_path / "test.db"
    db = SupervisorDB(db_path)
    
    spec = JobSpec(job_type="PING", params={"sleep_sec": 0.1})
    job_id = db.submit_job(spec)
    
    # Mark as running first
    db.fetch_next_queued_job()
    db.mark_running(job_id, "worker1", 1000)
    
    # Update heartbeat with progress
    db.update_heartbeat(job_id, progress=0.5, phase="testing")
    
    job = db.get_job_row(job_id)
    assert job.progress == 0.5
    assert job.phase == "testing"
    assert job.last_heartbeat is not None


def test_mark_succeeded(tmp_path: Path):
    """Test marking job as SUCCEEDED."""
    db_path = tmp_path / "test.db"
    db = SupervisorDB(db_path)
    
    spec = JobSpec(job_type="PING", params={"sleep_sec": 0.1})
    job_id = db.submit_job(spec)
    
    # Mark as running first
    db.fetch_next_queued_job()
    db.mark_running(job_id, "worker1", 1000)
    
    # Mark succeeded
    result = {"ok": True, "elapsed": 0.1}
    db.mark_succeeded(job_id, result)
    
    job = db.get_job_row(job_id)
    assert job.state == "SUCCEEDED"
    assert job.result_json == json.dumps(result)
    assert job.state_reason == ""


def test_mark_failed(tmp_path: Path):
    """Test marking job as FAILED."""
    db_path = tmp_path / "test.db"
    db = SupervisorDB(db_path)
    
    spec = JobSpec(job_type="PING", params={"sleep_sec": 0.1})
    job_id = db.submit_job(spec)
    
    # Mark as running first
    db.fetch_next_queued_job()
    db.mark_running(job_id, "worker1", 1000)
    
    # Mark failed
    reason = "test failure"
    db.mark_failed(job_id, reason)
    
    job = db.get_job_row(job_id)
    assert job.state == "FAILED"
    assert job.state_reason == reason


def test_mark_aborted(tmp_path: Path):
    """Test marking job as ABORTED."""
    db_path = tmp_path / "test.db"
    db = SupervisorDB(db_path)
    
    spec = JobSpec(job_type="PING", params={"sleep_sec": 0.1})
    job_id = db.submit_job(spec)
    
    # Mark as running first
    db.fetch_next_queued_job()
    db.mark_running(job_id, "worker1", 1000)
    
    # Mark aborted
    reason = "user requested"
    db.mark_aborted(job_id, reason)
    
    job = db.get_job_row(job_id)
    assert job.state == "ABORTED"
    assert job.state_reason == reason


def test_request_abort(tmp_path: Path):
    """Test abort request flag."""
    db_path = tmp_path / "test.db"
    db = SupervisorDB(db_path)
    
    spec = JobSpec(job_type="PING", params={"sleep_sec": 0.1})
    job_id = db.submit_job(spec)
    
    # Request abort
    db.request_abort(job_id)
    
    # Check flag
    assert db.is_abort_requested(job_id) is True
    
    # Job still QUEUED
    job = db.get_job_row(job_id)
    assert job.state == "QUEUED"
    assert job.abort_requested is True


def test_fetch_next_queued_job_empty(tmp_path: Path):
    """Test fetch when no queued jobs."""
    db_path = tmp_path / "test.db"
    db = SupervisorDB(db_path)
    
    result = db.fetch_next_queued_job()
    assert result is None


def test_fetch_next_queued_job_ordering(tmp_path: Path):
    """Test queued jobs are fetched in creation order."""
    db_path = tmp_path / "test.db"
    db = SupervisorDB(db_path)
    
    # Submit multiple jobs
    job_ids = []
    for i in range(3):
        spec = JobSpec(job_type="PING", params={"index": i})
        job_id = db.submit_job(spec)
        job_ids.append(job_id)
    
    # Fetch should return in creation order
    for expected_id in job_ids:
        fetched = db.fetch_next_queued_job()
        assert fetched == expected_id
    
    # No more queued jobs
    assert db.fetch_next_queued_job() is None