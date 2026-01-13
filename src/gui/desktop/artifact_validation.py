"""
Artifact validation utilities for Desktop UI (Phase 15.1 contract).

Provides canonical predicates and validation functions that enforce the
hard contract: only artifact_* directories with both manifest.json AND
metrics.json are considered promotable artifacts.
"""

import re
from pathlib import Path
from typing import Dict, Any, List

# Regex for valid run directory names matching ^(run|artifact)_[0-9a-f]{6,64}$
_DIR_RE = re.compile(r"^(run|artifact)_[0-9a-f]{6,64}$")


def is_artifact_dir_name(name: str) -> bool:
    """Canonical predicate: return True iff name matches ^(run|artifact)_[0-9a-f]{6,64}$."""
    return bool(_DIR_RE.match(name))


def validate_artifact_dir(run_dir: Path) -> Dict[str, Any]:
    """
    HARD CONTRACT: Validate artifact directory.
    
    Phase 18: Requires ALL of manifest.json, metrics.json, trades.parquet,
    equity.parquet, and report.json for a valid promotable artifact.
    
    Returns dict with:
        ok: bool
        reason: str
        path: str
        missing: List[str] (if applicable)
    """
    # HARD CONTRACT: MUST be artifact_*
    if not is_artifact_dir_name(run_dir.name):
        return {"ok": False, "reason": "not_artifact_prefix", "path": str(run_dir)}
    
    # Phase 18: Full artifact contract
    required_files = [
        ("manifest.json", run_dir / "manifest.json"),
        ("metrics.json", run_dir / "metrics.json"),
        ("trades.parquet", run_dir / "trades.parquet"),
        ("equity.parquet", run_dir / "equity.parquet"),
        ("report.json", run_dir / "report.json"),
    ]
    
    missing = list()
    for name, path in required_files:
        if not path.exists():
            missing.append(name)
    
    if missing:
        return {
            "ok": False,
            "reason": "missing_required_files",
            "missing": missing,
            "path": str(run_dir)
        }
    
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
        return {"valid": False, "run_dir": "", "found_files": list()}
    
    path = Path(artifact_path)
    if not path.exists():
        return {"valid": False, "run_dir": str(path), "found_files": list()}
    
    # HARD CONTRACT: MUST be artifact_*
    if not is_artifact_dir_name(path.name):
        return {"valid": False, "run_dir": str(path), "found_files": list()}
    
    # Backward compatibility: only require manifest.json and metrics.json
    # (Phase 15.1 contract)
    required_files = [
        ("manifest.json", path / "manifest.json"),
        ("metrics.json", path / "metrics.json"),
    ]
    
    found_files = list()
    for name, filepath in required_files:
        if filepath.exists():
            found_files.append(name)
    
    # Check if we have at least manifest and metrics
    if len(found_files) < 2:
        return {"valid": False, "run_dir": str(path), "found_files": found_files}
    
    # Also check for Phase 18 files for completeness
    phase18_files = ["trades.parquet", "equity.parquet", "report.json"]
    for name in phase18_files:
        if (path / name).exists():
            found_files.append(name)
    
    return {
        "valid": True,
        "run_dir": str(path),
        "found_files": found_files
    }