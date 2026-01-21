"""
Test supervisor heartbeat timeout and orphan detection v1.
"""
import json
import time
from pathlib import Path
import pytest

from control.supervisor.db import SupervisorDB
from control.supervisor.models import JobSpec, now_iso, parse_iso
from control.supervisor.supervisor import Supervisor


def test_find_running_jobs_stale(tmp_path: Path):
    """Test detection of stale jobs."""
    db_path = tmp_path / "test.db"
    db = SupervisorDB(db_path)
    
    # Submit and mark as running
    spec = JobSpec(job_type="PING", params={"sleep_sec": 1.0})
    job_id = db.submit_job(spec)
    
    # Manually set as running with old heartbeat
    with db._connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("""
            UPDATE jobs 
            SET state = 'RUNNING', worker_id = 'test', worker_pid = 9999,
                last_heartbeat = ?, updated_at = ?
            WHERE job_id = ?
        """, ("2026-01-01T00:00:00+00:00", now_iso(), job_id))
        conn.commit()
    
    # Find stale jobs with 1 second timeout
    now = now_iso()
    stale = db.find_running_jobs_stale(now, timeout_sec=1.0)
    
    assert len(stale) == 1
    assert stale[0].job_id == job_id
    
    # Job with recent heartbeat should not be stale
    with db._connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("""
            UPDATE jobs SET last_heartbeat = ? WHERE job_id = ?
        """, (now, job_id))
        conn.commit()
    
    stale = db.find_running_jobs_stale(now, timeout_sec=10.0)
    assert len(stale) == 0


def test_supervisor_orphan_detection(tmp_path: Path):
    """Test supervisor detects and handles orphaned jobs."""
    db_path = tmp_path / "jobs_v2.db"
    db = SupervisorDB(db_path)
    
    # Submit job
    spec = JobSpec(job_type="PING", params={"sleep_sec": 0.1})
    job_id = db.submit_job(spec)
    
    # Manually mark as running with old heartbeat (simulating dead worker)
    old_time = "2026-01-01T00:00:00+00:00"
    with db._connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("""
            UPDATE jobs 
            SET state = 'RUNNING', worker_id = 'dead_worker', 
                worker_pid = 99999, last_heartbeat = ?, updated_at = ?
            WHERE job_id = ?
        """, (old_time, now_iso(), job_id))
        conn.commit()
    
    # Create supervisor
    supervisor = Supervisor(
        db_path=db_path,
        max_workers=1,
        tick_interval=0.1,
        artifacts_root=tmp_path / "artifacts"
    )
    
    # Run one tick - should detect stale job
    supervisor.tick()
    
    # Check job was marked ORPHANED
    job = db.get_job_row(job_id)
    assert job is not None
    assert job.state == "ORPHANED"
    assert "heartbeat_timeout" in job.state_reason.lower()
    
    supervisor.shutdown()


def test_supervisor_handles_missing_worker(tmp_path: Path):
    """Test supervisor handles jobs where worker process is missing."""
    db_path = tmp_path / "jobs_v2.db"
    db = SupervisorDB(db_path)
    
    # Submit job
    spec = JobSpec(job_type="PING", params={"sleep_sec": 0.1})
    job_id = db.submit_job(spec)
    
    # Mark as running with non-existent PID
    with db._connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("""
            UPDATE jobs 
            SET state = 'RUNNING', worker_id = 'ghost', 
                worker_pid = 999999, last_heartbeat = ?, updated_at = ?
            WHERE job_id = ?
        """, (now_iso(), now_iso(), job_id))
        conn.commit()
    
    # Create supervisor
    supervisor = Supervisor(
        db_path=db_path,
        max_workers=1,
        tick_interval=0.1,
        artifacts_root=tmp_path / "artifacts"
    )
    
    # Run tick - should detect stale heartbeat after timeout
    # First, set heartbeat to old time
    old_time = "2026-01-01T00:00:00+00:00"
    with db._connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("""
            UPDATE jobs SET last_heartbeat = ? WHERE job_id = ?
        """, (old_time, job_id))
        conn.commit()
    
    supervisor.tick()
    
    # Job should be ORPHANED
    job = db.get_job_row(job_id)
    assert job.state == "ORPHANED"
    
    supervisor.shutdown()


def test_heartbeat_update_maintains_state(tmp_path: Path):
    """Test that heartbeat updates don't change job state."""
    db_path = tmp_path / "test.db"
    db = SupervisorDB(db_path)
    
    spec = JobSpec(job_type="PING", params={"sleep_sec": 0.1})
    job_id = db.submit_job(spec)
    
    # Mark as running
    db.fetch_next_queued_job()
    db.mark_running(job_id, "worker1", 1000)
    
    # Update heartbeat multiple times
    for i in range(3):
        db.update_heartbeat(job_id, progress=i/3, phase=f"phase_{i}")
        time.sleep(0.01)
    
    # Job should still be RUNNING
    job = db.get_job_row(job_id)
    assert job.state == "RUNNING"
    assert job.progress == 2/3  # Last progress
    assert job.phase == "phase_2"


def test_no_stale_detection_for_non_running(tmp_path: Path):
    """Test that stale detection only looks at RUNNING jobs."""
    db_path = tmp_path / "test.db"
    db = SupervisorDB(db_path)
    
    # Create jobs in various states
    states = ["QUEUED", "SUCCEEDED", "FAILED", "ABORTED"]
    job_ids = []
    
    for state in states:
        spec = JobSpec(job_type="PING", params={"sleep_sec": 0.1})
        job_id = db.submit_job(spec)
        
        # Manually set state
        with db._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("""
                UPDATE jobs 
                SET state = ?, last_heartbeat = ?
                WHERE job_id = ?
            """, (state, "2026-01-01T00:00:00+00:00", job_id))
            conn.commit()
        
        job_ids.append(job_id)
    
    # None should appear as stale (they're not RUNNING)
    now = now_iso()
    stale = db.find_running_jobs_stale(now, timeout_sec=1.0)
    assert len(stale) == 0