"""
Job boundary extraction for P2-A: Season SSOT + Boundary Validator.

Extracts hard boundary fields from job artifacts.
"""

import json
from pathlib import Path
from typing import Optional
from pydantic import BaseModel

from contracts.season import SeasonHardBoundary


class JobBoundary(BaseModel):
    """Boundary fields extracted from a job."""
    universe_fingerprint: str
    timeframes_fingerprint: str
    dataset_snapshot_id: str
    engine_constitution_id: str


class JobBoundaryExtractionError(Exception):
    """Raised when job boundary cannot be extracted."""
    pass


def extract_job_boundary(job_id: str, outputs_root: Path) -> JobBoundary:
    """
    Extract boundary fields from job artifacts.
    
    Looks for boundary information in:
    1. Job spec (spec.json) in supervisor DB
    2. Job artifacts directory (outputs/artifacts/jobs/{job_id}/)
    3. Research artifacts (if research job)
    
    Args:
        job_id: Job ID
        outputs_root: Root outputs directory
    
    Returns:
        JobBoundary with extracted fields
    
    Raises:
        JobBoundaryExtractionError: If boundary cannot be extracted
    """
    # First try to get from job spec in supervisor DB
    try:
        from control.supervisor import get_job
        job_row = get_job(job_id)
        if job_row:
            spec = json.loads(job_row.spec_json)
            boundary = _extract_from_spec(spec)
            if boundary:
                return boundary
    except Exception:
        pass  # Fall through to other methods
    
    # Try to get from job artifacts directory
    job_dir = outputs_root / "artifacts" / "jobs" / job_id
    if job_dir.exists():
        # Look for research artifacts
        research_dir = job_dir / "research"
        if research_dir.exists():
            boundary = _extract_from_research_artifacts(research_dir)
            if boundary:
                return boundary
        
        # Look for any boundary files
        boundary = _extract_from_job_dir(job_dir)
        if boundary:
            return boundary
    
    # Try to get from portfolio artifacts (for portfolio jobs)
    portfolio_dir = outputs_root / "portfolios" / job_id
    if portfolio_dir.exists():
        boundary = _extract_from_portfolio_artifacts(portfolio_dir)
        if boundary:
            return boundary
    
    raise JobBoundaryExtractionError(
        f"Could not extract boundary fields for job {job_id}. "
        f"Tried: job spec, job artifacts ({job_dir}), portfolio artifacts"
    )


def _extract_from_spec(spec: dict) -> Optional[JobBoundary]:
    """Extract boundary from job spec."""
    try:
        params = spec.get("params", {})
        
        # Look for boundary fields in params
        universe_fingerprint = params.get("universe_fingerprint")
        timeframes_fingerprint = params.get("timeframes_fingerprint")
        dataset_snapshot_id = params.get("dataset_snapshot_id")
        engine_constitution_id = params.get("engine_constitution_id")
        
        # Also check metadata
        metadata = spec.get("metadata", {})
        if not universe_fingerprint:
            universe_fingerprint = metadata.get("universe_fingerprint")
        if not timeframes_fingerprint:
            timeframes_fingerprint = metadata.get("timeframes_fingerprint")
        if not dataset_snapshot_id:
            dataset_snapshot_id = metadata.get("dataset_snapshot_id")
        if not engine_constitution_id:
            engine_constitution_id = metadata.get("engine_constitution_id")
        
        # Check if we have all fields
        if (universe_fingerprint and timeframes_fingerprint and 
            dataset_snapshot_id and engine_constitution_id):
            return JobBoundary(
                universe_fingerprint=universe_fingerprint,
                timeframes_fingerprint=timeframes_fingerprint,
                dataset_snapshot_id=dataset_snapshot_id,
                engine_constitution_id=engine_constitution_id,
            )
    except Exception:
        pass
    
    return None


