"""Artifact reader for governance evaluation.

Reads artifacts (manifest/metrics/winners/config_snapshot) from run directories.
Only reads JSON files - never parses README or other human-readable text.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict


def read_manifest(run_dir: Path) -> Dict[str, Any]:
    """
    Read manifest.json from run directory.
    
    Args:
        run_dir: Path to run directory
        
    Returns:
        Manifest dict (AuditSchema as dict)
        
    Raises:
        FileNotFoundError: If manifest.json does not exist
        json.JSONDecodeError: If manifest.json is invalid JSON
    """
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(f"manifest.json not found in {run_dir}")
    
    with manifest_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def read_metrics(run_dir: Path) -> Dict[str, Any]:
    """
    Read metrics.json from run directory.
    
    Args:
        run_dir: Path to run directory
        
    Returns:
        Metrics dict
        
    Raises:
        FileNotFoundError: If metrics.json does not exist
        json.JSONDecodeError: If metrics.json is invalid JSON
    """
    metrics_path = run_dir / "metrics.json"
    if not metrics_path.exists():
        raise FileNotFoundError(f"metrics.json not found in {run_dir}")
    
    with metrics_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def read_winners(run_dir: Path) -> Dict[str, Any]:
    """
    Read winners.json from run directory.
    
    Args:
        run_dir: Path to run directory
        
    Returns:
        Winners dict with schema {"topk": [...], "notes": {...}}
        
    Raises:
        FileNotFoundError: If winners.json does not exist
        json.JSONDecodeError: If winners.json is invalid JSON
    """
    winners_path = run_dir / "winners.json"
    if not winners_path.exists():
        raise FileNotFoundError(f"winners.json not found in {run_dir}")
    
    with winners_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def read_config_snapshot(run_dir: Path) -> Dict[str, Any]:
    """
    Read config_snapshot.json from run directory.
    
    Args:
        run_dir: Path to run directory
        
    Returns:
        Config snapshot dict
        
    Raises:
        FileNotFoundError: If config_snapshot.json does not exist
        json.JSONDecodeError: If config_snapshot.json is invalid JSON
    """
    config_path = run_dir / "config_snapshot.json"
    if not config_path.exists():
        raise FileNotFoundError(f"config_snapshot.json not found in {run_dir}")
    
    with config_path.open("r", encoding="utf-8") as f:
        return json.load(f)
