"""Run status heartbeat pattern for governance observability (Phase 14).

Implements deterministic observability without Socket.IO via HTTP pull.
Single Source of Truth = JSON on disk (outputs/run_status.json).
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, Literal

from control.artifacts import write_atomic_json

# File location (MANDATORY)
RUN_STATUS_PATH = Path("outputs/run_status.json")

# JSON Contract (STRICT)
RunState = Literal["IDLE", "RUNNING", "DONE", "FAILED", "CANCELED"]
RunStep = Literal["init", "load_data", "backtest_kernel", "scoring", "write_artifacts"]


def atomic_write_json(path: Path, payload: dict) -> None:
    """Atomic write JSON with fsync and os.replace.
    
    Rules:
    - Never write directly to run_status.json
    - Replace only via os.replace
    - Uses write_atomic_json from artifacts module which already implements this pattern
    """
    write_atomic_json(path, payload)


def get_default_status() -> Dict[str, Any]:
    """Return default IDLE status."""
    now = datetime.now(timezone.utc).isoformat()
    return {
        "schema_version": "1.0",
        "run_id": "",
        "state": "IDLE",
        "progress": 0,
        "step": "init",
        "message": "No active run",
        "started_at": now,
        "updated_at": now,
        "eta_seconds": 0,
        "artifacts": {
            "op_config": "outputs/op_config.json",
            "audit_log": "outputs/audit/events.jsonl"
        },
        "error": None
    }


def read_status() -> Dict[str, Any]:
    """Read run status from disk.
    
    Returns:
        - If file exists: parsed JSON
        - If missing: default IDLE status
    """
    if not RUN_STATUS_PATH.exists():
        return get_default_status()
    
    try:
        with open(RUN_STATUS_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Ensure required fields exist
        default = get_default_status()
        for key in default:
            if key not in data:
                data[key] = default[key]
        
        return data
    except (json.JSONDecodeError, OSError):
        # If file is corrupted or unreadable, return default
        return get_default_status()


def write_status(
    run_id: str = "",
    state: RunState = "IDLE",
    progress: int = 0,
    step: RunStep = "init",
    message: str = "",
    eta_seconds: int = 0,
    error: Optional[str] = None,
    artifacts: Optional[Dict[str, str]] = None,
) -> None:
    """Write run status to disk (atomic).
    
    Args:
        run_id: Unique run identifier
        state: Current state (IDLE, RUNNING, DONE, FAILED, CANCELED)
        progress: Progress percentage (0-100)
        step: Current step
        message: Human readable short message
        eta_seconds: Estimated seconds to completion
        error: Error message if state is FAILED
        artifacts: Dictionary of artifact paths (optional)
    """
    now = datetime.now(timezone.utc).isoformat()
    
    # Read existing status to preserve started_at if this is a continuation
    existing = read_status()
    
    # Determine started_at:
    # - If transitioning from IDLE to RUNNING, use current time
    # - If already RUNNING and continuing, keep existing started_at
    # - If any other transition, use current time
    if existing["state"] == "IDLE" and state == "RUNNING":
        started_at = now
    elif existing["state"] == "RUNNING" and state == "RUNNING":
        started_at = existing.get("started_at", now)
    else:
        started_at = now
    
    # Use provided artifacts or default
    if artifacts is None:
        artifacts = {
            "op_config": "outputs/op_config.json",
            "audit_log": "outputs/audit/events.jsonl"
        }
    
    payload = {
        "schema_version": "1.0",
        "run_id": run_id,
        "state": state,
        "progress": progress,
        "step": step,
        "message": message,
        "started_at": started_at,
        "updated_at": now,
        "eta_seconds": eta_seconds,
        "artifacts": artifacts,
        "error": error
    }
    
    # Validate progress range
    if state == "RUNNING" and not (0 <= progress <= 99):
        raise ValueError(f"RUNNING state requires progress 0-99, got {progress}")
    if state == "DONE" and progress != 100:
        raise ValueError(f"DONE state requires progress=100, got {progress}")
    
    atomic_write_json(RUN_STATUS_PATH, payload)


def update_status(
    state: Optional[RunState] = None,
    progress: Optional[int] = None,
    step: Optional[RunStep] = None,
    message: Optional[str] = None,
    eta_seconds: Optional[int] = None,
    error: Optional[str] = None,
) -> None:
    """Update specific fields of run status while preserving others.
    
    Reads current status, applies updates, writes back atomically.
    """
    current = read_status()
    
    if state is not None:
        current["state"] = state
    if progress is not None:
        current["progress"] = progress
    if step is not None:
        current["step"] = step
    if message is not None:
        current["message"] = message
    if eta_seconds is not None:
        current["eta_seconds"] = eta_seconds
    if error is not None:
        current["error"] = error
    
    # Always update timestamp
    current["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    atomic_write_json(RUN_STATUS_PATH, current)


def clear_status() -> None:
    """Clear run status (remove file)."""
    if RUN_STATUS_PATH.exists():
        RUN_STATUS_PATH.unlink()


def set_running(run_id: str, message: str = "Starting run") -> None:
    """Set status to RUNNING with initial progress."""
    write_status(
        run_id=run_id,
        state="RUNNING",
        progress=0,
        step="init",
        message=message,
        eta_seconds=0,
        error=None
    )


def set_done(message: str = "Run completed successfully") -> None:
    """Set status to DONE with progress=100."""
    current = read_status()
    write_status(
        run_id=current.get("run_id", ""),
        state="DONE",
        progress=100,
        step="write_artifacts",
        message=message,
        eta_seconds=0,
        error=None
    )


def set_failed(error: str) -> None:
    """Set status to FAILED with error message."""
    current = read_status()
    write_status(
        run_id=current.get("run_id", ""),
        state="FAILED",
        progress=current.get("progress", 0),
        step=current.get("step", "init"),
        message=f"Run failed: {error}",
        eta_seconds=0,
        error=error
    )


def set_canceled(message: str = "Run canceled by user") -> None:
    """Set status to CANCELED."""
    current = read_status()
    write_status(
        run_id=current.get("run_id", ""),
        state="CANCELED",
        progress=current.get("progress", 0),
        step=current.get("step", "init"),
        message=message,
        eta_seconds=0,
        error=None
    )