"""
Season SSOT contracts for P2-A: Season SSOT + Boundary Validator.

Defines the request/response shapes for Season management API.
"""

from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Literal, List, Optional, Dict, Any
from enum import Enum


SeasonState = Literal["DRAFT", "OPEN", "FROZEN", "DECIDING", "ARCHIVED"]


class AdmissionDecisionEnum(str, Enum):
    """Admission decision enum."""
    ADMIT = "ADMIT"
    REJECT = "REJECT"
    HOLD = "HOLD"


class DecisionOutcome(str, Enum):
    """Decision outcome enum (used in evidence)."""
    ADMIT = "ADMIT"
    REJECT = "REJECT"
    HOLD = "HOLD"


class AdmissionEvidence(BaseModel):
    """Evidence for an admission decision."""
    evidence_id: str
    generated_at: str
    decision_outcome: DecisionOutcome
    decision_reason: str
    decision_criteria: Dict[str, Any] = Field(default_factory=dict)
    actor: str = "ui"
    evidence_data: Dict[str, Any] = Field(default_factory=dict)


class AdmissionDecision(BaseModel):
    """Admission decision record (used in season_admission service)."""
    candidate_identity: str
    outcome: DecisionOutcome
    decision_reason: str
    evidence: AdmissionEvidence
    decided_at: str
    decided_by: str


class SeasonHardBoundary(BaseModel):
    """Hard boundary for a season - must match exactly for job attachment."""
    universe_fingerprint: str
    timeframes_fingerprint: str
    dataset_snapshot_id: str
    engine_constitution_id: str


class SeasonRecord(BaseModel):
    """Season record as stored in DB."""
    season_id: str
    label: str
    note: str = ""
    state: SeasonState = "DRAFT"
    hard_boundary: SeasonHardBoundary
    created_at: str
    created_by: str
    updated_at: str


class SeasonCreateRequest(BaseModel):
    """Request to create a new season."""
    label: str
    note: str = ""
    hard_boundary: SeasonHardBoundary


class SeasonCreateResponse(BaseModel):
    """Response after creating a season."""
    season: SeasonRecord


class SeasonListResponse(BaseModel):
    """Response for listing seasons."""
    seasons: List[SeasonRecord] = Field(default_factory=list)


class SeasonDetailResponse(BaseModel):
    """Response for getting season details."""
    season: SeasonRecord
    job_ids: List[str] = Field(default_factory=list)


class SeasonAttachRequest(BaseModel):
    """Request to attach a job to a season."""
    job_id: str
    actor: str = "ui"  # ui/api/cli


class BoundaryMismatchItem(BaseModel):
    """Details of a single boundary mismatch."""
    field: str
    season_value: str
    job_value: str


class BoundaryMismatchErrorPayload(BaseModel):
    """Error payload for boundary mismatch (409 Conflict)."""
    error_type: Literal["SeasonBoundaryMismatch"] = "SeasonBoundaryMismatch"
    season_id: str
    job_id: str
    mismatches: List[BoundaryMismatchItem] = Field(default_factory=list)


class SeasonAttachResponse(BaseModel):
    """Response after attempting to attach a job to a season."""
    season_id: str
    job_id: str
    result: Literal["ACCEPTED", "REJECTED"]
    mismatches: List[BoundaryMismatchItem] = Field(default_factory=list)


class SeasonFreezeResponse(BaseModel):
    """Response after freezing a season."""
    season_id: str
    previous_state: SeasonState
    new_state: SeasonState
    updated_at: str


class SeasonArchiveResponse(BaseModel):
    """Response after archiving a season."""
    season_id: str
    previous_state: SeasonState
    new_state: SeasonState
    updated_at: str


# ===== P2-B/C/D: Season Analysis, Admission Decisions, Export =====

class CandidateRef(BaseModel):
    """SSOT pointer to a candidate within a job."""
    season_id: str
    job_id: str
    candidate_key: str  # either candidate_id or "rank:12"
    
    # Optional fields for easier reference
    candidate_id: Optional[str] = None
    rank: Optional[int] = None


class CandidateIdentity(BaseModel):
    """Identity of a candidate."""
    candidate_id: str
    display_name: str = ""
    rank: int = 1


