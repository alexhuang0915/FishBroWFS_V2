"""
Job Admission Policy Engine (DP8).

Deterministic policy engine that evaluates job gate summaries and produces
admission decisions. Reads gate summaries as input, applies policy rules,
and writes job_admission_decision.json artifacts.
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
from pathlib import Path

from contracts.job_admission_schemas import (
    JobAdmissionDecision,
    JobAdmissionVerdict,
    AdmissionPolicyRule,
    AdmissionPolicyConfig,
    create_default_policy,
    JOB_ADMISSION_DECISION_FILE,
)
from contracts.portfolio.gate_summary_schemas import (
    GateSummaryV1,
    GateStatus,
    GateItemV1,
)
from control.job_artifacts import (
    get_job_evidence_dir,
    get_job_artifact_path,
)
from control.artifacts import write_json_atomic
from gui.services.consolidated_gate_summary_service import (
    get_consolidated_gate_summary_service,
)

logger = logging.getLogger(__name__)


class JobAdmissionPolicyEngine:
    """Deterministic policy engine for job admission decisions."""
    
    def __init__(self, policy_config: Optional[AdmissionPolicyConfig] = None):
        """Initialize policy engine with configuration."""
        self.policy_config = policy_config or create_default_policy()
        self.gate_summary_service = get_consolidated_gate_summary_service()
    
    def evaluate_job(self, job_id: str) -> JobAdmissionDecision:
        """
        Evaluate a job for admission based on its gate summary.
        
        Args:
            job_id: Job identifier to evaluate
            
        Returns:
            JobAdmissionDecision with verdict and rationale
            
        Raises:
            ValueError: If job gate summary cannot be fetched
        """
        # Fetch gate summary
        gate_summary = self.gate_summary_service.fetch_consolidated_summary(job_id)
        if not gate_summary:
            raise ValueError(f"No gate summary found for job {job_id}")
        
        # Apply policy rules
        verdict, reason, rules_applied = self._apply_policy_rules(gate_summary)
        
        # Extract gate details for debugging
        failing_gates, warning_gates = self._extract_gate_details(gate_summary)
        
        # Check for ranking explain artifact
        ranking_explain_artifact = self._check_ranking_explain_artifact(job_id)
        
        # Build navigation actions
        navigation_actions = self._build_navigation_actions(job_id, gate_summary)
        
        # Create decision
        decision = JobAdmissionDecision(
            verdict=verdict,
            job_id=job_id,
            evaluated_at_utc=datetime.now(timezone.utc).isoformat(),
            gate_summary_status=gate_summary.overall_status.value,
            total_gates=gate_summary.total_gates,
            gate_counts=gate_summary.counts,
            decision_reason=reason,
            policy_rules_applied=[rule.value for rule in rules_applied],
            failing_gates=failing_gates,
            warning_gates=warning_gates,
            ranking_explain_artifact=ranking_explain_artifact,
            navigation_actions=navigation_actions,
        )
        
        return decision
    
    def _apply_policy_rules(
        self, 
        gate_summary: GateSummaryV1
    ) -> tuple[JobAdmissionVerdict, str, List[AdmissionPolicyRule]]:
        """
        Apply policy rules to gate summary and determine verdict.
        
        Returns:
            Tuple of (verdict, reason, rules_applied)
        """
        rules_applied = []
        overall_status = gate_summary.overall_status
        
        # Rule 1: Basic status mapping
        if overall_status == GateStatus.PASS:
            verdict = self.policy_config.default_verdict_for_pass
            reason = "All gates passed"
            rules_applied.append(AdmissionPolicyRule.PASS_ALWAYS_ADMIT)
            
        elif overall_status == GateStatus.REJECT:
            verdict = self.policy_config.default_verdict_for_reject
            reason = "One or more gates rejected"
            rules_applied.append(AdmissionPolicyRule.REJECT_ALWAYS_REJECT)
            
        elif overall_status == GateStatus.WARN:
            verdict = self.policy_config.default_verdict_for_warn
            reason = "One or more gates have warnings"
            rules_applied.append(AdmissionPolicyRule.WARN_REQUIRES_REVIEW)
            
        else:  # UNKNOWN
            verdict = self.policy_config.default_verdict_for_unknown
            reason = "Gate status unknown"
            rules_applied.append(AdmissionPolicyRule.UNKNOWN_REQUIRES_REVIEW)
        
        # Rule 2: Check critical gates (override if critical gate failed)
        if gate_summary.gates:
            for gate in gate_summary.gates:
                if (gate.gate_id in self.policy_config.critical_gates and 
                    gate.status == GateStatus.REJECT):
                    verdict = JobAdmissionVerdict.REJECTED
                    reason = f"Critical gate '{gate.gate_name}' rejected"
                    rules_applied.append(AdmissionPolicyRule.DATA_ALIGNMENT_FAIL)
                    break
        
        # Rule 3: Check warning gates that require review
        if gate_summary.gates and verdict != JobAdmissionVerdict.REJECTED:
            for gate in gate_summary.gates:
                if (gate.gate_id in self.policy_config.warning_gates_require_review and 
                    gate.status == GateStatus.WARN):
                    if verdict != JobAdmissionVerdict.HOLD:
                        verdict = JobAdmissionVerdict.HOLD
                        reason = f"Gate '{gate.gate_name}' requires review"
                        rules_applied.append(AdmissionPolicyRule.RANKING_EXPLAIN_WARN)
        
        # Rule 4: Apply gate count thresholds
        if gate_summary.counts and verdict == JobAdmissionVerdict.ADMITTED:
            warn_count = gate_summary.counts.get("warn", 0)
            fail_count = gate_summary.counts.get("reject", 0)
            
            if warn_count > self.policy_config.max_warn_gates:
                verdict = JobAdmissionVerdict.HOLD
                reason = f"Too many warning gates ({warn_count} > {self.policy_config.max_warn_gates})"
                rules_applied.append(AdmissionPolicyRule.MAX_WARN_GATES)
            
            if fail_count > self.policy_config.max_fail_gates:
                verdict = JobAdmissionVerdict.REJECTED
                reason = f"Too many failing gates ({fail_count} > {self.policy_config.max_fail_gates})"
                rules_applied.append(AdmissionPolicyRule.MAX_FAIL_GATES)
        
        # Rule 5: Mixed status evaluation
        if (gate_summary.counts and
            gate_summary.counts.get("pass") and
            gate_summary.counts.get("warn") and
            gate_summary.counts.get("reject")):
            # Has mixed statuses
            rules_applied.append(AdmissionPolicyRule.MIXED_STATUS_EVALUATION)
        
        return verdict, reason, rules_applied
    
    def _extract_gate_details(
        self, 
        gate_summary: GateSummaryV1
    ) -> tuple[Optional[List[Dict[str, Any]]], Optional[List[Dict[str, Any]]]]:
        """Extract failing and warning gate details for debugging."""
        if not gate_summary.gates:
            return None, None
        
        failing_gates = []
        warning_gates = []
        
        for gate in gate_summary.gates:
            gate_details = {
                "gate_id": gate.gate_id,
                "gate_name": gate.gate_name,
                "status": gate.status.value,
                "message": gate.message,
                "reason_codes": gate.reason_codes,
            }
            
            if gate.status == GateStatus.REJECT:
                failing_gates.append(gate_details)
            elif gate.status == GateStatus.WARN:
                warning_gates.append(gate_details)
        
        return (failing_gates if failing_gates else None, 
                warning_gates if warning_gates else None)
    
    def _check_ranking_explain_artifact(self, job_id: str) -> Optional[str]:
        """Check if ranking explain artifact exists for job."""
        ranking_explain_path = get_job_artifact_path(job_id, "ranking_explain_report.json")
        if ranking_explain_path and ranking_explain_path.exists():
            return "ranking_explain_report.json"
        return None
    
    def _build_navigation_actions(
        self,
        job_id: str,
        gate_summary: GateSummaryV1
    ) -> Optional[List[Dict[str, Any]]]:
        """Build navigation actions for UI."""
        actions = []
        
        # Always include gate summary action
        actions.append({
            "label": "View Gate Summary",
            "target": "gate_summary",
            "context": {"job_id": job_id},
            "description": "Open consolidated gate summary for this job"
        })
        
        # Include ranking explain if available
        ranking_explain_path = get_job_artifact_path(job_id, "ranking_explain_report.json")
        if ranking_explain_path and ranking_explain_path.exists():
            actions.append({
                "label": "View Ranking Explain",
                "target": "explain://ranking",
                "context": {"job_id": job_id},
                "description": "Open ranking explain report"
            })
        
        # Include job admission decision (self-reference)
        actions.append({
            "label": "View Admission Decision",
            "target": f"job_admission://{job_id}",
            "context": {"job_id": job_id},
            "description": "Open this admission decision"
        })
        
        # Include gate dashboard action
        actions.append({
            "label": "Gate Dashboard",
            "target": "gate_dashboard",
            "description": "Open gate summary dashboard"
        })
        
        return actions if actions else None
    
    def write_decision(self, job_id: str, decision: JobAdmissionDecision) -> Path:
        """
        Write admission decision to job artifact directory.
        
        Args:
            job_id: Job identifier
            decision: Admission decision to write
            
        Returns:
            Path to written decision file
        """
        artifact_dir = get_job_evidence_dir(job_id)
        decision_path = artifact_dir / JOB_ADMISSION_DECISION_FILE
        
        # Ensure directory exists
        artifact_dir.mkdir(parents=True, exist_ok=True)
        
        # Write decision
        write_json_atomic(decision_path, decision.model_dump())
        logger.info(f"Wrote job admission decision to {decision_path}")
        
        return decision_path
    
    def read_decision(self, job_id: str) -> Optional[JobAdmissionDecision]:
        """
        Read existing admission decision for job.
        
        Args:
            job_id: Job identifier
            
        Returns:
            JobAdmissionDecision if exists, None otherwise
        """
        import json
        from pathlib import Path
        
        decision_path = get_job_artifact_path(job_id, JOB_ADMISSION_DECISION_FILE)
        if not decision_path or not decision_path.exists():
            return None
        
        try:
            with open(decision_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if data:
                return JobAdmissionDecision(**data)
        except Exception as e:
            logger.warning(f"Failed to read job admission decision for {job_id}: {e}")
        
        return None
    
    def evaluate_and_write(self, job_id: str) -> JobAdmissionDecision:
        """
        Evaluate job and write decision (convenience method).
        
        Args:
            job_id: Job identifier
            
        Returns:
            JobAdmissionDecision that was written
        """
        decision = self.evaluate_job(job_id)
        self.write_decision(job_id, decision)
        return decision


# -----------------------------------------------------------------------------
# Singleton pattern
# -----------------------------------------------------------------------------

_JOB_ADMISSION_POLICY_ENGINE = None


def get_job_admission_policy_engine(
    policy_config: Optional[AdmissionPolicyConfig] = None
) -> JobAdmissionPolicyEngine:
    """Get singleton instance of job admission policy engine."""
    global _JOB_ADMISSION_POLICY_ENGINE
    if _JOB_ADMISSION_POLICY_ENGINE is None:
        _JOB_ADMISSION_POLICY_ENGINE = JobAdmissionPolicyEngine(policy_config)
    return _JOB_ADMISSION_POLICY_ENGINE