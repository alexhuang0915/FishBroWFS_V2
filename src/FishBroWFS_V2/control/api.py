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
    
    # Read last n lines
    try:
        with log_path.open("r", encoding="utf-8") as f:
            all_lines = f.readlines()
        
        lines = all_lines[-n:] if len(all_lines) > n else all_lines
        truncated = len(all_lines) > n
        
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
    
    Returns:
        - report_link: Report link URL (always present, can be None)
    """
    db_path = get_db_path()
    try:
        job = get_job(db_path, job_id)
        return {"report_link": job.report_link}  # Always return the key, even if None
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


def _ensure_worker_running(db_path: Path) -> None:
    """
    Ensure worker process is running (start if not).
    
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
    
    # Start worker in background
    proc = subprocess.Popen(
        [sys.executable, "-m", "FishBroWFS_V2.control.worker_main", str(db_path)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    
    # Write pidfile
    pidfile.write_text(str(proc.pid))

