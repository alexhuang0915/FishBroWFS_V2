"""
Robust Run Index Resolver - Canonical run indexing for UI discovery.

Provides deterministic run discovery and matching for Desktop and NiceGUI.
Tolerates mixed legacy folders (run_*, artifact_*) and selects best matches.
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RunSummary:
    """Canonical run summary for UI consumption."""
    season: str
    run_id: str
    run_dir: str
    created_at: str
    status: str
    dataset_id: Optional[str]
    strategy_id: Optional[str]
    timeframe: Optional[str]
    metrics_path: Optional[str]
    manifest_path: Optional[str]


def _read_json(p: Path) -> Optional[Dict[str, Any]]:
    """Robust JSON read helper."""
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _iter_run_dirs(runs_root: Path):
    """Iterate over run directories, tolerating legacy folders."""
    if not runs_root.exists():
        return []
    for d in runs_root.iterdir():
        if d.is_dir() and (d.name.startswith("run_") or d.name.startswith("artifact_")):
            yield d


def _matches(manifest: dict, strategy_id: str, dataset_id: str, timeframe: str) -> bool:
    """Check if manifest matches intent."""
    # Extract timeframe from manifest (could be int or string)
    manifest_tf = manifest.get("timeframe")
    if manifest_tf is not None:
        # Convert to string for comparison
        if isinstance(manifest_tf, int):
            manifest_tf = f"{manifest_tf}m"
        elif isinstance(manifest_tf, float):
            manifest_tf = f"{int(manifest_tf)}m"
    
    return (
        manifest.get("strategy_id") == strategy_id
        and manifest.get("dataset_id") == dataset_id
        and manifest_tf == timeframe
    )


def _extract_run_metadata(run_dir: Path) -> Optional[Dict[str, Any]]:
    """Extract metadata from a run directory."""
    run_id = run_dir.name
    
    # Try to read run_record.json first
    run_record_path = run_dir / "run_record.json"
    run_record = None
    if run_record_path.exists():
        run_record = _read_json(run_record_path)
    
    # Try to read manifest.json
    manifest_path = run_dir / "manifest.json"
    manifest = None
    if manifest_path.exists():
        manifest = _read_json(manifest_path)
    
    # Try to read metrics.json
    metrics_path = run_dir / "metrics.json"
    metrics = None
    if metrics_path.exists():
        metrics = _read_json(metrics_path)
    
    # Determine status
    status = "UNKNOWN"
    if run_record and "status" in run_record:
        status = run_record["status"]
    elif manifest_path.exists():
        status = "COMPLETED"
    elif (run_dir / "derived.json").exists():
        status = "RUNNING"
    
    # Extract created_at
    created_at = ""
    if run_record and "created_at" in run_record:
        created_at = run_record["created_at"]
    elif manifest and "created_at" in manifest:
        created_at = manifest["created_at"]
    elif metrics and "created_at" in metrics:
        created_at = metrics["created_at"]
    else:
        # Fallback to directory mtime
        try:
            mtime = run_dir.stat().st_mtime
            created_at = datetime.fromtimestamp(mtime, timezone.utc).isoformat().replace("+00:00", "Z")
        except Exception:
            created_at = ""
    
    # Extract intent fields from manifest or run_record
    dataset_id = None
    strategy_id = None
    timeframe = None
    
    if manifest:
        dataset_id = manifest.get("dataset_id")
        strategy_id = manifest.get("strategy_id")
        timeframe = manifest.get("timeframe")
    
    if not dataset_id and run_record:
        # Try to extract from run_record intent
        intent = run_record.get("intent", {})
        if isinstance(intent, dict):
            dataset_id = intent.get("dataset_id") or intent.get("instrument")
            strategy_id = intent.get("strategy_id") or (intent.get("strategy_ids") or [None])[0]
            timeframe = intent.get("timeframe")
    
    return {
        "run_id": run_id,
        "run_dir": str(run_dir),
        "created_at": created_at,
        "status": status,
        "dataset_id": dataset_id,
        "strategy_id": strategy_id,
        "timeframe": timeframe,
        "manifest_path": str(manifest_path) if manifest_path.exists() else None,
        "metrics_path": str(metrics_path) if metrics_path.exists() else None,
        "run_record": run_record,
        "manifest": manifest,
        "metrics": metrics,
    }


def list_runs(outputs_root: Path, season: str) -> List[RunSummary]:
    """Return runs newest-first. Must tolerate mixed legacy folders."""
    runs_dir = outputs_root / "seasons" / season / "runs"
    
    runs = []
    for run_dir in _iter_run_dirs(runs_dir):
        metadata = _extract_run_metadata(run_dir)
        if not metadata:
            continue
        
        # Convert to RunSummary
        summary = RunSummary(
            season=season,
            run_id=metadata["run_id"],
            run_dir=metadata["run_dir"],
            created_at=metadata["created_at"],
            status=metadata["status"],
            dataset_id=metadata["dataset_id"],
            strategy_id=metadata["strategy_id"],
            timeframe=str(metadata["timeframe"]) if metadata["timeframe"] else None,
            metrics_path=metadata["metrics_path"],
            manifest_path=metadata["manifest_path"],
        )
        runs.append(summary)
    
    # Sort by created_at descending (newest first)
    runs.sort(key=lambda r: r.created_at or "", reverse=True)
    return runs


def find_best_run(
    outputs_root: Path,
    season: str,
    strategy_id: str,
    dataset_id: str,
    timeframe: str,
    *,
    created_after_iso: Optional[str] = None,
) -> Optional[RunSummary]:
    """Return the best matching completed run for the given intent."""
    all_runs = list_runs(outputs_root, season)
    
    # Filter by created_after if specified
    if created_after_iso:
        filtered_runs = []
        for run in all_runs:
            if run.created_at and run.created_at > created_after_iso:
                filtered_runs.append(run)
        all_runs = filtered_runs
    
    # Prefer COMPLETED runs
    completed_runs = [r for r in all_runs if r.status == "COMPLETED"]
    running_runs = [r for r in all_runs if r.status == "RUNNING"]
    
    # Try to find matching completed runs first
    for run in completed_runs:
        # Need manifest to match
        if not run.manifest_path:
            continue
            
        manifest = _read_json(Path(run.manifest_path))
        if not manifest:
            continue
            
        if _matches(manifest, strategy_id, dataset_id, timeframe):
            return run
    
    # If no completed match, check running runs (for live view)
    for run in running_runs:
        if not run.manifest_path:
            continue
            
        manifest = _read_json(Path(run.manifest_path))
        if not manifest:
            continue
            
        if _matches(manifest, strategy_id, dataset_id, timeframe):
            return run
    
    # No match found
    return None


def find_run_by_id(outputs_root: Path, season: str, run_id: str) -> Optional[RunSummary]:
    """Find a specific run by ID."""
    runs_dir = outputs_root / "seasons" / season / "runs"
    run_dir = runs_dir / run_id
    
    if not run_dir.exists() or not run_dir.is_dir():
        return None
    
    metadata = _extract_run_metadata(run_dir)
    if not metadata:
        return None
    
    return RunSummary(
        season=season,
        run_id=metadata["run_id"],
        run_dir=metadata["run_dir"],
        created_at=metadata["created_at"],
        status=metadata["status"],
        dataset_id=metadata["dataset_id"],
        strategy_id=metadata["strategy_id"],
        timeframe=str(metadata["timeframe"]) if metadata["timeframe"] else None,
        metrics_path=metadata["metrics_path"],
        manifest_path=metadata["manifest_path"],
    )


def get_run_diagnostics(
    outputs_root: Path,
    season: str,
    strategy_id: str,
    dataset_id: str,
    timeframe: str,
) -> Dict[str, Any]:
    """Return diagnostic information for debugging run discovery."""
    all_runs = list_runs(outputs_root, season)
    
    # Count by status
    status_counts = {}
    for run in all_runs:
        status_counts[run.status] = status_counts.get(run.status, 0) + 1
    
    # Find matching runs
    matching = []
    for run in all_runs:
        if not run.manifest_path:
            continue
            
        manifest = _read_json(Path(run.manifest_path))
        if not manifest:
            continue
            
        if _matches(manifest, strategy_id, dataset_id, timeframe):
            matching.append(run)
    
    # Get newest 3 runs for context
    newest_runs = all_runs[:3] if len(all_runs) > 3 else all_runs
    
    return {
        "total_runs": len(all_runs),
        "status_counts": status_counts,
        "matching_runs": len(matching),
        "newest_runs": [
            {
                "run_id": r.run_id,
                "status": r.status,
                "dataset_id": r.dataset_id,
                "strategy_id": r.strategy_id,
                "timeframe": r.timeframe,
                "created_at": r.created_at,
            }
            for r in newest_runs
        ],
        "search_params": {
            "season": season,
            "strategy_id": strategy_id,
            "dataset_id": dataset_id,
            "timeframe": timeframe,
        },
    }