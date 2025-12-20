"""SQLite jobs database - CRUD and state machine."""

from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, TypeVar
from uuid import uuid4

from FishBroWFS_V2.control.types import JobRecord, JobSpec, JobStatus, StopMode

T = TypeVar("T")


def _connect(db_path: Path) -> sqlite3.Connection:
    """
    Create SQLite connection with concurrency hardening.
    
    One operation = one connection (avoid shared connection across threads).
    
    Args:
        db_path: Path to SQLite database
        
    Returns:
        Configured SQLite connection with WAL mode and busy timeout
    """
    # One operation = one connection (avoid shared connection across threads)
    conn = sqlite3.connect(str(db_path), timeout=30.0)
    conn.row_factory = sqlite3.Row

    # Concurrency hardening
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("PRAGMA busy_timeout=30000;")  # ms

    return conn


def _with_retry_locked(fn: Callable[[], T]) -> T:
    """
    Retry DB operation on SQLITE_BUSY/locked errors.
    
    Args:
        fn: Callable that performs DB operation
        
    Returns:
        Result from fn()
        
    Raises:
        sqlite3.OperationalError: If operation fails after retries or for non-locked errors
    """
    # Retry only for SQLITE_BUSY/locked
    delays = (0.05, 0.10, 0.20, 0.40, 0.80, 1.0)
    last: Exception | None = None
    for d in delays:
        try:
            return fn()
        except sqlite3.OperationalError as e:
            msg = str(e).lower()
            if "locked" not in msg and "busy" not in msg:
                raise
            last = e
            time.sleep(d)
    assert last is not None
    raise last


