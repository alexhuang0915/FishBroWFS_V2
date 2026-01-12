"""
Portfolio Admission Controller - Orchestrates the admission gate for BUILD_PORTFOLIO_V2.

Enforces:
1. Phase C downstream_admissible precondition
2. Correlation constraint (GovernanceParams‑driven)
3. Risk budget constraint (GovernanceParams‑driven)
4. Full, replayable evidence bundle
"""
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timezone

from portfolio.governance.params import load_governance_params
from portfolio.models.governance_models import GovernanceParams
from control.portfolio.evidence_reader import RunEvidenceReader
from control.portfolio.policies.correlation import CorrelationGate, CorrelationGateResult
from control.portfolio.policies.risk_budget import RiskBudgetGate, RiskBudgetResult
from contracts.portfolio.admission_schemas import (
    AdmissionDecision,
    AdmissionVerdict,
    ADMISSION_DECISION_FILE,
    GOVERNANCE_PARAMS_SNAPSHOT_FILE,
    CORRELATION_MATRIX_FILE,
    CORRELATION_VIOLATIONS_FILE,
    RISK_BUDGET_SNAPSHOT_FILE,
    ADMITTED_RUN_IDS_FILE,
    REJECTED_RUN_IDS_FILE,
    EVIDENCE_FILES,
)
from control.rejection_artifact import create_governance_rejection


