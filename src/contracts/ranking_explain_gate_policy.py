"""
Ranking Explain Gate Policy for DP6 Phase III.

Defines mapping from ranking explain reason codes to gate impacts
for integration with Gate Summary.

Gate Impact:
- NONE: No gate impact (INFO only, no risk)
- WARN_ONLY: Gate WARN (risk advisory, can proceed)
- BLOCK: Gate REJECT/FAIL (governance redline, strongly not recommended)

Mapping follows Phase III default mapping exactly as specified.
"""

from enum import Enum
from typing import Dict

from .ranking_explain import RankingExplainReasonCode


class GateImpact(str, Enum):
    """Gate impact classification for ranking explain reasons."""
    NONE = "NONE"
    WARN_ONLY = "WARN_ONLY"
    BLOCK = "BLOCK"


# Default mapping (MUST match exactly as specified in Phase III requirements)
DEFAULT_RANKING_EXPLAIN_GATE_MAP: Dict[RankingExplainReasonCode, GateImpact] = {
    # BLOCK (FAIL) - governance redline advisory
    RankingExplainReasonCode.CONCENTRATION_HIGH: GateImpact.BLOCK,
    RankingExplainReasonCode.MDD_INVALID_OR_ZERO: GateImpact.BLOCK,
    RankingExplainReasonCode.METRICS_MISSING_REQUIRED_FIELDS: GateImpact.BLOCK,
    
    # WARN_ONLY (WARN) - risk advisory, can proceed but review recommended
    RankingExplainReasonCode.CONCENTRATION_MODERATE: GateImpact.WARN_ONLY,
    RankingExplainReasonCode.PLATEAU_WEAK_STABILITY: GateImpact.WARN_ONLY,
    RankingExplainReasonCode.PLATEAU_MISSING_ARTIFACT: GateImpact.WARN_ONLY,
    RankingExplainReasonCode.TRADES_TOO_LOW_FOR_RANKING: GateImpact.WARN_ONLY,
    RankingExplainReasonCode.AVG_PROFIT_BELOW_MIN: GateImpact.WARN_ONLY,
    
    # Note: All other codes default to NONE (including INFO-only Phase I codes)
}


def ranking_explain_gate_impact(code: RankingExplainReasonCode) -> GateImpact:
    """Get gate impact for a ranking explain reason code.
    
    Args:
        code: Ranking explain reason code
        
    Returns:
        GateImpact (NONE, WARN_ONLY, or BLOCK)
        
    Rules:
        - Codes in DEFAULT_RANKING_EXPLAIN_GATE_MAP return mapped impact
        - Unknown codes return GateImpact.NONE
        - Phase I INFO-only codes return GateImpact.NONE
    """
    return DEFAULT_RANKING_EXPLAIN_GATE_MAP.get(code, GateImpact.NONE)


def get_gate_status_from_impact(impact: GateImpact) -> str:
    """Convert GateImpact to gate status string.
    
    Args:
        impact: Gate impact classification
        
    Returns:
        Gate status string: "PASS", "WARN", or "FAIL"
        
    Mapping:
        - BLOCK → "FAIL"
        - WARN_ONLY → "WARN"
        - NONE → "PASS"
    """
    if impact == GateImpact.BLOCK:
        return "FAIL"
    elif impact == GateImpact.WARN_ONLY:
        return "WARN"
    else:  # NONE
        return "PASS"


def get_gate_impact_message(code: RankingExplainReasonCode, severity: str) -> str:
    """Get short message for gate item based on code and severity.
    
    Args:
        code: Ranking explain reason code
        severity: Severity string (INFO, WARN, ERROR)
        
    Returns:
        Short message for gate item display
    """
    # Base messages for mapped codes
    message_map = {
        RankingExplainReasonCode.CONCENTRATION_HIGH: "High concentration risk (top1_share ≥ 50%)",
        RankingExplainReasonCode.CONCENTRATION_MODERATE: "Moderate concentration risk (top1_share ≥ 35%)",
        RankingExplainReasonCode.MDD_INVALID_OR_ZERO: "MDD invalid or near zero",
        RankingExplainReasonCode.METRICS_MISSING_REQUIRED_FIELDS: "Required metrics fields missing",
        RankingExplainReasonCode.PLATEAU_WEAK_STABILITY: "Plateau stability weak (< 0.60)",
        RankingExplainReasonCode.PLATEAU_MISSING_ARTIFACT: "Plateau artifact missing",
        RankingExplainReasonCode.TRADES_TOO_LOW_FOR_RANKING: "Trade count too low (< 10)",
        RankingExplainReasonCode.AVG_PROFIT_BELOW_MIN: "Average profit below minimum threshold",
    }
    
    if code in message_map:
        return message_map[code]
    
    # Fallback for unmapped codes
    return f"{code.value.replace('_', ' ').title()} ({severity})"


__all__ = [
    "GateImpact",
    "DEFAULT_RANKING_EXPLAIN_GATE_MAP",
    "ranking_explain_gate_impact",
    "get_gate_status_from_impact",
    "get_gate_impact_message",
]