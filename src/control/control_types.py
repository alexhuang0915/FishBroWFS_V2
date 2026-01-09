
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