def ensure_schema(conn: sqlite3.Connection) -> None:
    """
    Create tables or migrate schema in-place.
    
    Idempotent: safe to call multiple times.
    
    Args:
        conn: SQLite connection
    """
    # Create jobs table if not exists
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
            requested_pause INTEGER NOT NULL DEFAULT 0,
            tags_json TEXT DEFAULT '[]'
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_status ON jobs(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_created_at ON jobs(created_at DESC)")
    
    # Check existing columns for migrations
    cursor = conn.execute("PRAGMA table_info(jobs)")
    columns = [row[1] for row in cursor.fetchall()]
    
    # Add run_id column if missing
    if "run_id" not in columns:
        conn.execute("ALTER TABLE jobs ADD COLUMN run_id TEXT")
    
    # Add report_link column if missing
    if "report_link" not in columns:
        conn.execute("ALTER TABLE jobs ADD COLUMN report_link TEXT")
    
    # Add tags_json column if missing
    if "tags_json" not in columns:
        conn.execute("ALTER TABLE jobs ADD COLUMN tags_json TEXT DEFAULT '[]'")
    
    # Add data_fingerprint_sha1 column if missing
    if "data_fingerprint_sha1" not in columns:
        conn.execute("ALTER TABLE jobs ADD COLUMN data_fingerprint_sha1 TEXT DEFAULT ''")
    
    # Create job_logs table if not exists
    conn.execute("""
        CREATE TABLE IF NOT EXISTS job_logs (
            log_id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            log_text TEXT NOT NULL,
            FOREIGN KEY (job_id) REFERENCES jobs(job_id)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_job_logs_job_id ON job_logs(job_id, created_at DESC)")
    
    conn.commit()


def init_db(db_path: Path) -> None:
    """
    Initialize jobs database schema.
    
    Args:
        db_path: Path to SQLite database file
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    def _op() -> None:
        with _connect(db_path) as conn:
            ensure_schema(conn)
            # ensure_schema handles CREATE TABLE IF NOT EXISTS + migrations
    
    _with_retry_locked(_op)


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


def create_job(db_path: Path, spec: JobSpec, *, tags: list[str] | None = None) -> str:
    """
    Create a new job record.
    
    Args:
        db_path: Path to SQLite database
        spec: Job specification
        tags: Optional list of tags for job categorization
        
    Returns:
        Generated job_id
    """
    job_id = str(uuid4())
    now = _now_iso()
    tags_json = json.dumps(tags if tags else [])
    
    def _op() -> str:
        with _connect(db_path) as conn:
            ensure_schema(conn)
            conn.execute("""
                INSERT INTO jobs (
                    job_id, status, created_at, updated_at,
                    season, dataset_id, outputs_root, config_hash,
                    config_snapshot_json, requested_pause, tags_json, data_fingerprint_sha1
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                tags_json,
                spec.data_fingerprint_sha1 if hasattr(spec, 'data_fingerprint_sha1') else '',
            ))
            conn.commit()
        return job_id
    
    return _with_retry_locked(_op)


def _row_to_record(row: tuple) -> JobRecord:
    """Convert database row to JobRecord."""
    # Handle schema versions:
    # - Old: 12 columns (before report_link)
    # - Middle: 13 columns (with report_link, before run_id)
    # - New: 14 columns (with run_id and report_link)
    # - Latest: 15 columns (with tags_json)
    # - Phase 6.5: 16 columns (with data_fingerprint_sha1)
    if len(row) == 16:
        # Phase 6.5 schema with data_fingerprint_sha1
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
            tags_json,
            data_fingerprint_sha1,
        ) = row
        # Parse tags_json, fallback to [] if None or invalid
        try:
            tags = json.loads(tags_json) if tags_json else []
            if not isinstance(tags, list):
                tags = []
        except (json.JSONDecodeError, TypeError):
            tags = []
        fingerprint_sha1 = data_fingerprint_sha1 if data_fingerprint_sha1 else ""
    elif len(row) == 15:
        # Latest schema with tags_json
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
            tags_json,
        ) = row
        # Parse tags_json, fallback to [] if None or invalid
        try:
            tags = json.loads(tags_json) if tags_json else []
            if not isinstance(tags, list):
                tags = []
        except (json.JSONDecodeError, TypeError):
            tags = []
        fingerprint_sha1 = ""  # Fallback for schema without data_fingerprint_sha1
    elif len(row) == 14:
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
        tags = []  # Fallback for schema without tags_json
        fingerprint_sha1 = ""  # Fallback for schema without data_fingerprint_sha1
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
        tags = []  # Fallback for old schema
        fingerprint_sha1 = ""  # Fallback for schema without data_fingerprint_sha1
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
        tags = []  # Fallback for old schema
        fingerprint_sha1 = ""  # Fallback for schema without data_fingerprint_sha1
    
    spec = JobSpec(
        season=season,
        dataset_id=dataset_id,
        outputs_root=outputs_root,
        config_snapshot=json.loads(config_snapshot_json),
        config_hash=config_hash,
        data_fingerprint_sha1=fingerprint_sha1,
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
        tags=tags if tags else [],
        data_fingerprint_sha1=fingerprint_sha1,
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
    def _op() -> JobRecord:
        with _connect(db_path) as conn:
            ensure_schema(conn)
            cursor = conn.execute("""
                SELECT job_id, status, created_at, updated_at,
                       season, dataset_id, outputs_root, config_hash,
                       config_snapshot_json, pid, 
                       COALESCE(run_id, NULL) as run_id,
                       run_link,
                       COALESCE(report_link, NULL) as report_link,
                       last_error,
                       COALESCE(tags_json, '[]') as tags_json,
                       COALESCE(data_fingerprint_sha1, '') as data_fingerprint_sha1
                FROM jobs
                WHERE job_id = ?
            """, (job_id,))
            row = cursor.fetchone()
            if row is None:
                raise KeyError(f"Job not found: {job_id}")
            return _row_to_record(row)
    
    return _with_retry_locked(_op)


def list_jobs(db_path: Path, *, limit: int = 50) -> list[JobRecord]:
    """
    List recent jobs.
    
    Args:
        db_path: Path to SQLite database
        limit: Maximum number of jobs to return
        
    Returns:
        List of JobRecord, ordered by created_at DESC
    """
    def _op() -> list[JobRecord]:
        with _connect(db_path) as conn:
            ensure_schema(conn)
            cursor = conn.execute("""
                SELECT job_id, status, created_at, updated_at,
                       season, dataset_id, outputs_root, config_hash,
                       config_snapshot_json, pid,
                       COALESCE(run_id, NULL) as run_id,
                       run_link,
                       COALESCE(report_link, NULL) as report_link,
                       last_error,
                       COALESCE(tags_json, '[]') as tags_json,
                       COALESCE(data_fingerprint_sha1, '') as data_fingerprint_sha1
                FROM jobs
                ORDER BY created_at DESC
                LIMIT ?
            """, (limit,))
            return [_row_to_record(row) for row in cursor.fetchall()]
    
    return _with_retry_locked(_op)


def request_pause(db_path: Path, job_id: str, pause: bool) -> None:
    """
    Request pause/unpause for a job (atomic update).
    
    Args:
        db_path: Path to SQLite database
        job_id: Job ID
        pause: True to pause, False to unpause
        
    Raises:
        KeyError: If job not found
    """
    def _op() -> None:
        with _connect(db_path) as conn:
            ensure_schema(conn)
            cur = conn.execute("""
                UPDATE jobs
                SET requested_pause = ?, updated_at = ?
                WHERE job_id = ?
            """, (1 if pause else 0, _now_iso(), job_id))
            
            if cur.rowcount == 0:
                raise KeyError(f"Job not found: {job_id}")
            
            conn.commit()
    
    _with_retry_locked(_op)


def request_stop(db_path: Path, job_id: str, mode: StopMode) -> None:
    """
    Request stop for a job (atomic update).
    
    If QUEUED, immediately mark as KILLED.
    Otherwise, set requested_stop flag (worker will handle).
    
    Args:
        db_path: Path to SQLite database
        job_id: Job ID
        mode: Stop mode (SOFT or KILL)
        
    Raises:
        KeyError: If job not found
    """
    def _op() -> None:
        with _connect(db_path) as conn:
            ensure_schema(conn)
            # Try to mark QUEUED as KILLED first (atomic)
            cur = conn.execute("""
                UPDATE jobs
                SET status = ?, requested_stop = ?, updated_at = ?
                WHERE job_id = ? AND status = ?
            """, (JobStatus.KILLED.value, mode.value, _now_iso(), job_id, JobStatus.QUEUED.value))
            
            if cur.rowcount == 1:
                conn.commit()
                return
            
            # Otherwise, set requested_stop flag (atomic)
            cur = conn.execute("""
                UPDATE jobs
                SET requested_stop = ?, updated_at = ?
                WHERE job_id = ?
            """, (mode.value, _now_iso(), job_id))
            
            if cur.rowcount == 0:
                raise KeyError(f"Job not found: {job_id}")
            
            conn.commit()
    
    _with_retry_locked(_op)


def mark_running(db_path: Path, job_id: str, *, pid: int) -> None:
    """
    Mark job as RUNNING with PID (atomic update from QUEUED).
    
    Args:
        db_path: Path to SQLite database
        job_id: Job ID
        pid: Process ID
        
    Raises:
        KeyError: If job not found
        ValueError: If status is terminal (DONE/FAILED/KILLED) or invalid transition
    """
    def _op() -> None:
        with _connect(db_path) as conn:
            ensure_schema(conn)
            cur = conn.execute("""
                UPDATE jobs
                SET status = ?, pid = ?, updated_at = ?
                WHERE job_id = ? AND status = ?
            """, (JobStatus.RUNNING.value, pid, _now_iso(), job_id, JobStatus.QUEUED.value))
            
            if cur.rowcount == 1:
                conn.commit()
                return
            
            # Check if job exists and current status
            row = conn.execute("SELECT status FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
            if row is None:
                raise KeyError(f"Job not found: {job_id}")
            
            status = JobStatus(row[0])
            
            if status == JobStatus.RUNNING:
                # Already running (idempotent)
                return
            
            # Terminal status => ValueError (match existing tests/contract)
            if status in {JobStatus.DONE, JobStatus.FAILED, JobStatus.KILLED}:
                raise ValueError("Cannot transition from terminal status")
            
            # Everything else is invalid transition (keep ValueError)
            raise ValueError(f"Invalid status transition: {status.value} → RUNNING")
    
    _with_retry_locked(_op)


def update_running(db_path: Path, job_id: str, *, pid: int) -> None:
    """
    Update job to RUNNING status with PID (legacy alias for mark_running).
    
    Args:
        db_path: Path to SQLite database
        job_id: Job ID
        pid: Process ID
        
    Raises:
        KeyError: If job not found
        RuntimeError: If status transition is invalid
    """
    mark_running(db_path, job_id, pid=pid)


def update_run_link(db_path: Path, job_id: str, *, run_link: str) -> None:
    """
    Update job run_link.
    
    Args:
        db_path: Path to SQLite database
        job_id: Job ID
        run_link: Run link path
    """
    def _op() -> None:
        with _connect(db_path) as conn:
            ensure_schema(conn)
            conn.execute("""
                UPDATE jobs
                SET run_link = ?, updated_at = ?
                WHERE job_id = ?
            """, (run_link, _now_iso(), job_id))
            conn.commit()
    
    _with_retry_locked(_op)


def set_report_link(db_path: Path, job_id: str, report_link: str) -> None:
    """
    Set report_link for a job.
    
    Args:
        db_path: Path to SQLite database
        job_id: Job ID
        report_link: Report link URL
    """
    def _op() -> None:
        with _connect(db_path) as conn:
            ensure_schema(conn)
            conn.execute("""
                UPDATE jobs
                SET report_link = ?, updated_at = ?
                WHERE job_id = ?
            """, (report_link, _now_iso(), job_id))
            conn.commit()
    
    _with_retry_locked(_op)


def mark_done(
    db_path: Path, 
    job_id: str, 
    *, 
    run_id: Optional[str] = None,
    report_link: Optional[str] = None
) -> None:
    """
    Mark job as DONE (atomic update from RUNNING or KILLED).
    
    Idempotent: safe to call multiple times.
    
    Args:
        db_path: Path to SQLite database
        job_id: Job ID
        run_id: Optional final stage run_id
        report_link: Optional report link URL
        
    Raises:
        KeyError: If job not found
        RuntimeError: If status is QUEUED/PAUSED (mark_done before RUNNING)
    """
    def _op() -> None:
        with _connect(db_path) as conn:
            ensure_schema(conn)
            cur = conn.execute("""
                UPDATE jobs
                SET status = ?, updated_at = ?, run_id = ?, report_link = ?, last_error = NULL
                WHERE job_id = ? AND status IN (?, ?)
            """, (
                JobStatus.DONE.value,
                _now_iso(),
                run_id,
                report_link,
                job_id,
                JobStatus.RUNNING.value,
                JobStatus.KILLED.value,
            ))
            
            if cur.rowcount == 1:
                conn.commit()
                return
            
            # Fallback: check if already DONE (idempotent success)
            row = conn.execute("SELECT status FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
            if row is None:
                raise KeyError(f"Job not found: {job_id}")
            
            status = JobStatus(row[0])
            if status == JobStatus.DONE:
                # Already done (idempotent)
                return
            
            # If QUEUED/PAUSED, raise RuntimeError (process flow incorrect)
            raise RuntimeError(f"mark_done rejected: status={status} (expected RUNNING or KILLED)")
    
    _with_retry_locked(_op)


def mark_failed(db_path: Path, job_id: str, *, error: str) -> None:
    """
    Mark job as FAILED with error message (atomic update from RUNNING or PAUSED).
    
    Idempotent: safe to call multiple times.
    
    Args:
        db_path: Path to SQLite database
        job_id: Job ID
        error: Error message
        
    Raises:
        KeyError: If job not found
        RuntimeError: If status is QUEUED (mark_failed before RUNNING)
    """
    def _op() -> None:
        with _connect(db_path) as conn:
            ensure_schema(conn)
            cur = conn.execute("""
                UPDATE jobs
                SET status = ?, last_error = ?, updated_at = ?
                WHERE job_id = ? AND status IN (?, ?)
            """, (
                JobStatus.FAILED.value,
                error,
                _now_iso(),
                job_id,
                JobStatus.RUNNING.value,
                JobStatus.PAUSED.value,
            ))
            
            if cur.rowcount == 1:
                conn.commit()
                return
            
            # Fallback: check if already FAILED (idempotent success)
            row = conn.execute("SELECT status FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
            if row is None:
                raise KeyError(f"Job not found: {job_id}")
            
            status = JobStatus(row[0])
            if status == JobStatus.FAILED:
                # Already failed (idempotent)
                return
            
            # If QUEUED, raise RuntimeError (process flow incorrect)
            raise RuntimeError(f"mark_failed rejected: status={status} (expected RUNNING or PAUSED)")
    
    _with_retry_locked(_op)


def mark_killed(db_path: Path, job_id: str, *, error: str | None = None) -> None:
    """
    Mark job as KILLED (atomic update).
    
    Idempotent: safe to call multiple times.
    
    Args:
        db_path: Path to SQLite database
        job_id: Job ID
        error: Optional error message
        
    Raises:
        KeyError: If job not found
    """
    def _op() -> None:
        with _connect(db_path) as conn:
            ensure_schema(conn)
            cur = conn.execute("""
                UPDATE jobs
                SET status = ?, last_error = ?, updated_at = ?
                WHERE job_id = ?
            """, (JobStatus.KILLED.value, error, _now_iso(), job_id))
            
            if cur.rowcount == 0:
                raise KeyError(f"Job not found: {job_id}")
            
            conn.commit()
    
    _with_retry_locked(_op)


def get_requested_stop(db_path: Path, job_id: str) -> Optional[str]:
    """
    Get requested_stop value for a job.
    
    Args:
        db_path: Path to SQLite database
        job_id: Job ID
        
    Returns:
        Stop mode string or None
    """
    def _op() -> Optional[str]:
        with _connect(db_path) as conn:
            ensure_schema(conn)
            cursor = conn.execute("SELECT requested_stop FROM jobs WHERE job_id = ?", (job_id,))
            row = cursor.fetchone()
            return row[0] if row and row[0] else None
    
    return _with_retry_locked(_op)


def get_requested_pause(db_path: Path, job_id: str) -> bool:
    """
    Get requested_pause value for a job.
    
    Args:
        db_path: Path to SQLite database
        job_id: Job ID
        
    Returns:
        True if pause requested, False otherwise
    """
    def _op() -> bool:
        with _connect(db_path) as conn:
            ensure_schema(conn)
            cursor = conn.execute("SELECT requested_pause FROM jobs WHERE job_id = ?", (job_id,))
            row = cursor.fetchone()
            return bool(row[0]) if row else False
    
    return _with_retry_locked(_op)


def search_by_tag(db_path: Path, tag: str, *, limit: int = 50) -> list[JobRecord]:
    """
    Search jobs by tag.
    
    Uses LIKE query to find jobs containing the tag in tags_json.
    For exact matching, use application-layer filtering.
    
    Args:
        db_path: Path to SQLite database
        tag: Tag to search for
        limit: Maximum number of jobs to return
        
    Returns:
        List of JobRecord matching the tag, ordered by created_at DESC
    """
    def _op() -> list[JobRecord]:
        with _connect(db_path) as conn:
            ensure_schema(conn)
            # Use LIKE to search for tag in JSON array
            # Pattern: tag can appear as ["tag"] or ["tag", ...] or [..., "tag", ...] or [..., "tag"]
            search_pattern = f'%"{tag}"%'
            cursor = conn.execute("""
                SELECT job_id, status, created_at, updated_at,
                       season, dataset_id, outputs_root, config_hash,
                       config_snapshot_json, pid,
                       COALESCE(run_id, NULL) as run_id,
                       run_link,
                       COALESCE(report_link, NULL) as report_link,
                       last_error,
                       COALESCE(tags_json, '[]') as tags_json,
                       COALESCE(data_fingerprint_sha1, '') as data_fingerprint_sha1
                FROM jobs
                WHERE tags_json LIKE ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (search_pattern, limit))
            
            records = [_row_to_record(row) for row in cursor.fetchall()]
            
            # Application-layer filtering for exact match (more reliable than LIKE)
            # Filter to ensure tag is actually in the list, not just substring match
            filtered = []
            for record in records:
                if tag in record.tags:
                    filtered.append(record)
            
            return filtered
    
    return _with_retry_locked(_op)


def append_log(db_path: Path, job_id: str, log_text: str) -> None:
    """
    Append log entry to job_logs table.
    
    Args:
        db_path: Path to SQLite database
        job_id: Job ID
        log_text: Log text to append (can be full traceback)
    """
    def _op() -> None:
        with _connect(db_path) as conn:
            ensure_schema(conn)
            conn.execute("""
                INSERT INTO job_logs (job_id, created_at, log_text)
                VALUES (?, ?, ?)
            """, (job_id, _now_iso(), log_text))
            conn.commit()
    
    _with_retry_locked(_op)


def get_job_logs(db_path: Path, job_id: str, *, limit: int = 100) -> list[str]:
    """
    Get log entries for a job.
    
    Args:
        db_path: Path to SQLite database
        job_id: Job ID
        limit: Maximum number of log entries to return
        
    Returns:
        List of log text entries, ordered by created_at DESC
    """
    def _op() -> list[str]:
        with _connect(db_path) as conn:
            ensure_schema(conn)
            cursor = conn.execute("""
                SELECT log_text
                FROM job_logs
                WHERE job_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (job_id, limit))
            return [row[0] for row in cursor.fetchall()]
    
    return _with_retry_locked(_op)
