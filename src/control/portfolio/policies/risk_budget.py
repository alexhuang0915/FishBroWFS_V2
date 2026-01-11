"""
Risk Budget Gate - Enforces portfolio‑level risk budget constraint.

Deterministic: iteratively reject lowest‑score strategies until total risk ≤ budget.
"""
import json
from pathlib import Path
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import numpy as np


@dataclass
class RiskBudgetStep:
    """Record of a single rejection step."""
    iteration: int
    rejected_run_id: str
    reason: str
    portfolio_risk_before: float
    portfolio_risk_after: float
    per_run_risk: Dict[str, float]


@dataclass
class RiskBudgetResult:
    """Result of applying risk budget gate."""
    admitted_run_ids: List[str]
    rejected_run_ids: List[str]
    total_risk: float
    budget_max: float
    per_run_risk: Dict[str, float]  # run_id -> risk contribution
    steps: List[RiskBudgetStep]  # rejection steps (empty if within budget)

    def write_evidence(self, output_dir: Path) -> None:
        """Write risk budget gate evidence files."""
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # risk_budget_snapshot.json
        snapshot = {
            "budget_max": self.budget_max,
            "total_risk": self.total_risk,
            "per_run_risk": {rid: float(val) for rid, val in self.per_run_risk.items()},
            "steps": [
                {
                    "iteration": s.iteration,
                    "rejected_run_id": s.rejected_run_id,
                    "reason": s.reason,
                    "portfolio_risk_before": s.portfolio_risk_before,
                    "portfolio_risk_after": s.portfolio_risk_after,
                    "per_run_risk": {rid: float(val) for rid, val in s.per_run_risk.items()}
                }
                for s in self.steps
            ]
        }
        snapshot_path = output_dir / "risk_budget_snapshot.json"
        with open(snapshot_path, "w", encoding="utf-8") as f:
            json.dump(snapshot, f, indent=2, sort_keys=True)
        
        # admitted_run_ids.json (overwrites correlation gate's file)
        admitted_path = output_dir / "admitted_run_ids.json"
        with open(admitted_path, "w", encoding="utf-8") as f:
            json.dump(self.admitted_run_ids, f, indent=2)
        
        # rejected_run_ids.json (append?)
        rejected_path = output_dir / "rejected_run_ids.json"
        with open(rejected_path, "w", encoding="utf-8") as f:
            json.dump(self.rejected_run_ids, f, indent=2)


class RiskBudgetGate:
    """Gate that ensures portfolio total risk does not exceed budget."""
    
    def __init__(self, portfolio_risk_budget_max: float):
        """
        Args:
            portfolio_risk_budget_max: maximum total risk (0 < value ≤ 1)
        """
        self.portfolio_risk_budget_max = portfolio_risk_budget_max
    
    def evaluate(
        self,
        candidate_run_ids: List[str],
        max_drawdowns: Dict[str, float],  # run_id -> max drawdown (positive magnitude)
        scores: Dict[str, float]
    ) -> RiskBudgetResult:
        """
        Apply risk budget gate.
        
        Risk model v1:
          per_run_risk = max_drawdown / sum(max_drawdown of all candidates)
          portfolio_risk = sum(per_run_risk for admitted)
        
        If portfolio_risk > budget_max:
          iteratively reject lowest score; tie -> reject lexicographically larger run_id.
        
        Returns:
            RiskBudgetResult with admitted/rejected lists and evidence.
        """
        # Deterministic ordering
        sorted_candidates = sorted(candidate_run_ids)
        
        # Compute per‑run risk contributions
        total_mdd = sum(max_drawdowns.get(rid, 0.0) for rid in sorted_candidates)
        if total_mdd == 0:
            # Edge case: all max drawdowns zero -> uniform risk
            per_run_risk = {rid: 1.0 / len(sorted_candidates) for rid in sorted_candidates}
        else:
            per_run_risk = {
                rid: max_drawdowns.get(rid, 0.0) / total_mdd
                for rid in sorted_candidates
            }
        
        # Initial portfolio risk (sum of contributions)
        portfolio_risk = sum(per_run_risk.values())
        
        admitted = set(sorted_candidates)
        rejected = set()
        steps = []
        
        iteration = 0
        while portfolio_risk > self.portfolio_risk_budget_max and len(admitted) > 0:
            iteration += 1
            
            # Find candidate with lowest score among admitted
            # Tie‑break: lexicographically larger run_id
            candidates_list = sorted(admitted)
            lowest_score = min(scores.get(rid, 0.0) for rid in candidates_list)
            # Collect all with lowest score
            lowest_candidates = [rid for rid in candidates_list if scores.get(rid, 0.0) == lowest_score]
            # Choose lexicographically largest among them
            reject_id = max(lowest_candidates)
            
            # Record step
            steps.append(RiskBudgetStep(
                iteration=iteration,
                rejected_run_id=reject_id,
                reason=f"lowest score {lowest_score}",
                portfolio_risk_before=portfolio_risk,
                portfolio_risk_after=portfolio_risk - per_run_risk[reject_id],
                per_run_risk=per_run_risk.copy()
            ))
            
            # Update sets
            admitted.remove(reject_id)
            rejected.add(reject_id)
            
            # Recompute per‑run risk with remaining candidates
            total_mdd = sum(max_drawdowns.get(rid, 0.0) for rid in admitted)
            if total_mdd == 0:
                per_run_risk = {rid: 1.0 / len(admitted) for rid in admitted} if admitted else {}
            else:
                per_run_risk = {
                    rid: max_drawdowns.get(rid, 0.0) / total_mdd
                    for rid in admitted
                }
            
            portfolio_risk = sum(per_run_risk.values())
        
        # Final admitted list (sorted)
        admitted_sorted = sorted(admitted)
        rejected_sorted = sorted(rejected)
        
        return RiskBudgetResult(
            admitted_run_ids=admitted_sorted,
            rejected_run_ids=rejected_sorted,
            total_risk=portfolio_risk,
            budget_max=self.portfolio_risk_budget_max,
            per_run_risk=per_run_risk,
            steps=steps
        )