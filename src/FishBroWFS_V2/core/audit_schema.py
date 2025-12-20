"""Audit schema for run tracking and reproducibility.

Single Source of Truth (SSOT) for audit data.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict


@dataclass(frozen=True)
class AuditSchema:
    """
    Audit schema for run tracking.
    
    All fields are required and must be JSON-serializable.
    This is the Single Source of Truth (SSOT) for audit data.
    """
    run_id: str
    created_at: str  # ISO8601 with Z suffix (UTC)
    git_sha: str  # At least 12 chars
    dirty_repo: bool  # Whether repo has uncommitted changes
    param_subsample_rate: float  # Required, must be in [0.0, 1.0]
    config_hash: str  # Stable hash of config
    season: str  # Season identifier
    dataset_id: str  # Dataset identifier
    bars: int  # Number of bars processed
    params_total: int  # Total parameters before subsample
    params_effective: int  # Effective parameters after subsample (= int(params_total * param_subsample_rate))
    artifact_version: str = "v1"  # Artifact version
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


def compute_params_effective(params_total: int, param_subsample_rate: float) -> int:
    """
    Compute effective parameters after subsample.
    
    Rounding rule: int(params_total * param_subsample_rate)
    This is locked in code/docs/tests - do not change.
    
    Args:
        params_total: Total parameters before subsample
        param_subsample_rate: Subsample rate in [0.0, 1.0]
        
    Returns:
        Effective parameters (integer, rounded down)
    """
    if not (0.0 <= param_subsample_rate <= 1.0):
        raise ValueError(f"param_subsample_rate must be in [0.0, 1.0], got {param_subsample_rate}")
    
    return int(params_total * param_subsample_rate)
