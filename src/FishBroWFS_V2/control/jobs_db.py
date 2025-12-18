"""SQLite jobs database - CRUD and state machine."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4

from FishBroWFS_V2.control.types import JobRecord, JobSpec, JobStatus, StopMode


def ensure_schema(conn: sqlite3.Connection) -> None:
    """
    Create tables or migrate schema in-place.
    
    Args:
        conn: SQLite connection
    """
    # Check existing columns
    cursor = conn.execute("PRAGMA table_info(jobs)")
    columns = [row[1] for row in cursor.fetchall()]
    
    # Add run_id column if missing
    if "run_id" not in columns:
        conn.execute("ALTER TABLE jobs ADD COLUMN run_id TEXT")
    
    # Add report_link column if missing
    if "report_link" not in columns:
        conn.execute("ALTER TABLE jobs ADD COLUMN report_link TEXT")
    
    conn.commit()


def init_db(db_path: Path) -> None:
    """
    Initialize jobs database schema.
    
    Args:
        db_path: Path to SQLite database file
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                season TEXT NOT NULL,
                dataset_id TEXT NOT NULL,
                outputs_root TEXT NOT NULL,
                config_hash TEXT NOT NULL,
                config_snapshot_json TEXT NOT NULL,
                pid INTEGER NULL,
                run_id TEXT NULL,
                run_link TEXT NULL,
                report_link TEXT NULL,
                last_error TEXT NULL,
                requested_stop TEXT NULL,
                requested_pause INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_status ON jobs(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_created_at ON jobs(created_at DESC)")
        
        # Ensure schema is up to date (migration)
        ensure_schema(conn)
        
        conn.commit()
    finally:
        conn.close()


def _now_iso() -> str:
    """Get current UTC time as ISO8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _validate_status_transition(old_status: JobStatus, new_status: JobStatus) -> None:
    """
    Validate status transition (state machine).
    
    Allowed transitions:
    - QUEUED → RUNNING
    - RUNNING → PAUSED (pause=1 and worker checkpoint)
    - PAUSED → RUNNING (pause=0 and worker continues)
    - RUNNING/PAUSED → DONE | FAILED | KILLED
    - QUEUED → KILLED (cancel before running)
    
    Args:
        old_status: Current status
        new_status: Target status
        
    Raises:
        ValueError: If transition is not allowed
    """
    allowed = {
        JobStatus.QUEUED: {JobStatus.RUNNING, JobStatus.KILLED},
        JobStatus.RUNNING: {JobStatus.PAUSED, JobStatus.DONE, JobStatus.FAILED, JobStatus.KILLED},
        JobStatus.PAUSED: {JobStatus.RUNNING, JobStatus.DONE, JobStatus.FAILED, JobStatus.KILLED},
    }
    
    if old_status in allowed:
        if new_status not in allowed[old_status]:
            raise ValueError(
                f"Invalid status transition: {old_status} → {new_status}. "
                f"Allowed: {allowed[old_status]}"
            )
    elif old_status in {JobStatus.DONE, JobStatus.FAILED, JobStatus.KILLED}:
        raise ValueError(f"Cannot transition from terminal status: {old_status}")


def create_job(db_path: Path, spec: JobSpec) -> str:
    """
    Create a new job record.
    
    Args:
        db_path: Path to SQLite database
        spec: Job specification
        
    Returns:
        Generated job_id
    """
    job_id = str(uuid4())
    now = _now_iso()
    
    conn = sqlite3.connect(str(db_path))
    try:
        ensure_schema(conn)
        conn.execute("""
            INSERT INTO jobs (
                job_id, status, created_at, updated_at,
                season, dataset_id, outputs_root, config_hash,
                config_snapshot_json, requested_pause
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            job_id,
            JobStatus.QUEUED.value,
            now,
            now,
            spec.season,
            spec.dataset_id,
            spec.outputs_root,
            spec.config_hash,
            json.dumps(spec.config_snapshot),
            0,
        ))
        conn.commit()
    finally:
        conn.close()
    
    return job_id


