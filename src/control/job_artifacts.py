from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import HTTPException

from core.paths import get_outputs_root


def get_jobs_evidence_root() -> Path:
    """Return the canonical root for job evidence bundles."""
    return get_outputs_root() / "jobs"


def get_job_evidence_dir(job_id: str) -> Path:
    """Return the locked evidence directory for a job (path traversal guarded)."""
    root = get_jobs_evidence_root()
    job_dir = root / job_id
    try:
        job_dir.resolve().relative_to(root.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Job ID contains path traversal")
    return job_dir


def job_evidence_dir_exists(job_id: str) -> bool:
    """Check whether the job evidence directory exists."""
    return get_job_evidence_dir(job_id).exists()


def job_artifact_exists(job_id: str, filename: str) -> bool:
    """Check whether a named artifact exists for the job."""
    return (get_job_evidence_dir(job_id) / filename).exists()


def job_artifact_url(job_id: str, filename: str) -> str:
    """Return the artifact URL for a job."""
    return f"/api/v1/jobs/{job_id}/artifacts/{filename}"


def artifact_url_if_exists(job_id: str, filename: str) -> Optional[str]:
    """Return the artifact URL only when the file exists."""
    if job_artifact_exists(job_id, filename):
        return job_artifact_url(job_id, filename)
    return None


def stdout_tail_url(job_id: str) -> Optional[str]:
    """Return the stdout tail endpoint when evidence exists."""
    if job_evidence_dir_exists(job_id):
        return f"/api/v1/jobs/{job_id}/logs/stdout_tail"
    return None


def evidence_bundle_url(job_id: str) -> Optional[str]:
    """Return the evidence bundle reveal endpoint when evidence exists."""
    if job_evidence_dir_exists(job_id):
        return f"/api/v1/jobs/{job_id}/reveal_evidence_path"
    return None
