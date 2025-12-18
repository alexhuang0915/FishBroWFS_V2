"""FastAPI endpoints for B5-C Mission Control."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from collections import deque

from FishBroWFS_V2.control.jobs_db import (
    create_job,
    get_job,
    init_db,
    list_jobs,
    request_pause,
    request_stop,
)
from FishBroWFS_V2.control.paths import run_log_path
from FishBroWFS_V2.control.preflight import PreflightResult, run_preflight
from FishBroWFS_V2.control.types import JobRecord, JobSpec, StopMode

# Default DB path (can be overridden via environment)
DEFAULT_DB_PATH = Path("outputs/jobs.db")


def read_tail(path: Path, n: int = 200) -> list[str]:
    """
    Read last n lines from a file using deque (memory-efficient for large files).
    
    Args:
        path: Path to file
        n: Number of lines to return
        
    Returns:
        List of lines (with trailing newlines preserved)
    """
    if not path.exists():
        return []
    
    with path.open("r", encoding="utf-8", errors="replace") as f:
        tail = deque(f, maxlen=n)
    
    return list(tail)


def get_db_path() -> Path:
    """Get database path from environment or default."""
    db_path_str = os.getenv("JOBS_DB_PATH")
    if db_path_str:
        return Path(db_path_str)
    return DEFAULT_DB_PATH


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown."""
    # startup
    db_path = get_db_path()
    init_db(db_path)
    yield
    # shutdown (currently empty)


app = FastAPI(title="B5-C Mission Control API", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}


@app.get("/jobs", response_model=list[JobRecord])
async def list_jobs_endpoint() -> list[JobRecord]:
    """List recent jobs."""
    db_path = get_db_path()
    return list_jobs(db_path)


