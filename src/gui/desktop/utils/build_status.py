from __future__ import annotations

from datetime import datetime
from typing import Iterable, Any, Optional

TERMINAL_SUCCESS = {"SUCCEEDED", "COMPLETED"}
TERMINAL_FAILURE = {"FAILED", "ABORTED", "REJECTED"}
RUNNING_STATES = {"RUNNING", "QUEUED"}


def derive_overall_status(statuses: Iterable[str]) -> str:
    """Derive a user-facing overall status from job statuses."""
    status_list = [s for s in statuses if s]
    if any(s in TERMINAL_FAILURE for s in status_list):
        return "FAILED"
    if any(s in RUNNING_STATES for s in status_list):
        return "RUNNING"
    if status_list and all(s in TERMINAL_SUCCESS for s in status_list):
        return "DONE"
    return "UNKNOWN"


def extract_status_message(job: dict[str, Any]) -> str:
    """Pick a reasonable status message from a job payload."""
    for key in ("status_message", "message", "phase", "policy_stage"):
        value = job.get(key)
        if value:
            return str(value)
    return ""


def compute_stall_warning(
    last_change_at: Optional[datetime],
    now: datetime,
    threshold_seconds: int = 20,
) -> str:
    """Return stall warning text if no update within threshold."""
    if last_change_at is None:
        return ""
    seconds_since_change = int((now - last_change_at).total_seconds())
    if seconds_since_change >= threshold_seconds:
        return f"STALL WARNING • no update for {seconds_since_change}s"
    return ""
