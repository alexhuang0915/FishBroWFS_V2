"""Truth Providers - Single Source-of-Truth for UI data.

This module provides unified, truthful data sources that guarantee:
1. No fake/cached state leaks
2. Consistent data format across all UI components
3. Evidence-backed data (actions that claim to create artifacts must create them)
4. Deterministic output for forensics

All UI components MUST use these providers instead of direct service calls.
"""

import logging
from typing import Dict, Any, List, Optional, NamedTuple
from pathlib import Path
import time

from ..services.status_service import (
    get_status as _get_status,
    get_system_status as _get_system_status,
    get_forensics_snapshot as _get_forensics_snapshot,
    StatusSnapshot,
)
from ..services.run_index_service import list_runs as _list_runs
# Note: We use list_runs directly instead of list_local_runs to avoid parameter mismatch

logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Backend Status Truth Provider
# -----------------------------------------------------------------------------

class BackendStatus(NamedTuple):
    """Immutable, truthful backend status snapshot."""
    backend_up: bool
    backend_error: Optional[str]
    backend_last_ok_ts: Optional[float]
    worker_up: bool
    worker_error: Optional[str]
    worker_last_ok_ts: Optional[float]
    last_check_ts: float
    overall_state: str  # "ONLINE", "DEGRADED", "OFFLINE"
    human_summary: str


def get_backend_status() -> BackendStatus:
    """
    Single source-of-truth for backend status.
    
    Returns:
        Immutable BackendStatus tuple with all status information.
        
    Guarantees:
        - Always returns fresh data (no stale caches beyond service's own polling)
        - Consistent format across all UI components
        - No side effects
    """
    snap: StatusSnapshot = _get_status()
    
    # Compute overall state
    if not snap.backend_up:
        overall_state = "OFFLINE"
    elif not snap.worker_up:
        overall_state = "DEGRADED"
    else:
        overall_state = "ONLINE"
    
    # Generate human-readable summary
    if overall_state == "ONLINE":
        human_summary = "System fully operational"
    elif overall_state == "DEGRADED":
        human_summary = f"Backend up, worker down: {snap.worker_error or 'unknown error'}"
    else:  # OFFLINE
        human_summary = f"Backend unreachable: {snap.backend_error or 'connection failed'}"
    
    return BackendStatus(
        backend_up=snap.backend_up,
        backend_error=snap.backend_error,
        backend_last_ok_ts=snap.backend_last_ok_ts,
        worker_up=snap.worker_up,
        worker_error=snap.worker_error,
        worker_last_ok_ts=snap.worker_last_ok_ts,
        last_check_ts=snap.last_check_ts,
        overall_state=overall_state,
        human_summary=human_summary,
    )


def get_backend_status_dict() -> Dict[str, Any]:
    """
    Legacy-compatible dict version of backend status.
    
    Returns:
        Dict with same structure as old get_system_status().
        
    Note: New code should prefer get_backend_status() for type safety.
    """
    status = get_backend_status()
    return {
        "backend": {
            "online": status.backend_up,
            "error": status.backend_error,
        },
        "worker": {
            "alive": status.worker_up,
            "error": status.worker_error,
        },
        "overall": status.backend_up and status.worker_up,
        "state": status.overall_state,
        "summary": status.human_summary,
        "last_checked": status.last_check_ts,
    }


# -----------------------------------------------------------------------------
# Local Runs Truth Provider
# -----------------------------------------------------------------------------

def list_local_runs(limit: int = 20, season: str = "2026Q1") -> List[Dict[str, Any]]:
    """
    Single source-of-truth for local runs listing.
    
    Args:
        limit: Maximum number of runs to return (default 20).
        season: Season identifier (default "2026Q1").
        
    Returns:
        List of run metadata dicts, sorted by most recent first.
        
    Guarantees:
        - Always reads from actual filesystem (no fake data)
        - Consistent sorting (most recent first)
        - Deterministic output format
        - Respects limit parameter
    """
    # Use the run_index_service directly which supports limit parameter
    runs = _list_runs(season=season, limit=limit)
    
    # Ensure consistent format and truthfulness
    truthful_runs = []
    for run in runs:
        # Validate required fields exist
        if not isinstance(run, dict):
            logger.warning(f"Skipping invalid run entry: {run}")
            continue
            
        # Ensure all runs have at least these fields
        truthful_run = {
            "run_id": run.get("run_id", "unknown"),
            "season": run.get("season", season),
            "status": run.get("status", "UNKNOWN"),
            "started": run.get("started", "N/A"),
            "duration": run.get("duration", "N/A"),
            "has_intent": run.get("intent_exists", False),
            "has_derived": run.get("derived_exists", False),
            "has_manifest": run.get("manifest_exists", False),
            "has_artifacts": run.get("has_artifacts", False),
            "path": run.get("path", ""),
        }
        truthful_runs.append(truthful_run)
    
    return truthful_runs


