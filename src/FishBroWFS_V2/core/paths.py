"""Path management for artifact output.

Centralized contract for output directory structure.
"""

from __future__ import annotations

from pathlib import Path


def get_run_dir(outputs_root: Path, season: str, run_id: str) -> Path:
    """
    Get path for a specific run.
    
    Fixed path structure: outputs/seasons/{season}/runs/{run_id}/
    
    Args:
        outputs_root: Root outputs directory (e.g., Path("outputs"))
        season: Season identifier
        run_id: Run ID
        
    Returns:
        Path to run directory
    """
    return outputs_root / "seasons" / season / "runs" / run_id


def ensure_run_dir(outputs_root: Path, season: str, run_id: str) -> Path:
    """
    Ensure run directory exists and return its path.
    
    Args:
        outputs_root: Root outputs directory
        season: Season identifier
        run_id: Run ID
        
    Returns:
        Path to run directory (created if needed)
    """
    run_dir = get_run_dir(outputs_root, season, run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir
