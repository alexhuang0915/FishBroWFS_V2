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
    
    # Phase 6.5: Mandatory fingerprint (validation enforces non-empty)
    data_fingerprint_sha1: Optional[str] = None
    
    # Phase 6.6: Timezone database metadata
    tzdb_provider: Optional[str] = None  # e.g., "zoneinfo"
    tzdb_version: Optional[str] = None  # Timezone database version
    data_tz: Optional[str] = None  # Data timezone (e.g., "Asia/Taipei")
    exchange_tz: Optional[str] = None  # Exchange timezone (e.g., "America/Chicago")
    
    # Phase 7: Strategy metadata
    strategy_id: Optional[str] = None  # Strategy identifier (e.g., "sma_cross")
    strategy_version: Optional[str] = None  # Strategy version (e.g., "v1")
    param_schema_hash: Optional[str] = None  # SHA1 hash of param_schema JSON
