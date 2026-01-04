from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Any, Dict, Optional, Literal
import uuid
from datetime import datetime, timezone

JobState = Literal["QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "ABORTED", "ORPHANED"]

HEARTBEAT_INTERVAL_SEC: float = 2.0
HEARTBEAT_TIMEOUT_SEC: float = 10.0
REAP_GRACE_SEC: float = 2.0


class JobSpec(BaseModel):
    job_type: str
    params: Dict[str, Any]
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SubmitResult(BaseModel):
    job_id: str


class JobRow(BaseModel):
    job_id: str
    job_type: str
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