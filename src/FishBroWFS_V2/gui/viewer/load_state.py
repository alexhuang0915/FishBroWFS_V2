
"""Viewer load state model and contract.

Defines unified artifact load status for Viewer pages.
Never raises exceptions - pure mapping logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

from FishBroWFS_V2.core.artifact_reader import SafeReadResult
from FishBroWFS_V2.core.artifact_status import ValidationResult, ArtifactStatus


class ArtifactLoadStatus(str, Enum):
    """Artifact load status - fixed string values for UI consistency."""
    OK = "OK"
    MISSING = "MISSING"
    INVALID = "INVALID"
    DIRTY = "DIRTY"


@dataclass(frozen=True)
class ArtifactLoadState:
    """
    Artifact load state for Viewer.
    
    Represents the load status of a single artifact (manifest/winners_v2/governance).
    """
    status: ArtifactLoadStatus
    artifact_name: str  # "manifest" / "winners_v2" / "governance"
    path: Path
    error: Optional[str] = None  # Error message when INVALID
    dirty_reasons: list[str] = None  # List of reasons when DIRTY (can be empty)
    last_modified_ts: Optional[float] = None  # Optional timestamp for UI display
    
    def __post_init__(self) -> None:
        """Ensure dirty_reasons is always a list."""
        if self.dirty_reasons is None:
            object.__setattr__(self, "dirty_reasons", [])


def compute_load_state(
    artifact_name: str,
    path: Path,
    read_result: SafeReadResult,
    validation_result: Optional[ValidationResult] = None,
) -> ArtifactLoadState:
    """
    Compute ArtifactLoadState from read and validation results.
    
    Zero-trust function - never assumes any attribute exists.
    This function performs pure mapping - no IO, no inference, no exceptions.
    
    Args:
        artifact_name: Name of artifact ("manifest", "winners_v2", "governance")
        path: Path to artifact file
        read_result: Result from try_read_artifact()
        validation_result: Optional validation result from validate_*_status()
        
    Returns:
        ArtifactLoadState with mapped status and error information
        
    Contract:
        - Never raises exceptions
        - Only performs mapping logic
        - Status strings are fixed (OK/MISSING/INVALID/DIRTY)
        - Zero-trust: uses getattr for all attribute access
    """
    try:
        # ❶ Zero-trust: check is_error property safely
        is_error = getattr(read_result, "is_error", False)
        
        if is_error:
            # Read error - map to MISSING or INVALID
            error = getattr(read_result, "error", None)
            if error is not None:
                error_code = getattr(error, "error_code", "")
                error_message = getattr(error, "message", "Unknown error")
                
                # FILE_NOT_FOUND -> MISSING
                if error_code == "FILE_NOT_FOUND":
                    return ArtifactLoadState(
                        status=ArtifactLoadStatus.MISSING,
                        artifact_name=artifact_name,
                        path=path,
                        error=None,
                        dirty_reasons=[],
                        last_modified_ts=None,
                    )
                
                # Other errors -> INVALID
                return ArtifactLoadState(
                    status=ArtifactLoadStatus.INVALID,
                    artifact_name=artifact_name,
                    path=path,
                    error=str(error_message),
                    dirty_reasons=[],
                    last_modified_ts=None,
                )
            else:
                # Error object missing -> INVALID
                return ArtifactLoadState(
                    status=ArtifactLoadStatus.INVALID,
                    artifact_name=artifact_name,
                    path=path,
                    error="Read error but error object missing",
                    dirty_reasons=[],
                    last_modified_ts=None,
                )
        
        # File read successfully - check validation result
        read_result_obj = getattr(read_result, "result", None)
        if read_result_obj is None:
            # No result but no error -> INVALID
            return ArtifactLoadState(
                status=ArtifactLoadStatus.INVALID,
                artifact_name=artifact_name,
                path=path,
                error="Read result missing",
                dirty_reasons=[],
                last_modified_ts=None,
            )
        
        # Extract metadata safely
        meta = getattr(read_result_obj, "meta", None)
        last_modified_ts = None
        if meta is not None:
            last_modified_ts = getattr(meta, "mtime_s", None)
        
        # If validation_result is provided, use it
        if validation_result is not None:
            # Zero-trust: get status safely
            validation_status = getattr(validation_result, "status", None)
            
            # Map ValidationResult.status to ArtifactLoadStatus
            if validation_status == ArtifactStatus.OK:
                load_status = ArtifactLoadStatus.OK
            elif validation_status == ArtifactStatus.MISSING:
                load_status = ArtifactLoadStatus.MISSING
            elif validation_status == ArtifactStatus.INVALID:
                load_status = ArtifactLoadStatus.INVALID
            elif validation_status == ArtifactStatus.DIRTY:
                load_status = ArtifactLoadStatus.DIRTY
            else:
                # Fallback to INVALID for unknown status
                load_status = ArtifactLoadStatus.INVALID
            
            # Extract error and dirty_reasons from validation_result safely
            error_msg = None
            dirty_reasons_list: list[str] = []
            
            if load_status == ArtifactLoadStatus.INVALID:
                error_msg = getattr(validation_result, "message", "Unknown validation error")
                error_details = getattr(validation_result, "error_details", None)
                if error_details:
                    # Prefer error_details if available
                    error_msg = str(error_details)
            elif load_status == ArtifactLoadStatus.DIRTY:
                # Extract dirty reason from message
                message = getattr(validation_result, "message", "")
                dirty_reasons_list = [message] if message else []
            
            return ArtifactLoadState(
                status=load_status,
                artifact_name=artifact_name,
                path=path,
                error=error_msg,
                dirty_reasons=dirty_reasons_list,
                last_modified_ts=last_modified_ts,
            )
        
        # No validation result - assume OK if file read successfully
        return ArtifactLoadState(
            status=ArtifactLoadStatus.OK,
            artifact_name=artifact_name,
            path=path,
            error=None,
            dirty_reasons=[],
            last_modified_ts=last_modified_ts,
        )
    
    except Exception as e:
        # ❸ Final safety net: compute_load_state never raises
        return ArtifactLoadState(
            status=ArtifactLoadStatus.INVALID,
            artifact_name=artifact_name,
            path=path,
            error=f"compute_load_state exception: {e}",
            dirty_reasons=[],
            last_modified_ts=None,
        )


