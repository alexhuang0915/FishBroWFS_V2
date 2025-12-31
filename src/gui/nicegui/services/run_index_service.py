"""Run index service - list runs and status."""
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


def list_runs(season: str, limit: int = 50, base_dir: str = "outputs") -> List[Dict[str, Any]]:
    """List runs for a given season.

    Reads outputs/seasons/<season>/runs/*/run_record.json and returns newest first.
    If run_record.json doesn't exist, falls back to scanning intent.json, derived.json, manifest.json.

    Args:
        season: Season identifier.
        limit: Maximum number of runs to return (default 50).
        base_dir: Root outputs directory (default "outputs").

    Returns:
        List of run metadata dicts.
    """
    runs_dir = Path(base_dir) / "seasons" / season / "runs"
    if not runs_dir.exists():
        return []

    runs = []
    for run_dir in runs_dir.iterdir():
        if not run_dir.is_dir():
            continue
        run_id = run_dir.name
        
        # Try to read run_record.json first
        run_record_path = run_dir / "run_record.json"
        if run_record_path.exists():
            try:
                with open(run_record_path, "r", encoding="utf-8") as f:
                    run_record = json.load(f)
                # Extract fields from run_record
                status = run_record.get("status", "UNKNOWN")
                created_at = run_record.get("created_at", "")
                # Convert ISO timestamp to display format if possible
                started_fmt = ""
                if created_at:
                    try:
                        dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                        started_fmt = dt.strftime("%Y-%m-%d %H:%M")
                    except ValueError:
                        started_fmt = created_at
                else:
                    # Fallback to directory mtime
                    started = run_dir.stat().st_mtime
                    started_fmt = datetime.fromtimestamp(started).strftime("%Y-%m-%d %H:%M") if started else "N/A"
                
                runs.append({
                    "run_id": run_id,
                    "season": season,
                    "status": status,
                    "started": started_fmt,
                    "created_at": created_at,
                    "intent_exists": (run_dir / "intent.json").exists(),
                    "derived_exists": (run_dir / "derived.json").exists(),
                    "manifest_exists": (run_dir / "manifest.json").exists(),
                    "run_record_exists": True,
                    "path": str(run_dir),
                    "experiment_yaml": _extract_experiment_yaml_from_record(run_record),
                })
                continue
            except Exception as e:
                logger.warning(f"Failed to read run_record.json for {run_dir}: {e}")
                # Fall through to legacy scanning
        
        # Legacy scanning (no run_record.json or failed to read)
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
            "run_record_exists": False,
            "status": status,
            "started": started_fmt,
            "duration": "N/A",  # could compute from logs
            "path": str(run_dir),
            "experiment_yaml": None,
        })

    # Sort by started timestamp descending (most recent first)
    # Use created_at from run_record if available, else started string
    def sort_key(r: Dict[str, Any]) -> str:
        if "created_at" in r and r["created_at"]:
            return r["created_at"]
        return r.get("started", "")
    
    runs.sort(key=sort_key, reverse=True)
    if limit is not None:
        runs = runs[:limit]
    return runs


def _extract_experiment_yaml_from_record(run_record: Dict[str, Any]) -> Optional[str]:
    """Extract experiment YAML path from run record if available."""
    # Check notes or intent fields
    notes = run_record.get("notes", "")
    if "experiment YAML" in notes:
        # Could parse, but for now return generic
        return "experiment.yaml"
    return None


# Backward compatibility wrapper
def list_runs_legacy(outputs_root: Path = Path("outputs"), season: str = "2026Q1", limit: int = None) -> List[Dict[str, Any]]:
    """Legacy interface for backward compatibility."""
    return list_runs(season=season, limit=limit or 50, base_dir=str(outputs_root))


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
    run_record_path = run_dir / "run_record.json"

    # Read run_record if exists
    run_record = {}
    if run_record_path.exists():
        try:
            with open(run_record_path, "r", encoding="utf-8") as f:
                run_record = json.load(f)
        except Exception:
            pass

    # Read intent if exists
    intent = {}
    if intent_path.exists():
        try:
            with open(intent_path, "r", encoding="utf-8") as f:
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

    # Use created_at from run_record if available
    created_at = run_record.get("created_at", "")
    if created_at:
        try:
            dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            started_fmt = dt.strftime("%Y-%m-%d %H:%M")
        except ValueError:
            pass

    return {
        "run_id": run_id,
        "season": season,
        "status": status,
        "started": started_fmt,
        "created_at": created_at,
        "duration": "N/A",
        "intent": intent,
        "run_record": run_record,
        "has_intent": intent_path.exists(),
        "has_derived": derived_path.exists(),
        "has_manifest": manifest_path.exists(),
        "has_run_record": run_record_path.exists(),
        "has_logs": log_path.exists(),
        "path": str(run_dir),
    }


# Export the main function with both names for compatibility
list_runs_compat = list_runs