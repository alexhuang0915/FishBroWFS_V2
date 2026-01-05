"""
Portfolio governance data models (Pydantic v2).

All models are pure, serializable, and stable. No side effects at import time.
"""
from enum import Enum
from typing import Optional, Any, Dict, List
from pydantic import BaseModel, Field, ConfigDict, field_validator


# ========== Enums ==========

class StrategyState(str, Enum):
    """Lifecycle states of a strategy."""
    INCUBATION = "INCUBATION"
    CANDIDATE = "CANDIDATE"
    PAPER_TRADING = "PAPER_TRADING"
    LIVE = "LIVE"
    PROBATION = "PROBATION"
    FREEZE = "FREEZE"
    RETIRED = "RETIRED"


class ReasonCode(str, Enum):
    """Reason codes for governance events."""
    # Admission gates
    INTEGRITY_GATE_FAIL = "INTEGRITY_GATE_FAIL"
    DIVERSITY_GATE_FAIL = "DIVERSITY_GATE_FAIL"
    CORR_GATE_DENY = "CORR_GATE_DENY"
    REPLACEMENT_APPROVED = "REPLACEMENT_APPROVED"
    PROMOTE_TO_PAPER = "PROMOTE_TO_PAPER"
    PROMOTE_TO_LIVE = "PROMOTE_TO_LIVE"
    DEMOTE_TO_PROBATION = "DEMOTE_TO_PROBATION"
    RETIRE_KILL_SWITCH = "RETIRE_KILL_SWITCH"
    RETIRE_STRUCTURAL_FAILURE = "RETIRE_STRUCTURAL_FAILURE"
    PORTFOLIO_CIRCUIT_BREAKER = "PORTFOLIO_CIRCUIT_BREAKER"
    MANUAL_EMERGENCY_HALT = "MANUAL_EMERGENCY_HALT"


# ========== Immutable Identity ==========

class StrategyIdentity(BaseModel):
    """Immutable identity of a strategy."""
    strategy_id: str = Field(..., description="Unique identifier (e.g., 'S2_001')")
    version_hash: str = Field(..., description="Hash of the strategy source + parameters")
    universe: Dict[str, str] = Field(
        ...,
        description="Minimal universe description: {symbol, timeframe, session, venue}"
    )
    data_fingerprint: str = Field(
        ...,
        description="Hash of the training/validation dataset"
    )
    cost_model_id: str = Field(..., description="Identifier of the cost model used")
    tags: List[str] = Field(
        default_factory=list,
        description="Bucket tags (e.g., 'Trend', 'MeanRev') and style tags"
    )

    model_config = ConfigDict(frozen=True)

    def identity_key(self) -> str:
        """Return the immutable key used throughout governance."""
        return f"{self.strategy_id}:{self.version_hash}:{self.data_fingerprint}"


# ========== Governance Parameters ==========

class GovernanceParams(BaseModel):
    """Tunable parameters for portfolio governance."""
    # Correlation gate
    corr_rolling_days: int = Field(
        default=30,
        description="Window (days) for rolling correlation calculation"
    )
    corr_min_samples: int = Field(
        default=20,
        description="Minimum samples required to compute correlation"
    )
    corr_portfolio_hard_limit: float = Field(
        default=0.7,
        description="Maximum allowed correlation vs. portfolio returns"
    )
    corr_member_hard_limit: float = Field(
        default=0.8,
        description="Maximum allowed correlation vs. any existing member"
    )
    max_pairwise_correlation: float = Field(
        default=0.60,
        description="Maximum allowed pairwise correlation between candidate strategies (0 < value < 1)"
    )
    portfolio_risk_budget_max: float = Field(
        default=1.00,
        description="Maximum total risk budget for portfolio (0 < value ≤ 1)"
    )

    # Diversity gate
    bucket_slots: Dict[str, int] = Field(
        default_factory=lambda: {
            "Trend": 2,
            "MeanRev": 2,
            "Carry/Income": 1,
            "LongVol": 1,
            "Other": 1,
        },
        description="Maximum number of strategies per style bucket"
    )

    # Risk allocation
    allowed_risk_models: List[str] = Field(
        default_factory=lambda: ["vol_target", "risk_parity"],
        description="List of permitted risk models"
    )
    risk_model: str = Field(
        default="vol_target",
        description="Currently active risk model"
    )
    portfolio_vol_target: float = Field(
        default=0.10,
        description="Target annualized portfolio volatility"
    )
    vol_floor: float = Field(
        default=0.02,
        description="Minimum volatility used in weight calculation"
    )
    w_max: float = Field(
        default=0.35,
        description="Maximum weight per strategy (0 < w_max ≤ 1)"
    )
    w_min: float = Field(
        default=0.0,
        description="Minimum weight per strategy (0 ≤ w_min < w_max)"
    )

    # Kill‑switch thresholds
    dd_absolute_cap: float = Field(
        default=0.35,
        description="Absolute drawdown cap (0 < cap < 1)"
    )
    dd_k_multiplier: float = Field(
        default=1.0,
        description="Multiplier on reference drawdown"
    )
    portfolio_dd_cap: float = Field(
        default=0.20,
        description="Portfolio‑wide drawdown cap"
    )
    exposure_reduction_on_breaker: float = Field(
        default=0.5,
        description="Fraction of exposure retained during circuit breaker"
    )

    @field_validator("corr_portfolio_hard_limit", "corr_member_hard_limit", "max_pairwise_correlation")
    @classmethod
    def validate_corr_limits(cls, v: float) -> float:
        if not 0 < v < 1:
            raise ValueError("Correlation limits must be in (0, 1)")
        return v

    @field_validator("portfolio_risk_budget_max")
    @classmethod
    def validate_risk_budget_max(cls, v: float) -> float:
        if not 0 < v <= 1:
            raise ValueError("portfolio_risk_budget_max must be in (0, 1]")
        return v

    @field_validator("w_max")
    @classmethod
    def validate_w_max(cls, v: float) -> float:
        if not 0 < v <= 1:
            raise ValueError("w_max must be in (0, 1]")
        return v

    @field_validator("w_min")
    @classmethod
    def validate_w_min(cls, v: float, info) -> float:
        w_max = info.data.get("w_max", 0.35)
        if not 0 <= v < w_max:
            raise ValueError(f"w_min must be in [0, w_max={w_max})")
        return v

    @field_validator("risk_model")
    @classmethod
    def validate_risk_model(cls, v: str, info) -> str:
        allowed = info.data.get("allowed_risk_models", ["vol_target", "risk_parity"])
        if v not in allowed:
            raise ValueError(f"risk_model '{v}' not in allowed_risk_models {allowed}")
        return v


