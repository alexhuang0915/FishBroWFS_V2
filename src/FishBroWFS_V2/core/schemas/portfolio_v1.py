"""Portfolio engine schemas V1."""

from pydantic import BaseModel, Field
from typing import Literal, Dict, List, Optional
from datetime import datetime, timezone


class PortfolioPolicyV1(BaseModel):
    """Portfolio policy defining allocation limits and behavior."""
    version: Literal["PORTFOLIO_POLICY_V1"] = "PORTFOLIO_POLICY_V1"

    base_currency: str  # "TWD"
    instruments_config_sha256: str

    # account hard caps
    max_slots_total: int  # e.g. 4
    max_margin_ratio: float  # e.g. 0.35 (margin_used/equity)
    max_notional_ratio: Optional[float] = None  # optional v1

    # per-instrument cap (optional v1)
    max_slots_by_instrument: Dict[str, int] = Field(default_factory=dict)  # {"CME.MNQ":4, "TWF.MXF":2}

    # deterministic tie-breaker inputs
    strategy_priority: Dict[str, int]  # {strategy_id: priority_int}
    signal_strength_field: str  # e.g. "edge_score" or "signal_score"

    # behavior flags
    allow_force_kill: bool = False  # MUST default False
    allow_queue: bool = False  # v1: reject only


class PortfolioSpecV1(BaseModel):
    """Portfolio specification defining input sources (frozen only)."""
    version: Literal["PORTFOLIO_SPEC_V1"] = "PORTFOLIO_SPEC_V1"
    
    # Input seasons/artifacts sources
    seasons: List[str]  # e.g. ["2026Q1"]
    strategy_ids: List[str]  # e.g. ["S1", "S2"]
    instrument_ids: List[str]  # e.g. ["CME.MNQ", "TWF.MXF"]
    
    # Time range (optional)
    start_date: Optional[str] = None  # ISO format
    end_date: Optional[str] = None  # ISO format
    
    # Reference to policy
    policy_sha256: str  # SHA256 of canonicalized PortfolioPolicyV1 JSON
    
    # Canonicalization metadata
    spec_sha256: str  # SHA256 of this spec (computed after canonicalization)


class OpenPositionV1(BaseModel):
    """Open position in the portfolio."""
    strategy_id: str
    instrument_id: str  # MNQ / MXF
    slots: int = 1  # v1 fixed
    margin_base: float  # TWD
    notional_base: float  # TWD
    entry_bar_index: int
    entry_bar_ts: datetime


class SignalCandidateV1(BaseModel):
    """Candidate signal for admission."""
    strategy_id: str
    instrument_id: str  # MNQ / MXF
    bar_ts: datetime
    bar_index: int
    signal_strength: float  # higher = stronger signal
    candidate_score: float = 0.0  # deterministic score for sorting (higher = better)
    required_margin_base: float  # TWD
    required_slot: int = 1  # v1 fixed
    # Optional: additional metadata
    signal_series_sha256: Optional[str] = None  # for audit


class AdmissionDecisionV1(BaseModel):
    """Admission decision for a candidate signal."""
    version: Literal["ADMISSION_DECISION_V1"] = "ADMISSION_DECISION_V1"
    
    # Candidate identification
    strategy_id: str
    instrument_id: str
    bar_ts: datetime
    bar_index: int
    
    # Candidate metrics
    signal_strength: float
    candidate_score: float
    signal_series_sha256: Optional[str] = None  # for audit
    
    # Decision
    accepted: bool
    reason: Literal[
        "ACCEPT",
        "REJECT_FULL",
        "REJECT_MARGIN",
        "REJECT_POLICY",
        "REJECT_UNKNOWN"
    ]
    
    # Deterministic tie-breaking info
    sort_key_used: str  # e.g., "priority=-10,signal_strength=0.85,strategy_id=S1"
    
    # Portfolio state after this decision
    slots_after: int
    margin_after_base: float  # TWD
    
    # Timestamp of decision
    decision_ts: datetime = Field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))


class PortfolioStateV1(BaseModel):
    """Portfolio state at a given bar."""
    bar_ts: datetime
    bar_index: int
    equity_base: float  # TWD
    slots_used: int
    margin_used_base: float  # TWD
    notional_used_base: float  # TWD
    open_positions: List[OpenPositionV1] = Field(default_factory=list)
    reject_count: int = 0  # cumulative rejects up to this bar


class PortfolioSummaryV1(BaseModel):
    """Summary of portfolio admission results."""
    total_candidates: int
    accepted_count: int
    rejected_count: int
    reject_reasons: Dict[str, int]  # reason -> count
    final_slots_used: int
    final_margin_used_base: float
    final_margin_ratio: float  # margin_used / equity
    policy_sha256: str
    spec_sha256: str