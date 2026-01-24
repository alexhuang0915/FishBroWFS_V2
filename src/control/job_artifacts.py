from __future__ import annotations

from pathlib import Path
from typing import Optional

from core.paths import get_outputs_root


def get_jobs_evidence_root() -> Path:
    """Return the canonical root for job evidence bundles."""
    return get_outputs_root() / "artifacts" / "jobs"


def get_job_evidence_dir(job_id: str) -> Path:
    """Return the locked evidence directory for a job (path traversal guarded)."""
    root = get_jobs_evidence_root()
    job_dir = root / job_id
    try:
        job_dir.resolve().relative_to(root.resolve())
    except ValueError:
        raise ValueError("job_id contains path traversal")
    return job_dir


def job_evidence_dir_exists(job_id: str) -> bool:
    """Check whether the job evidence directory exists."""
    return get_job_evidence_dir(job_id).exists()


def job_artifact_exists(job_id: str, filename: str) -> bool:
    """Check whether a named artifact exists for the job."""
    return (get_job_evidence_dir(job_id) / filename).exists()

def get_job_artifact_path(job_id: str, filename: str) -> Path:
    """Return the Path to a job artifact file."""
    return get_job_evidence_dir(job_id) / filename
