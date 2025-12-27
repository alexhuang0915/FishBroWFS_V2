"""
Deterministic Snapshot - Freeze-time artifact hash registry.

Phase 5: Create reproducible snapshot of all artifacts when season is frozen.
"""

import json
import hashlib
from pathlib import Path
from typing import Dict, List, Any, Optional
import os


def compute_file_hash(filepath: Path) -> str:
    """Compute SHA256 hash of a file."""
    sha256 = hashlib.sha256()
    try:
        with open(filepath, "rb") as f:
            # Read in chunks to handle large files
            for chunk in iter(lambda: f.read(4096), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
    except (OSError, IOError):
        # If file cannot be read, return empty hash
        return ""


def collect_artifact_hashes(season_dir: Path) -> Dict[str, Any]:
    """
    Collect SHA256 hashes of all artifacts in a season directory.
    
    Returns:
        Dict with structure:
        {
            "snapshot_ts": "ISO-8601 timestamp",
            "season": "season identifier",
            "artifacts": {
                "relative/path/to/file": {
                    "sha256": "hexdigest",
                    "size_bytes": 1234,
                    "mtime": 1234567890.0
                },
                ...
            },
            "directories_scanned": [
                "runs/",
                "portfolio/",
                "research/",
                "governance/"
            ]
        }
    """
    from datetime import datetime, timezone
    
    # Directories to scan (relative to season_dir)
    scan_dirs = [
        "runs",
        "portfolio",
        "research",
        "governance"
    ]
    
    artifacts = {}
    
    for rel_dir in scan_dirs:
        dir_path = season_dir / rel_dir
        if not dir_path.exists():
            continue
        
        # Walk through directory
        for root, dirs, files in os.walk(dir_path):
            root_path = Path(root)
            for filename in files:
                filepath = root_path / filename
                
                # Skip temporary files and hidden files
                if filename.startswith(".") or filename.endswith(".tmp"):
                    continue
                
                # Skip very large files (>100MB) to avoid performance issues
                try:
                    file_size = filepath.stat().st_size
                    if file_size > 100 * 1024 * 1024:  # 100MB
                        continue
                except OSError:
                    continue
                
                # Compute relative path from season_dir
                try:
                    rel_path = filepath.relative_to(season_dir)
                except ValueError:
                    # Should not happen, but skip if it does
                    continue
                
                # Compute hash
                sha256 = compute_file_hash(filepath)
                if not sha256:  # Skip if hash computation failed
                    continue
                
                # Get file metadata
                try:
                    stat = filepath.stat()
                    artifacts[str(rel_path)] = {
                        "sha256": sha256,
                        "size_bytes": stat.st_size,
                        "mtime": stat.st_mtime,
                        "mtime_iso": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
                    }
                except OSError:
                    # Skip if metadata cannot be read
                    continue
    
    return {
        "snapshot_ts": datetime.now(timezone.utc).isoformat(),
        "season": season_dir.name,
        "artifacts": artifacts,
        "directories_scanned": scan_dirs,
        "artifact_count": len(artifacts)
    }


def create_freeze_snapshot(season: str) -> Path:
    """
    Create deterministic snapshot of all artifacts in a season.
    
    Args:
        season: Season identifier (e.g., "2026Q1")
    
    Returns:
        Path to the created snapshot file.
    
    Raises:
        FileNotFoundError: If season directory does not exist.
        OSError: If snapshot cannot be written.
    """
    from .season_context import season_dir as get_season_dir
    
    season_path = get_season_dir(season)
    if not season_path.exists():
        raise FileNotFoundError(f"Season directory does not exist: {season_path}")
    
    # Collect artifact hashes
    snapshot_data = collect_artifact_hashes(season_path)
    
    # Write snapshot file
    governance_dir = season_path / "governance"
    governance_dir.mkdir(parents=True, exist_ok=True)
    
    snapshot_path = governance_dir / "freeze_snapshot.json"
    
    # Write atomically
    temp_path = snapshot_path.with_suffix(".tmp")
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(snapshot_data, f, indent=2, ensure_ascii=False, sort_keys=True)
    
    # Replace original
    temp_path.replace(snapshot_path)
    
    return snapshot_path


def load_freeze_snapshot(season: str) -> Dict[str, Any]:
    """
    Load freeze snapshot for a season.
    
    Args:
        season: Season identifier
    
    Returns:
        Snapshot data dictionary.
    
    Raises:
        FileNotFoundError: If snapshot file does not exist.
        json.JSONDecodeError: If snapshot file is corrupted.
    """
    from .season_context import season_dir as get_season_dir
    
    season_path = get_season_dir(season)
    snapshot_path = season_path / "governance" / "freeze_snapshot.json"
    
    if not snapshot_path.exists():
        raise FileNotFoundError(f"Freeze snapshot not found: {snapshot_path}")
    
    with open(snapshot_path, "r", encoding="utf-8") as f:
        return json.load(f)


def verify_snapshot_integrity(season: str) -> Dict[str, Any]:
    """
    Verify current artifacts against freeze snapshot.
    
    Args:
        season: Season identifier
    
    Returns:
        Dict with verification results:
        {
            "ok": bool,
            "missing_files": List[str],
            "changed_files": List[str],
            "new_files": List[str],
            "total_checked": int,
            "errors": List[str]
        }
    """
    from .season_context import season_dir as get_season_dir
    
    season_path = get_season_dir(season)
    
    try:
        snapshot = load_freeze_snapshot(season)
    except FileNotFoundError:
        return {
            "ok": False,
            "missing_files": [],
            "changed_files": [],
            "new_files": [],
            "total_checked": 0,
            "errors": ["Freeze snapshot not found"]
        }
    
    # Get current artifact hashes
    current_artifacts = collect_artifact_hashes(season_path)
    
    # Compare
    snapshot_artifacts = snapshot.get("artifacts", {})
    current_artifact_paths = set(current_artifacts.get("artifacts", {}).keys())
    snapshot_artifact_paths = set(snapshot_artifacts.keys())
    
    missing_files = list(snapshot_artifact_paths - current_artifact_paths)
    new_files = list(current_artifact_paths - snapshot_artifact_paths)
    
    changed_files = []
    for path in snapshot_artifact_paths.intersection(current_artifact_paths):
        snapshot_hash = snapshot_artifacts[path].get("sha256", "")
        current_hash = current_artifacts["artifacts"][path].get("sha256", "")
        if snapshot_hash != current_hash:
            changed_files.append(path)
    
    ok = len(missing_files) == 0 and len(changed_files) == 0
    
    return {
        "ok": ok,
        "missing_files": sorted(missing_files),
        "changed_files": sorted(changed_files),
        "new_files": sorted(new_files),
        "total_checked": len(snapshot_artifact_paths),
        "errors": [] if ok else ["Artifacts have been modified since freeze"]
    }