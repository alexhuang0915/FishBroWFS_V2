from __future__ import annotations
from pathlib import Path
from pydantic import BaseModel, Field
from typing import Any, Dict, Optional, Literal
from enum import StrEnum
import uuid
from datetime import datetime, timezone

# Canonical Job Contract
# ======================

# JobType enum (string constants)
# FROZEN — Do not modify without Phase approval
class JobType(StrEnum):
    """Canonical job types."""
    BUILD_DATA = "BUILD_DATA"
    BUILD_BARS = "BUILD_BARS"
    BUILD_FEATURES = "BUILD_FEATURES"
    BUILD_PORTFOLIO_V2 = "BUILD_PORTFOLIO_V2"
    FINALIZE_PORTFOLIO_V1 = "FINALIZE_PORTFOLIO_V1"
    RUN_RESEARCH_WFS = "RUN_RESEARCH_WFS"  # Phase4-A: Walk-Forward Simulation research
    
    # Legacy / Utility
    RUN_RESEARCH_V2 = "RUN_RESEARCH_V2"
    RUN_FREEZE_V2 = "RUN_FREEZE_V2"
    RUN_COMPILE_V2 = "RUN_COMPILE_V2"
    RUN_PLATEAU_V2 = "RUN_PLATEAU_V2"

# JobStatus enum (matches JobState values)
class JobStatus(StrEnum):
    """Canonical job status values."""
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    ABORTED = "ABORTED"
    ORPHANED = "ORPHANED"
    REJECTED = "REJECTED"

# JobState remains as Literal for backward compatibility
JobState = Literal["QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "ABORTED", "ORPHANED", "REJECTED"]

# JobStateMachine - validates state transitions
class JobStateMachine:
    """Canonical job state machine."""
    
    # Valid transitions: from -> set(to)
    TRANSITIONS = {
        JobStatus.QUEUED: {JobStatus.RUNNING, JobStatus.FAILED, JobStatus.ABORTED, JobStatus.REJECTED},
        JobStatus.RUNNING: {JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.ABORTED, JobStatus.ORPHANED},
        JobStatus.SUCCEEDED: set(),  # terminal
        JobStatus.FAILED: set(),     # terminal
        JobStatus.ABORTED: set(),    # terminal
        JobStatus.ORPHANED: set(),   # terminal
        JobStatus.REJECTED: set(),   # terminal
    }
    
    @classmethod
    def can_transition(cls, from_state: JobStatus, to_state: JobStatus) -> bool:
        """Check if transition is valid."""
        return to_state in cls.TRANSITIONS.get(from_state, set())
    
    @classmethod
    def validate_transition(cls, from_state: JobStatus, to_state: JobStatus) -> None:
        """Raise ValueError if transition is invalid."""
        if not cls.can_transition(from_state, to_state):
            raise ValueError(
                f"Invalid job state transition: {from_state} -> {to_state}. "
                f"Allowed: {cls.TRANSITIONS.get(from_state, set())}"
            )

def normalize_job_type(job_type: str | JobType) -> JobType:
    """
    Convert any job type string (including legacy aliases) to canonical JobType.
    
    Supported legacy aliases:
      - "BUILD_PORTFOLIO" -> JobType.BUILD_PORTFOLIO_V2
      - case-insensitive matching (uppercase/lowercase)
    
    Raises ValueError if job_type cannot be normalized.
    """
    if isinstance(job_type, JobType):
        return job_type
    
    # Normalize to uppercase, strip whitespace
    normalized = job_type.strip().upper()
    
    # Legacy alias mapping
    legacy_map = {
        "BUILD_PORTFOLIO": JobType.BUILD_PORTFOLIO_V2,
        "FINALIZE_PORTFOLIO": JobType.FINALIZE_PORTFOLIO_V1,
        "BUILD_DATA": JobType.BUILD_DATA,
        "BUILD_BARS": JobType.BUILD_BARS,
        "BUILD_FEATURES": JobType.BUILD_FEATURES,
    }
    
    # Check legacy map first
    if normalized in legacy_map:
        return legacy_map[normalized]
    
    # Try direct enum lookup
    try:
        return JobType(normalized)
    except ValueError:
        # Provide helpful error message
        valid = [t.value for t in JobType]
        raise ValueError(
            f"Invalid job type: {job_type}. Must be one of {valid} "
            f"(or legacy aliases: {list(legacy_map.keys())})"
        )


HEARTBEAT_INTERVAL_SEC: float = 2.0
HEARTBEAT_TIMEOUT_SEC: float = 10.0
REAP_GRACE_SEC: float = 2.0


class JobSpec(BaseModel):
    """Canonical job specification."""
    job_type: JobType
    params: Dict[str, Any]
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SubmitResult(BaseModel):
    job_id: str


class JobRow(BaseModel):
    job_id: str
    job_type: JobType
    spec_json: str
    state: JobState
    state_reason: str = ""
    result_json: str = ""
    created_at: str
    updated_at: str
    worker_id: Optional[str] = None
    worker_pid: Optional[int] = None
    last_heartbeat: Optional[str] = None
    abort_requested: bool = False
    progress: Optional[float] = None
    phase: Optional[str] = None
    error_details: Optional[str] = None
    params_hash: str = ""
    failure_code: str = ""
    failure_message: str = ""
    failure_details: Optional[str] = None
    policy_stage: str = ""


class WorkerRow(BaseModel):
    worker_id: str
    pid: int
    current_job_id: Optional[str] = None
    status: Literal["IDLE", "BUSY", "EXITED"] = "IDLE"
    spawned_at: str
    exited_at: Optional[str] = None


def new_job_id() -> str:
    return str(uuid.uuid4())


def new_worker_id() -> str:
    return str(uuid.uuid4())


def now_iso() -> str:
    """Return current UTC time in ISO format."""
    return datetime.now(timezone.utc).isoformat()


def parse_iso(iso_str: str) -> datetime:
    """Parse ISO string to datetime (timezone-aware)."""
    if iso_str.endswith("Z"):
        iso_str = iso_str[:-1] + "+00:00"
    return datetime.fromisoformat(iso_str)


def seconds_since(timestamp: str, now: Optional[str] = None) -> float:
    """Calculate seconds elapsed since given ISO timestamp."""
    if not timestamp:
        return float("inf")
    t = parse_iso(timestamp)
    n = parse_iso(now) if now else datetime.now(timezone.utc)
    return (n - t).total_seconds()


def get_job_artifact_dir(outputs_root: Path, job_id: str) -> Path:
    """
    Return canonical artifact directory for a job.
    
    Contract:
      - returns outputs_root / "artifacts" / "jobs" / job_id
      - job_id must be a valid UUID (or at least safe path component)
      - no path traversal allowed (job_id must not contain '/', '..', etc.)
      - caller should mkdir(parents=True, exist_ok=True) before writing.
    """
    # Basic sanitization: ensure job_id is a single path component
    if not job_id or "/" in job_id or "\\" in job_id or job_id in (".", ".."):
        raise ValueError(f"Invalid job_id for artifact directory: {job_id}")
    return (outputs_root / "artifacts" / "jobs" / job_id).resolve()