@app.get("/jobs/{job_id}", response_model=JobRecord)
async def get_job_endpoint(job_id: str) -> JobRecord:
    """Get job by ID."""
    db_path = get_db_path()
    try:
        return get_job(db_path, job_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


class CreateJobRequest(BaseModel):
    """Request body for creating a job."""

    season: str
    dataset_id: str
    outputs_root: str
    config_snapshot: dict[str, Any]
    config_hash: str
    created_by: str = "b5c"


@app.post("/jobs")
async def create_job_endpoint(req: CreateJobRequest) -> dict[str, str]:
    """Create a new job."""
    db_path = get_db_path()
    spec = JobSpec(
        season=req.season,
        dataset_id=req.dataset_id,
        outputs_root=req.outputs_root,
        config_snapshot=req.config_snapshot,
        config_hash=req.config_hash,
        created_by=req.created_by,
    )
    job_id = create_job(db_path, spec)
    return {"job_id": job_id}


@app.post("/jobs/{job_id}/check", response_model=PreflightResult)
async def check_job_endpoint(job_id: str) -> PreflightResult:
    """Run preflight check for a job (does not write to DB)."""
    db_path = get_db_path()
    try:
        job = get_job(db_path, job_id)
        result = run_preflight(job.spec.config_snapshot)
        return result
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/jobs/{job_id}/start")
async def start_job_endpoint(job_id: str) -> dict[str, str]:
    """Start a job (ensure worker is running)."""
    db_path = get_db_path()
    try:
        job = get_job(db_path, job_id)
        
        # If job is QUEUED, worker will pick it up
        # If worker not running, start it
        _ensure_worker_running(db_path)
        
        return {"status": "started", "job_id": job_id}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


class PauseRequest(BaseModel):
    """Request body for pause/unpause."""

    pause: bool


@app.post("/jobs/{job_id}/pause")
async def pause_job_endpoint(job_id: str, req: PauseRequest) -> dict[str, str]:
    """Pause/unpause a job."""
    db_path = get_db_path()
    try:
        request_pause(db_path, job_id, req.pause)
        return {"status": "paused" if req.pause else "unpaused", "job_id": job_id}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


class StopRequest(BaseModel):
    """Request body for stop."""

    mode: str  # "SOFT" or "KILL"


@app.post("/jobs/{job_id}/stop")
async def stop_job_endpoint(job_id: str, req: StopRequest) -> dict[str, str]:
    """Stop a job."""
    db_path = get_db_path()
    try:
        mode = StopMode(req.mode.upper())
        request_stop(db_path, job_id, mode)
        
        # If KILL, also kill the process
        if mode == StopMode.KILL:
            job = get_job(db_path, job_id)
            if job.pid:
                try:
                    os.kill(job.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass  # Process already dead
        
        return {"status": "stopped", "job_id": job_id, "mode": mode.value}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/jobs/{job_id}/log_tail")
async def get_log_tail_endpoint(job_id: str, n: int = 200) -> dict[str, Any]:
    """
    Return last n lines of worker.log for this job's current run_id.
    
    Args:
        job_id: Job ID
        n: Number of lines to return
        
    Returns:
        Dictionary with ok, log_path, lines, truncated
    """
    db_path = get_db_path()
    try:
        job = get_job(db_path, job_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    
    # Get run_id from run_link or use job_id as fallback
    run_id = job.run_link.split("/")[-1] if job.run_link else job_id
    season = job.spec.season
    outputs_root = Path(job.spec.outputs_root)
    
    log_path = run_log_path(outputs_root, season, run_id)
    
    if not log_path.exists():
        return {
            "ok": True,
            "log_path": str(log_path),
            "lines": [],
            "truncated": False,
        }
    
    # Read last n lines using deque (memory-efficient for large files)
    try:
        lines = read_tail(log_path, n)
        # Check if file was truncated (if we read exactly n lines, might be more)
        # Simple heuristic: if file size is very large, likely truncated
        file_size = log_path.stat().st_size
        truncated = file_size > 1024 * 1024  # 1MB threshold
        
        return {
            "ok": True,
            "log_path": str(log_path),
            "lines": [line.rstrip("\n") for line in lines],
            "truncated": truncated,
        }
    except Exception as e:
        # Don't 500 on log read errors, but still return ok=True
        return {
            "ok": True,
            "log_path": str(log_path),
            "lines": [],
            "truncated": False,
            "error": str(e),
        }


@app.get("/jobs/{job_id}/report_link")
async def get_report_link_endpoint(job_id: str) -> dict[str, Any]:
    """
    Get report_link for a job.
    
    Phase 6 rule: Always return Viewer URL if run_id exists.
    Viewer will handle missing/invalid artifacts gracefully.
    
    Returns:
        - ok: Always True if job exists
        - report_link: Report link URL (always present if run_id exists)
    """
    from FishBroWFS_V2.control.report_links import build_report_link
    
    db_path = get_db_path()
    try:
        job = get_job(db_path, job_id)
        
        # Respect DB: if report_link exists in DB, return it as-is
        if job.report_link:
            return {"ok": True, "report_link": job.report_link}
        
        # If no report_link in DB but has run_id, build it
        if job.run_id:
            season = job.spec.season
            report_link = build_report_link(season, job.run_id)
            return {"ok": True, "report_link": report_link}
        
        # If no run_id, return empty string (never None)
        return {"ok": True, "report_link": ""}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


def _ensure_worker_running(db_path: Path) -> None:
    """
    Ensure worker process is running (start if not).
    
    Worker stdout/stderr are redirected to worker_process.log (append mode)
    to avoid deadlock from unread PIPE buffers.
    
    Args:
        db_path: Path to SQLite database
    """
    # Check if worker is already running (simple check via pidfile)
    pidfile = db_path.parent / "worker.pid"
    if pidfile.exists():
        try:
            pid = int(pidfile.read_text().strip())
            # Check if process exists
            os.kill(pid, 0)
            return  # Worker already running
        except (OSError, ValueError):
            # Process dead, remove pidfile
            pidfile.unlink(missing_ok=True)
    
    # Prepare log file (same directory as db_path)
    logs_dir = db_path.parent  # usually outputs/.../control/
    logs_dir.mkdir(parents=True, exist_ok=True)
    worker_log = logs_dir / "worker_process.log"
    
    # Open in append mode, line-buffered
    out = open(worker_log, "a", buffering=1, encoding="utf-8")  # noqa: SIM115
    
    # Start worker in background
    proc = subprocess.Popen(
        [sys.executable, "-m", "FishBroWFS_V2.control.worker_main", str(db_path)],
        stdout=out,
        stderr=out,
        stdin=subprocess.DEVNULL,
        close_fds=True,
        start_new_session=True,  # detach from API server session
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    
    # Write pidfile
    pidfile.write_text(str(proc.pid))

