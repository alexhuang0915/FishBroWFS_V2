"""Job API for M1 Wizard.

Provides job creation and governance checking for the wizard UI.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Any, Optional, List
from datetime import datetime

from FishBroWFS_V2.control.jobs_db import create_job, get_job, list_jobs
from FishBroWFS_V2.control.types import DBJobSpec, JobRecord, JobStatus
from FishBroWFS_V2.control.dataset_catalog import get_dataset_catalog
from FishBroWFS_V2.control.strategy_catalog import get_strategy_catalog
from FishBroWFS_V2.control.dataset_descriptor import get_descriptor
from FishBroWFS_V2.control.input_manifest import create_input_manifest, write_input_manifest
from FishBroWFS_V2.core.config_snapshot import make_config_snapshot


class JobAPIError(Exception):
    """Base exception for Job API errors."""
    pass


class SeasonFrozenError(JobAPIError):
    """Raised when trying to submit a job to a frozen season."""
    pass


class ValidationError(JobAPIError):
    """Raised when job validation fails."""
    pass


def check_season_not_frozen(season: str, action: str = "submit_job") -> None:
    """Check if a season is frozen.
    
    Args:
        season: Season identifier (e.g., "2024Q1")
        action: Action being performed (for error message)
        
    Raises:
        SeasonFrozenError: If season is frozen
    """
    # TODO: Implement actual season frozen check
    # For M1, we'll assume seasons are not frozen
    # In a real implementation, this would check season governance state
    pass


def validate_wizard_payload(payload: Dict[str, Any]) -> List[str]:
    """Validate wizard payload.
    
    Args:
        payload: Wizard payload dictionary
        
    Returns:
        List of validation error messages (empty if valid)
    """
    errors = []
    
    # Required fields
    required_fields = ["season", "data1", "strategy_id", "params"]
    for field in required_fields:
        if field not in payload:
            errors.append(f"Missing required field: {field}")
    
    # Validate data1
    if "data1" in payload:
        data1 = payload["data1"]
        if not isinstance(data1, dict):
            errors.append("data1 must be a dictionary")
        else:
            if "dataset_id" not in data1:
                errors.append("data1 missing dataset_id")
            else:
                # Check dataset exists and has Parquet files
                dataset_id = data1["dataset_id"]
                try:
                    descriptor = get_descriptor(dataset_id)
                    if descriptor is None:
                        errors.append(f"Dataset not found: {dataset_id}")
                    else:
                        # Check if Parquet files exist
                        from pathlib import Path
                        parquet_missing = []
                        for parquet_path_str in descriptor.parquet_expected_paths:
                            parquet_path = Path(parquet_path_str)
                            if not parquet_path.exists():
                                parquet_missing.append(parquet_path_str)
                        
                        if parquet_missing:
                            missing_list = ", ".join(parquet_missing[:3])  # Show first 3
                            if len(parquet_missing) > 3:
                                missing_list += f" and {len(parquet_missing) - 3} more"
                            errors.append(f"Dataset {dataset_id} missing Parquet files: {missing_list}")
                            errors.append(f"Use the Status page to build Parquet from TXT sources")
                except Exception as e:
                    errors.append(f"Error checking dataset {dataset_id}: {str(e)}")
            
            if "symbols" not in data1:
                errors.append("data1 missing symbols")
            if "timeframes" not in data1:
                errors.append("data1 missing timeframes")
    
    # Validate data2 if present
    if "data2" in payload and payload["data2"]:
        data2 = payload["data2"]
        if not isinstance(data2, dict):
            errors.append("data2 must be a dictionary or null")
        else:
            if "dataset_id" not in data2:
                errors.append("data2 missing dataset_id")
            else:
                # Check data2 dataset exists and has Parquet files
                dataset_id = data2["dataset_id"]
                try:
                    descriptor = get_descriptor(dataset_id)
                    if descriptor is None:
                        errors.append(f"DATA2 dataset not found: {dataset_id}")
                    else:
                        # Check if Parquet files exist
                        from pathlib import Path
                        parquet_missing = []
                        for parquet_path_str in descriptor.parquet_expected_paths:
                            parquet_path = Path(parquet_path_str)
                            if not parquet_path.exists():
                                parquet_missing.append(parquet_path_str)
                        
                        if parquet_missing:
                            missing_list = ", ".join(parquet_missing[:3])
                            if len(parquet_missing) > 3:
                                missing_list += f" and {len(parquet_missing) - 3} more"
                            errors.append(f"DATA2 dataset {dataset_id} missing Parquet files: {missing_list}")
                except Exception as e:
                    errors.append(f"Error checking DATA2 dataset {dataset_id}: {str(e)}")
            
            if "filters" not in data2:
                errors.append("data2 missing filters")
    
    # Validate strategy
    if "strategy_id" in payload:
        strategy_catalog = get_strategy_catalog()
        strategy = strategy_catalog.get_strategy(payload["strategy_id"])
        if strategy is None:
            errors.append(f"Unknown strategy: {payload['strategy_id']}")
        else:
            # Validate parameters
            params = payload.get("params", {})
            param_errors = strategy_catalog.validate_parameters(payload["strategy_id"], params)
            for param_name, error_msg in param_errors.items():
                errors.append(f"Parameter '{param_name}': {error_msg}")
    
    return errors


def calculate_units(payload: Dict[str, Any]) -> int:
    """Calculate units count for wizard payload.
    
    Units formula: |DATA1.symbols| × |DATA1.timeframes| × |strategies| × |DATA2.filters|
    
    Args:
        payload: Wizard payload dictionary
        
    Returns:
        Total units count
    """
    # Extract data1 symbols and timeframes
    data1 = payload.get("data1", {})
    symbols = data1.get("symbols", [])
    timeframes = data1.get("timeframes", [])
    
    # Count strategies (always 1 for single strategy, but could be list)
    strategy_id = payload.get("strategy_id")
    strategies = [strategy_id] if strategy_id else []
    
    # Extract data2 filters if present
    data2 = payload.get("data2")
    if data2 is None:
        filters = []
    else:
        filters = data2.get("filters", [])
    
    # Apply formula
    symbols_count = len(symbols) if isinstance(symbols, list) else 1
    timeframes_count = len(timeframes) if isinstance(timeframes, list) else 1
    strategies_count = len(strategies) if isinstance(strategies, list) else 1
    filters_count = len(filters) if isinstance(filters, list) else 1
    
    # If data2 is not enabled, filters_count should be 1 (no filter multiplication)
    if not data2 or not payload.get("enable_data2", False):
        filters_count = 1
    
    units = symbols_count * timeframes_count * strategies_count * filters_count
    return units


def create_job_from_wizard(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Create a job from wizard payload.
    
    This is the main function called by the wizard UI on submit.
    
    Args:
        payload: Wizard payload dictionary with structure:
            {
                "season": "2024Q1",
                "data1": {
                    "dataset_id": "CME.MNQ.60m.2020-2024",
                    "symbols": ["MNQ", "MXF"],
                    "timeframes": ["60m", "120m"],
                    "start_date": "2020-01-01",
                    "end_date": "2024-12-31"
                },
                "data2": {
                    "dataset_id": "TWF.MXF.15m.2018-2023",
                    "filters": ["filter1", "filter2"]
                } | null,
                "strategy_id": "sma_cross_v1",
                "params": {
                    "window_fast": 10,
                    "window_slow": 30
                },
                "wfs": {
                    "stage0_subsample": 0.1,
                    "top_k": 20,
                    "mem_limit_mb": 8192,
                    "allow_auto_downsample": True
                }
            }
        
    Returns:
        Dictionary with job_id and units count:
            {
                "job_id": "uuid-here",
                "units": 4,
                "season": "2024Q1",
                "status": "queued"
            }
        
    Raises:
        SeasonFrozenError: If season is frozen
        ValidationError: If payload validation fails
    """
    # Check season not frozen
    season = payload.get("season")
    if season:
        check_season_not_frozen(season, action="submit_job")
    
    # Validate payload
    errors = validate_wizard_payload(payload)
    if errors:
        raise ValidationError(f"Payload validation failed: {', '.join(errors)}")
    
    # Calculate units
    units = calculate_units(payload)
    
    # Create config snapshot
    config_snapshot = make_config_snapshot(payload)
    
    # Create DBJobSpec
    data1 = payload["data1"]
    dataset_id = data1["dataset_id"]
    
    # Generate outputs root path
    outputs_root = f"outputs/{season}/jobs"
    
    # Create job spec
    spec = DBJobSpec(
        season=season,
        dataset_id=dataset_id,
        outputs_root=outputs_root,
        config_snapshot=config_snapshot,
        config_hash="",  # Will be computed by create_job
        data_fingerprint_sha256_40=""  # Will be populated if needed
    )
    
    # Create job in database
    db_path = Path("outputs/jobs.db")
    job_id = create_job(db_path, spec)
    
    # Create input manifest for auditability
    try:
        # Extract DATA2 dataset ID if present
        data2_dataset_id = None
        if "data2" in payload and payload["data2"]:
            data2 = payload["data2"]
            data2_dataset_id = data2.get("dataset_id")
        
        # Create input manifest
        from FishBroWFS_V2.control.input_manifest import create_input_manifest, write_input_manifest
        
        manifest = create_input_manifest(
            job_id=job_id,
            season=season,
            config_snapshot=config_snapshot,
            data1_dataset_id=dataset_id,
            data2_dataset_id=data2_dataset_id,
            previous_manifest_hash=None  # First in chain
        )
        
        # Write manifest to job outputs directory
        manifest_dir = Path(f"outputs/{season}/jobs/{job_id}")
        manifest_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = manifest_dir / "input_manifest.json"
        
        write_success = write_input_manifest(manifest, manifest_path)
        
        if not write_success:
            # Log warning but don't fail the job
            print(f"Warning: Failed to write input manifest for job {job_id}")
    except Exception as e:
        # Don't fail job creation if manifest creation fails
        print(f"Warning: Failed to create input manifest for job {job_id}: {e}")
    
    return {
        "job_id": job_id,
        "units": units,
        "season": season,
        "status": "queued"
    }


