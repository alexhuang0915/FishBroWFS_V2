"""
UI Action Evidence Writer – writes read-only audit evidence for UI control actions.

Implements deterministic, safe writing of JSON evidence files for UI actions
(e.g., abort requests) under the existing job outputs tree.

Rules:
- Write to outputs/jobs/<job_id>/ui_actions/abort_request.json
- Create directories if missing (within outputs only)
- No overwrite: if file exists, append suffix abort_request_2.json, abort_request_3.json…
- Schema v1.0 with required fields
- If evidence write fails, raise typed exception to block UI action
"""

import json
import os
import pathlib
import time
from datetime import datetime, timezone
from typing import Optional
from dataclasses import dataclass, asdict


@dataclass
class AbortRequestEvidence:
    """Schema v1.0 for abort request evidence."""
    schema_version: str = "1.0"
    action: str = "abort_request"
    job_id: str = ""
    requested_at_utc: str = ""
    requested_by: str = "desktop_ui"
    reason: Optional[str] = None
    ui_build: Optional[str] = None
    gate_enabled: bool = True
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        d = asdict(self)
        # Remove None values for cleaner JSON
        d = {k: v for k, v in d.items() if v is not None}
        return d


class UIEvidenceError(Exception):
    """Base exception for UI evidence writing failures."""
    pass


class EvidenceWriteError(UIEvidenceError):
    """Raised when evidence cannot be written (disk full, permissions, etc.)."""
    pass


def _get_iso8601_utc() -> str:
    """Return current UTC time in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


def _find_available_filename(base_path: pathlib.Path) -> pathlib.Path:
    """
    Find available filename with suffix strategy to avoid overwrites.
    
    Args:
        base_path: Base path without suffix (e.g., /path/to/abort_request.json)
    
    Returns:
        Path with suffix if needed (e.g., /path/to/abort_request_2.json)
    """
    if not base_path.exists():
        return base_path
    
    # Try suffixes _2, _3, ... up to _100
    for i in range(2, 101):
        suffixed = base_path.with_name(f"{base_path.stem}_{i}{base_path.suffix}")
        if not suffixed.exists():
            return suffixed
    
    # If all suffixes taken, fall back to timestamp
    timestamp = int(time.time())
    return base_path.with_name(f"{base_path.stem}_{timestamp}{base_path.suffix}")


def write_abort_request_evidence(job_id: str, reason: Optional[str] = None) -> pathlib.Path:
    """
    Write abort request evidence JSON file.
    
    Args:
        job_id: Job identifier (string)
        reason: Optional human-readable reason for abort
    
    Returns:
        Path to the written evidence file
    
    Raises:
        EvidenceWriteError: If evidence cannot be written (disk full, permissions, etc.)
        ValueError: If job_id is empty or invalid
    """
    if not job_id or not isinstance(job_id, str):
        raise ValueError(f"Invalid job_id: {job_id!r}")
    
    # Build evidence object
    evidence = AbortRequestEvidence(
        job_id=job_id,
        requested_at_utc=_get_iso8601_utc(),
        reason=reason,
        gate_enabled=True,  # This function is only called when gate is enabled
    )
    
    # Determine output path
    # Use outputs/jobs/<job_id>/ui_actions/abort_request.json
    outputs_root = pathlib.Path("outputs")
    try:
        if not outputs_root.exists():
            # In test environments, outputs might not exist; create it
            outputs_root.mkdir(parents=True, exist_ok=True)
    except (OSError, PermissionError) as e:
        raise EvidenceWriteError(f"Cannot create outputs directory {outputs_root}: {e}")
    
    job_dir = outputs_root / "jobs" / job_id
    ui_actions_dir = job_dir / "ui_actions"
    
    try:
        # Create directories if missing
        ui_actions_dir.mkdir(parents=True, exist_ok=True)
    except (OSError, PermissionError) as e:
        raise EvidenceWriteError(f"Cannot create directory {ui_actions_dir}: {e}")
    
    # Determine filename with suffix strategy
    base_file = ui_actions_dir / "abort_request.json"
    target_file = _find_available_filename(base_file)
    
    # Write JSON
    try:
        with open(target_file, "w", encoding="utf-8") as f:
            json.dump(evidence.to_dict(), f, indent=2, ensure_ascii=False)
    except (OSError, IOError, TypeError, ValueError) as e:
        raise EvidenceWriteError(f"Cannot write evidence to {target_file}: {e}")
    
    return target_file


def verify_evidence_write_possible() -> bool:
    """
    Quick check if evidence writing is likely to succeed.
    
    This can be used by UI to pre-check before offering abort action.
    Checks if outputs directory exists and is writable.
    
    Returns:
        bool: True if evidence writing appears possible
    """
    outputs_root = pathlib.Path("outputs")
    
    # Check if outputs exists or can be created
    if outputs_root.exists():
        # Check if writable
        try:
            test_file = outputs_root / ".write_test"
            test_file.touch()
            test_file.unlink()
            return True
        except (OSError, PermissionError):
            return False
    else:
        # Try to create it
        try:
            outputs_root.mkdir(parents=True, exist_ok=True)
            return True
        except (OSError, PermissionError):
            return False