def _row_to_record(row: tuple) -> JobRecord:
    """Convert database row to JobRecord."""
    # Handle schema versions:
    # - Old: 12 columns (before report_link)
    # - Middle: 13 columns (with report_link, before run_id)
    # - New: 14 columns (with run_id and report_link)
    if len(row) == 14:
        # New schema with run_id and report_link
        # Order: job_id, status, created_at, updated_at, season, dataset_id, outputs_root,
        #        config_hash, config_snapshot_json, pid, run_id, run_link, report_link, last_error
        (
            job_id,
            status,
            created_at,
            updated_at,
            season,
            dataset_id,
            outputs_root,
            config_hash,
            config_snapshot_json,
            pid,
            run_id,
            run_link,
            report_link,
            last_error,
        ) = row
    elif len(row) == 13:
        # Middle schema with report_link but no run_id
        (
            job_id,
            status,
            created_at,
            updated_at,
            season,
            dataset_id,
            outputs_root,
            config_hash,
            config_snapshot_json,
            pid,
            run_link,
            last_error,
            report_link,
        ) = row
        run_id = None
    else:
        # Old schema (backward compatibility)
        (
            job_id,
            status,
            created_at,
            updated_at,
            season,
            dataset_id,
            outputs_root,
            config_hash,
            config_snapshot_json,
            pid,
            run_link,
            last_error,
        ) = row
        run_id = None
        report_link = None
    
    spec = JobSpec(
        season=season,
        dataset_id=dataset_id,
        outputs_root=outputs_root,
        config_snapshot=json.loads(config_snapshot_json),
        config_hash=config_hash,
    )
    
    return JobRecord(
        job_id=job_id,
        status=JobStatus(status),
        created_at=created_at,
        updated_at=updated_at,
        spec=spec,
        pid=pid,
        run_id=run_id if run_id else None,
        run_link=run_link,
        report_link=report_link if report_link else None,
        last_error=last_error,
    )


def get_job(db_path: Path, job_id: str) -> JobRecord:
    """
    Get job record by ID.
    
    Args:
        db_path: Path to SQLite database
        job_id: Job ID
        
    Returns:
        JobRecord
        
    Raises:
        KeyError: If job not found
    """
    conn = sqlite3.connect(str(db_path))
    try:
        ensure_schema(conn)
        cursor = conn.execute("""
            SELECT job_id, status, created_at, updated_at,
                   season, dataset_id, outputs_root, config_hash,
                   config_snapshot_json, pid, 
                   COALESCE(run_id, NULL) as run_id,
                   run_link,
                   COALESCE(report_link, NULL) as report_link,
                   last_error
            FROM jobs
            WHERE job_id = ?
        """, (job_id,))
        row = cursor.fetchone()
        if row is None:
            raise KeyError(f"Job not found: {job_id}")
        return _row_to_record(row)
    finally:
        conn.close()


def list_jobs(db_path: Path, *, limit: int = 50) -> list[JobRecord]:
    """
    List recent jobs.
    
    Args:
        db_path: Path to SQLite database
        limit: Maximum number of jobs to return
        
    Returns:
        List of JobRecord, ordered by created_at DESC
    """
    conn = sqlite3.connect(str(db_path))
    try:
        ensure_schema(conn)
        cursor = conn.execute("""
            SELECT job_id, status, created_at, updated_at,
                   season, dataset_id, outputs_root, config_hash,
                   config_snapshot_json, pid,
                   COALESCE(run_id, NULL) as run_id,
                   run_link,
                   COALESCE(report_link, NULL) as report_link,
                   last_error
            FROM jobs
            ORDER BY created_at DESC
            LIMIT ?
        """, (limit,))
        return [_row_to_record(row) for row in cursor.fetchall()]
    finally:
        conn.close()


