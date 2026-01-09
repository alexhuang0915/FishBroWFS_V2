"""
Supervisor v1 - Process-based job supervisor with plugin registry.
"""
from __future__ import annotations
from typing import Optional, List, Dict, Any
from pathlib import Path

from .models import JobSpec, JobRow, SubmitResult, JobType, normalize_job_type
from .db import SupervisorDB, get_default_db_path
from .job_handler import register_handler, get_handler, validate_job_spec


# Import and register built-in handlers
from .handlers.ping import ping_handler
from .handlers.clean_cache import clean_cache_handler
from .handlers.build_data import build_data_handler
from .handlers.generate_reports import generate_reports_handler
from .handlers.run_research import run_research_handler
from .handlers.run_plateau import run_plateau_handler
from .handlers.run_freeze import run_freeze_handler
from .handlers.run_compile import run_compile_handler
from .handlers.build_portfolio import build_portfolio_handler
from .handlers.run_research_wfs import run_research_wfs_handler
from .handlers.run_portfolio_admission import run_portfolio_admission_handler

register_handler("PING", ping_handler)
register_handler("CLEAN_CACHE", clean_cache_handler)
register_handler("BUILD_DATA", build_data_handler)
register_handler("GENERATE_REPORTS", generate_reports_handler)
register_handler("RUN_RESEARCH_V2", run_research_handler)
register_handler("RUN_PLATEAU_V2", run_plateau_handler)
register_handler("RUN_FREEZE_V2", run_freeze_handler)
register_handler("RUN_COMPILE_V2", run_compile_handler)
register_handler("BUILD_PORTFOLIO_V2", build_portfolio_handler)
register_handler("RUN_RESEARCH_WFS", run_research_wfs_handler)
register_handler("RUN_PORTFOLIO_ADMISSION", run_portfolio_admission_handler)


def submit(job_type: str, params: dict, metadata: Optional[dict] = None) -> str:
    """Submit a job to supervisor."""
    if metadata is None:
        metadata = {}
    
    # Convert string to canonical JobType enum (including legacy aliases)
    canonical_job_type = normalize_job_type(job_type)
    
    spec = JobSpec(job_type=canonical_job_type, params=params, metadata=metadata)
    validate_job_spec(spec)
    
    db = SupervisorDB(get_default_db_path())
    return db.submit_job(spec)


def request_abort(job_id: str) -> None:
    """Request abort for a job."""
    db = SupervisorDB(get_default_db_path())
    db.request_abort(job_id)


def get_job(job_id: str) -> Optional[JobRow]:
    """Get job details."""
    db = SupervisorDB(get_default_db_path())
    return db.get_job_row(job_id)


def list_jobs(state: Optional[str] = None) -> List[JobRow]:
    """List jobs, optionally filtered by state."""
    db = SupervisorDB(get_default_db_path())
    
    with db._connect() as conn:
        if state:
            cursor = conn.execute(
                "SELECT * FROM jobs WHERE state = ? ORDER BY created_at DESC",
                (state,)
            )
        else:
            cursor = conn.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC"
            )
        
        rows = cursor.fetchall()
        return [JobRow(**dict(row)) for row in rows]


__all__ = [
    "SupervisorDB",
    "JobSpec",
    "JobRow",
    "SubmitResult",
    "submit",
    "request_abort",
    "get_job",
    "list_jobs",
    "register_handler",
    "get_handler",
]