def get_job_status(job_id: str) -> Dict[str, Any]:
    """Get job status with units progress.
    
    Args:
        job_id: Job ID
        
    Returns:
        Dictionary with job status and progress:
            {
                "job_id": "uuid-here",
                "status": "running",
                "units_done": 10,
                "units_total": 20,
                "progress": 0.5,
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-01T00:00:00Z"
            }
    """
    db_path = Path("outputs/jobs.db")
    try:
        job = get_job(db_path, job_id)
        
        # For M1, we need to calculate units_done and units_total
        # This would normally come from job execution progress
        # For now, we'll return placeholder values
        units_total = 0
        units_done = 0
        
        # Try to extract units from config snapshot
        if hasattr(job.spec, 'config_snapshot'):
            config = job.spec.config_snapshot
            if isinstance(config, dict) and 'units' in config:
                units_total = config.get('units', 0)
        
        # Estimate units_done based on status
        if job.status == JobStatus.DONE:
            units_done = units_total
        elif job.status == JobStatus.RUNNING:
            # For demo, assume 50% progress
            units_done = units_total // 2 if units_total > 0 else 0
        
        progress = units_done / units_total if units_total > 0 else 0
        
        return {
            "job_id": job_id,
            "status": job.status.value,
            "units_done": units_done,
            "units_total": units_total,
            "progress": progress,
            "created_at": job.created_at,
            "updated_at": job.updated_at,
            "season": job.spec.season,
            "dataset_id": job.spec.dataset_id
        }
    except KeyError:
        raise JobAPIError(f"Job not found: {job_id}")