class PortfolioAdmissionController:
    """Main controller for portfolio admission gate."""
    
    def __init__(
        self,
        params: GovernanceParams,
        evidence_reader: RunEvidenceReader,
        season: str = "current"
    ):
        self.params = params
        self.evidence_reader = evidence_reader
        self.season: str  # type annotation for Pylance
        setattr(self, 'season', season)
    
    @classmethod
    def from_defaults(cls, season: str = "current") -> "PortfolioAdmissionController":
        """Factory method using default GovernanceParams and RunEvidenceReader."""
        params = load_governance_params()
        reader = RunEvidenceReader()
        return cls(params, reader, season)
    
    def evaluate(
        self,
        candidate_run_ids: List[str],
        portfolio_id: str
    ) -> Tuple[AdmissionDecision, CorrelationGateResult, RiskBudgetResult]:
        """
        Evaluate candidate runs for portfolio admission.
        
        Flow (LOCKED order):
        1) Sort candidate_run_ids (deterministic)
        2) Precondition gate (Phase C downstream_admissible)
        3) If returns missing for any remaining -> reject those runs (loud)
        4) Correlation gate on remaining
        5) Risk budget gate on remaining
        6) Produce AdmissionDecision
        
        Returns:
            Tuple of (AdmissionDecision, CorrelationGateResult, RiskBudgetResult)
        """
        # 1) Sort deterministically
        sorted_candidates = sorted(candidate_run_ids)
        
        # 2) Precondition gate: downstream_admissible must be True
        admissible_runs = []
        rejected_precondition = []
        reasons = {}
        
        for run_id in sorted_candidates:
            try:
                bundle = self.evidence_reader.read_policy_check(run_id, self.season)
                if bundle.downstream_admissible:
                    admissible_runs.append(run_id)
                else:
                    rejected_precondition.append(run_id)
                    reasons[run_id] = "Phase C downstream_admissible = False"
            except FileNotFoundError:
                # Missing policy_check.json -> treat as not admissible
                rejected_precondition.append(run_id)
                reasons[run_id] = "Missing policy_check.json (cannot verify downstream_admissible)"
        
        # 3) Returns series availability
        runs_with_returns = []
        missing_returns = []
        
        for run_id in admissible_runs:
            returns = self.evidence_reader.read_returns_series_if_exists(run_id, self.season)
            if returns is None:
                missing_returns.append(run_id)
                reasons[run_id] = "Missing returns series artifact; cannot compute correlation"
            else:
                runs_with_returns.append(run_id)
        
        # Reject runs missing returns
        admissible_runs = runs_with_returns
        rejected_missing_returns = missing_returns
        
        # 4) Correlation gate
        # Gather returns series and scores for remaining candidates
        returns_series = {}
        scores = {}
        max_drawdowns = {}
        
        for run_id in admissible_runs:
            returns_series[run_id] = self.evidence_reader.read_returns_series(run_id, self.season)
            scores[run_id] = self.evidence_reader.read_score(run_id, self.season)
            max_drawdowns[run_id] = self.evidence_reader.read_max_drawdown(run_id, self.season)
        
        correlation_gate = CorrelationGate(
            max_pairwise_correlation=self.params.max_pairwise_correlation,
            min_overlap_days=60  # could be configurable
        )
        corr_result = correlation_gate.evaluate(admissible_runs, returns_series, scores)
        
        # 5) Risk budget gate on correlation‑admitted runs
        risk_gate = RiskBudgetGate(
            portfolio_risk_budget_max=self.params.portfolio_risk_budget_max
        )
        # Filter max_drawdowns to only those admitted by correlation gate
        corr_admitted_mdd = {rid: max_drawdowns[rid] for rid in corr_result.admitted_run_ids}
        corr_admitted_scores = {rid: scores[rid] for rid in corr_result.admitted_run_ids}
        
        risk_result = risk_gate.evaluate(
            corr_result.admitted_run_ids,
            corr_admitted_mdd,
            corr_admitted_scores
        )
        
        # 6) Compile final decision
        final_admitted = risk_result.admitted_run_ids
        final_rejected = (
            rejected_precondition +
            rejected_missing_returns +
            corr_result.rejected_run_ids +
            risk_result.rejected_run_ids
        )
        # Remove duplicates and ensure deterministic order
        final_rejected = sorted(set(final_rejected))
        
        # Build reasons for all rejected runs
        for rid in rejected_precondition:
            reasons.setdefault(rid, "Phase C downstream_admissible = False")
        for rid in rejected_missing_returns:
            reasons.setdefault(rid, "Missing returns series artifact; cannot compute correlation")
        for viol in corr_result.violations:
            if viol.run_id_a in corr_result.rejected_run_ids:
                reasons.setdefault(viol.run_id_a, f"Correlation violation with {viol.run_id_b} (corr={viol.correlation:.3f})")
            if viol.run_id_b in corr_result.rejected_run_ids:
                reasons.setdefault(viol.run_id_b, f"Correlation violation with {viol.run_id_a} (corr={viol.correlation:.3f})")
        for step in risk_result.steps:
            reasons.setdefault(step.rejected_run_id, f"Risk budget exceeded (portfolio risk {step.portfolio_risk_before:.3f} > {self.params.portfolio_risk_budget_max})")
        
        verdict = AdmissionVerdict.ADMITTED if final_admitted else AdmissionVerdict.REJECTED
        
        decision = AdmissionDecision(
            verdict=verdict,
            admitted_run_ids=final_admitted,
            rejected_run_ids=final_rejected,
            reasons=reasons,
            portfolio_id=portfolio_id,
            evaluated_at_utc=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            correlation_violations={
                viol.run_id_a: [viol.run_id_b] for viol in corr_result.violations
            } if corr_result.violations else None,
            risk_budget_steps=[
                {
                    "iteration": s.iteration,
                    "rejected_run_id": s.rejected_run_id,
                    "reason": s.reason,
                    "portfolio_risk_before": s.portfolio_risk_before,
                    "portfolio_risk_after": s.portfolio_risk_after,
                }
                for s in risk_result.steps
            ] if risk_result.steps else None,
            missing_artifacts=missing_returns if missing_returns else None
        )
        
        return decision, corr_result, risk_result
    
    def evaluate_and_write_evidence(
        self,
        candidate_run_ids: List[str],
        portfolio_id: str,
        evidence_dir: Path
    ) -> AdmissionDecision:
        """
        Evaluate admission and write full evidence bundle.
        
        Evidence files are written atomically to:
            {evidence_dir}/{portfolio_id}/admission/
        
        Returns:
            AdmissionDecision
        """
        decision, corr_result, risk_result = self.evaluate(candidate_run_ids, portfolio_id)
        
        # Prepare evidence directory
        admission_dir = evidence_dir / portfolio_id / "admission"
        admission_dir.mkdir(parents=True, exist_ok=True)
        
        # Write admission_decision.json
        decision_path = admission_dir / ADMISSION_DECISION_FILE
        with open(decision_path, "w", encoding="utf-8") as f:
            json.dump(decision.model_dump(mode="json"), f, indent=2, sort_keys=True)
        
        # Write governance_params_snapshot.json
        params_path = admission_dir / GOVERNANCE_PARAMS_SNAPSHOT_FILE
        with open(params_path, "w", encoding="utf-8") as f:
            json.dump(self.params.model_dump(mode="json"), f, indent=2, sort_keys=True)
        
        # Write correlation gate evidence
        corr_result.write_evidence(admission_dir)
        
        # Write risk budget gate evidence
        risk_result.write_evidence(admission_dir)
        
        # Write admitted/rejected IDs as separate files (redundant but required)
        admitted_path = admission_dir / ADMITTED_RUN_IDS_FILE
        with open(admitted_path, "w", encoding="utf-8") as f:
            json.dump(decision.admitted_run_ids, f, indent=2)
        
        rejected_path = admission_dir / REJECTED_RUN_IDS_FILE
        with open(rejected_path, "w", encoding="utf-8") as f:
            json.dump(decision.rejected_run_ids, f, indent=2)
        
        # Write standardized rejection artifact if portfolio is rejected
        if decision.verdict == AdmissionVerdict.REJECTED:
            rejection_reason = f"Portfolio {portfolio_id} rejected: {len(decision.rejected_run_ids)} runs failed admission gates"
            rejection_artifact = create_governance_rejection(
                governance_rule="portfolio_admission",
                reason=rejection_reason,
                affected_ids=decision.rejected_run_ids,
                metrics={
                    "total_candidates": len(candidate_run_ids),
                    "admitted_count": len(decision.admitted_run_ids),
                    "rejected_count": len(decision.rejected_run_ids),
                    "correlation_violations": len(corr_result.violations) if corr_result.violations else 0,
                    "risk_budget_steps": len(risk_result.steps) if risk_result.steps else 0
                }
            )
            rejection_path = admission_dir / "rejection.json"
            rejection_artifact.write(rejection_path)
        
        return decision