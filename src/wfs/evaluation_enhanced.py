"""
Enhanced Research=WFS evaluation module with Red-Team Scoring Guards.

Extends the base evaluation with:
1. Anti-gaming scoring guards (trade multiplier cap, minimum edge gate)
2. RobustScore + Cliff Gates (OAT neighborhood analysis)
3. Bimodality cluster detection
4. Optional Mode B pipeline integration

Maintains backward compatibility with the original 5D scoring system.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, TypedDict, Optional, Any
import math

from wfs.evaluation import (
    RawMetrics as BaseRawMetrics,
    Scores as BaseScores,
    EvaluationResult as BaseEvaluationResult,
    compute_hard_gates as base_compute_hard_gates,
    compute_scores as base_compute_scores,
    compute_total as base_compute_total,
    grade_from_total as base_grade_from_total,
    evaluate as base_evaluate,
    clamp
)

from wfs.scoring_guards import (
    ScoringGuardConfig,
    compute_trade_multiplier,
    compute_min_edge_gate,
    compute_final_score,
    compute_robust_stats,
    detect_bimodality_cluster,
    apply_scoring_guards,
    score_with_guards,
    DEFAULT_CONFIG as DEFAULT_SCORING_CONFIG
)


class EnhancedRawMetrics(BaseRawMetrics):
    """Enhanced raw metrics with additional fields for scoring guards."""
    net_profit: Optional[float] = None  # Net profit (dollars)
    max_dd: Optional[float] = None      # Maximum drawdown (positive magnitude)
    avg_profit: Optional[float] = None  # Average profit per trade
    trades_oat: Optional[int] = None    # Trades in OAT neighborhood (for robust stats)


@dataclass
class EnhancedEvaluationResult(BaseEvaluationResult):
    """Enhanced evaluation result with scoring guard outputs."""
    # Original fields from base EvaluationResult
    hard_gates_triggered: List[str]
    scores: BaseScores
    grade: str
    is_tradable: bool
    summary: str
    
    # Enhanced fields
    scoring_guard_result: Optional[Dict[str, Any]] = None
    final_score_guarded: Optional[float] = None
    edge_gate_passed: Optional[bool] = None
    cliff_gate_passed: Optional[bool] = None
    bimodality_detected: Optional[bool] = None
    robust_stats: Optional[Dict[str, Any]] = None


def evaluate_enhanced(
    raw: EnhancedRawMetrics,
    scoring_config: Optional[ScoringGuardConfig] = None,
    enable_scoring_guards: bool = True
) -> EnhancedEvaluationResult:
    """
    Complete enhanced evaluation pipeline with scoring guards.
    
    Args:
        raw: Enhanced raw metrics (must include net_profit, max_dd, avg_profit)
        scoring_config: Optional scoring guard configuration
        enable_scoring_guards: Whether to apply scoring guards
    
    Returns:
        EnhancedEvaluationResult with both 5D scores and scoring guard outputs
    """
    # Use default config if not provided
    if scoring_config is None:
        scoring_config = DEFAULT_SCORING_CONFIG
    
    # First, run the base evaluation (5D scoring + hard gates)
    base_result = base_evaluate(raw)
    
    # Initialize enhanced result with base values
    enhanced_result = EnhancedEvaluationResult(
        hard_gates_triggered=base_result.hard_gates_triggered,
        scores=base_result.scores,
        grade=base_result.grade,
        is_tradable=base_result.is_tradable,
        summary=base_result.summary
    )
    
    # Apply scoring guards if enabled and we have the required metrics
    if enable_scoring_guards and raw.get('net_profit') is not None:
        try:
            # Prepare metrics for scoring guards
            guard_metrics = {
                'net_profit': raw.get('net_profit', 0.0),
                'max_dd': raw.get('max_dd', 0.0),
                'trades': raw.get('trades', 0),
                'avg_profit': raw.get('avg_profit', 0.0),
                'trades_oat': raw.get('trades_oat')
            }
            
            # Apply scoring guards
            scoring_result = apply_scoring_guards(guard_metrics, scoring_config)
            
            # Update enhanced result
            enhanced_result.scoring_guard_result = scoring_result
            enhanced_result.final_score_guarded = scoring_result.get('final_score')
            enhanced_result.edge_gate_passed = scoring_result.get('edge_gate_passed', False)
            enhanced_result.cliff_gate_passed = scoring_result.get('cliff_gate_passed', True)
            enhanced_result.bimodality_detected = scoring_result.get('bimodality_detected', False)
            enhanced_result.robust_stats = scoring_result.get('robust_stats')
            
            # Update summary to include scoring guard info
            if enhanced_result.scoring_guard_result:
                guard_summary = []
                if enhanced_result.edge_gate_passed is not None:
                    guard_summary.append(f"EdgeGate={'PASS' if enhanced_result.edge_gate_passed else 'FAIL'}")
                if enhanced_result.final_score_guarded is not None:
                    guard_summary.append(f"FinalScore={enhanced_result.final_score_guarded:.2f}")
                if guard_summary:
                    enhanced_result.summary = f"{base_result.summary} [ScoringGuards: {', '.join(guard_summary)}]"
        
        except Exception as e:
            # Log but don't fail the evaluation
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Scoring guards failed: {e}")
            enhanced_result.summary = f"{base_result.summary} [ScoringGuards: ERROR]"
    
    return enhanced_result


def evaluate_with_mode_b(
    raw: EnhancedRawMetrics,
    scoring_config: Optional[ScoringGuardConfig] = None,
    mode_b_config: Optional[Dict[str, Any]] = None
) -> EnhancedEvaluationResult:
    """
    Evaluate with Mode B pipeline integration.
    
    This is a placeholder for future integration with the Mode B pipeline.
    Currently delegates to evaluate_enhanced.
    """
    # For now, just use enhanced evaluation
    # In future implementation, would:
    # 1. Run Mode B pipeline to get anchor-calibrated parameters
    # 2. Evaluate with those parameters
    # 3. Apply scoring guards
    
    result = evaluate_enhanced(raw, scoring_config, enable_scoring_guards=True)
    
    # Add Mode B placeholder info
    if mode_b_config:
        result.summary = f"{result.summary} [ModeB: placeholder]"
    
    return result


def create_test_enhanced_raw_metrics(
    rf: float = 2.0,
    wfe: float = 0.7,
    ecr: float = 2.0,
    trades: int = 100,
    pass_rate: float = 0.8,
    ulcer_index: float = 5.0,
    max_underwater_days: int = 10,
    net_profit: float = 5000.0,
    max_dd: float = 1000.0,
    avg_profit: float = 50.0,
    trades_oat: Optional[int] = None
) -> EnhancedRawMetrics:
    """Create test enhanced raw metrics."""
    return {
        'rf': rf,
        'wfe': wfe,
        'ecr': ecr,
        'trades': trades,
        'pass_rate': pass_rate,
        'ulcer_index': ulcer_index,
        'max_underwater_days': max_underwater_days,
        'net_profit': net_profit,
        'max_dd': max_dd,
        'avg_profit': avg_profit,
        'trades_oat': trades_oat
    }


if __name__ == "__main__":
    # Quick test
    test_raw = create_test_enhanced_raw_metrics()
    result = evaluate_enhanced(test_raw)
    
    print("Enhanced evaluation test:")
    print(f"  Hard gates: {result.hard_gates_triggered}")
    print(f"  5D Scores: {result.scores}")
    print(f"  Grade: {result.grade}")
    print(f"  Tradable: {result.is_tradable}")
    print(f"  Summary: {result.summary}")
    
    if result.scoring_guard_result:
        print(f"  Scoring guard final score: {result.final_score_guarded:.2f}")
        print(f"  Edge gate passed: {result.edge_gate_passed}")
        print(f"  Cliff gate passed: {result.cliff_gate_passed}")
        print(f"  Bimodality detected: {result.bimodality_detected}")