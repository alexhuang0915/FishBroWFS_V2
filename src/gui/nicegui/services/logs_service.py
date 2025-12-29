"""Logs service - tail logs from runs."""
import logging
from pathlib import Path
from typing import List, Tuple

logger = logging.getLogger(__name__)


def tail_log(
    run_id: str,
    season: str = "2026Q1",
    n_lines: int = 100,
    outputs_root: Path = Path("outputs"),
) -> Tuple[List[str], bool]:
    """Tail last n lines of run log.
    
    Args:
        run_id: Run identifier.
        season: Season identifier.
        n_lines: Number of lines to return.
        outputs_root: Root outputs directory.
    
    Returns:
        (lines, truncated) where truncated indicates file had more lines.
    """
    log_path = outputs_root / "seasons" / season / "runs" / run_id / "logs.txt"
    if not log_path.exists():
        return [], False
    
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        truncated = len(lines) > n_lines
        return lines[-n_lines:], truncated
    except Exception as e:
        logger.error(f"Failed to tail log {log_path}: {e}")
        return [], False


def stream_log_updates(run_id: str, season: str = "2026Q1", last_position: int = 0):
    """Generator yielding new log lines (placeholder).
    
    Args:
        run_id: Run identifier.
        season: Season identifier.
        last_position: Last read byte position.
    
    Yields:
        (new_lines, new_position)
    """
    # Not implemented; could be used for real‑time log streaming.
    pass


def get_recent_logs(lines: int = 20) -> List[str]:
    """Return recent lines from system log."""
    system_log_path = Path("outputs/system.log")
    if not system_log_path.exists():
        return []
    try:
        with open(system_log_path, "r", encoding="utf-8", errors="replace") as f:
            all_lines = f.readlines()
        return [line.rstrip() for line in all_lines[-lines:]]
    except Exception as e:
        logger.error(f"Failed to read system log: {e}")
        return []