def get_run_count_by_status(season: str = "2026Q1") -> Dict[str, int]:
    """
    Get counts of runs by status.
    
    Args:
        season: Season identifier (default "2026Q1").
        
    Returns:
        Dict with counts for each status category.
    """
    runs = list_local_runs(limit=None, season=season)  # Get all runs for season
    counts = {
        "COMPLETED": 0,
        "RUNNING": 0,
        "PENDING": 0,
        "UNKNOWN": 0,
        "TOTAL": len(runs),
    }
    
    for run in runs:
        status = run.get("status", "UNKNOWN")
        if status in counts:
            counts[status] += 1
        else:
            counts["UNKNOWN"] += 1
    
    return counts


# -----------------------------------------------------------------------------
# System Health Truth Provider
# -----------------------------------------------------------------------------

def get_system_health() -> Dict[str, Any]:
    """
    Comprehensive system health snapshot.
    
    Returns:
        Dict with backend status, run counts, and overall health.
        
    Guarantees:
        - All data is truthful (reads actual state)
        - Consistent format for forensics
        - No side effects
    """
    backend = get_backend_status()
    run_counts = get_run_count_by_status()
    
    # Determine overall system health
    if backend.overall_state == "OFFLINE":
        system_health = "CRITICAL"
    elif backend.overall_state == "DEGRADED":
        system_health = "WARNING"
    elif run_counts.get("RUNNING", 0) > 5:
        system_health = "BUSY"
    else:
        system_health = "HEALTHY"
    
    return {
        "timestamp": time.time(),
        "backend": {
            "state": backend.overall_state,
            "summary": backend.human_summary,
            "backend_up": backend.backend_up,
            "worker_up": backend.worker_up,
            "last_check": backend.last_check_ts,
        },
        "runs": {
            "total": run_counts["TOTAL"],
            "completed": run_counts["COMPLETED"],
            "running": run_counts["RUNNING"],
            "pending": run_counts["PENDING"],
            "unknown": run_counts["UNKNOWN"],
        },
        "system_health": system_health,
        "forensics_safe": True,
    }


# -----------------------------------------------------------------------------
# Evidence Guarantee Helpers
# -----------------------------------------------------------------------------

def verify_evidence_created(filepath: Path) -> bool:
    """
    Verify that an evidence file was actually created.
    
    Args:
        filepath: Path to the evidence file.
        
    Returns:
        True if file exists and has non-zero size.
        
    Guarantees:
        - Returns truthful result (no fake success)
        - Logs verification result
    """
    if not filepath.exists():
        logger.warning(f"Evidence file not created: {filepath}")
        return False
    
    size = filepath.stat().st_size
    if size == 0:
        logger.warning(f"Evidence file is empty: {filepath}")
        return False
    
    logger.info(f"Evidence verified: {filepath} ({size} bytes)")
    return True


def create_evidence_with_guarantee(
    filepath: Path,
    content: str,
    description: str = "evidence",
) -> bool:
    """
    Create evidence file with guarantee that it will be created.
    
    Args:
        filepath: Path where evidence should be written.
        content: Content to write.
        description: Human-readable description for logging.
        
    Returns:
        True if evidence was successfully created and verified.
        
    Guarantees:
        - If function returns True, file exists and has content
        - If function returns False, failure is logged
        - No silent failures
    """
    try:
        # Ensure parent directory exists
        filepath.parent.mkdir(parents=True, exist_ok=True)
        
        # Write content
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        
        # Verify creation
        if verify_evidence_created(filepath):
            logger.info(f"{description} created successfully: {filepath}")
            return True
        else:
            logger.error(f"{description} creation failed verification: {filepath}")
            return False
            
    except Exception as e:
        logger.error(f"Failed to create {description} at {filepath}: {e}")
        return False