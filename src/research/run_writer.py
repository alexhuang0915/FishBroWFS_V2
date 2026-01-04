"""
Canonical Run Writer - Creates and updates canonical run artifacts.

Enforces the canonical run artifact contract:
- outputs/seasons/{season}/runs/{run_id}/run_record.json
- outputs/seasons/{season}/runs/{run_id}/manifest.json
- outputs/seasons/{season}/runs/{run_id}/metrics.json

Provides atomic write operations and status lifecycle management.
"""

import json
import tempfile
import shutil
from pathlib import Path
from typing import Any, Dict, Optional
from datetime import datetime, timezone


def ensure_run_dir(outputs_root: Path, season: str, run_id: str) -> Path:
    """
    Ensure run directory exists and return its path.
    
    Args:
        outputs_root: Root outputs directory (e.g., Path("outputs"))
        season: Season identifier (e.g., "2026Q1")
        run_id: Run ID (e.g., "run_abc123")
        
    Returns:
        Path to run directory (created if needed)
    """
    run_dir = outputs_root / "seasons" / season / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def write_run_manifest(run_dir: Path, manifest: Dict[str, Any]) -> Path:
    """
    Write manifest.json to run directory with atomic write.
    
    Args:
        run_dir: Run directory path
        manifest: Manifest dictionary
        
    Returns:
        Path to written manifest.json
        
    Raises:
        ValueError: If manifest missing required fields
    """
    # Validate required fields
    required = {"season", "run_id", "dataset_id", "strategy_id", "timeframe", "created_at", "git_sha"}
    missing = required - set(manifest.keys())
    if missing:
        raise ValueError(f"Manifest missing required fields: {missing}")
    
    # Ensure created_at is ISO format
    if "created_at" not in manifest:
        manifest["created_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    # Write atomically via temp file
    manifest_path = run_dir / "manifest.json"
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', dir=run_dir, delete=False) as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
        temp_path = Path(f.name)
    
    # Atomic rename
    temp_path.rename(manifest_path)
    return manifest_path


def write_run_metrics(run_dir: Path, metrics: Dict[str, Any]) -> Path:
    """
    Write metrics.json to run directory with atomic write.
    
    Args:
        run_dir: Run directory path
        metrics: Metrics dictionary
        
    Returns:
        Path to written metrics.json
        
    Raises:
        ValueError: If metrics missing required fields
    """
    # Validate required fields
    required = {"stage_name", "net_profit", "max_dd", "trades", "created_at"}
    missing = required - set(metrics.keys())
    if missing:
        raise ValueError(f"Metrics missing required fields: {missing}")
    
    # Ensure created_at is ISO format
    if "created_at" not in metrics:
        metrics["created_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    # Write atomically via temp file
    metrics_path = run_dir / "metrics.json"
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', dir=run_dir, delete=False) as f:
        json.dump(metrics, f, indent=2, sort_keys=True)
        temp_path = Path(f.name)
    
    # Atomic rename
    temp_path.rename(metrics_path)
    return metrics_path


def update_run_record_status(run_dir: Path, status: str, extra: Optional[Dict[str, Any]] = None) -> Path:
    """
    Update run_record.json status with atomic write.
    
    Args:
        run_dir: Run directory path
        status: New status (CREATED, RUNNING, COMPLETED, FAILED)
        extra: Optional extra fields to merge into run_record
        
    Returns:
        Path to updated run_record.json
        
    Raises:
        FileNotFoundError: If run_record.json doesn't exist
        ValueError: If status is invalid
    """
    valid_statuses = {"CREATED", "RUNNING", "COMPLETED", "FAILED"}
    if status not in valid_statuses:
        raise ValueError(f"Invalid status {status}. Must be one of {valid_statuses}")
    
    run_record_path = run_dir / "run_record.json"
    
    # Load existing run_record or create new
    if run_record_path.exists():
        with open(run_record_path, 'r', encoding='utf-8') as f:
            run_record = json.load(f)
    else:
        # Create minimal run_record
        run_record = {
            "version": "1.0",
            "run_id": run_dir.name,
            "season": run_dir.parent.parent.name,  # Extract from path: .../seasons/{season}/runs/{run_id}
            "status": status,
            "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "artifacts": {}
        }
    
    # Update status and timestamp
    run_record["status"] = status
    run_record["updated_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    # Merge extra fields
    if extra:
        run_record.update(extra)
    
    # Write atomically via temp file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', dir=run_dir, delete=False) as f:
        json.dump(run_record, f, indent=2, sort_keys=True)
        temp_path = Path(f.name)
    
    # Atomic rename
    temp_path.rename(run_record_path)
    return run_record_path


def create_canonical_run(
    outputs_root: Path,
    season: str,
    run_id: str,
    manifest: Dict[str, Any],
    metrics: Dict[str, Any],
    initial_status: str = "CREATED"
) -> Path:
    """
    Create a complete canonical run with all required artifacts.
    
    Args:
        outputs_root: Root outputs directory
        season: Season identifier
        run_id: Run ID
        manifest: Manifest dictionary (must include required fields)
        metrics: Metrics dictionary (must include required fields)
        initial_status: Initial run status (default: CREATED)
        
    Returns:
        Path to run directory
    """
    # Ensure run directory exists
    run_dir = ensure_run_dir(outputs_root, season, run_id)
    
    # Create run_record with initial status
    update_run_record_status(run_dir, initial_status, {
        "intent": {
            "strategy_id": manifest.get("strategy_id"),
            "dataset_id": manifest.get("dataset_id"),
            "timeframe": manifest.get("timeframe"),
        }
    })
    
    # Write manifest and metrics
    write_run_manifest(run_dir, manifest)
    write_run_metrics(run_dir, metrics)
    
    return run_dir


def complete_run(
    run_dir: Path,
    manifest: Optional[Dict[str, Any]] = None,
    metrics: Optional[Dict[str, Any]] = None,
    generate_phase18_artifacts: bool = True,
) -> Path:
    """
    Mark a run as COMPLETED and update artifacts.
    
    Args:
        run_dir: Run directory path
        manifest: Optional updated manifest (if None, existing is kept)
        metrics: Optional updated metrics (if None, existing is kept)
        generate_phase18_artifacts: Whether to generate Phase 18 artifacts
            (trades.parquet, equity.parquet, report.json)
        
    Returns:
        Path to run directory
    """
    # Update manifest if provided
    if manifest is not None:
        write_run_manifest(run_dir, manifest)
    
    # Update metrics if provided
    if metrics is not None:
        write_run_metrics(run_dir, metrics)
    
    # Generate Phase 18 artifacts if requested
    if generate_phase18_artifacts:
        try:
            _generate_phase18_artifacts(run_dir, metrics or {})
        except Exception as e:
            # Log but don't fail - run can still be marked as COMPLETED
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to generate Phase 18 artifacts: {e}")
    
    # Update status to COMPLETED
    update_run_record_status(run_dir, "COMPLETED", {
        "completed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    })
    
    return run_dir


def _generate_phase18_artifacts(run_dir: Path, metrics: Dict[str, Any]) -> None:
    """
    Generate Phase 18 required artifacts (trades.parquet, equity.parquet, report.json).
    
    Args:
        run_dir: Run directory path
        metrics: Metrics dictionary for generating appropriate artifacts
    """
    try:
        from core.artifact_writers import write_full_artifact
        
        # Load existing manifest and config if available
        manifest_path = run_dir / "manifest.json"
        config_path = run_dir / "config_snapshot.json"
        
        manifest = {}
        config_snapshot = {}
        
        if manifest_path.exists():
            with open(manifest_path, 'r', encoding='utf-8') as f:
                manifest = json.load(f)
        
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                config_snapshot = json.load(f)
        
        # Generate full artifact
        write_full_artifact(
            run_dir=run_dir,
            manifest=manifest,
            config_snapshot=config_snapshot,
            metrics=metrics,
            winners=None,
        )
        
    except ImportError:
        # Fall back to minimal artifact generation
        _generate_minimal_phase18_artifacts(run_dir, metrics)


def _generate_minimal_phase18_artifacts(run_dir: Path, metrics: Dict[str, Any]) -> None:
    """
    Generate minimal Phase 18 artifacts when full writer is not available.
    
    Creates empty but valid parquet files and a basic report.json.
    """
    import pandas as pd
    import numpy as np
    from datetime import datetime, timezone
    
    # Create empty trades.parquet with correct schema
    trades_df = pd.DataFrame({
        "entry_ts": pd.Series([], dtype="datetime64[ns, UTC]"),
        "exit_ts": pd.Series([], dtype="datetime64[ns, UTC]"),
        "side": pd.Series([], dtype="str"),
        "entry_px": pd.Series([], dtype="float64"),
        "exit_px": pd.Series([], dtype="float64"),
        "pnl": pd.Series([], dtype="float64"),
        "bars_held": pd.Series([], dtype="int64"),
    })
    trades_df.to_parquet(run_dir / "trades.parquet", index=False)
    
    # Create minimal equity.parquet with flat equity curve
    dates = pd.date_range("2026-01-01", periods=10, tz="UTC")
    equity_df = pd.DataFrame({
        "ts": dates,
        "equity": [10000.0] * len(dates),
        "drawdown": [0.0] * len(dates),
    })
    equity_df.to_parquet(run_dir / "equity.parquet", index=False)
    
    # Create basic report.json
    report = {
        "run_id": run_dir.name,
        "season": run_dir.parent.parent.name if "seasons" in str(run_dir) else "2026Q1",
        "market": metrics.get("dataset_id", "unknown"),
        "tf": metrics.get("timeframe", "60m"),
        "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "summary": {
            "net_profit": metrics.get("net_profit", 0.0),
            "max_dd": metrics.get("max_dd", 0.0),
            "trades": metrics.get("trades", 0),
            "fills_count": metrics.get("fills_count", 0),
        },
        "status": "PARTIAL" if metrics.get("trades", 0) == 0 else "READY",
        "notes": "Generated by minimal Phase 18 artifact writer",
    }
    
    with open(run_dir / "report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, sort_keys=True)