def request_pause(db_path: Path, job_id: str, pause: bool) -> None:
    """
    Request pause/unpause for a job.
    
    Args:
        db_path: Path to SQLite database
        job_id: Job ID
        pause: True to pause, False to unpause
        
    Raises:
        KeyError: If job not found
    """
    conn = sqlite3.connect(str(db_path))
    try:
        ensure_schema(conn)
        cursor = conn.execute("SELECT status FROM jobs WHERE job_id = ?", (job_id,))
        if cursor.fetchone() is None:
            raise KeyError(f"Job not found: {job_id}")
        
        conn.execute("""
            UPDATE jobs
            SET requested_pause = ?, updated_at = ?
            WHERE job_id = ?
        """, (1 if pause else 0, _now_iso(), job_id))
        conn.commit()
    finally:
        conn.close()


def request_stop(db_path: Path, job_id: str, mode: StopMode) -> None:
    """
    Request stop for a job.
    
    Args:
        db_path: Path to SQLite database
        job_id: Job ID
        mode: Stop mode (SOFT or KILL)
        
    Raises:
        KeyError: If job not found
    """
    conn = sqlite3.connect(str(db_path))
    try:
        ensure_schema(conn)
        cursor = conn.execute("SELECT status FROM jobs WHERE job_id = ?", (job_id,))
        row = cursor.fetchone()
        if row is None:
            raise KeyError(f"Job not found: {job_id}")
        
        old_status = JobStatus(row[0])
        
        # If QUEUED, immediately mark as KILLED
        if old_status == JobStatus.QUEUED:
            conn.execute("""
                UPDATE jobs
                SET status = ?, requested_stop = ?, updated_at = ?
                WHERE job_id = ?
            """, (JobStatus.KILLED.value, mode.value, _now_iso(), job_id))
        else:
            # Otherwise, set requested_stop flag (worker will handle)
            conn.execute("""
                UPDATE jobs
                SET requested_stop = ?, updated_at = ?
                WHERE job_id = ?
            """, (mode.value, _now_iso(), job_id))
        
        conn.commit()
    finally:
        conn.close()


def update_running(db_path: Path, job_id: str, *, pid: int) -> None:
    """
    Update job to RUNNING status with PID.
    
    Args:
        db_path: Path to SQLite database
        job_id: Job ID
        pid: Process ID
        
    Raises:
        KeyError: If job not found
        ValueError: If status transition is invalid
    """
    conn = sqlite3.connect(str(db_path))
    try:
        ensure_schema(conn)
        cursor = conn.execute("SELECT status FROM jobs WHERE job_id = ?", (job_id,))
        row = cursor.fetchone()
        if row is None:
            raise KeyError(f"Job not found: {job_id}")
        
        old_status = JobStatus(row[0])
        _validate_status_transition(old_status, JobStatus.RUNNING)
        
        conn.execute("""
            UPDATE jobs
            SET status = ?, pid = ?, updated_at = ?
            WHERE job_id = ?
        """, (JobStatus.RUNNING.value, pid, _now_iso(), job_id))
        conn.commit()
    finally:
        conn.close()


def update_run_link(db_path: Path, job_id: str, *, run_link: str) -> None:
    """
    Update job run_link.
    
    Args:
        db_path: Path to SQLite database
        job_id: Job ID
        run_link: Run link path
    """
    conn = sqlite3.connect(str(db_path))
    try:
        ensure_schema(conn)
        conn.execute("""
            UPDATE jobs
            SET run_link = ?, updated_at = ?
            WHERE job_id = ?
        """, (run_link, _now_iso(), job_id))
        conn.commit()
    finally:
        conn.close()


def set_report_link(db_path: Path, job_id: str, report_link: str) -> None:
    """
    Set report_link for a job.
    
    Args:
        db_path: Path to SQLite database
        job_id: Job ID
        report_link: Report link URL
    """
    conn = sqlite3.connect(str(db_path))
    try:
        ensure_schema(conn)
        conn.execute("""
            UPDATE jobs
            SET report_link = ?, updated_at = ?
            WHERE job_id = ?
        """, (report_link, _now_iso(), job_id))
        conn.commit()
    finally:
        conn.close()


