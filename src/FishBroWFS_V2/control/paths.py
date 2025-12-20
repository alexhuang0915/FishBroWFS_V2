"""Path helpers for B5-C Mission Control."""

from __future__ import annotations

from pathlib import Path


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

