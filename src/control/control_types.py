
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


class ReasonCode(StrEnum):
    """Reason codes for job status."""
    
    # Generic
    ERR_JOB_FAILED = "ERR_JOB_FAILED"
    
    # Artifact Guard Failures (Fail-Closed)
    ERR_FEATURE_ARTIFACTS_MISSING = "ERR_FEATURE_ARTIFACTS_MISSING"
    ERR_RESEARCH_ARTIFACTS_MISSING = "ERR_RESEARCH_ARTIFACTS_MISSING"
    ERR_PLATEAU_ARTIFACTS_MISSING = "ERR_PLATEAU_ARTIFACTS_MISSING"