def mark_done(
    db_path: Path, 
    job_id: str, 
    *, 
    run_id: Optional[str] = None,
    report_link: Optional[str] = None
) -> None:
    """
    Mark job as DONE.
    
    Args:
        db_path: Path to SQLite database
        job_id: Job ID
        run_id: Optional final stage run_id
        report_link: Optional report link URL
        
    Raises:
        KeyError: If job not found
        ValueError: If status transition is invalid
    """
    conn = sqlite3.connect(str(db_path))
    try:
        ensure_schema(conn)
        cursor = conn.execute("SELECT status FROM jobs WHERE job_id = ?", (job_id,))
        row = cursor.fetchone()
        if row is None:
            raise KeyError(f"Job not found: {job_id}")
        
        old_status = JobStatus(row[0])
        _validate_status_transition(old_status, JobStatus.DONE)
        
        # Always update run_id and report_link (even if None, to clear old values)
        conn.execute("""
            UPDATE jobs
            SET status = ?, updated_at = ?, run_id = ?, report_link = ?, last_error = NULL
            WHERE job_id = ?
        """, (JobStatus.DONE.value, _now_iso(), run_id, report_link, job_id))
        conn.commit()
    finally:
        conn.close()


def mark_failed(db_path: Path, job_id: str, *, error: str) -> None:
    """
    Mark job as FAILED with error message.
    
    Args:
        db_path: Path to SQLite database
        job_id: Job ID
        error: Error message
        
    Raises:
        KeyError: If job not found
        ValueError: If status transition is invalid
    """
    conn = sqlite3.connect(str(db_path))
    try:
        ensure_schema(conn)
        cursor = conn.execute("SELECT status FROM jobs WHERE job_id = ?", (job_id,))
        row = cursor.fetchone()
        if row is None:
            raise KeyError(f"Job not found: {job_id}")
        
        old_status = JobStatus(row[0])
        _validate_status_transition(old_status, JobStatus.FAILED)
        
        conn.execute("""
            UPDATE jobs
            SET status = ?, last_error = ?, updated_at = ?
            WHERE job_id = ?
        """, (JobStatus.FAILED.value, error, _now_iso(), job_id))
        conn.commit()
    finally:
        conn.close()


def mark_killed(db_path: Path, job_id: str, *, error: str | None = None) -> None:
    """
    Mark job as KILLED.
    
    Args:
        db_path: Path to SQLite database
        job_id: Job ID
        error: Optional error message
    """
    conn = sqlite3.connect(str(db_path))
    try:
        ensure_schema(conn)
        conn.execute("""
            UPDATE jobs
            SET status = ?, last_error = ?, updated_at = ?
            WHERE job_id = ?
        """, (JobStatus.KILLED.value, error, _now_iso(), job_id))
        conn.commit()
    finally:
        conn.close()


def get_requested_stop(db_path: Path, job_id: str) -> Optional[str]:
    """
    Get requested_stop value for a job.
    
    Args:
        db_path: Path to SQLite database
        job_id: Job ID
        
    Returns:
        Stop mode string or None
    """
    conn = sqlite3.connect(str(db_path))
    try:
        ensure_schema(conn)
        cursor = conn.execute("SELECT requested_stop FROM jobs WHERE job_id = ?", (job_id,))
        row = cursor.fetchone()
        return row[0] if row and row[0] else None
    finally:
        conn.close()


def get_requested_pause(db_path: Path, job_id: str) -> bool:
    """
    Get requested_pause value for a job.
    
    Args:
        db_path: Path to SQLite database
        job_id: Job ID
        
    Returns:
        True if pause requested, False otherwise
    """
    conn = sqlite3.connect(str(db_path))
    try:
        ensure_schema(conn)
        cursor = conn.execute("SELECT requested_pause FROM jobs WHERE job_id = ?", (job_id,))
        row = cursor.fetchone()
        return bool(row[0]) if row else False
    finally:
        conn.close()
