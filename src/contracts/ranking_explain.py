"""
Ranking Explain Contracts for DP6 Phase I & II.

Defines Pydantic v2 models for explainable ranking reports.
Phase I is INFO-only, context-aware, and plateau-artifact-gated.
Phase II adds WARN/ERROR severity for governance/risk layer.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, field_validator

# Import config for Phase II thresholds
from .ranking_explain_config import RankingExplainConfig, DEFAULT_RANKING_EXPLAIN_CONFIG


class RankingExplainContext(str, Enum):
    """Context for ranking explanations."""
    CANDIDATE = "CANDIDATE"
    FINAL_SELECTION = "FINAL_SELECTION"


class RankingExplainSeverity(str, Enum):
    """Severity levels for ranking explanations.
    
    Phase I supports INFO only. Phase II adds WARN/ERROR for governance/risk.
    """
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"


class RankingExplainReasonCode(str, Enum):
    """Standardized reason codes for ranking explanations."""
    
    # Score formula and threshold reasons (Phase I)
    SCORE_FORMULA = "SCORE_FORMULA"
    THRESHOLD_TMAX_APPLIED = "THRESHOLD_TMAX_APPLIED"
    THRESHOLD_MIN_AVG_PROFIT_APPLIED = "THRESHOLD_MIN_AVG_PROFIT_APPLIED"
    METRIC_SUMMARY = "METRIC_SUMMARY"
    
    # Plateau artifact reasons (Phase I)
    PLATEAU_CONFIRMED = "PLATEAU_CONFIRMED"
    DATA_MISSING_PLATEAU_ARTIFACT = "DATA_MISSING_PLATEAU_ARTIFACT"
    
    # Concentration reasons (Phase II)
    CONCENTRATION_HIGH = "CONCENTRATION_HIGH"
    CONCENTRATION_MODERATE = "CONCENTRATION_MODERATE"
    CONCENTRATION_OK = "CONCENTRATION_OK"
    
    # Plateau quality reasons (Phase II)
    PLATEAU_STRONG_STABILITY = "PLATEAU_STRONG_STABILITY"
    PLATEAU_WEAK_STABILITY = "PLATEAU_WEAK_STABILITY"
    PLATEAU_MISSING_ARTIFACT = "PLATEAU_MISSING_ARTIFACT"
    
    # Guard breach / robustness reasons (Phase II)
    AVG_PROFIT_BELOW_MIN = "AVG_PROFIT_BELOW_MIN"
    MDD_INVALID_OR_ZERO = "MDD_INVALID_OR_ZERO"
    TRADES_TOO_LOW_FOR_RANKING = "TRADES_TOO_LOW_FOR_RANKING"
    METRICS_MISSING_REQUIRED_FIELDS = "METRICS_MISSING_REQUIRED_FIELDS"


class RankingExplainReasonCard(BaseModel):
    """A single explainable reason card for ranking."""
    
    code: RankingExplainReasonCode = Field(
        ...,
        description="Standardized reason code"
    )
    
    severity: RankingExplainSeverity = Field(
        default=RankingExplainSeverity.INFO,
        description="Severity level (INFO/WARN/ERROR)"
    )
    
    title: str = Field(
        ...,
        description="Human-readable title (context-aware)"
    )
    
    summary: str = Field(
        ...,
        description="Detailed explanation (context-aware)"
    )
    
    actions: List[str] = Field(
        default_factory=list,
        description="Research-oriented action verbs (inspect, validate, review)"
    )
    
    details: Dict[str, Any] = Field(
        default_factory=dict,
        description="SSOT values only (t_max, alpha, min_avg_profit, net_profit, max_dd, trades, final_score)"
    )
    
    @field_validator("severity")
    @classmethod
    def validate_severity_allowed(cls, v: RankingExplainSeverity) -> RankingExplainSeverity:
        """Validate severity is one of allowed values."""
        # All enum values are allowed (INFO, WARN, ERROR)
        return v
    
    @field_validator("actions")
    @classmethod
    def validate_actions(cls, v: List[str]) -> List[str]:
        """Ensure actions use research-oriented verbs only."""
        allowed_prefixes = ("inspect", "validate", "review")
        for action in v:
            action_lower = action.strip().lower()
            if not any(action_lower.startswith(prefix) for prefix in allowed_prefixes):
                raise ValueError(
                    f"Action must start with {allowed_prefixes}: {action}"
                )
        return v


class RankingExplainReport(BaseModel):
    """Complete ranking explain report for a job/run."""
    
    schema_version: Literal["1"] = Field(
        default="1",
        description="Schema version for forward compatibility"
    )
    
    context: RankingExplainContext = Field(
        ...,
        description="Context (CANDIDATE or FINAL_SELECTION)"
    )
    
    job_id: str = Field(
        ...,
        description="Job identifier"
    )
    
    run_id: Optional[str] = Field(
        default=None,
        description="Run identifier (if available in artifacts)"
    )
    
    generated_at: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat() + "Z",
        description="ISO 8601 timestamp of report generation"
    )
    
    scoring: Dict[str, Any] = Field(
        default_factory=dict,
        description="Scoring configuration and formula details"
    )
    
    reasons: List[RankingExplainReasonCard] = Field(
        default_factory=list,
        description="Ordered list of reason cards"
    )
    
    @field_validator("scoring")
    @classmethod
    def validate_scoring_contains_formula(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        """Ensure scoring dict contains formula information."""
        if "formula" not in v:
            raise ValueError("Scoring dict must contain 'formula' field")
        return v
    
    @field_validator("reasons")
    @classmethod
    def validate_reasons_ordering(cls, v: List[RankingExplainReasonCard]) -> List[RankingExplainReasonCard]:
        """Ensure deterministic ordering of reasons."""
        # Sort by code for deterministic output
        return sorted(v, key=lambda r: r.code.value)


# Helper functions for context-aware wording
def get_context_wording(
    context: RankingExplainContext,
    code: RankingExplainReasonCode,
    metric_values: Optional[Dict[str, Any]] = None
) -> tuple[str, str]:
    """Get context-aware title and summary for a reason code.
    
    Args:
        context: CANDIDATE or FINAL_SELECTION
        code: Reason code
        metric_values: Optional metric values for templating
        
    Returns:
        Tuple of (title, summary)
    """
    metric_values = metric_values or {}
    
    # Base templates
    templates = {
        # Phase I templates
        RankingExplainReasonCode.SCORE_FORMULA: {
            "CANDIDATE": (
                "Score formula applied (候選)",
                "Final score computed using SSOT formula: {formula}"
            ),
            "FINAL_SELECTION": (
                "Score formula applied (勝出)",
                "Final score computed using SSOT formula: {formula}"
            )
        },
        RankingExplainReasonCode.THRESHOLD_TMAX_APPLIED: {
            "CANDIDATE": (
                "Trade count capped at t_max (候選)",
                "Trade count capped at t_max={t_max} as per scoring guard configuration"
            ),
            "FINAL_SELECTION": (
                "Trade count capped at t_max (勝出)",
                "Trade count capped at t_max={t_max} as per scoring guard configuration"
            )
        },
        RankingExplainReasonCode.THRESHOLD_MIN_AVG_PROFIT_APPLIED: {
            "CANDIDATE": (
                "Minimum average profit threshold (候選)",
                "Average profit ${avg_profit:.2f} meets minimum ${min_avg_profit:.2f} requirement"
            ),
            "FINAL_SELECTION": (
                "Minimum average profit threshold (勝出)",
                "Average profit ${avg_profit:.2f} meets minimum ${min_avg_profit:.2f} requirement"
            )
        },
        RankingExplainReasonCode.METRIC_SUMMARY: {
            "CANDIDATE": (
                "Performance metrics summary (候選)",
                "Net profit ${net_profit:.2f}, max drawdown ${max_dd:.2f}, trades {trades}"
            ),
            "FINAL_SELECTION": (
                "Performance metrics summary (勝出)",
                "Net profit ${net_profit:.2f}, max drawdown ${max_dd:.2f}, trades {trades}"
            )
        },
        RankingExplainReasonCode.PLATEAU_CONFIRMED: {
            "CANDIDATE": (
                "Parameter plateau stability confirmed (候選)",
                "Parameter neighborhood shows consistent performance (stability score: {stability_score:.2f})"
            ),
            "FINAL_SELECTION": (
                "Parameter plateau stability confirmed (勝出)",
                "Parameter neighborhood shows consistent performance (stability score: {stability_score:.2f})"
            )
        },
        RankingExplainReasonCode.DATA_MISSING_PLATEAU_ARTIFACT: {
            "CANDIDATE": (
                "Plateau artifact not available (候選)",
                "Plateau stability analysis requires plateau_report.json artifact"
            ),
            "FINAL_SELECTION": (
                "Plateau artifact not available (勝出)",
                "Plateau stability analysis requires plateau_report.json artifact"
            )
        },
        # Phase II: Concentration reasons
        RankingExplainReasonCode.CONCENTRATION_HIGH: {
            "CANDIDATE": (
                "High concentration risk (候選)",
                "Top candidate dominates score distribution (top1_share={top1_share:.1%} ≥ {threshold:.0%})"
            ),
            "FINAL_SELECTION": (
                "High concentration risk (勝出)",
                "Top candidate dominates score distribution (top1_share={top1_share:.1%} ≥ {threshold:.0%})"
            )
        },
        RankingExplainReasonCode.CONCENTRATION_MODERATE: {
            "CANDIDATE": (
                "Moderate concentration risk (候選)",
                "Top candidate has significant score share (top1_share={top1_share:.1%} ≥ {threshold:.0%})"
            ),
            "FINAL_SELECTION": (
                "Moderate concentration risk (勝出)",
                "Top candidate has significant score share (top1_share={top1_share:.1%} ≥ {threshold:.0%})"
            )
        },
        RankingExplainReasonCode.CONCENTRATION_OK: {
            "CANDIDATE": (
                "Concentration within acceptable range (候選)",
                "Score distribution shows healthy diversity (top1_share={top1_share:.1%})"
            ),
            "FINAL_SELECTION": (
                "Concentration within acceptable range (勝出)",
                "Score distribution shows healthy diversity (top1_share={top1_share:.1%})"
            )
        },
        # Phase II: Plateau quality reasons
        RankingExplainReasonCode.PLATEAU_STRONG_STABILITY: {
            "CANDIDATE": (
                "Plateau shows strong stability (候選)",
                "Parameter neighborhood stability score {stability_score:.2f} ≥ {threshold:.2f}"
            ),
            "FINAL_SELECTION": (
                "Plateau shows strong stability (勝出)",
                "Parameter neighborhood stability score {stability_score:.2f} ≥ {threshold:.2f}"
            )
        },
        RankingExplainReasonCode.PLATEAU_WEAK_STABILITY: {
            "CANDIDATE": (
                "Plateau shows weak stability (候選)",
                "Parameter neighborhood stability score {stability_score:.2f} < {threshold:.2f}"
            ),
            "FINAL_SELECTION": (
                "Plateau shows weak stability (勝出)",
                "Parameter neighborhood stability score {stability_score:.2f} < {threshold:.2f}"
            )
        },
        RankingExplainReasonCode.PLATEAU_MISSING_ARTIFACT: {
            "CANDIDATE": (
                "Plateau artifact missing (候選)",
                "Plateau stability assessment unavailable (plateau_report.json not found)"
            ),
            "FINAL_SELECTION": (
                "Plateau artifact missing (勝出)",
                "Plateau stability assessment unavailable (plateau_report.json not found)"
            )
        },
        # Phase II: Guard breach / robustness reasons
        RankingExplainReasonCode.AVG_PROFIT_BELOW_MIN: {
            "CANDIDATE": (
                "Average profit below minimum threshold (候選)",
                "Average profit ${avg_profit:.2f} < ${threshold:.2f} per trade"
            ),
            "FINAL_SELECTION": (
                "Average profit below minimum threshold (勝出)",
                "Average profit ${avg_profit:.2f} < ${threshold:.2f} per trade"
            )
        },
        RankingExplainReasonCode.MDD_INVALID_OR_ZERO: {
            "CANDIDATE": (
                "Maximum drawdown invalid or near zero (候選)",
                "MDD value {mdd:.6f} ≤ {threshold:.6f}, may cause division illusions"
            ),
            "FINAL_SELECTION": (
                "Maximum drawdown invalid or near zero (勝出)",
                "MDD value {mdd:.6f} ≤ {threshold:.6f}, may cause division illusions"
            )
        },
        RankingExplainReasonCode.TRADES_TOO_LOW_FOR_RANKING: {
            "CANDIDATE": (
                "Trade count too low for reliable ranking (候選)",
                "Only {trades} trades < minimum {threshold} for statistical significance"
            ),
            "FINAL_SELECTION": (
                "Trade count too low for reliable ranking (勝出)",
                "Only {trades} trades < minimum {threshold} for statistical significance"
            )
        },
        RankingExplainReasonCode.METRICS_MISSING_REQUIRED_FIELDS: {
            "CANDIDATE": (
                "Required metrics fields missing (候選)",
                "Missing required fields: {missing_fields}"
            ),
            "FINAL_SELECTION": (
                "Required metrics fields missing (勝出)",
                "Missing required fields: {missing_fields}"
            )
        }
    }
    
    if code not in templates:
        # Fallback template
        title = f"{code.value.replace('_', ' ').title()} ({'候選' if context == RankingExplainContext.CANDIDATE else '勝出'})"
        summary = f"Reason: {code.value}"
        return title, summary
    
    template = templates[code][context.value]
    title, summary = template
    
    # Apply templating if metric_values provided
    try:
        summary = summary.format(**metric_values)
    except KeyError:
        # If formatting fails, return unformatted summary
        pass
    
    return title, summary


def get_research_actions(code: RankingExplainReasonCode) -> List[str]:
    """Get research-oriented actions for a reason code.
    
    Args:
        code: Reason code
        
    Returns:
        List of action strings starting with research verbs
    """
    actions_map = {
        # Phase I actions
        RankingExplainReasonCode.SCORE_FORMULA: [
            "inspect scoring breakdown details",
            "validate formula parameters"
        ],
        RankingExplainReasonCode.THRESHOLD_TMAX_APPLIED: [
            "review trade count distribution",
            "validate t_max configuration"
        ],
        RankingExplainReasonCode.THRESHOLD_MIN_AVG_PROFIT_APPLIED: [
            "inspect profit per trade statistics",
            "validate minimum profit threshold"
        ],
        RankingExplainReasonCode.METRIC_SUMMARY: [
            "review performance metrics",
            "inspect equity curve details"
        ],
        RankingExplainReasonCode.PLATEAU_CONFIRMED: [
            "inspect plateau report",
            "validate parameter neighborhood stability"
        ],
        RankingExplainReasonCode.DATA_MISSING_PLATEAU_ARTIFACT: [
            "review plateau artifact availability",
            "inspect job artifact directory"
        ],
        # Phase II: Concentration actions
        RankingExplainReasonCode.CONCENTRATION_HIGH: [
            "inspect score distribution across candidates",
            "validate concentration risk thresholds"
        ],
        RankingExplainReasonCode.CONCENTRATION_MODERATE: [
            "review score diversity metrics",
            "inspect runner-up performance"
        ],
        RankingExplainReasonCode.CONCENTRATION_OK: [
            "validate healthy score distribution",
            "review runner-up candidates"
        ],
        # Phase II: Plateau quality actions
        RankingExplainReasonCode.PLATEAU_STRONG_STABILITY: [
            "inspect plateau stability metrics",
            "validate parameter neighborhood consistency"
        ],
        RankingExplainReasonCode.PLATEAU_WEAK_STABILITY: [
            "review plateau stability analysis",
            "inspect parameter sensitivity"
        ],
        RankingExplainReasonCode.PLATEAU_MISSING_ARTIFACT: [
            "review plateau artifact generation",
            "inspect job artifact completeness"
        ],
        # Phase II: Guard breach / robustness actions
        RankingExplainReasonCode.AVG_PROFIT_BELOW_MIN: [
            "inspect profit per trade distribution",
            "validate minimum profit guard configuration"
        ],
        RankingExplainReasonCode.MDD_INVALID_OR_ZERO: [
            "review drawdown calculation",
            "validate MDD guard thresholds"
        ],
        RankingExplainReasonCode.TRADES_TOO_LOW_FOR_RANKING: [
            "inspect trade count distribution",
            "validate statistical significance thresholds"
        ],
        RankingExplainReasonCode.METRICS_MISSING_REQUIRED_FIELDS: [
            "review metrics artifact completeness",
            "inspect required fields validation"
        ]
    }
    
    return actions_map.get(code, ["review relevant artifacts"])


__all__ = [
    "RankingExplainContext",
    "RankingExplainSeverity",
    "RankingExplainReasonCode",
    "RankingExplainReasonCard",
    "RankingExplainReport",
    "get_context_wording",
    "get_research_actions",
]