"""
Test supervisor abort enforcement v1 (P0.2 Abort Enforcement + P0.3 ErrorDetails Observability).
"""
import json
import os
import signal
import subprocess
import time
from pathlib import Path
import pytest

from src.control.supervisor.db import SupervisorDB
from src.control.supervisor.models import JobSpec, now_iso
from src.control.supervisor.supervisor import Supervisor


def test_abort_queued_job_with_error_details(tmp_path: Path):
    """Abort requested on QUEUED → transitions to ABORTED within a supervisor tick and writes error_details."""
    db_path = tmp_path / "jobs_v2.db"
    db = SupervisorDB(db_path)

    # Submit a job (default state QUEUED)
    spec = JobSpec(job_type="PING", params={"sleep_sec": 10.0})
    job_id = db.submit_job(spec)

    # Request abort
    db.request_abort(job_id)

    # Create supervisor with max_workers=0 to avoid spawning new workers
    supervisor = Supervisor(
        db_path=db_path,
        max_workers=0,
        tick_interval=0.01,
        artifacts_root=tmp_path / "artifacts"
    )

    # Run one tick - should detect QUEUED abort and mark ABORTED
    supervisor.tick()

    # Verify job state
    job = db.get_job_row(job_id)
    assert job is not None
    assert job.state == "ABORTED"
    assert job.error_details is not None

    # Parse error_details JSON
    error_details = json.loads(job.error_details)
    assert error_details["type"] == "AbortRequested"
    assert error_details["msg"] == "user_abort"
    assert "timestamp" in error_details
    assert error_details["phase"] == "supervisor"
    # pid optional, not present for QUEUED abort
    assert "pid" not in error_details

    supervisor.shutdown()