class CandidateSource(BaseModel):
    """Source information for a candidate."""
    job_id: str
    batch_id: Optional[str] = None
    artifact_type: str = "winners.json"
    extracted_at: str


class SeasonCandidate(BaseModel):
    """A candidate in season analysis."""
    identity: CandidateIdentity
    strategy_id: str
    param_hash: str = ""
    research_metrics: Dict[str, float] = Field(default_factory=dict)
    source: CandidateSource
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SeasonGatekeeperSummary(BaseModel):
    """Aggregate gatekeeper statistics for a season."""
    jobs_total: int = 0
    jobs_with_candidates: int = 0
    jobs_plateau_pass: int = 0
    jobs_failed: int = 0
    valid_candidates_total: int = 0


class SeasonAnalysisItem(BaseModel):
    """A single candidate in the season leaderboard."""
    ref: CandidateRef
    metrics: Dict[str, float] = Field(default_factory=dict)  # metrics allowed only here
    params: Dict[str, object] = Field(default_factory=dict)  # parameter snapshot
    source_job_status: str = "unknown"


class SeasonAnalysisResponse(BaseModel):
    """Response for season analysis (P2-B)."""
    season_id: str
    season_state: str = ""
    total_jobs: int = 0
    valid_candidates: int = 0
    skipped_jobs: List[str] = Field(default_factory=list)
    candidates: List[SeasonCandidate] = Field(default_factory=list)
    generated_at: str = ""
    deterministic_order: str = "score desc, candidate_id asc"


class AdmissionDecisionRequest(BaseModel):
    """Request to make an admission decision (P2-C)."""
    ref: CandidateRef
    decision: AdmissionDecisionEnum
    reason: str
    actor: str = "ui"


class AdmissionDecisionRecord(BaseModel):
    """Record of an admission decision (stored in DB)."""
    season_id: str
    job_id: str
    candidate_key: str
    decision: AdmissionDecisionEnum
    reason: str
    decided_at: str
    decided_by: str
    evidence_path: str


class AdmissionDecisionListResponse(BaseModel):
    """Response listing admission decisions for a season."""
    decisions: List[AdmissionDecisionRecord] = Field(default_factory=list)


class PortfolioCandidateSetV1(BaseModel):
    """Portfolio candidate set export schema v1.0 (P2-D)."""
    schema_version: Literal["1.0"] = "1.0"
    season_id: str
    hard_boundary: SeasonHardBoundary
    created_at: str
    created_by: str
    admitted: List[Dict[str, Any]] = Field(default_factory=list)  # list of {ref, metrics_snapshot, params_snapshot}
    rejected: List[Dict[str, Any]] = Field(default_factory=list)  # optional
    hold: List[Dict[str, Any]] = Field(default_factory=list)  # optional


class SeasonAnalysisRequest(BaseModel):
    """Request for season analysis (P2-B)."""
    season_id: str
    actor: str = "ui"


class SeasonAdmissionRequest(BaseModel):
    """Request for season admission decisions (P2-C)."""
    season_id: str
    candidate_refs: List[CandidateRef] = Field(default_factory=list)
    actor: str = "ui"


class SeasonAdmissionResponse(BaseModel):
    """Response for season admission decisions (P2-C)."""
    season_id: str
    total_candidates: int = 0
    admitted_count: int = 0
    rejected_count: int = 0
    held_count: int = 0
    decisions: List[AdmissionDecision] = Field(default_factory=list)
    generated_at: str = ""


class SeasonExportCandidatesRequest(BaseModel):
    """Request to export portfolio candidate set (P2-D)."""
    season_id: str
    actor: str = "ui"


class SeasonExportCandidatesResponse(BaseModel):
    """Response after exporting portfolio candidate set (P2-D)."""
    season_id: str
    export_id: str
    candidate_count: int
    artifact_path: str
    evidence: Dict[str, Any] = Field(default_factory=dict)
    generated_at: str


class SeasonExportResponse(BaseModel):
    """Response after exporting a season (P2-D)."""
    season_id: str
    artifact_path: str
    exported_at: str
    exported_by: str