from __future__ import annotations
import sqlite3
import json
from pathlib import Path
from typing import Optional, List, Dict, Any
from .models import (
    JobSpec, JobRow, WorkerRow, JobState, JobStatus, JobStateMachine,
    new_job_id, new_worker_id, now_iso, parse_iso, seconds_since
)


def get_default_db_path(outputs_root: Optional[Path] = None) -> Path:
    """Return default DB path under outputs/jobs_v2.db."""
    if outputs_root is None:
        outputs_root = Path("outputs")
    return outputs_root / "jobs_v2.db"


class SupervisorDB:
    """SQLite v2 with atomic transitions."""
    
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.init_schema()
    
    def _connect(self) -> sqlite3.Connection:
        """Create connection with explicit transaction control."""
        conn = sqlite3.connect(str(self.db_path), isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn
    
    def init_schema(self) -> None:
        """Initialize database schema."""
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                # jobs table
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS jobs (
                        job_id TEXT PRIMARY KEY,
                        job_type TEXT NOT NULL,
                        spec_json TEXT NOT NULL,
                        state TEXT NOT NULL,
                        state_reason TEXT DEFAULT '',
                        result_json TEXT DEFAULT '',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        worker_id TEXT NULL,
                        worker_pid INTEGER NULL,
                        last_heartbeat TEXT NULL,
                        abort_requested INTEGER DEFAULT 0,
                        progress REAL NULL,
                        phase TEXT NULL,
                        params_hash TEXT DEFAULT ''
                    )
                """)
                
                # Add params_hash column if it doesn't exist (schema migration)
                cursor = conn.execute("PRAGMA table_info(jobs)")
                columns = [row[1] for row in cursor.fetchall()]
                if "params_hash" not in columns:
                    conn.execute("ALTER TABLE jobs ADD COLUMN params_hash TEXT DEFAULT ''")
                
                # workers table
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS workers (
                        worker_id TEXT PRIMARY KEY,
                        pid INTEGER NOT NULL,
                        current_job_id TEXT NULL,
                        status TEXT NOT NULL DEFAULT 'IDLE',
                        spawned_at TEXT NOT NULL,
                        exited_at TEXT NULL,
                        FOREIGN KEY (current_job_id) REFERENCES jobs (job_id)
                    )
                """)
                # indexes
                conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_state ON jobs(state)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_worker ON jobs(worker_id)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_heartbeat ON jobs(last_heartbeat)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_workers_status ON workers(status)")
                # Index for duplicate fingerprint checks
                conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_type_params_hash ON jobs(job_type, params_hash)")
                # Unique index for duplicate prevention (only for non-empty params_hash and active states)
                conn.execute("""
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_type_params_hash_unique
                    ON jobs(job_type, params_hash)
                    WHERE params_hash != '' AND state IN ('QUEUED', 'RUNNING', 'SUCCEEDED')
                """)
                
                # Repair invalid state records (quarantine)
                valid_states = [
                    JobStatus.QUEUED,
                    JobStatus.RUNNING,
                    JobStatus.SUCCEEDED,
                    JobStatus.FAILED,
                    JobStatus.ABORTED,
                    JobStatus.ORPHANED,
                    JobStatus.REJECTED,
                ]
                placeholders = ",".join(["?"] * len(valid_states))
                conn.execute(f"""
                    UPDATE jobs
                    SET state = ?, state_reason = ?
                    WHERE state NOT IN ({placeholders})
                """, (JobStatus.ORPHANED, "invalid state repaired", *valid_states))
                
                conn.commit()
            except Exception:
                conn.rollback()
                raise
    
    def submit_job(self, spec: JobSpec, params_hash: str = "", state: JobStatus = JobStatus.QUEUED) -> str:
        """Submit a new job and return job_id."""
        job_id = new_job_id()
        now = now_iso()
        spec_json = spec.model_dump_json()
        
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute("""
                    INSERT INTO jobs (
                        job_id, job_type, spec_json, state, state_reason,
                        result_json, created_at, updated_at,
                        worker_id, worker_pid, last_heartbeat,
                        abort_requested, progress, phase, params_hash
                    ) VALUES (?, ?, ?, ?, '', '', ?, ?, NULL, NULL, NULL, 0, NULL, NULL, ?)
                """, (job_id, spec.job_type, spec_json, state, now, now, params_hash))
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        
        return job_id
    
    def submit_rejected_job(self, spec: JobSpec, params_hash: str, rejection_reason: str) -> str:
        """Submit a job with REJECTED state."""
        job_id = new_job_id()
        now = now_iso()
        spec_json = spec.model_dump_json()
        
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute("""
                    INSERT INTO jobs (
                        job_id, job_type, spec_json, state, state_reason,
                        result_json, created_at, updated_at,
                        worker_id, worker_pid, last_heartbeat,
                        abort_requested, progress, phase, params_hash
                    ) VALUES (?, ?, ?, ?, ?, '', ?, ?, NULL, NULL, NULL, 0, NULL, NULL, ?)
                """, (job_id, spec.job_type, spec_json, JobStatus.REJECTED, rejection_reason, now, now, params_hash))
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        
        return job_id
    
    def fetch_next_queued_job(self) -> Optional[str]:
        """Fetch next QUEUED job ID, marking it RUNNING atomically."""
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                cursor = conn.execute("""
                    SELECT job_id FROM jobs
                    WHERE state = ?
                    AND abort_requested = 0
                    ORDER BY created_at ASC
                    LIMIT 1
                """, (JobStatus.QUEUED,))
                row = cursor.fetchone()
                if row is None:
                    conn.commit()
                    return None
                job_id = row["job_id"]
                # Validate transition QUEUED -> RUNNING
                JobStateMachine.validate_transition(
                    JobStatus.QUEUED, JobStatus.RUNNING
                )
                # Mark as RUNNING (no worker assigned yet)
                conn.execute("""
                    UPDATE jobs
                    SET state = ?, updated_at = ?
                    WHERE job_id = ? AND state = ?
                """, (JobStatus.RUNNING, now_iso(), job_id, JobStatus.QUEUED))
                conn.commit()
                return job_id
            except Exception:
                conn.rollback()
                raise
    
    def get_job_row(self, job_id: str) -> Optional[JobRow]:
        """Get job row by ID."""
        with self._connect() as conn:
            cursor = conn.execute("""
                SELECT * FROM jobs WHERE job_id = ?
            """, (job_id,))
            row = cursor.fetchone()
            if row is None:
                return None
            return JobRow(**dict(row))
    
    def mark_running(self, job_id: str, worker_id: str, pid: int) -> None:
        """Mark job as RUNNING with worker assignment."""
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute("""
                    UPDATE jobs
                    SET state = ?, updated_at = ?,
                        worker_id = ?, worker_pid = ?, last_heartbeat = ?
                    WHERE job_id = ? AND state IN (?, ?)
                """, (JobStatus.RUNNING, now_iso(), worker_id, pid, now_iso(), job_id, JobStatus.QUEUED, JobStatus.RUNNING))
                # Update worker
                conn.execute("""
                    UPDATE workers
                    SET current_job_id = ?, status = 'BUSY'
                    WHERE worker_id = ?
                """, (job_id, worker_id))
                conn.commit()
            except Exception:
                conn.rollback()
                raise
    
    def mark_succeeded(self, job_id: str, result: dict) -> None:
        """Mark job as SUCCEEDED with result."""
        result_json = json.dumps(result)
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                # Get current state for validation
                cursor = conn.execute("SELECT state, worker_id, worker_pid FROM jobs WHERE job_id = ?", (job_id,))
                row = cursor.fetchone()
                if row is None:
                    raise ValueError(f"Job {job_id} not found")
                current_state = row["state"]
                # Validate transition
                JobStateMachine.validate_transition(
                    JobStatus(current_state), JobStatus.SUCCEEDED
                )
                
                conn.execute("""
                    UPDATE jobs
                    SET state = ?, updated_at = ?,
                        result_json = ?, state_reason = ''
                    WHERE job_id = ? AND state = ?
                """, (JobStatus.SUCCEEDED, now_iso(), result_json, job_id, JobStatus.RUNNING))
                # Clear worker assignment
                if row["worker_id"]:
                    conn.execute("""
                        UPDATE workers
                        SET current_job_id = NULL, status = 'IDLE'
                        WHERE worker_id = ?
                    """, (row["worker_id"],))
                conn.commit()
            except Exception:
                conn.rollback()
                raise
    
    def mark_failed(self, job_id: str, reason: str) -> None:
        """Mark job as FAILED with reason."""
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                # Get current state for validation
                cursor = conn.execute("SELECT state, worker_id FROM jobs WHERE job_id = ?", (job_id,))
                row = cursor.fetchone()
                if row is None:
                    raise ValueError(f"Job {job_id} not found")
                current_state = row["state"]
                # Validate transition
                JobStateMachine.validate_transition(
                    JobStatus(current_state), JobStatus.FAILED
                )
                
                conn.execute("""
                    UPDATE jobs
                    SET state = ?, updated_at = ?, state_reason = ?
                    WHERE job_id = ? AND state IN (?, ?)
                """, (JobStatus.FAILED, now_iso(), reason, job_id, JobStatus.QUEUED, JobStatus.RUNNING))
                # Clear worker assignment if any
                if row["worker_id"]:
                    conn.execute("""
                        UPDATE workers
                        SET current_job_id = NULL, status = 'IDLE'
                        WHERE worker_id = ?
                    """, (row["worker_id"],))
                conn.commit()
            except Exception:
                conn.rollback()
                raise
    
    def mark_aborted(self, job_id: str, reason: str) -> None:
        """Mark job as ABORTED with reason."""
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                # Get current state for validation
                cursor = conn.execute("SELECT state, worker_id FROM jobs WHERE job_id = ?", (job_id,))
                row = cursor.fetchone()
                if row is None:
                    raise ValueError(f"Job {job_id} not found")
                current_state = row["state"]
                # Validate transition
                JobStateMachine.validate_transition(
                    JobStatus(current_state), JobStatus.ABORTED
                )
                
                conn.execute("""
                    UPDATE jobs
                    SET state = ?, updated_at = ?, state_reason = ?
                    WHERE job_id = ? AND state IN (?, ?)
                """, (JobStatus.ABORTED, now_iso(), reason, job_id, JobStatus.QUEUED, JobStatus.RUNNING))
                # Clear worker assignment if any
                if row["worker_id"]:
                    conn.execute("""
                        UPDATE workers
                        SET current_job_id = NULL, status = 'IDLE'
                        WHERE worker_id = ?
                    """, (row["worker_id"],))
                conn.commit()
            except Exception:
                conn.rollback()
                raise
    
    def mark_orphaned(self, job_id: str, reason: str) -> None:
        """Mark job as ORPHANED with reason."""
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                # Get current state for validation
                cursor = conn.execute("SELECT state FROM jobs WHERE job_id = ?", (job_id,))
                row = cursor.fetchone()
                if row is None:
                    raise ValueError(f"Job {job_id} not found")
                current_state = row["state"]
                # Validate transition
                JobStateMachine.validate_transition(
                    JobStatus(current_state), JobStatus.ORPHANED
                )
                
                conn.execute("""
                    UPDATE jobs
                    SET state = ?, updated_at = ?, state_reason = ?
                    WHERE job_id = ? AND state = ?
                """, (JobStatus.ORPHANED, now_iso(), reason, job_id, JobStatus.RUNNING))
                conn.commit()
            except Exception:
                conn.rollback()
                raise
    
    def update_heartbeat(self, job_id: str, progress: float | None = None, phase: str | None = None) -> None:
        """Update heartbeat timestamp and optional progress/phase."""
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                update_fields = ["last_heartbeat = ?", "updated_at = ?"]
                params = [now_iso(), now_iso()]
                
                if progress is not None:
                    update_fields.append("progress = ?")
                    params.append(progress)
                if phase is not None:
                    update_fields.append("phase = ?")
                    params.append(phase)
                
                params.append(job_id)
                params.append(JobStatus.RUNNING)
                query = f"""
                    UPDATE jobs
                    SET {', '.join(update_fields)}
                    WHERE job_id = ? AND state = ?
                """
                conn.execute(query, params)
                conn.commit()
            except Exception:
                conn.rollback()
                raise
    
    def request_abort(self, job_id: str) -> None:
        """Set abort_requested flag for a job."""
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute("""
                    UPDATE jobs
                    SET abort_requested = 1, updated_at = ?
                    WHERE job_id = ? AND state IN (?, ?)
                """, (now_iso(), job_id, JobStatus.QUEUED, JobStatus.RUNNING))
                conn.commit()
            except Exception:
                conn.rollback()
                raise
    
    def is_abort_requested(self, job_id: str) -> bool:
        """Check if abort is requested for a job."""
        with self._connect() as conn:
            cursor = conn.execute("""
                SELECT abort_requested FROM jobs WHERE job_id = ?
            """, (job_id,))
            row = cursor.fetchone()
            return bool(row and row["abort_requested"])
    
    def find_running_jobs_stale(self, now_iso: str, timeout_sec: float) -> List[JobRow]:
        """Find RUNNING jobs with stale heartbeat beyond timeout."""
        with self._connect() as conn:
            cursor = conn.execute("""
                SELECT * FROM jobs
                WHERE state = ? AND last_heartbeat IS NOT NULL
            """, (JobStatus.RUNNING,))
            rows = cursor.fetchall()
        
        stale = []
        for row in rows:
            last = row["last_heartbeat"]
            if last and seconds_since(last, now_iso) > timeout_sec:
                stale.append(JobRow(**dict(row)))
        return stale
    
    def register_worker(self, worker_id: str, pid: int) -> None:
        """Register a new worker."""
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute("""
                    INSERT INTO workers (worker_id, pid, spawned_at, status)
                    VALUES (?, ?, ?, 'IDLE')
                """, (worker_id, pid, now_iso()))
                conn.commit()
            except Exception:
                conn.rollback()
                raise
    
    def mark_worker_exited(self, worker_id: str) -> None:
        """Mark worker as EXITED."""
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute("""
                    UPDATE workers 
                    SET status = 'EXITED', exited_at = ?
                    WHERE worker_id = ?
                """, (now_iso(), worker_id))
                conn.commit()
            except Exception:
                conn.rollback()
                raise
    
    def get_worker_by_pid(self, pid: int) -> Optional[WorkerRow]:
        """Get worker row by PID."""
        with self._connect() as conn:
            cursor = conn.execute("""
                SELECT * FROM workers WHERE pid = ?
            """, (pid,))
            row = cursor.fetchone()
            if row is None:
                return None
            return WorkerRow(**dict(row))