"""
Research Flow Controller v2.0 - Runtime Kernel

This is the KERNEL PROCESS of the Research OS.
It implements the single authoritative research lifecycle controller.

NON-NEGOTIABLE CONSTITUTION:
- MUST auto-detect the stage (NO UI input)
- MUST derive state from system gates, job existence, artifact presence, gate summary verdicts, admission state
- MUST NOT rely on UI input
- MUST provide blocking reasons with explain text
- MUST terminate deterministically (no daemon/long-running processes)
"""

import logging
import time
from typing import Optional, Dict, Any, List
from datetime import datetime

from contracts.research.research_flow_kernel import (
    ResearchStage,
    ResearchFlowState,
    GateReasonCode,
)
from contracts.research.ui_stage_mapping import (
    UiPageClassification,
    UiPageTier,
    get_page_classification,
    validate_page_navigation,
    get_available_pages_for_stage,
    get_primary_entry_point,
)
from contracts.portfolio.gate_reason_explain import get_gate_reason_explanation

logger = logging.getLogger(__name__)


class ResearchFlowController:
    """
    Research OS Kernel - The single authoritative research lifecycle controller.
    
    This is the KERNEL PROCESS that evaluates current research state based on:
    - System gates
    - Job existence and status
    - Artifact presence and validity
    - Gate summary verdicts
    - Admission state
    
    NO UI INPUT ALLOWED - State must be derived from system evidence only.
    """
    
    def __init__(self):
        """Initialize research flow controller."""
        self._last_evaluation_time: Optional[datetime] = None
        self._last_evaluation_duration_ms: Optional[int] = None
        
    def evaluate_current_state(self) -> ResearchFlowState:
        """
        Evaluate current research state (KERNEL PROCESS).
        
        This method:
        - MUST auto-detect the stage
        - MUST NOT rely on UI input
        - MUST derive state from system evidence
        - MUST provide blocking reasons with explain text
        - MUST terminate deterministically
        
        Returns:
            ResearchFlowState: Current research state with blocking reasons if applicable
        """
        start_time = time.time()
        
        try:
            # Collect system context
            system_context = self._collect_system_context()
            
            # Auto-detect current stage
            current_stage = self._detect_current_stage(system_context)
            
            # Evaluate if stage is blocked
            is_blocked, blocking_reason, blocking_details = self._evaluate_blocking(
                current_stage, system_context
            )
            
            # Get allowed actions for current stage
            allowed_actions = self._get_allowed_actions(current_stage, is_blocked, system_context)
            
            # Get recommended next action
            recommended_next_action = self._get_recommended_next_action(
                current_stage, is_blocked, blocking_reason, system_context
            )
            
            # Get evidence references
            evidence_refs = self._get_evidence_references(system_context)
            
            # Get blocking explanation from Explain Dictionary
            blocking_explain = None
            if blocking_reason:
                explanation = get_gate_reason_explanation(blocking_reason.value)
                blocking_explain = explanation.get("developer_explanation", "No explanation available")
            
            # Calculate evaluation duration
            evaluation_duration_ms = int((time.time() - start_time) * 1000)
            
            # Create research flow state with all fields including duration
            state = ResearchFlowState(
                current_stage=current_stage,
                is_blocked=is_blocked,
                blocking_reason=blocking_reason,
                blocking_explain=blocking_explain,
                allowed_actions=allowed_actions,
                recommended_next_action=recommended_next_action,
                evidence_refs=evidence_refs,
                system_context=system_context,
                evaluation_duration_ms=evaluation_duration_ms,
            )
            
            # Validate blocked state has required fields
            state.validate_blocking_state()
            
            # Update timing information
            self._last_evaluation_time = datetime.now()
            self._last_evaluation_duration_ms = evaluation_duration_ms
            
            logger.info(f"Research flow state evaluated: {current_stage.value}, blocked={is_blocked}, duration={evaluation_duration_ms}ms")
            return state
            
        except Exception as e:
            logger.error(f"Failed to evaluate research flow state: {e}")
            # Calculate evaluation duration even on error
            evaluation_duration_ms = int((time.time() - start_time) * 1000)
            
            # Return error state
            return ResearchFlowState(
                current_stage=ResearchStage.DATA_READINESS,
                is_blocked=True,
                blocking_reason=GateReasonCode.GATE_SUMMARY_FETCH_ERROR,
                blocking_explain=f"Research flow evaluation failed: {str(e)}",
                allowed_actions=["retry_evaluation", "view_logs"],
                recommended_next_action="Retry evaluation or check system logs",
                evidence_refs=[],
                system_context={"error": str(e)},
                evaluation_duration_ms=evaluation_duration_ms,
            )
    
    def _collect_system_context(self) -> Dict[str, Any]:
        """
        Collect system context for evaluation.
        
        Returns:
            Dict[str, Any]: System context including gates, jobs, artifacts, etc.
        """
        # TODO: Implement actual system context collection
        # For now, return mock context
        return {
            "system_gates": self._check_system_gates(),
            "research_jobs": self._check_research_jobs(),
            "artifacts": self._check_artifacts(),
            "gate_summaries": self._check_gate_summaries(),
            "admission_state": self._check_admission_state(),
            "dataset_availability": self._check_dataset_availability(),
            "registry_validation": self._check_registry_validation(),
            "policy_gates": self._check_policy_gates(),
        }
    
    def _detect_current_stage(self, system_context: Dict[str, Any]) -> ResearchStage:
        """
        Auto-detect current research stage (STRICT ORDER).
        
        Stage detection logic (STRICT ORDER):
        1. DATA_READINESS: No valid research job executed OR required datasets/registry/policy gates fail
        2. RUN_RESEARCH: Data readiness passed, job submitted but artifacts incomplete
        3. OUTCOME_TRIAGE: Jobs completed, artifacts present, gate summary available
        4. DECISION: At least one candidate passed triage, portfolio build possible
        
        Args:
            system_context: System context for evaluation
            
        Returns:
            ResearchStage: Detected research stage
        """
        # Check Stage 0: DATA_READINESS
        if not self._is_data_ready(system_context):
            return ResearchStage.DATA_READINESS
        
        # Check Stage 1: RUN_RESEARCH
        if not self._is_research_completed(system_context):
            return ResearchStage.RUN_RESEARCH
        
        # Check Stage 2: OUTCOME_TRIAGE
        if not self._is_outcome_triaged(system_context):
            return ResearchStage.OUTCOME_TRIAGE
        
        # Stage 3: DECISION
        return ResearchStage.DECISION
    
    def _evaluate_blocking(
        self, current_stage: ResearchStage, system_context: Dict[str, Any]
    ) -> tuple[bool, Optional[GateReasonCode], Optional[Dict[str, Any]]]:
        """
        Evaluate if current stage is blocked.
        
        Args:
            current_stage: Current research stage
            system_context: System context for evaluation
            
        Returns:
            Tuple of (is_blocked, blocking_reason, blocking_details)
        """
        if current_stage == ResearchStage.DATA_READINESS:
            return self._evaluate_data_readiness_blocking(system_context)
        elif current_stage == ResearchStage.RUN_RESEARCH:
            return self._evaluate_run_research_blocking(system_context)
        elif current_stage == ResearchStage.OUTCOME_TRIAGE:
            return self._evaluate_outcome_triage_blocking(system_context)
        elif current_stage == ResearchStage.DECISION:
            return self._evaluate_decision_blocking(system_context)
        else:
            # Should never happen (STRICT enum)
            return True, GateReasonCode.GATE_ITEM_PARSE_ERROR, {"error": "Unknown research stage"}
    
    # -------------------------------------------------------------------------
    # Stage Detection Helpers
    # -------------------------------------------------------------------------
    
    def _is_data_ready(self, system_context: Dict[str, Any]) -> bool:
        """Check if data readiness stage is complete."""
        gates = system_context.get("system_gates", {})
        return all(gates.values())
    
    def _is_research_completed(self, system_context: Dict[str, Any]) -> bool:
        """Check if research execution is complete."""
        jobs = system_context.get("research_jobs", {})
        artifacts = system_context.get("artifacts", {})
        
        # Check if at least one research job is completed with artifacts
        return any(
            job.get("status") == "completed" and artifacts.get(job.get("job_id"))
            for job in jobs
        )
    
    def _is_outcome_triaged(self, system_context: Dict[str, Any]) -> bool:
        """Check if outcome triage is complete."""
        gate_summaries = system_context.get("gate_summaries", [])
        return len(gate_summaries) > 0
    
    # -------------------------------------------------------------------------
    # Blocking Evaluation Helpers
    # -------------------------------------------------------------------------
    
    def _evaluate_data_readiness_blocking(
        self, system_context: Dict[str, Any]
    ) -> tuple[bool, Optional[GateReasonCode], Optional[Dict[str, Any]]]:
        """Evaluate blocking for DATA_READINESS stage."""
        gates = system_context.get("system_gates", {})
        
        # Check specific gates
        if not gates.get("dataset_available", False):
            return True, GateReasonCode.GATE_SUMMARY_FETCH_ERROR, {
                "gate": "dataset_availability",
                "details": "Required datasets not available"
            }
        
        if not gates.get("registry_valid", False):
            return True, GateReasonCode.GATE_ITEM_PARSE_ERROR, {
                "gate": "registry_validation",
                "details": "Registry validation failed"
            }
        
        if not gates.get("policy_gates_pass", False):
            return True, GateReasonCode.GATE_SCHEMA_VERSION_UNSUPPORTED, {
                "gate": "policy_gates",
                "details": "Policy gates failed"
            }
        
        # Not blocked
        return False, None, None
    
    def _evaluate_run_research_blocking(
        self, system_context: Dict[str, Any]
    ) -> tuple[bool, Optional[GateReasonCode], Optional[Dict[str, Any]]]:
        """Evaluate blocking for RUN_RESEARCH stage."""
        jobs = system_context.get("research_jobs", [])
        artifacts = system_context.get("artifacts", {})
        
        if not jobs:
            return True, GateReasonCode.EVIDENCE_SNAPSHOT_MISSING, {
                "reason": "JOB_NOT_STARTED",
                "details": "No research jobs have been started"
            }
        
        # Check if any job is running
        running_jobs = [j for j in jobs if j.get("status") == "running"]
        if running_jobs:
            return True, GateReasonCode.EVIDENCE_SNAPSHOT_HASH_MISMATCH, {
                "reason": "JOB_RUNNING",
                "details": f"{len(running_jobs)} research job(s) still running"
            }
        
        # Check artifact completeness
        completed_jobs = [j for j in jobs if j.get("status") == "completed"]
        for job in completed_jobs:
            job_id = job.get("job_id")
            if not artifacts.get(job_id):
                return True, GateReasonCode.VERDICT_STAMP_MISSING, {
                    "reason": "ARTIFACT_INCOMPLETE",
                    "details": f"Job {job_id} completed but artifacts missing"
                }
        
        # Not blocked
        return False, None, None
    
    def _evaluate_outcome_triage_blocking(
        self, system_context: Dict[str, Any]
    ) -> tuple[bool, Optional[GateReasonCode], Optional[Dict[str, Any]]]:
        """Evaluate blocking for OUTCOME_TRIAGE stage."""
        gate_summaries = system_context.get("gate_summaries", [])
        
        if not gate_summaries:
            return True, GateReasonCode.GATE_SUMMARY_PARSE_ERROR, {
                "reason": "SCORING_NOT_AVAILABLE",
                "details": "No gate summaries available for triage"
            }
        
        # Check if all jobs were rejected
        all_rejected = all(
            summary.get("overall_status") == "REJECT"
            for summary in gate_summaries
        )
        if all_rejected:
            return True, GateReasonCode.GATE_DEPENDENCY_CYCLE, {
                "reason": "ALL_JOBS_REJECTED",
                "details": "All research jobs rejected by gates"
            }
        
        # Not blocked
        return False, None, None
    
    def _evaluate_decision_blocking(
        self, system_context: Dict[str, Any]
    ) -> tuple[bool, Optional[GateReasonCode], Optional[Dict[str, Any]]]:
        """Evaluate blocking for DECISION stage."""
        admission_state = system_context.get("admission_state", {})
        
        if not admission_state.get("portfolio_build_possible", False):
            return True, GateReasonCode.GATE_BACKEND_INVALID_JSON, {
                "reason": "PORTFOLIO_NOT_BUILT",
                "details": "Portfolio build not possible with current candidates"
            }
        
        if not admission_state.get("admission_gates_pass", False):
            return True, GateReasonCode.GATE_ITEM_PARSE_ERROR, {
                "reason": "ADMISSION_GATE_FAILED",
                "details": "Admission gates failed for candidate strategies"
            }
        
        # Not blocked
        return False, None, None
    
    # -------------------------------------------------------------------------
    # Action and Recommendation Helpers
    # -------------------------------------------------------------------------
    
    def _get_allowed_actions(
        self, current_stage: ResearchStage, is_blocked: bool, system_context: Dict[str, Any]
    ) -> List[str]:
        """Get allowed actions for current stage."""
        if is_blocked:
            # Limited actions when blocked
            return ["view_explanation", "view_evidence", "retry_check"]
        
        # Stage-specific actions
        actions = {
            ResearchStage.DATA_READINESS: [
                "run_data_preparation",
                "validate_datasets",
                "check_registry",
                "run_policy_gates",
                "start_research",
            ],
            ResearchStage.RUN_RESEARCH: [
                "monitor_jobs",
                "view_job_status",
                "check_artifacts",
                "run_triage",
            ],
            ResearchStage.OUTCOME_TRIAGE: [
                "view_gate_summaries",
                "analyze_results",
                "compare_candidates",
                "make_decision",
            ],
            ResearchStage.DECISION: [
                "build_portfolio",
                "review_admission",
                "execute_decisions",
                "start_new_research",
            ],
        }
        
        return actions.get(current_stage, [])
    
    def _get_recommended_next_action(
        self,
        current_stage: ResearchStage,
        is_blocked: bool,
        blocking_reason: Optional[GateReasonCode],
        system_context: Dict[str, Any],
    ) -> Optional[str]:
        """Get recommended next action for user."""
        if is_blocked and blocking_reason:
            return f"Address blocking issue: {blocking_reason.value}"
        
        recommendations = {
            ResearchStage.DATA_READINESS: "Start research execution",
            ResearchStage.RUN_RESEARCH: "Monitor research jobs and check artifacts",
            ResearchStage.OUTCOME_TRIAGE: "Analyze gate summaries and triage outcomes",
            ResearchStage.DECISION: "Build portfolio and make final decisions",
        }
        
        return recommendations.get(current_stage)
    
    def _get_evidence_references(self, system_context: Dict[str, Any]) -> List[str]:
        """Get evidence artifact references."""
        evidence_refs = []
        
        # Add job references
        for job in system_context.get("research_jobs", []):
            if job_id := job.get("job_id"):
                evidence_refs.append(f"job:{job_id}")
        
        # Add artifact references
        for artifact_id in system_context.get("artifacts", {}).keys():
            evidence_refs.append(f"artifact:{artifact_id}")
        
        # Add gate summary references
        for i, summary in enumerate(system_context.get("gate_summaries", [])):
            evidence_refs.append(f"gate_summary:{i}")
        
        return evidence_refs
    
    # -------------------------------------------------------------------------
    # System Context Collection (Mock Implementation)
    # -------------------------------------------------------------------------
    
    def _check_system_gates(self) -> Dict[str, bool]:
        """Check system gates (mock)."""
        # TODO: Implement actual gate checking
        return {
            "dataset_available": True,
            "registry_valid": True,
            "policy_gates_pass": True,
            "resource_available": True,
        }
    
    def _check_research_jobs(self) -> List[Dict[str, Any]]:
        """Check research jobs (mock)."""
        # TODO: Implement actual job checking
        return []
    
    def _check_artifacts(self) -> Dict[str, Any]:
        """Check artifacts (mock)."""
        # TODO: Implement actual artifact checking
        return {}
    
    def _check_gate_summaries(self) -> List[Dict[str, Any]]:
        """Check gate summaries (mock)."""
        # TODO: Implement actual gate summary checking
        return []
    
    def _check_admission_state(self) -> Dict[str, Any]:
        """Check admission state (mock)."""
        # TODO: Implement actual admission state checking
        return {
            "portfolio_build_possible": False,
            "admission_gates_pass": False,
            "candidate_count": 0,
        }
    
    def _check_dataset_availability(self) -> Dict[str, Any]:
        """Check dataset availability (mock)."""
        # TODO: Implement actual dataset checking
        return {
            "datasets_available": True,
            "missing_datasets": [],
        }
    
    def _check_registry_validation(self) -> Dict[str, Any]:
        """Check registry validation (mock)."""
        # TODO: Implement actual registry checking
        return {
            "registry_valid": True,
            "validation_errors": [],
        }
    
    def _check_policy_gates(self) -> Dict[str, Any]:
        """Check policy gates (mock)."""
        # TODO: Implement actual policy gate checking
        return {
            "policy_gates_pass": True,
            "failed_gates": [],
        }
    
    # -------------------------------------------------------------------------
    # UI Navigation Validation Methods
    # -------------------------------------------------------------------------
    
    def validate_ui_navigation(
        self,
        target_page_id: str,
        current_stage: Optional[ResearchStage] = None
    ) -> tuple[bool, Optional[str], Optional[UiPageClassification]]:
        """
        Validate navigation to a UI page.
        
        Args:
            target_page_id: Page identifier to navigate to
            current_stage: Current research stage (if None, will evaluate)
            
        Returns:
            Tuple of (is_allowed, reason_if_blocked, page_classification)
        """
        # Get current stage if not provided
        if current_stage is None:
            state = self.evaluate_current_state()
            current_stage = state.current_stage
        
        # Validate navigation
        is_allowed, reason = validate_page_navigation(target_page_id, current_stage)
        
        # Get page classification
        classification = get_page_classification(target_page_id)
        
        return is_allowed, reason, classification
    
    def get_available_ui_pages(
        self,
        current_stage: Optional[ResearchStage] = None
    ) -> List[UiPageClassification]:
        """
        Get all UI pages available in current research stage.
        
        Args:
            current_stage: Current research stage (if None, will evaluate)
            
        Returns:
            List of available UI page classifications
        """
        # Get current stage if not provided
        if current_stage is None:
            state = self.evaluate_current_state()
            current_stage = state.current_stage
        
        return get_available_pages_for_stage(current_stage)
    
    def get_primary_entry_point_info(self) -> UiPageClassification:
        """
        Get the PRIMARY entry point (Research Flow).
        
        Returns:
            UiPageClassification for Research Flow
        """
        return get_primary_entry_point()
    
    def enforce_primary_entry_point(self) -> bool:
        """
        Enforce that only Research Flow can be primary entry point.
        
        Returns:
            bool: True if enforcement is valid
        """
        primary = get_primary_entry_point()
        
        # Verify that Research Flow is the only PRIMARY page
        if primary.page_id != "research_flow":
            logger.error(f"Invalid primary entry point: {primary.page_id}")
            return False
        
        # Verify that Research Flow is PRIMARY tier
        if primary.tier != UiPageTier.PRIMARY:
            logger.error(f"Research Flow is not PRIMARY tier: {primary.tier}")
            return False
        
        return True
    
    def get_ui_navigation_recommendations(
        self,
        current_stage: Optional[ResearchStage] = None
    ) -> Dict[str, Any]:
        """
        Get UI navigation recommendations for current stage.
        
        Args:
            current_stage: Current research stage (if None, will evaluate)
            
        Returns:
            Dict with navigation recommendations
        """
        # Get current stage if not provided
        if current_stage is None:
            state = self.evaluate_current_state()
            current_stage = state.current_stage
        
        # Get available pages
        available_pages = get_available_pages_for_stage(current_stage)
        
        # Categorize by tier
        primary_pages = [p for p in available_pages if p.tier == UiPageTier.PRIMARY]
        tool_pages = [p for p in available_pages if p.tier == UiPageTier.TOOL]
        expert_pages = [p for p in available_pages if p.tier == UiPageTier.EXPERT]
        
        # Get recommended next page based on stage
        recommended_page = self._get_recommended_ui_page(current_stage)
        
        return {
            "current_stage": current_stage.value,
            "available_pages": {
                "primary": [p.page_id for p in primary_pages],
                "tool": [p.page_id for p in tool_pages],
                "expert": [p.page_id for p in expert_pages],
            },
            "recommended_page": recommended_page,
            "total_available": len(available_pages),
        }
    
    def _get_recommended_ui_page(self, current_stage: ResearchStage) -> Optional[str]:
        """
        Get recommended UI page for current stage.
        
        Args:
            current_stage: Current research stage
            
        Returns:
            Recommended page ID or None
        """
        recommendations = {
            ResearchStage.DATA_READINESS: "operation",
            ResearchStage.RUN_RESEARCH: "operation",
            ResearchStage.OUTCOME_TRIAGE: "gate_dashboard",
            ResearchStage.DECISION: "allocation",
        }
        
        recommended_page = recommendations.get(current_stage)
        
        # Verify recommendation is available
        if recommended_page:
            classification = get_page_classification(recommended_page)
            if classification and classification.is_available_in_stage(current_stage):
                return recommended_page
        
        # Fallback to Research Flow
        return "research_flow"


# -----------------------------------------------------------------------------
#