# ========== Admission Artifacts ==========

class AdmissionReport(BaseModel):
    """Artifact recording the outcome of admission gates."""
    candidate: StrategyIdentity
    timestamp_utc: str = Field(..., description="ISO‑8601 UTC timestamp")
    gates: Dict[str, Dict[str, Any]] = Field(
        ...,
        description="Detailed gate results: integrity, diversity, correlation"
    )
    approved: bool = Field(..., description="Overall admission decision")
    replacement_mode: bool = Field(default=False, description="Whether replacement mode was active")
    replacement_target: Optional[str] = Field(
        default=None,
        description="Identity key of the strategy being replaced"
    )
    notes: str = Field(default="", description="Human‑readable notes")


class ReplacementReport(BaseModel):
    """Artifact recording a replacement decision."""
    new_strategy_key: str = Field(..., description="Identity key of the new strategy")
    old_strategy_key: str = Field(..., description="Identity key of the strategy being replaced")
    dominance_proof: Dict[str, float] = Field(
        ...,
        description="Metrics proving dominance: expected_score_new, expected_score_old, risk_adj_new, risk_adj_old"
    )
    approved: bool = Field(..., description="Whether replacement was approved")
    timestamp_utc: str = Field(..., description="ISO‑8601 UTC timestamp")


# ========== Kill‑Switch Artifacts ==========

class KillSwitchReport(BaseModel):
    """Artifact recording a kill‑switch trigger."""
    strategy_key: str = Field(..., description="Identity key of the strategy")
    dd_live: float = Field(..., description="Live drawdown observed")
    dd_reference: float = Field(..., description="Reference drawdown (e.g., backtest)")
    k_multiplier: float = Field(..., description="dd_k_multiplier at time of trigger")
    dd_absolute_cap: float = Field(..., description="dd_absolute_cap at time of trigger")
    triggered: bool = Field(..., description="Whether kill‑switch was triggered")
    reason: str = Field(..., description="Human‑readable reason")
    timestamp_utc: str = Field(..., description="ISO‑8601 UTC timestamp")


# ========== Governance Log Event ==========

class GovernanceLogEvent(BaseModel):
    """Append‑only log entry for all governance actions."""
    timestamp_utc: str = Field(..., description="ISO‑8601 UTC timestamp")
    actor: str = Field(..., description="Who performed the action: 'worker', 'system', 'manual'")
    strategy_key: Optional[str] = Field(
        default=None,
        description="Identity key of the affected strategy (None for portfolio‑level events)"
    )
    from_state: Optional[StrategyState] = Field(
        default=None,
        description="Previous state of the strategy"
    )
    to_state: Optional[StrategyState] = Field(
        default=None,
        description="New state of the strategy"
    )
    reason_code: ReasonCode = Field(..., description="Coded reason for the transition")
    attached_artifacts: List[str] = Field(
        default_factory=list,
        description="Paths to related artifact files (relative to governance root)"
    )
    data_fingerprint: Optional[str] = Field(
        default=None,
        description="Data fingerprint at time of event (if applicable)"
    )
    extra: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional unstructured data"
    )


# ========== Return Series (for admission) ==========

class ReturnSeries(BaseModel):
    """Minimal representation of a return series."""
    name: str = Field(..., description="Identifier of the series")
    returns: List[float] = Field(
        ...,
        description="Daily (or bar) returns; must be consistent across series"
    )
    timestamps_utc: Optional[List[str]] = Field(
        default=None,
        description="Optional ISO‑8601 timestamps for each return"
    )