def _extract_from_research_artifacts(research_dir: Path) -> Optional[JobBoundary]:
    """Extract boundary from research artifacts."""
    # Look for research manifest
    manifest_path = research_dir / "manifest.json"
    if manifest_path.exists():
        try:
            with open(manifest_path, "r") as f:
                manifest = json.load(f)
            
            # Research manifest should have boundary fields
            universe_fingerprint = manifest.get("universe_fingerprint")
            timeframes_fingerprint = manifest.get("timeframes_fingerprint")
            dataset_snapshot_id = manifest.get("dataset_snapshot_id")
            engine_constitution_id = manifest.get("engine_constitution_id")
            
            if (universe_fingerprint and timeframes_fingerprint and 
                dataset_snapshot_id and engine_constitution_id):
                return JobBoundary(
                    universe_fingerprint=universe_fingerprint,
                    timeframes_fingerprint=timeframes_fingerprint,
                    dataset_snapshot_id=dataset_snapshot_id,
                    engine_constitution_id=engine_constitution_id,
                )
        except Exception:
            pass
    
    # Look for research config
    config_path = research_dir / "config.json"
    if config_path.exists():
        try:
            with open(config_path, "r") as f:
                config = json.load(f)
            
            universe_fingerprint = config.get("universe_fingerprint")
            timeframes_fingerprint = config.get("timeframes_fingerprint")
            dataset_snapshot_id = config.get("dataset_snapshot_id")
            engine_constitution_id = config.get("engine_constitution_id")
            
            if (universe_fingerprint and timeframes_fingerprint and 
                dataset_snapshot_id and engine_constitution_id):
                return JobBoundary(
                    universe_fingerprint=universe_fingerprint,
                    timeframes_fingerprint=timeframes_fingerprint,
                    dataset_snapshot_id=dataset_snapshot_id,
                    engine_constitution_id=engine_constitution_id,
                )
        except Exception:
            pass
    
    return None


def _extract_from_job_dir(job_dir: Path) -> Optional[JobBoundary]:
    """Extract boundary from job directory files."""
    # Look for boundary.json file
    boundary_path = job_dir / "boundary.json"
    if boundary_path.exists():
        try:
            with open(boundary_path, "r") as f:
                boundary_data = json.load(f)
            
            return JobBoundary(**boundary_data)
        except Exception:
            pass
    
    # Look for any JSON files that might contain boundary info
    for json_file in job_dir.glob("*.json"):
        try:
            with open(json_file, "r") as f:
                data = json.load(f)
            
            # Check if this looks like a boundary file
            if all(key in data for key in [
                "universe_fingerprint", "timeframes_fingerprint",
                "dataset_snapshot_id", "engine_constitution_id"
            ]):
                return JobBoundary(**data)
        except Exception:
            continue
    
    return None


def _extract_from_portfolio_artifacts(portfolio_dir: Path) -> Optional[JobBoundary]:
    """Extract boundary from portfolio artifacts."""
    # Look for portfolio manifest
    manifest_path = portfolio_dir / "manifest.json"
    if manifest_path.exists():
        try:
            with open(manifest_path, "r") as f:
                manifest = json.load(f)
            
            universe_fingerprint = manifest.get("universe_fingerprint")
            timeframes_fingerprint = manifest.get("timeframes_fingerprint")
            dataset_snapshot_id = manifest.get("dataset_snapshot_id")
            engine_constitution_id = manifest.get("engine_constitution_id")
            
            if (universe_fingerprint and timeframes_fingerprint and 
                dataset_snapshot_id and engine_constitution_id):
                return JobBoundary(
                    universe_fingerprint=universe_fingerprint,
                    timeframes_fingerprint=timeframes_fingerprint,
                    dataset_snapshot_id=dataset_snapshot_id,
                    engine_constitution_id=engine_constitution_id,
                )
        except Exception:
            pass
    
    return None


def get_job_artifact_dir(job_id: str, outputs_root: Path) -> Path:
    """
    Get job artifact directory.
    
    Args:
        job_id: Job ID
        outputs_root: Root outputs directory
    
    Returns:
        Path to job artifact directory
    """
    return outputs_root / "jobs" / job_id
