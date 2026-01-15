"""
API payload contracts (SSOT for GUI ↔ Control communication).

These models define the request/response shapes for the Mission Control API v1.
They are imported by both control/api.py and GUI components (if needed).
"""

from __future__ import annotations

from typing import Optional, Any, List, Dict, Literal
from pydantic import BaseModel, Field


class ReadinessResponse(BaseModel):
    """Response for GET /api/v1/readiness/{season}/{dataset_id}/{timeframe}."""
    season: str
    dataset_id: str
    timeframe: str
    bars_ready: bool
    features_ready: bool
    bars_path: Optional[str] = None
    features_path: Optional[str] = None
    error: Optional[str] = None


class SubmitJobRequest(BaseModel):
    # Accept GUI params directly
    strategy_id: str
    instrument: str
    timeframe: str
    run_mode: str
    season: str
    dataset: Optional[str] = None
    wfs_policy: Optional[str] = None


class PolicyGateModel(BaseModel):
    metric: str
    op: str
    threshold: float
    enabled: bool
    fail_reason: str


class PolicyModesModel(BaseModel):
    mode_b_enabled: bool
    scoring_guards_enabled: bool


class WfsPolicyRegistryEntry(BaseModel):
    selector: str
    name: str
    version: str
    hash: str
    source: str
    resolved_source: str
    modes: PolicyModesModel
    gates: Dict[str, PolicyGateModel]
    description: str


class WfsPolicyRegistryResponse(BaseModel):
    entries: List[WfsPolicyRegistryEntry]


class JobListResponse(BaseModel):
    """Response for GET /api/v1/jobs."""
    job_id: str
    type: str = "strategy"  # default type
    status: str
    created_at: str
    finished_at: Optional[str] = None
    strategy_name: Optional[str] = None
    instrument: Optional[str] = None
    timeframe: Optional[str] = None
    run_mode: Optional[str] = None
    season: Optional[str] = None
    duration_seconds: Optional[float] = None
    score: Optional[float] = None
    error_details: Optional[dict] = None
    failure_code: Optional[str] = None
    failure_message: Optional[str] = None
    policy_stage: Optional[str] = None


class JobExplainCodes(BaseModel):
    failure_code: str = ""
    policy_stage: str = ""
    http_status: Optional[int] = None


class JobExplainEvidence(BaseModel):
    policy_check_url: Optional[str] = None
    manifest_url: Optional[str] = None
    inputs_fingerprint_url: Optional[str] = None
    stdout_tail_url: Optional[str] = None
    evidence_bundle_url: Optional[str] = None


class JobExplainCache(BaseModel):
    hit: bool
    ttl_s: int


class JobExplainDebug(BaseModel):
    derived_from: List[str]
    cache: JobExplainCache


class JobExplainResponse(BaseModel):
    """Response for GET /api/v1/jobs/{job_id}/explain."""
    schema_version: Literal["1.0"] = "1.0"
    job_id: str
    job_type: str
    final_status: str
    decision_layer: Literal["POLICY", "INPUT", "GOVERNANCE", "ARTIFACT", "SYSTEM", "UNKNOWN"]
    human_tag: Literal["VIOLATION", "MALFORMED", "FROZEN", "CORRUPTED", "INFRA_FAILURE", "UNKNOWN"]
    recoverable: bool
    summary: str
    action_hint: str
    codes: JobExplainCodes
    evidence: JobExplainEvidence
    debug: JobExplainDebug


class ArtifactIndexResponse(BaseModel):
    """Response for GET /api/v1/jobs/{job_id}/artifacts."""
    job_id: str
    links: dict[str, Optional[str]]
    files: list[dict[str, Any]]


class RevealEvidencePathResponse(BaseModel):
    """Response for GET /api/v1/jobs/{job_id}/reveal_evidence_path."""
    approved: bool
    path: str


class BatchStatusResponse(BaseModel):
    """Response for batch status."""
    batch_id: str
    state: str  # PENDING, RUNNING, DONE, FAILED, PARTIAL_FAILED
    jobs_total: int = 0
    jobs_done: int = 0
    jobs_failed: int = 0


class BatchSummaryResponse(BaseModel):
    """Response for batch summary."""
    batch_id: str
    topk: list[dict[str, Any]] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)


class BatchMetadataUpdate(BaseModel):
    """Request for updating batch metadata."""
    season: Optional[str] = None
    tags: Optional[list[str]] = None
    note: Optional[str] = None
    frozen: Optional[bool] = None


class SeasonMetadataUpdate(BaseModel):
    """Request for updating season metadata."""
    tags: Optional[list[str]] = None
    note: Optional[str] = None
    frozen: Optional[bool] = None