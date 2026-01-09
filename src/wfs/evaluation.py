"""
Research=WFS evaluation module (5D + hard gates) — FIXED FORMULAS.

Provides these function signatures exactly:
- compute_hard_gates(raw) -> list[str]
- compute_scores(raw) -> dict[str, float]
- compute_total(scores) -> float
- grade_from_total(total) -> str
- evaluate(raw) -> EvaluationResult

Hard gates (exact):
- ECR < 1.5
- WFE < 0.5
- PassRate < 0.6
- TotalTrades < 30

Weights (exact):
- profit: 0.25
- armor: 0.20
- stability: 0.25
- robustness: 0.20
- reliability: 0.10

Normalization (exact):
- profit = min(100, (RF / 4.0) * 100)
- stability = clamp(60*WFE + 40*PassRate, 0, 100)  # WFE,PassRate are 0..1
- robustness = min(100, (ECR / 5.0) * 100)
- reliability = min(100, (Trades / 200) * 100)
- armor = clamp(100 - 5*ulcer_index - 2*max(0, underwater_days-20), 0, 100)

If any hard gate triggers:
- verdict.is_tradable = false
- verdict.grade = "D"
- verdict.summary begins "HardGate:"
- STILL compute scores + total_weighted for diagnostics

Grade mapping if no hard gate (suggested fixed for now):
- S >= 90
- A >= 80
- B >= 70
- C >= 60
- D < 60
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, TypedDict, Optional
import math


class RawMetrics(TypedDict):
    """Raw metrics required for evaluation."""
    rf: float  # Return Factor
    wfe: float  # Walk-Forward Efficiency (0..1)
    ecr: float  # Efficiency to Capital Ratio
    trades: int
    pass_rate: float  # (0..1)
    ulcer_index: float
    max_underwater_days: int


class Scores(TypedDict):
    """5D expert scores (0..100)."""
    profit: float
    stability: float
    robustness: float
    reliability: float
    armor: float
    total_weighted: float


@dataclass
class EvaluationResult:
    """Complete evaluation result."""
    hard_gates_triggered: List[str]
    scores: Scores
    grade: str  # "S", "A", "B", "C", "D"
    is_tradable: bool
    summary: str


def clamp(value: float, min_val: float, max_val: float) -> float:
    """Clamp value between min and max."""
    return max(min_val, min(value, max_val))


def compute_hard_gates(raw: RawMetrics) -> List[str]:
    """
    Compute hard gates (one-vote veto).
    
    Hard gates (exact):
    - ECR < 1.5
    - WFE < 0.5
    - PassRate < 0.6
    - TotalTrades < 30
    """
    triggered = []
    
    if raw['ecr'] < 1.5:
        triggered.append("ECR < 1.5")
    
    if raw['wfe'] < 0.5:
        triggered.append("WFE < 0.5")
    
    if raw['pass_rate'] < 0.6:
        triggered.append("PassRate < 0.6")
    
    if raw['trades'] < 30:
        triggered.append("TotalTrades < 30")
    
    return triggered


def compute_scores(raw: RawMetrics) -> Scores:
    """
    Compute 5D expert scores from raw metrics.
    
    Normalization (exact):
    - profit = min(100, (RF / 4.0) * 100)
    - stability = clamp(60*WFE + 40*PassRate, 0, 100)  # WFE,PassRate are 0..1
    - robustness = min(100, (ECR / 5.0) * 100)
    - reliability = min(100, (Trades / 200) * 100)
    - armor = clamp(100 - 5*ulcer_index - 2*max(0, underwater_days-20), 0, 100)
    """
    # Profit score
    profit = min(100.0, (raw['rf'] / 4.0) * 100.0)
    
    # Stability score
    stability = clamp(60.0 * raw['wfe'] + 40.0 * raw['pass_rate'], 0.0, 100.0)
    
    # Robustness score
    robustness = min(100.0, (raw['ecr'] / 5.0) * 100.0)
    
    # Reliability score
    reliability = min(100.0, (raw['trades'] / 200.0) * 100.0)
    
    # Armor score
    armor_penalty = 5.0 * raw['ulcer_index'] + 2.0 * max(0.0, raw['max_underwater_days'] - 20.0)
    armor = clamp(100.0 - armor_penalty, 0.0, 100.0)
    
    return {
        'profit': round(profit, 2),
        'stability': round(stability, 2),
        'robustness': round(robustness, 2),
        'reliability': round(reliability, 2),
        'armor': round(armor, 2),
        'total_weighted': 0.0  # Will be computed by compute_total
    }


def compute_total(scores: Scores) -> float:
    """
    Compute weighted total score.
    
    Weights (exact):
    - profit: 0.25
    - armor: 0.20
    - stability: 0.25
    - robustness: 0.20
    - reliability: 0.10
    """
    weights = {
        'profit': 0.25,
        'armor': 0.20,
        'stability': 0.25,
        'robustness': 0.20,
        'reliability': 0.10
    }
    
    total = 0.0
    for key, weight in weights.items():
        total += scores[key] * weight
    
    return round(total, 2)


def grade_from_total(total: float, hard_gates_triggered: List[str]) -> str:
    """
    Determine grade from total score, considering hard gates.
    
    If any hard gate triggers: grade = "D"
    Otherwise:
    - S >= 90
    - A >= 80
    - B >= 70
    - C >= 60
    - D < 60
    """
    if hard_gates_triggered:
        return "D"
    
    if total >= 90.0:
        return "S"
    elif total >= 80.0:
        return "A"
    elif total >= 70.0:
        return "B"
    elif total >= 60.0:
        return "C"
    else:
        return "D"


def evaluate(raw: RawMetrics) -> EvaluationResult:
    """
    Complete evaluation pipeline.
    
    Returns EvaluationResult with:
    - hard_gates_triggered
    - scores (including total_weighted)
    - grade
    - is_tradable
    - summary
    """
    # Compute hard gates
    hard_gates = compute_hard_gates(raw)
    
    # Compute scores
    scores = compute_scores(raw)
    
    # Compute weighted total
    total = compute_total(scores)
    scores['total_weighted'] = total
    
    # Determine grade
    grade = grade_from_total(total, hard_gates)
    
    # Determine tradability
    is_tradable = len(hard_gates) == 0 and grade != "D"
    
    # Build summary
    if hard_gates:
        summary = f"HardGate: {', '.join(hard_gates)}. Scores: profit={scores['profit']}, stability={scores['stability']}, robustness={scores['robustness']}, reliability={scores['reliability']}, armor={scores['armor']}, total={total}"
    else:
        summary = f"Grade {grade}. Scores: profit={scores['profit']}, stability={scores['stability']}, robustness={scores['robustness']}, reliability={scores['reliability']}, armor={scores['armor']}, total={total}"
    
    return EvaluationResult(
        hard_gates_triggered=hard_gates,
        scores=scores,
        grade=grade,
        is_tradable=is_tradable,
        summary=summary
    )


# -----------------------------------------------------------------------------
# Test utilities
# -----------------------------------------------------------------------------

def create_test_raw_metrics(
    rf: float = 2.0,
    wfe: float = 0.7,
    ecr: float = 2.0,
    trades: int = 100,
    pass_rate: float = 0.8,
    ulcer_index: float = 5.0,
    max_underwater_days: int = 10
) -> RawMetrics:
    """Create test raw metrics."""
    return {
        'rf': rf,
        'wfe': wfe,
        'ecr': ecr,
        'trades': trades,
        'pass_rate': pass_rate,
        'ulcer_index': ulcer_index,
        'max_underwater_days': max_underwater_days
    }


if __name__ == "__main__":
    # Quick test
    test_raw = create_test_raw_metrics()
    result = evaluate(test_raw)
    
    print("Test evaluation:")
    print(f"  Hard gates: {result.hard_gates_triggered}")
    print(f"  Scores: {result.scores}")
    print(f"  Grade: {result.grade}")
    print(f"  Tradable: {result.is_tradable}")
    print(f"  Summary: {result.summary}")