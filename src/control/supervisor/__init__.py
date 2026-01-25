"""
Supervisor v1 - Process-based job supervisor with plugin registry.
"""
from __future__ import annotations
from typing import Optional, List, Dict, Any
from pathlib import Path

from .models import JobSpec, JobRow, SubmitResult, JobType, normalize_job_type
from .db import SupervisorDB, get_default_db_path
from .job_handler import register_handler, get_handler, validate_job_spec
from ..policy_enforcement import evaluate_preflight, PolicyEnforcementError, write_policy_check_artifact, PolicyResult


# Import and register built-in handlers (Local Research OS mode: mainline only)
from .handlers.build_data import build_data_handler
from .handlers.build_data import build_bars_handler, build_features_handler
from .handlers.build_portfolio import build_portfolio_handler
from .handlers.finalize_portfolio import finalize_portfolio_handler
from .handlers.run_research_wfs import run_research_wfs_handler

register_handler("BUILD_DATA", build_data_handler)
register_handler("BUILD_BARS", build_bars_handler)
register_handler("BUILD_FEATURES", build_features_handler)
register_handler("BUILD_PORTFOLIO_V2", build_portfolio_handler)
register_handler("FINALIZE_PORTFOLIO_V1", finalize_portfolio_handler)
register_handler("RUN_RESEARCH_WFS", run_research_wfs_handler)


def submit(job_type: str, params: dict, metadata: Optional[dict] = None) -> str:
    """Submit a job to supervisor."""
    if metadata is None:
        metadata = {}
    
    # Convert string to canonical JobType enum (including legacy aliases)
    canonical_job_type = normalize_job_type(job_type)
    
    spec = JobSpec(job_type=canonical_job_type, params=params, metadata=metadata)
    validate_job_spec(spec)

    policy_result = evaluate_preflight(spec)
    db = SupervisorDB(get_default_db_path())
    if not policy_result.allowed:
        job_id = db.submit_rejected_job(
            spec,
            "",
            policy_result.message,
            failure_code=policy_result.code,
            failure_message=policy_result.message,
            failure_details=policy_result.details,
            policy_stage=policy_result.stage,
        )
        write_policy_check_artifact(
            job_id,
            spec.job_type,
            preflight_results=[policy_result],
            final_reason={
                "policy_stage": policy_result.stage,
                "failure_code": policy_result.code,
                "failure_message": policy_result.message,
                "failure_details": policy_result.details,
            },
        )
        raise PolicyEnforcementError(job_id, policy_result)

    # After policy passes, validate handler payload. If invalid, record REJECTED.
    handler = get_handler(str(spec.job_type))
    if handler is None:
        # Should not happen due to validate_job_spec, but keep deterministic.
        invalid = PolicyResult(
            allowed=False,
            code="POLICY_REJECT_UNKNOWN_HANDLER",
            message=f"Unknown job_type: {spec.job_type}",
            details={"job_type": str(spec.job_type)},
            stage="preflight",
        )
        job_id = db.submit_rejected_job(
            spec,
            "",
            invalid.message,
            failure_code=invalid.code,
            failure_message=invalid.message,
            failure_details=invalid.details,
            policy_stage=invalid.stage,
        )
        write_policy_check_artifact(job_id, spec.job_type, preflight_results=[invalid])
        raise PolicyEnforcementError(job_id, invalid)

    try:
        handler.validate_params(spec.params)
    except Exception as e:
        invalid = PolicyResult(
            allowed=False,
            code="POLICY_REJECT_INVALID_PAYLOAD",
            message=str(e),
            details={"params_keys": list(spec.params.keys())},
            stage="preflight",
        )
        job_id = db.submit_rejected_job(
            spec,
            "",
            invalid.message,
            failure_code=invalid.code,
            failure_message=invalid.message,
            failure_details=invalid.details,
            policy_stage=invalid.stage,
        )
        write_policy_check_artifact(job_id, spec.job_type, preflight_results=[invalid])
        raise PolicyEnforcementError(job_id, invalid)

    job_id = db.submit_job(spec)
    write_policy_check_artifact(
        job_id,
        spec.job_type,
        preflight_results=[policy_result],
    )
    return job_id


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
