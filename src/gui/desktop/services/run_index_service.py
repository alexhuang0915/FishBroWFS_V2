"""
Run Index Service for Desktop UI - provides run discovery and selection.

Implements the contract:
- Scan outputs/seasons/<season>/runs/ for directories matching ^(run|artifact)_[0-9a-f]{6,64}$
- Sort by finished_at from meta.json (if exists) or directory mtime descending
- Provide API for listing runs and picking the last run
"""

import re
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)

# Regex for valid run directory names
_DIR_RE = re.compile(r"^(run|artifact)_[0-9a-f]{6,64}$")


@dataclass(frozen=True)
class RunRef:
    """Reference to a run directory."""
    name: str           # "run_ac8a71aa"
    path: Path
    mtime: float
    finished_at: Optional[float]  # epoch seconds if available in meta.json


def is_artifact_dir_name(name: str) -> bool:
    """Valid if (run|artifact)_[0-9a-f]{6,64}."""
    return bool(_DIR_RE.match(name))


def list_runs(season: str, outputs_root: Path) -> List[RunRef]:
    """Return runs sorted newest-first from outputs/seasons/<season>/runs/."""
    runs_dir = outputs_root / "seasons" / season / "runs"
    if not runs_dir.exists():
        return []
    
    runs = []
    for run_dir in runs_dir.iterdir():
        if not run_dir.is_dir():
            continue
        
        if not is_artifact_dir_name(run_dir.name):
            continue
        
        # Get mtime
        try:
            mtime = run_dir.stat().st_mtime
        except OSError:
            continue
        
        # Try to read finished_at from meta.json
        finished_at = None
        meta_path = run_dir / "meta.json"
        if meta_path.exists():
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                # Try different possible field names
                finished_at_str = meta.get("finished_at") or meta.get("completed_at") or meta.get("created_at")
                if finished_at_str:
                    # Parse ISO timestamp to epoch seconds
                    try:
                        dt = datetime.fromisoformat(finished_at_str.replace('Z', '+00:00'))
                        finished_at = dt.timestamp()
                    except ValueError:
                        pass
            except Exception as e:
                logger.debug(f"Failed to read meta.json for {run_dir}: {e}")
        
        runs.append(RunRef(
            name=run_dir.name,
            path=run_dir,
            mtime=mtime,
            finished_at=finished_at
        ))
    
    # Sort by finished_at if available, else mtime, descending (newest first)
    runs.sort(key=lambda r: r.finished_at if r.finished_at is not None else r.mtime, reverse=True)
    return runs


def pick_last_run(season: str, outputs_root: Path) -> Optional[RunRef]:
    """Return the most recent run for the given season."""
    runs = list_runs(season, outputs_root)
    return runs[0] if runs else None


def get_run_summary(run_dir: Path) -> tuple[Optional[dict], str]:
    """Return (summary_dict, reason). reason non-empty on missing/parse error."""
    # Check for common summary files
    summary_files = [
        ("summary.json", run_dir / "summary.json"),
        ("metrics.json", run_dir / "metrics.json"),
        ("stats.json", run_dir / "stats.json"),
        ("report.json", run_dir / "report.json"),
    ]
    
    for name, path in summary_files:
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return data, f"Loaded from {name}"
            except Exception as e:
                logger.warning(f"Failed to parse {path}: {e}")
                continue
    
    # Check for any .npz files that might contain metrics
    npz_files = list(run_dir.glob("*.npz"))
    if npz_files:
        return {}, f"Found {len(npz_files)} NPZ files but no JSON summary"
    
    return None, "No summary files found (summary.json, metrics.json, stats.json, report.json, *.npz)"