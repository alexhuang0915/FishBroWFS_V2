
"""Type definitions for B5-C Mission Control."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal, Optional


class JobStatus(StrEnum):
    """Job status state machine."""

    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    DONE = "DONE"
    FAILED = "FAILED"
    KILLED = "KILLED"


class StopMode(StrEnum):
    """Stop request mode."""

    SOFT = "SOFT"
    KILL = "KILL"


@dataclass(frozen=True)
class DBJobSpec:
    """Job specification for DB/worker runtime (input to create_job)."""

    season: str
    dataset_id: str
    outputs_root: str
    config_snapshot: dict[str, Any]  # sanitized; no ndarrays
    config_hash: str
    data_fingerprint_sha256_40: str = ""  # Data fingerprint SHA256[:40] (empty if not provided, marks DIRTY)
    created_by: str = "b5c"


@dataclass(frozen=True)
class JobRecord:
    """Job record (returned from DB)."""

    job_id: str
    status: JobStatus
    created_at: str
    updated_at: str
    spec: DBJobSpec
    pid: Optional[int] = None
    run_id: Optional[str] = None  # Final stage run_id (e.g. stage2_confirm-xxx)
    run_link: Optional[str] = None  # e.g. outputs/.../stage0_run_id or final run index pointer
    report_link: Optional[str] = None  # Link to B5 report viewer
    last_error: Optional[str] = None
    tags: list[str] = field(default_factory=list)  # Tags for job categorization and search
    data_fingerprint_sha256_40: str = ""  # Data fingerprint SHA256[:40] (empty if missing, marks DIRTY)