def list_jobs_with_progress(limit: int = 50) -> List[Dict[str, Any]]:
    """List jobs with units progress.
    
    Args:
        limit: Maximum number of jobs to return
        
    Returns:
        List of job dictionaries with progress information
    """
    db_path = Path("outputs/jobs.db")
    jobs = list_jobs(db_path, limit=limit)
    
    result = []
    for job in jobs:
        # Calculate progress for each job
        units_total = 0
        units_done = 0
        
        if hasattr(job.spec, 'config_snapshot'):
            config = job.spec.config_snapshot
            if isinstance(config, dict) and 'units' in config:
                units_total = config.get('units', 0)
        
        if job.status == JobStatus.DONE:
            units_done = units_total
        elif job.status == JobStatus.RUNNING:
            units_done = units_total // 2 if units_total > 0 else 0
        
        progress = units_done / units_total if units_total > 0 else 0
        
        result.append({
            "job_id": job.job_id,
            "status": job.status.value,
            "units_done": units_done,
            "units_total": units_total,
            "progress": progress,
            "created_at": job.created_at,
            "updated_at": job.updated_at,
            "season": job.spec.season,
            "dataset_id": job.spec.dataset_id
        })
    
    return result


def get_job_logs_tail(job_id: str, lines: int = 50) -> List[str]:
    """Get tail of job logs.
    
    Args:
        job_id: Job ID
        lines: Number of lines to return
        
    Returns:
        List of log lines (most recent first)
    """
    # TODO: Implement actual log retrieval
    # For M1, return placeholder logs
    return [
        f"[{datetime.now().isoformat()}] Job {job_id} started",
        f"[{datetime.now().isoformat()}] Loading dataset...",
        f"[{datetime.now().isoformat()}] Running strategy...",
        f"[{datetime.now().isoformat()}] Processing units...",
    ][-lines:]


# Convenience functions for GUI
def submit_wizard_job(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Submit wizard job (alias for create_job_from_wizard)."""
    return create_job_from_wizard(payload)


def get_job_summary(job_id: str) -> Dict[str, Any]:
    """Get job summary for detail page."""
    status = get_job_status(job_id)
    logs = get_job_logs_tail(job_id, lines=20)
    
    return {
        **status,
        "logs": logs,
        "log_tail": "\n".join(logs[-10:]) if logs else "No logs available"
    }