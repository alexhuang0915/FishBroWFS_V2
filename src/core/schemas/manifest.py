
"""Pydantic schema for manifest.json validation.

Validates run manifest with stages and artifacts tracking.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
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


class UnifiedManifest(BaseModel):
    """
    Unified manifest schema for all manifest types (export, plan, view, quality).
    
    This schema defines the standard fields that should be present in all manifests
    for Manifest Tree Completeness verification.
    """
    # Common required fields
    manifest_type: str  # "export", "plan", "view", or "quality"
    manifest_version: str = "1.0"
    
    # Identification fields
    id: str  # run_id for export, plan_id for plan/view/quality
    
    # Timestamps
    generated_at_utc: Optional[str] = None
    created_at: Optional[str] = None
    
    # Source information
    source: Optional[Dict[str, Any]] = None
    
    # Input references (SHA256 hashes of input files)
    inputs: Optional[Dict[str, str]] = None
    
    # Files listing with SHA256 checksums (sorted by rel_path asc)
    files: Optional[List[Dict[str, str]]] = None
    
    # Combined SHA256 of all files (concatenated hashes)
    files_sha256: Optional[str] = None
    
    # Checksums for output files
    checksums: Optional[Dict[str, str]] = None
    
    # Type-specific checksums
    export_checksums: Optional[Dict[str, str]] = None
    plan_checksums: Optional[Dict[str, str]] = None
    view_checksums: Optional[Dict[str, str]] = None
    quality_checksums: Optional[Dict[str, str]] = None
    
    # Manifest self-hash (must be the last field)
    manifest_sha256: str
    
    model_config = ConfigDict(extra="allow")  # Allow additional type-specific fields