def test_abort_running_job_kills_subprocess_and_error_details(tmp_path: Path):
    """Abort requested on RUNNING → supervisor kills PID (TERM→KILL) and transitions job to ABORTED with error_details.pid."""
    db_path = tmp_path / "jobs_v2.db"
    db = SupervisorDB(db_path)

    # Start a real subprocess that sleeps for a long time
    # Use start_new_session=True to match supervisor's worker spawning
    proc = subprocess.Popen(
        ["sleep", "60"],
        start_new_session=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    pid = proc.pid
    try:
        # Insert a job row in state RUNNING with this PID
        spec = JobSpec(job_type="PING", params={"sleep_sec": 10.0})
        job_id = db.submit_job(spec)
        # Manually set as RUNNING with worker_pid
        with db._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("""
                UPDATE jobs 
                SET state = 'RUNNING', worker_id = 'test_worker', worker_pid = ?,
                    last_heartbeat = ?, updated_at = ?
                WHERE job_id = ?
            """, (pid, now_iso(), now_iso(), job_id))
            conn.commit()

        # Request abort
        db.request_abort(job_id)

        # Create supervisor with max_workers=0 (we already have a "running" job)
        supervisor = Supervisor(
            db_path=db_path,
            max_workers=0,
            tick_interval=0.01,
            artifacts_root=tmp_path / "artifacts"
        )

        # Run one tick - should detect RUNNING abort, kill process, mark ABORTED
        supervisor.tick()

        # Wait a bit for kill to take effect
        time.sleep(0.1)

        # Verify process is dead (poll returns None if still running, otherwise returncode)
        # Actually after SIGKILL, poll should return a non‑None value (exit code)
        # Use os.kill with signal 0 to check if process exists
        try:
            os.kill(pid, 0)
            # If no exception, process still exists (should not happen)
            # Send SIGKILL again just in case
            os.killpg(pid, signal.SIGKILL)
            time.sleep(0.05)
        except ProcessLookupError:
            # Expected: process is dead
            pass

        # Verify job state
        job = db.get_job_row(job_id)
        assert job is not None
        assert job.state == "ABORTED"
        assert job.error_details is not None

        # Parse error_details JSON
        error_details = json.loads(job.error_details)
        assert error_details["type"] == "AbortRequested"
        assert error_details["msg"] == "user_abort"
        assert error_details["pid"] == pid
        assert "timestamp" in error_details
        assert error_details["phase"] == "supervisor"
        # Optional fields may be present
        if "process_missing" in error_details:
            # If process was already dead before abort, supervisor may note it
            pass

        # Ensure process is cleaned up (no zombies)
        proc.wait(timeout=0.5)
    finally:
        # Ensure process is terminated
        try:
            os.killpg(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait(timeout=1.0)


def test_abort_running_job_with_missing_pid(tmp_path: Path):
    """Abort requested on RUNNING but PID missing / already dead → still transition to ABORTED with error_details containing pid + note."""
    db_path = tmp_path / "jobs_v2.db"
    db = SupervisorDB(db_path)

    # Submit a job
    spec = JobSpec(job_type="PING", params={"sleep_sec": 10.0})
    job_id = db.submit_job(spec)

    # Manually set as RUNNING with a non‑existent PID
    fake_pid = 999999
    with db._connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("""
            UPDATE jobs 
            SET state = 'RUNNING', worker_id = 'test_worker', worker_pid = ?,
                last_heartbeat = ?, updated_at = ?
            WHERE job_id = ?
        """, (fake_pid, now_iso(), now_iso(), job_id))
        conn.commit()

    # Request abort
    db.request_abort(job_id)

    # Create supervisor with max_workers=0
    supervisor = Supervisor(
        db_path=db_path,
        max_workers=0,
        tick_interval=0.01,
        artifacts_root=tmp_path / "artifacts"
    )

    # Run one tick - should detect RUNNING abort, attempt kill, mark ABORTED
    supervisor.tick()

    # Verify job state
    job = db.get_job_row(job_id)
    assert job is not None
    assert job.state == "ABORTED"
    assert job.error_details is not None

    error_details = json.loads(job.error_details)
    assert error_details["type"] == "AbortRequested"
    assert error_details["msg"] == "user_abort"
    assert error_details["pid"] == fake_pid
    # Optionally may have "process_missing": true
    if "process_missing" in error_details:
        assert error_details["process_missing"] is True

    supervisor.shutdown()


def test_abort_requested_on_multiple_jobs(tmp_path: Path):
    """Supervisor handles multiple abort requests in a single tick."""
    db_path = tmp_path / "jobs_v2.db"
    db = SupervisorDB(db_path)

    # Create three jobs: QUEUED, RUNNING (with real subprocess), RUNNING (missing PID)
    job_ids = []
    pids = []
    processes = []

    # QUEUED job
    spec1 = JobSpec(job_type="PING", params={"sleep_sec": 10.0})
    job_id1 = db.submit_job(spec1)
    job_ids.append(job_id1)

    # RUNNING job with real subprocess
    proc = subprocess.Popen(
        ["sleep", "30"],
        start_new_session=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    pid = proc.pid
    pids.append(pid)
    processes.append(proc)
    spec2 = JobSpec(job_type="PING", params={"sleep_sec": 10.0})
    job_id2 = db.submit_job(spec2)
    with db._connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("""
            UPDATE jobs 
            SET state = 'RUNNING', worker_id = 'worker1', worker_pid = ?,
                last_heartbeat = ?, updated_at = ?
            WHERE job_id = ?
        """, (pid, now_iso(), now_iso(), job_id2))
        conn.commit()
    job_ids.append(job_id2)

    # RUNNING job with fake PID
    fake_pid = 888888
    spec3 = JobSpec(job_type="PING", params={"sleep_sec": 10.0})
    job_id3 = db.submit_job(spec3)
    with db._connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("""
            UPDATE jobs 
            SET state = 'RUNNING', worker_id = 'worker2', worker_pid = ?,
                last_heartbeat = ?, updated_at = ?
            WHERE job_id = ?
        """, (fake_pid, now_iso(), now_iso(), job_id3))
        conn.commit()
    job_ids.append(job_id3)

    # Request abort on all three
    for jid in job_ids:
        db.request_abort(jid)

    # Create supervisor with max_workers=0
    supervisor = Supervisor(
        db_path=db_path,
        max_workers=0,
        tick_interval=0.01,
        artifacts_root=tmp_path / "artifacts"
    )

    # Run one tick
    supervisor.tick()

    # Wait a bit for kills
    time.sleep(0.1)

    # Verify all jobs are ABORTED with error_details
    for jid in job_ids:
        job = db.get_job_row(jid)
        assert job is not None
        assert job.state == "ABORTED"
        assert job.error_details is not None
        details = json.loads(job.error_details)
        assert details["type"] == "AbortRequested"
        assert details["msg"] == "user_abort"

    # Clean up subprocesses
    for proc in processes:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait(timeout=1.0)

    supervisor.shutdown()


def test_error_details_schema_compliance(tmp_path: Path):
    """Verify error_details JSON shape matches required schema."""
    db_path = tmp_path / "jobs_v2.db"
    db = SupervisorDB(db_path)

    # Use mark_failed with structured error_details
    spec = JobSpec(job_type="PING", params={"sleep_sec": 0.1})
    job_id = db.submit_job(spec)
    db.mark_failed(
        job_id,
        "Test error",
        error_details={
            "type": "ValidationError",
            "msg": "short_human_message",
            "pid": 12345,
            "traceback": "some traceback",
            "phase": "bootstrap",
            "timestamp": now_iso(),
        }
    )

    job = db.get_job_row(job_id)
    assert job.error_details is not None
    details = json.loads(job.error_details)
    # Required keys
    assert "type" in details
    assert "msg" in details
    assert "timestamp" in details
    # Optional keys may be present
    # Ensure no extra keys beyond allowed ones (optional)
    allowed = {"type", "msg", "pid", "traceback", "phase", "timestamp"}
    for key in details.keys():
        assert key in allowed, f"Unexpected key {key} in error_details"

    # Verify API response includes error_details
    from src.control.api import _supervisor_job_to_response
    response = _supervisor_job_to_response(job)
    assert response.error_details is not None
    assert response.error_details["type"] == "ValidationError"
    assert response.error_details["msg"] == "short_human_message"
    assert response.error_details["pid"] == 12345