"""Run index service - list runs and status."""
import json
import logging
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


def list_runs(outputs_root: Path = Path("outputs"), season: str = "2026Q1", limit: int = None) -> List[Dict[str, Any]]:
    """List runs for a given season.

    Args:
        outputs_root: Root outputs directory.
        season: Season identifier.
        limit: Maximum number of runs to return (None for all).

    Returns:
        List of run metadata dicts.
    """
    runs_dir = outputs_root / "seasons" / season / "runs"
    if not runs_dir.exists():
        return []

    runs = []
    for run_dir in runs_dir.iterdir():
        if not run_dir.is_dir():
            continue
        run_id = run_dir.name
        intent_path = run_dir / "intent.json"
        derived_path = run_dir / "derived.json"
        manifest_path = run_dir / "manifest.json"

        # Determine status based on artifacts
        if manifest_path.exists():
            status = "COMPLETED"
        elif derived_path.exists():
            status = "RUNNING"
        else:
            status = "UNKNOWN"

        # Get start time from directory mtime
        started = run_dir.stat().st_mtime
        started_fmt = datetime.fromtimestamp(started).strftime("%Y-%m-%d %H:%M") if started else "N/A"

        runs.append({
            "run_id": run_id,
            "season": season,
            "intent_exists": intent_path.exists(),
            "derived_exists": derived_path.exists(),
            "manifest_exists": manifest_path.exists(),
            "status": status,
            "started": started_fmt,
            "duration": "N/A",  # could compute from logs
            "has_artifacts": manifest_path.exists(),
            "path": str(run_dir),
        })

    # Sort by started timestamp descending (most recent first)
    runs.sort(key=lambda r: r.get("started", ""), reverse=True)
    if limit is not None:
        runs = runs[:limit]
    return runs


def get_run_status(run_id: str, season: str = "2026Q1") -> Dict[str, Any]:
    """Get detailed status of a run."""
    # Placeholder
    return {
        "run_id": run_id,
        "season": season,
        "status": "unknown",
        "progress": 0,
        "artifacts": [],
    }


def get_run_details(run_id: str, season: str = "2026Q1") -> Dict[str, Any]:
    """Get detailed metadata for a specific run."""
    runs_dir = Path("outputs") / "seasons" / season / "runs"
    run_dir = runs_dir / run_id
    if not run_dir.exists():
        return {}

    intent_path = run_dir / "intent.json"
    derived_path = run_dir / "derived.json"
    manifest_path = run_dir / "manifest.json"
    log_path = run_dir / "logs.txt"

    # Read intent if exists
    intent = {}
    if intent_path.exists():
        try:
            with open(intent_path, "r") as f:
                intent = json.load(f)
        except Exception:
            pass

    # Determine status
    if manifest_path.exists():
        status = "COMPLETED"
    elif derived_path.exists():
        status = "RUNNING"
    else:
        status = "UNKNOWN"

    # Get directory mtime as started
    started = run_dir.stat().st_mtime
    started_fmt = datetime.fromtimestamp(started).strftime("%Y-%m-%d %H:%M") if started else "N/A"

    return {
        "run_id": run_id,
        "season": season,
        "status": status,
        "started": started_fmt,
        "duration": "N/A",
        "intent": intent,
        "has_intent": intent_path.exists(),
        "has_derived": derived_path.exists(),
        "has_manifest": manifest_path.exists(),
        "has_logs": log_path.exists(),
        "path": str(run_dir),
    }