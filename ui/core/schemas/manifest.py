"""Pydantic schema for manifest.json validation.

Validates run manifest with stages and artifacts tracking.
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional


class ManifestStage(BaseModel):
    """Stage information in manifest."""
    name: str
    status: str  # e.g. "DONE"/"FAILED"/"ABORTED"
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    artifacts: Dict[str, str] = Field(default_factory=dict)  # filename -> relpath


class RunManifest(BaseModel):
    """
    Run manifest schema.
    
    Validates manifest.json structure with run metadata, config hash, and stages.
    """
    schema_version: Optional[str] = None  # For future versioning
    run_id: str
    season: str
    config_hash: str
    created_at: Optional[str] = None
    stages: List[ManifestStage] = Field(default_factory=list)
    meta: Dict[str, Any] = Field(default_factory=dict)
    
    # Additional fields from AuditSchema (for backward compatibility)
    git_sha: Optional[str] = None
    dirty_repo: Optional[bool] = None
    param_subsample_rate: Optional[float] = None
    dataset_id: Optional[str] = None
    bars: Optional[int] = None
    params_total: Optional[int] = None
    params_effective: Optional[int] = None
    artifact_version: Optional[str] = None
