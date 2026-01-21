
"""Path management for artifact output.

Centralized contract for output directory structure.
Follows the Logic-Only Constitution:
- outputs/runtime/   : Ephemeral system state
- outputs/artifacts/ : Immutable results
- outputs/exports/   : User-facing deliverables
- outputs/legacy/    : Deprecated/Historical
"""

from __future__ import annotations

import os
from pathlib import Path


def get_outputs_root() -> Path:
    """
    Single source of truth for outputs root.
    - Default: ./outputs (repo relative)
    - Override: env FISHBRO_OUTPUTS_ROOT
    """
    p = os.environ.get("FISHBRO_OUTPUTS_ROOT", "outputs")
    return Path(p).resolve()


def get_runtime_root() -> Path:
    """Ephemeral system state (DB, locks, status)."""
    return get_outputs_root() / "runtime"


def get_artifacts_root() -> Path:
    """Immutable results (runs, logs)."""
    return get_outputs_root() / "artifacts"


def get_exports_root() -> Path:
    """User-facing deliverables."""
    return get_outputs_root() / "exports"


def get_legacy_root() -> Path:
    """Deprecated or historical paths."""
    return get_outputs_root() / "legacy"


def get_db_path() -> Path:
    """Get path to the main jobs database."""
    return get_runtime_root() / "jobs_v2.db"


def get_jobs_dir() -> Path:
    """Get path to the jobs artifact directory."""
    return get_artifacts_root() / "jobs"


def get_run_dir(outputs_root: Path, season: str, run_id: str) -> Path:
    """
    Get path for a specific run.
    
    Fixed path structure: outputs/artifacts/seasons/{season}/runs/{run_id}/
    
    Args:
        outputs_root: Root outputs directory (ignored in favor of strict artifact root, 
                     kept for signature compatibility if needed, but we should prefer internal logic)
        season: Season identifier
        run_id: Run ID
        
    Returns:
        Path to run directory
    """
    # Note: We ignore outputs_root argument to enforce the artifact root
    # but strictly speaking if the caller passed a custom root, they might expect it there.
    # However, the invariants say "No Hidden Hard-Coding".
    # To be safe and compliant, we rely on the global get_artifacts_root().
    return get_artifacts_root() / "seasons" / season / "runs" / run_id


def ensure_run_dir(outputs_root: Path, season: str, run_id: str) -> Path:
    """
    Ensure run directory exists and return its path.
    """
    run_dir = get_run_dir(outputs_root, season, run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


