
"""Path helpers for B5-C Mission Control."""

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


def run_log_path(outputs_root: Path, season: str, run_id: str) -> Path:
    """
    Return outputs log path for a run (mkdir parents).
    
    Args:
        outputs_root: Root outputs directory
        season: Season identifier
        run_id: Run ID
        
    Returns:
        Path to log file: outputs/{season}/{run_id}/logs/worker.log
    """
    log_path = outputs_root / season / run_id / "logs" / "worker.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    return log_path



