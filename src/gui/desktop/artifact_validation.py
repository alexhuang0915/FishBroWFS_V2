"""
Artifact validation utilities for Desktop UI (Phase 15.1 contract).

Provides canonical predicates and validation functions that enforce the
hard contract: only artifact_* directories with both manifest.json AND
metrics.json are considered promotable artifacts.
"""

from pathlib import Path
from typing import Dict, Any, List


def is_artifact_dir_name(name: str) -> bool:
    """Canonical predicate: return True iff name starts with 'artifact_'."""
    return name.startswith("artifact_")


def validate_artifact_dir(run_dir: Path) -> Dict[str, Any]:
    """
    HARD CONTRACT: Validate artifact directory.
    
    Returns dict with:
        ok: bool
        reason: str
        path: str
        missing: List[str] (if applicable)
    """
    # HARD CONTRACT: MUST be artifact_*
    if not is_artifact_dir_name(run_dir.name):
        return {"ok": False, "reason": "not_artifact_prefix", "path": str(run_dir)}
    
    manifest = run_dir / "manifest.json"
    metrics = run_dir / "metrics.json"
    if not manifest.exists() or not metrics.exists():
        missing = []
        if not manifest.exists(): missing.append("manifest.json")
        if not metrics.exists(): missing.append("metrics.json")
        return {"ok": False, "reason": "missing_required_files", "missing": missing, "path": str(run_dir)}
    
    return {"ok": True, "reason": "ok", "path": str(run_dir)}


def find_latest_valid_artifact(runs_dir: Path) -> Dict[str, Any]:
    """Find the latest valid artifact directory in runs_dir."""
    if not runs_dir.exists():
        return {"ok": False, "reason": "runs_dir_missing"}
    
    candidates = [p for p in runs_dir.iterdir() if p.is_dir() and is_artifact_dir_name(p.name)]
    # newest first by mtime
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    
    for p in candidates:
        v = validate_artifact_dir(p)
        if v.get("ok"):
            return {"ok": True, "artifact_dir": str(p), "validation": v}
    
    return {"ok": False, "reason": "no_valid_artifact_found"}


def validate_artifact_backward_compatible(artifact_path: str) -> Dict[str, Any]:
    """
    Backward-compatible validation (returns old format).
    
    Returns dict with:
        valid: bool
        run_dir: str
        found_files: List[str]
    """
    if not artifact_path:
        return {"valid": False, "run_dir": "", "found_files": []}
    
    path = Path(artifact_path)
    if not path.exists():
        return {"valid": False, "run_dir": str(path), "found_files": []}
    
    # Use strict validation
    v = validate_artifact_dir(path)
    if not v.get("ok"):
        return {"valid": False, "run_dir": str(path), "found_files": []}
    
    # Check which files exist for backward compatibility
    required_patterns = ["metrics.json", "manifest.json", "trades.parquet"]
    found_files = []
    
    for pattern in required_patterns:
        if (path / pattern).exists():
            found_files.append(pattern)
    
    return {
        "valid": True,
        "run_dir": str(path),
        "found_files": found_files
    }