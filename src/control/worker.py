
"""Worker - long-running task executor."""

from __future__ import annotations

import os
import signal
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ✅ Module-level import for patch support
from pipeline.funnel_runner import run_funnel

from control.jobs_db import (
    get_job,
    get_requested_pause,
    get_requested_stop,
    mark_done,
    mark_failed,
    mark_killed,
    update_running,
    update_run_link,
)
from control.paths import run_log_path
from control.report_links import make_report_link
from control.types import JobStatus, StopMode


def _append_log(log_path: Path, text: str) -> None:
    """
    Append text to log file.
    
    Args:
        log_path: Path to log file
        text: Text to append
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(text)
        if not text.endswith("\n"):
            f.write("\n")


def worker_loop(db_path: Path, *, poll_s: float = 0.5) -> None:
    """
    Worker loop: poll QUEUED jobs and execute them sequentially.
    
    Args:
        db_path: Path to SQLite database
        poll_s: Polling interval in seconds
    """
    while True:
        try:
            # Find QUEUED jobs
            from control.jobs_db import list_jobs
            
            jobs = list_jobs(db_path, limit=100)
            queued_jobs = [j for j in jobs if j.status == JobStatus.QUEUED]
            
            if queued_jobs:
                # Process first QUEUED job
                job = queued_jobs[0]
                run_one_job(db_path, job.job_id)
            else:
                # No jobs, sleep
                time.sleep(poll_s)
        except KeyboardInterrupt:
            break
        except Exception as e:
            # Log error but continue loop
            print(f"Worker loop error: {e}")
            time.sleep(poll_s)


def run_one_job(db_path: Path, job_id: str) -> None:
    """
    Run a single job.
    
    Args:
        db_path: Path to SQLite database
        job_id: Job ID
    """
    log_path: Path | None = None
    try:
        job = get_job(db_path, job_id)
        
        # Check if already terminal
        if job.status in {JobStatus.DONE, JobStatus.FAILED, JobStatus.KILLED}:
            return
        
        # Update to RUNNING with current PID
        pid = os.getpid()
        update_running(db_path, job_id, pid=pid)
        
        # Log status update
        timestamp = datetime.now(timezone.utc).isoformat()
        outputs_root = Path(job.spec.outputs_root)
        season = job.spec.season
        
        # Initialize log_path early (use job_id as run_id fallback)
        log_path = run_log_path(outputs_root, season, job_id)
        
        # Check for KILL before starting
        stop_mode = get_requested_stop(db_path, job_id)
        if stop_mode == StopMode.KILL.value:
            _append_log(log_path, f"{timestamp} [job_id={job_id}] [status=KILLED] Killed before execution")
            mark_killed(db_path, job_id, error="Killed before execution")
            return
        
        outputs_root.mkdir(parents=True, exist_ok=True)
        
        # Reconstruct runtime config from snapshot
        cfg = dict(job.spec.config_snapshot)
        # Ensure required fields are present
        cfg["season"] = job.spec.season
        cfg["dataset_id"] = job.spec.dataset_id
        
        # Log job start
        _append_log(
            log_path,
            f"{timestamp} [job_id={job_id}] [status=RUNNING] Starting funnel execution"
        )
        
        # Check pause/stop before each stage
        _check_pause_stop(db_path, job_id)
        
        # Run funnel
        result = run_funnel(cfg, outputs_root)
        
        # Extract run_id and generate report_link
        run_id: Optional[str] = None
        report_link: Optional[str] = None
        
        if getattr(result, "stages", None) and result.stages:
            last = result.stages[-1]
            run_id = last.run_id
            report_link = make_report_link(season=job.spec.season, run_id=run_id)
            
            # Update run_link
            run_link = str(last.run_dir)
            update_run_link(db_path, job_id, run_link=run_link)
            
            # Log summary
            log_path = run_log_path(outputs_root, season, run_id)
            timestamp = datetime.now(timezone.utc).isoformat()
            _append_log(
                log_path,
                f"{timestamp} [job_id={job_id}] [status=DONE] Funnel completed: "
                f"run_id={run_id}, stage={last.stage.value}, run_dir={run_link}"
            )
        
        # Mark as done with run_id and report_link (both can be None if no stages)
        mark_done(db_path, job_id, run_id=run_id, report_link=report_link)
        
        # Log final status
        timestamp = datetime.now(timezone.utc).isoformat()
        if log_path:
            _append_log(log_path, f"{timestamp} [job_id={job_id}] [status=DONE] Job completed successfully")
        
    except KeyboardInterrupt:
        if log_path:
            timestamp = datetime.now(timezone.utc).isoformat()
            _append_log(log_path, f"{timestamp} [job_id={job_id}] [status=KILLED] Interrupted by user")
        mark_killed(db_path, job_id, error="Interrupted by user")
        raise
    except Exception as e:
        import traceback
        
        # Short for DB column (500 chars)
        error_msg = str(e)[:500]
        mark_failed(db_path, job_id, error=error_msg)
        
        # Full traceback for audit log (MUST)
        tb = traceback.format_exc()
        from control.jobs_db import append_log
        append_log(db_path, job_id, "[ERROR] Unhandled exception\n" + tb)
        
        # Also write to file log if available
        if log_path:
            timestamp = datetime.now(timezone.utc).isoformat()
            _append_log(log_path, f"{timestamp} [job_id={job_id}] [status=FAILED] Error: {error_msg}\n{tb}")
        
        # Keep worker stable
        return


def _check_pause_stop(db_path: Path, job_id: str) -> None:
    """
    Check pause/stop flags and handle accordingly.
    
    Args:
        db_path: Path to SQLite database
        job_id: Job ID
        
    Raises:
        SystemExit: If KILL requested
    """
    stop_mode = get_requested_stop(db_path, job_id)
    if stop_mode == StopMode.KILL.value:
        # Get PID and kill process
        job = get_job(db_path, job_id)
        if job.pid:
            try:
                os.kill(job.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass  # Process already dead
        mark_killed(db_path, job_id, error="Killed by user")
        raise SystemExit("Job killed")
    
    # Handle pause
    while get_requested_pause(db_path, job_id):
        time.sleep(0.5)
        # Re-check stop while paused
        stop_mode = get_requested_stop(db_path, job_id)
        if stop_mode == StopMode.KILL.value:
            job = get_job(db_path, job_id)
            if job.pid:
                try:
                    os.kill(job.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
            mark_killed(db_path, job_id, error="Killed while paused")
            raise SystemExit("Job killed while paused")



