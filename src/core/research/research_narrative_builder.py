"""
Research Narrative Builder v2.4 - Core Logic with Persona Support & Quality Normalization

Converts ResearchFlowState into human-readable narrative using Explain Dictionary v1.5+.
This is the PURE FUNCTION that transforms kernel output into "human explanation pack".

NON-NEGOTIABLE CONSTITUTION:
- Kernel remains SSOT for truth. Narrative must not change state.
- Narrative must be pure function of Kernel output (+ optional evidence lookups)
- Every narrative MUST output: headline, why, next_step
- Must support Persona-specific views (TRADER, ENGINEER, QA, PM, EXEC)
- Must apply quality normalization for persona tone consistency
- Must be frozen models (ConfigDict(frozen=True))
- Must terminate deterministically (make check), no servers
"""

import logging
from typing import Dict, Any, Optional, List

from contracts.research.research_flow_kernel import (
    ResearchStage,
    ResearchFlowState,
    GateReasonCode,
)
from contracts.research.research_narrative import (
    ResearchNarrativeV1,
    NarrativeActionId,
    create_narrative,
)
from contracts.research.explain_persona import (
    ExplainPersona,
    get_default_persona,
    validate_persona,
)
from contracts.portfolio.gate_reason_explain import (
    get_gate_reason_explanation,
    DICTIONARY_VERSION,
)
from ..explain_quality_normalizer import (
    normalize_explanation_for_persona,
    NormalizationResult,
)

logger = logging.getLogger(__name__)


class ResearchNarrativeBuilder:
    """
    Research Narrative Builder - Pure function that converts kernel state to narrative.
    
    This builder:
    - Takes ResearchFlowState as input
    - Uses Explain Dictionary v1.5+ for developer/business views
    - Supports persona-specific content generation (TRADER, ENGINEER, QA, PM, EXEC)
    - Generates stable action IDs for UI mapping
    - Applies length constraints and validation rules
    - Returns frozen ResearchNarrativeV1 model
    """
    
    def __init__(self):
        """Initialize narrative builder."""
        self._explain_dict_version = DICTIONARY_VERSION
    
    def build_narrative(
        self,
        flow_state: ResearchFlowState,
        persona: ExplainPersona = None
    ) -> ResearchNarrativeV1:
        """
        Build narrative from research flow state with optional persona.
        
        Args:
            flow_state: ResearchFlowState from kernel
            persona: Optional ExplainPersona for audience-specific content.
                    Defaults to TRADER for backward compatibility.
            
        Returns:
            ResearchNarrativeV1: Frozen narrative model
        """
        # Use default persona if not specified
        if persona is None:
            persona = get_default_persona()
        
        # Extract core state
        stage = flow_state.current_stage
        is_blocked = flow_state.is_blocked
        blocking_reason = flow_state.blocking_reason
        
        # Determine severity
        severity = self._determine_severity(is_blocked, blocking_reason)
        
        # Get primary reason code
        primary_reason_code = self._get_primary_reason_code(
            stage, is_blocked, blocking_reason
        )
        
        # Get explanation from dictionary
        explanation = self._get_explanation_with_context(
            primary_reason_code, flow_state
        )
        
        # Build headline
        headline = self._build_headline(stage, is_blocked, blocking_reason)
        
        # Build why explanation
        why = self._build_why_explanation(stage, is_blocked, blocking_reason, explanation, persona)
        
        # Build persona-specific views
        developer_view = self._build_developer_view(
            stage, is_blocked, blocking_reason, explanation, flow_state, persona
        )
        
        business_view = self._build_business_view(
            stage, is_blocked, blocking_reason, explanation, flow_state, persona
        )
        
        # Determine next step action
        next_step_action, next_step_label = self._determine_next_step(
            stage, is_blocked, blocking_reason, flow_state
        )
        
        # Build drilldown actions
        drilldown_actions = self._build_drilldown_actions(
            stage, is_blocked, blocking_reason, flow_state
        )
        
        # Get evidence references
        evidence_refs = self._get_evidence_references(flow_state)
        
        # Create narrative
        narrative = create_narrative(
            stage=stage,
            severity=severity,
            headline=headline,
            why=why,
            primary_reason_code=primary_reason_code,
            developer_view=developer_view,
            business_view=business_view,
            next_step_action=next_step_action,
            next_step_label=next_step_label,
            drilldown_actions=drilldown_actions,
            evidence_refs=evidence_refs,
        )
        
        logger.debug(f"Narrative built for stage {stage.value}, severity {severity}, persona {persona.value}")
        return narrative
    
    def _determine_severity(
        self, is_blocked: bool, blocking_reason: Optional[GateReasonCode]
    ) -> str:
        """
        Determine narrative severity.
        
        Rules:
        - BLOCKED: is_blocked=True with blocking_reason
        - WARN: is_blocked=True but no blocking_reason (silent blocking)
        - OK: is_blocked=False
        """
        if is_blocked:
            if blocking_reason:
                return "BLOCKED"
            else:
                return "WARN"  # Silent blocking
        else:
            return "OK"
    
    def _get_primary_reason_code(
        self,
        stage: ResearchStage,
        is_blocked: bool,
        blocking_reason: Optional[GateReasonCode]
    ) -> GateReasonCode:
        """
        Get primary reason code for narrative.
        
        If blocked, use blocking_reason. Otherwise, use stage-specific success code.
        """
        if is_blocked and blocking_reason:
            return blocking_reason
        
        # Stage-specific success codes
        success_codes = {
            ResearchStage.DATA_READINESS: GateReasonCode.GATE_ITEM_PARSE_ERROR,  # Fallback
            ResearchStage.RUN_RESEARCH: GateReasonCode.GATE_SUMMARY_PARSE_ERROR,  # Fallback
            ResearchStage.OUTCOME_TRIAGE: GateReasonCode.GATE_SCHEMA_VERSION_UNSUPPORTED,  # Fallback
            ResearchStage.DECISION: GateReasonCode.GATE_SUMMARY_FETCH_ERROR,  # Fallback
        }
        
        return success_codes.get(stage, GateReasonCode.GATE_ITEM_PARSE_ERROR)
    
    def _get_explanation_with_context(
        self, reason_code: GateReasonCode, flow_state: ResearchFlowState
    ) -> Dict[str, Any]:
        """
        Get explanation from dictionary with context variables.
        
        Args:
            reason_code: GateReasonCode to explain
            flow_state: ResearchFlowState for context
            
        Returns:
            Dictionary with developer/business explanation
        """
        # Build context variables
        context_vars = {
            "stage": flow_state.current_stage.value,
            "is_blocked": str(flow_state.is_blocked),
            "evaluation_duration_ms": str(flow_state.evaluation_duration_ms or 0),
        }
        
        # Add system context variables
        if flow_state.system_context:
            for key, value in flow_state.system_context.items():
                if isinstance(value, (str, int, float, bool)):
                    context_vars[key] = str(value)
        
        # Get explanation from dictionary with explicit keyword for clarity
        return get_gate_reason_explanation(
            reason_code.value,
            context_vars=context_vars,
        )
    
    def _build_headline(
        self,
        stage: ResearchStage,
        is_blocked: bool,
        blocking_reason: Optional[GateReasonCode]
    ) -> str:
        """
        Build one-sentence headline (<= 120 chars).
        
        Format: [Stage] - [Status] - [Action]
        """
        stage_names = {
            ResearchStage.DATA_READINESS: "Data Readiness",
            ResearchStage.RUN_RESEARCH: "Research Execution",
            ResearchStage.OUTCOME_TRIAGE: "Outcome Triage",
            ResearchStage.DECISION: "Decision Making",
        }
        
        status = "Blocked" if is_blocked else "Ready"
        
        if is_blocked and blocking_reason:
            # Short blocking headline
            headline = f"{stage_names[stage]} - {status} - {blocking_reason.value}"
        else:
            # Success headline
            actions = {
                ResearchStage.DATA_READINESS: "Start research",
                ResearchStage.RUN_RESEARCH: "Monitor jobs",
                ResearchStage.OUTCOME_TRIAGE: "Analyze results",
                ResearchStage.DECISION: "Make decisions",
            }
            headline = f"{stage_names[stage]} - {status} - {actions.get(stage, 'Proceed')}"
        
        # Enforce length constraint
        if len(headline) > 120:
            headline = headline[:117] + "..."
        
        return headline
    
    def _build_why_explanation(
        self,
        stage: ResearchStage,
        is_blocked: bool,
        blocking_reason: Optional[GateReasonCode],
        explanation: Dict[str, Any],
        persona: ExplainPersona = None
    ) -> str:
        """
        Build why explanation (<= 400 chars).
        
        Uses developer_explanation from dictionary for blocked states,
        stage-specific success messages for unblocked states.
        Applies quality normalization for persona tone consistency.
        """
        if persona is None:
            persona = get_default_persona()
        
        if is_blocked and blocking_reason:
            # Use developer explanation from dictionary
            why = explanation.get("developer_explanation", "Blocked by unknown reason")
            
            # Persona-specific enhancements for blocked state
            if persona == ExplainPersona.ENGINEER:
                why += " [ENGINEER: Review error stack trace and system logs.]"
            elif persona == ExplainPersona.QA:
                why += " [QA: Validate error conditions and test scenarios.]"
            elif persona == ExplainPersona.TRADER:
                why += " [TRADER: Issue may affect research timing and signal generation.]"
            elif persona == ExplainPersona.PM:
                why += " [PM: Root cause analysis needed for timeline impact assessment.]"
            elif persona == ExplainPersona.EXEC:
                why = f"System issue detected: {blocking_reason.value}. Engineering investigating root cause."
        else:
            # Success messages with persona-specific content
            success_messages = {
                ResearchStage.DATA_READINESS: {
                    ExplainPersona.TRADER: (
                        "Market data validated and ready. All prerequisites satisfied for research execution."
                    ),
                    ExplainPersona.ENGINEER: (
                        "All system gates passed. Datasets available, registry valid, "
                        "policy gates satisfied. Ready to start research execution."
                    ),
                    ExplainPersona.QA: (
                        "All quality gates passed. Ready to start research execution."
                    ),
                    ExplainPersona.PM: (
                        "All prerequisites satisfied. Ready to start research pipeline."
                    ),
                    ExplainPersona.EXEC: (
                        "Data systems ready for research execution."
                    ),
                },
                ResearchStage.RUN_RESEARCH: {
                    ExplainPersona.TRADER: (
                        "Research execution started. Strategy evaluation underway."
                    ),
                    ExplainPersona.ENGINEER: (
                        "Research jobs submitted and running/completed. "
                        "Artifacts being generated. Ready for outcome triage."
                    ),
                    ExplainPersona.QA: (
                        "Research execution proceeding as expected. Quality monitoring active."
                    ),
                    ExplainPersona.PM: (
                        "Research pipeline executing. Results expected upon completion."
                    ),
                    ExplainPersona.EXEC: (
                        "Research execution underway."
                    ),
                },
                ResearchStage.OUTCOME_TRIAGE: {
                    ExplainPersona.TRADER: (
                        "Research completed. Outcomes ready for analysis and candidate evaluation."
                    ),
                    ExplainPersona.ENGINEER: (
                        "Research completed with artifacts. "
                        "Gate summaries available for analysis. Ready for decision making."
                    ),
                    ExplainPersona.QA: (
                        "Research outcomes validated. Ready for quality assessment."
                    ),
                    ExplainPersona.PM: (
                        "Research outcomes available for business analysis and decision making."
                    ),
                    ExplainPersona.EXEC: (
                        "Research completed. Outcomes ready for evaluation."
                    ),
                },
                ResearchStage.DECISION: {
                    ExplainPersona.TRADER: (
                        "All admission gates passed. Ready for portfolio construction and allocation decisions."
                    ),
                    ExplainPersona.ENGINEER: (
                        "Outcomes triaged, candidates identified. "
                        "Portfolio build possible. Ready for final decisions."
                    ),
                    ExplainPersona.QA: (
                        "All quality gates passed. Ready for portfolio construction."
                    ),
                    ExplainPersona.PM: (
                        "All business gates passed. Ready for portfolio decisions based on ROI analysis."
                    ),
                    ExplainPersona.EXEC: (
                        "All gates passed. Ready for portfolio allocation decisions."
                    ),
                },
            }
            
            # Get persona-specific content or fallback to default
            stage_dict = success_messages.get(stage, {})
            why = stage_dict.get(persona, "Ready to proceed to next stage")
        
        # Apply quality normalization for persona tone consistency
        normalized_result = normalize_explanation_for_persona(why, persona)
        why = normalized_result.normalized_text
        
        # Enforce length constraint (after normalization)
        if len(why) > 400:
            why = why[:397] + "..."
        
        # Log normalization if changes were made
        if normalized_result.was_changed:
            logger.debug(
                f"Why explanation normalized for {persona.value}: "
                f"{len(normalized_result.applied_transformations)} transformations applied"
            )
        
        return why
    
    def _build_developer_view(
        self,
        stage: ResearchStage,
        is_blocked: bool,
        blocking_reason: Optional[GateReasonCode],
        explanation: Dict[str, Any],
        flow_state: ResearchFlowState,
        persona: ExplainPersona = None
    ) -> str:
        """
        Build developer view (<= 800 chars).
        
        Technical details tailored to persona.
        Applies quality normalization for persona tone consistency.
        """
        if persona is None:
            persona = get_default_persona()
        
        if is_blocked and blocking_reason:
            # Use full explanation from dictionary
            dev_view = explanation.get("developer_explanation", "No technical details available")
            
            # Add context details
            context_details = []
            if flow_state.system_context:
                for key, value in flow_state.system_context.items():
                    if key in ["error", "details", "reason"]:
                        context_details.append(f"{key}: {value}")
            
            if context_details:
                dev_view += f" Context: {', '.join(context_details)}"
            
            # Persona-specific enhancements for blocked state
            if persona == ExplainPersona.ENGINEER:
                dev_view += " [ENGINEER: Review system logs and error traces.]"
            elif persona == ExplainPersona.QA:
                dev_view += " [QA: Validate error reproducibility and test coverage.]"
            elif persona == ExplainPersona.TRADER:
                dev_view += " [TRADER: Technical issue may impact execution timing.]"
            elif persona == ExplainPersona.PM:
                dev_view += " [PM: Technical blocker affects feature delivery timeline.]"
            elif persona == ExplainPersona.EXEC:
                dev_view = f"Technical issue detected: {blocking_reason.value}. Engineering team investigating."
        else:
            # Success technical details with persona-specific content
            stage_details = {
                ResearchStage.DATA_READINESS: {
                    ExplainPersona.TRADER: (
                        "Data pipeline ready: datasets validated, registry operational. "
                        "Ready for research execution with current market conditions."
                    ),
                    ExplainPersona.ENGINEER: (
                        "System gates: dataset_available=True, registry_valid=True, "
                        "policy_gates_pass=True. All prerequisites satisfied for research execution."
                    ),
                    ExplainPersona.QA: (
                        "Data readiness validation passed: all quality gates satisfied. "
                        "Test coverage adequate for research execution."
                    ),
                    ExplainPersona.PM: (
                        "Data infrastructure operational. No blockers for research pipeline. "
                        "Expected delivery timeline on track."
                    ),
                    ExplainPersona.EXEC: (
                        "Data systems operational and ready for quantitative research."
                    ),
                },
                ResearchStage.RUN_RESEARCH: {
                    ExplainPersona.TRADER: (
                        f"Research execution active: {len(flow_state.system_context.get('research_jobs', []))} jobs running. "
                        "Monitor for completion and signal generation."
                    ),
                    ExplainPersona.ENGINEER: (
                        f"Research jobs: {len(flow_state.system_context.get('research_jobs', []))} "
                        f"jobs, artifacts: {len(flow_state.system_context.get('artifacts', {}))}. "
                        "Execution pipeline active."
                    ),
                    ExplainPersona.QA: (
                        f"Research execution in progress: {len(flow_state.system_context.get('research_jobs', []))} jobs. "
                        "Monitoring for completion and artifact generation."
                    ),
                    ExplainPersona.PM: (
                        "Research pipeline executing. Results expected upon completion. "
                        "Monitor progress for any timeline adjustments."
                    ),
                    ExplainPersona.EXEC: (
                        "Research execution underway. Results pending completion."
                    ),
                },
                ResearchStage.OUTCOME_TRIAGE: {
                    ExplainPersona.TRADER: (
                        f"Research completed: {len(flow_state.system_context.get('gate_summaries', []))} gate summaries available. "
                        "Analyzing outcomes for portfolio candidates."
                    ),
                    ExplainPersona.ENGINEER: (
                        f"Gate summaries: {len(flow_state.system_context.get('gate_summaries', []))} "
                        "available for analysis. Triage logic ready to evaluate candidate strategies."
                    ),
                    ExplainPersona.QA: (
                        f"Research outcomes ready for triage: {len(flow_state.system_context.get('gate_summaries', []))} gate summaries. "
                        "Validation process ready for candidate evaluation."
                    ),
                    ExplainPersona.PM: (
                        "Research outcomes available for analysis. "
                        "Candidate strategies identified for portfolio consideration."
                    ),
                    ExplainPersona.EXEC: (
                        "Research outcomes ready for evaluation and decision making."
                    ),
                },
                ResearchStage.DECISION: {
                    ExplainPersona.TRADER: (
                        f"Portfolio construction ready: {flow_state.system_context.get('admission_state', {}).get('candidate_count', 0)} candidates. "
                        "Proceed with allocation decisions."
                    ),
                    ExplainPersona.ENGINEER: (
                        f"Admission state: portfolio_build_possible="
                        f"{flow_state.system_context.get('admission_state', {}).get('portfolio_build_possible', False)}, "
                        f"candidate_count={flow_state.system_context.get('admission_state', {}).get('candidate_count', 0)}. "
                        "Decision engine ready."
                    ),
                    ExplainPersona.QA: (
                        f"Decision phase ready: {flow_state.system_context.get('admission_state', {}).get('candidate_count', 0)} validated candidates. "
                        "Quality gates passed for portfolio construction."
                    ),
                    ExplainPersona.PM: (
                        "Ready for portfolio decisions. Candidate strategies validated. "
                        "Proceed with allocation based on business priorities."
                    ),
                    ExplainPersona.EXEC: (
                        "Ready for final portfolio allocation decisions."
                    ),
                },
            }
            
            # Get persona-specific content or fallback to default
            stage_dict = stage_details.get(stage, {})
            dev_view = stage_dict.get(persona, "System operational")
        
        # Apply quality normalization for persona tone consistency
        normalized_result = normalize_explanation_for_persona(dev_view, persona)
        dev_view = normalized_result.normalized_text
        
        # Enforce length constraint (after normalization)
        if len(dev_view) > 800:
            dev_view = dev_view[:797] + "..."
        
        # Log normalization if changes were made
        if normalized_result.was_changed:
            logger.debug(
                f"Developer view normalized for {persona.value}: "
                f"{len(normalized_result.applied_transformations)} transformations applied"
            )
        
        return dev_view
    
    def _build_business_view(
        self,
        stage: ResearchStage,
        is_blocked: bool,
        blocking_reason: Optional[GateReasonCode],
        explanation: Dict[str, Any],
        flow_state: ResearchFlowState,
        persona: ExplainPersona = None
    ) -> str:
        """
        Build business view (<= 800 chars).
        
        Business impact explanation tailored to persona.
        Applies quality normalization for persona tone consistency.
        """
        if persona is None:
            persona = get_default_persona()
        
        if is_blocked and blocking_reason:
            # Use business impact from dictionary
            business_view = explanation.get("business_impact", "No business impact details available")
            
            # Add recommended action
            recommended_action = explanation.get("recommended_action", "Check system logs")
            business_view += f" Recommended action: {recommended_action}"
            
            # Persona-specific enhancements for blocked state
            if persona == ExplainPersona.TRADER:
                business_view += " [TRADER: Blocking issue may impact trade execution timing.]"
            elif persona == ExplainPersona.ENGINEER:
                business_view += " [ENGINEER: Technical blocker requires immediate resolution.]"
            elif persona == ExplainPersona.QA:
                business_view += " [QA: Quality issue detected, requires validation fix.]"
            elif persona == ExplainPersona.PM:
                business_view += " [PM: Feature delivery timeline impacted.]"
            elif persona == ExplainPersona.EXEC:
                business_view = f"Operational issue detected: {blocking_reason.value}. Team working on resolution."
        else:
            # Success business impact with persona-specific content
            business_impacts = {
                ResearchStage.DATA_READINESS: {
                    ExplainPersona.TRADER: (
                        "Market data pipeline ready. No delays expected for research execution. "
                        "Ready to generate trading signals upon completion."
                    ),
                    ExplainPersona.ENGINEER: (
                        "Research pipeline ready to start. No operational delays expected. "
                        "All prerequisites verified for successful execution."
                    ),
                    ExplainPersona.QA: (
                        "Quality gates passed for data readiness. No validation issues detected. "
                        "Ready for research execution with confidence."
                    ),
                    ExplainPersona.PM: (
                        "Data infrastructure operational. Research pipeline ready for execution. "
                        "Expected delivery timeline on track."
                    ),
                    ExplainPersona.EXEC: (
                        "Data systems ready for quantitative research execution."
                    ),
                },
                ResearchStage.RUN_RESEARCH: {
                    ExplainPersona.TRADER: (
                        "Research execution active. Strategy evaluation underway. "
                        "Trading signals expected upon completion."
                    ),
                    ExplainPersona.ENGINEER: (
                        "Research execution in progress. Strategy evaluation underway. "
                        "Results expected upon completion. Monitor progress for any issues."
                    ),
                    ExplainPersona.QA: (
                        "Research execution proceeding as expected. "
                        "Quality monitoring active for artifact generation."
                    ),
                    ExplainPersona.PM: (
                        "Research pipeline executing. Results expected upon completion. "
                        "Monitor progress for any timeline adjustments."
                    ),
                    ExplainPersona.EXEC: (
                        "Research execution underway. Results pending completion."
                    ),
                },
                ResearchStage.OUTCOME_TRIAGE: {
                    ExplainPersona.TRADER: (
                        "Research completed, outcomes ready for analysis. "
                        "Candidate strategies identified for portfolio consideration. "
                        "Evaluate for trading signal potential."
                    ),
                    ExplainPersona.ENGINEER: (
                        "Research completed, outcomes being analyzed. "
                        "Candidate strategies identified for portfolio consideration. "
                        "Decision quality depends on gate evaluation results."
                    ),
                    ExplainPersona.QA: (
                        "Research outcomes ready for quality assessment. "
                        "Candidate strategies validated against quality gates."
                    ),
                    ExplainPersona.PM: (
                        "Research outcomes available for business analysis. "
                        "Candidate strategies ready for portfolio consideration."
                    ),
                    ExplainPersona.EXEC: (
                        "Research outcomes ready for evaluation and portfolio decisions."
                    ),
                },
                ResearchStage.DECISION: {
                    ExplainPersona.TRADER: (
                        "Ready for portfolio construction. Candidate strategies validated. "
                        "Proceed with allocation based on risk-adjusted returns."
                    ),
                    ExplainPersona.ENGINEER: (
                        "Ready for portfolio construction and final decisions. "
                        "Candidate strategies validated, admission gates passed. "
                        "Proceed to build optimal portfolio allocation."
                    ),
                    ExplainPersona.QA: (
                        "Decision phase ready. Quality gates passed for all candidates. "
                        "Proceed with confidence in portfolio construction."
                    ),
                    ExplainPersona.PM: (
                        "Ready for portfolio decisions. Candidate strategies validated. "
                        "Proceed with allocation based on business priorities and ROI."
                    ),
                    ExplainPersona.EXEC: (
                        "Ready for final portfolio allocation decisions."
                    ),
                },
            }
            
            # Get persona-specific content or fallback to default
            stage_dict = business_impacts.get(stage, {})
            business_view = stage_dict.get(persona, "System operational, ready for next steps")
        
        # Apply quality normalization for persona tone consistency
        normalized_result = normalize_explanation_for_persona(business_view, persona)
        business_view = normalized_result.normalized_text
        
        # Enforce length constraint (after normalization)
        if len(business_view) > 800:
            business_view = business_view[:797] + "..."
        
        # Log normalization if changes were made
        if normalized_result.was_changed:
            logger.debug(
                f"Business view normalized for {persona.value}: "
                f"{len(normalized_result.applied_transformations)} transformations applied"
            )
        
        return business_view
    
    def _determine_next_step(
        self,
        stage: ResearchStage,
        is_blocked: bool,
        blocking_reason: Optional[GateReasonCode],
        flow_state: ResearchFlowState
    ) -> tuple[NarrativeActionId, str]:
        """
        Determine next step action and label.
        
        Returns:
            Tuple of (action_id, label)
        """
        if is_blocked:
            # Blocked state actions
            if blocking_reason:
                # Specific blocking reason
                return (
                    NarrativeActionId.OPEN_GATE_DASHBOARD,
                    "View blocking details"
                )
            else:
                # Silent blocking
                return (
                    NarrativeActionId.OPEN_DATA_READINESS,
                    "Check data readiness"
                )
        
        # Unblocked state actions
        stage_actions = {
            ResearchStage.DATA_READINESS: (
                NarrativeActionId.RUN_RESEARCH,
                "Start research execution"
            ),
            ResearchStage.RUN_RESEARCH: (
                NarrativeActionId.OPEN_GATE_DASHBOARD,
                "Monitor research progress"
            ),
            ResearchStage.OUTCOME_TRIAGE: (
                NarrativeActionId.OPEN_REPORT,
                "Analyze research outcomes"
            ),
            ResearchStage.DECISION: (
                NarrativeActionId.BUILD_PORTFOLIO,
                "Build portfolio allocation"
            ),
        }
        
        action_id, label = stage_actions.get(
            stage,
            (NarrativeActionId.OPEN_DATA_READINESS, "Check system status")
        )
        
        return action_id, label
    
    def _build_drilldown_actions(
        self,
        stage: ResearchStage,
        is_blocked: bool,
        blocking_reason: Optional[GateReasonCode],
        flow_state: ResearchFlowState
    ) -> List[Dict[str, str]]:
        """
        Build drilldown actions (max 5 items).
        
        Returns:
            List of dicts with 'action' and 'label' keys
        """
        actions = []
        
        if is_blocked:
            # Blocked state drilldown
            actions.append({
                "action": "view_evidence",
                "label": "View evidence artifacts"
            })
            actions.append({
                "action": "view_logs",
                "label": "Check system logs"
            })
            actions.append({
                "action": "retry_check",
                "label": "Retry system check"
            })
        else:
            # Unblocked state drilldown
            stage_drilldown = {
                ResearchStage.DATA_READINESS: [
                    {"action": "validate_datasets", "label": "Validate datasets"},
                    {"action": "check_registry", "label": "Check registry"},
                    {"action": "run_policy_gates", "label": "Run policy gates"},
                ],
                ResearchStage.RUN_RESEARCH: [
                    {"action": "view_job_status", "label": "View job status"},
                    {"action": "check_artifacts", "label": "Check artifacts"},
                    {"action": "run_triage", "label": "Run triage"},
                ],
                ResearchStage.OUTCOME_TRIAGE: [
                    {"action": "view_gate_summaries", "label": "View gate summaries"},
                    {"action": "analyze_results", "label": "Analyze results"},
                    {"action": "compare_candidates", "label": "Compare candidates"},
                ],
                ResearchStage.DECISION: [
                    {"action": "review_admission", "label": "Review admission"},
                    {"action": "execute_decisions", "label": "Execute decisions"},
                    {"action": "start_new_research", "label": "Start new research"},
                ],
            }
            
            actions.extend(stage_drilldown.get(stage, []))
        
        # Add common actions
        actions.append({
            "action": "open_documentation",
            "label": "Open documentation"
        })
        
        # Limit to 5 actions
        return actions[:5]
    
    def _get_evidence_references(self, flow_state: ResearchFlowState) -> List[str]:
        """
        Get evidence references from flow state.
        
        Returns:
            List of evidence reference strings (max 10)
        """
        evidence_refs = []
        
        # Add flow state evidence refs
        evidence_refs.extend(flow_state.evidence_refs)
        
        # Add system context evidence
        if flow_state.system_context:
            # Add job references
            for job in flow_state.system_context.get("research_jobs", []):
                if job_id := job.get("job_id"):
                    evidence_refs.append(f"job:{job_id}")
            
            # Add artifact references
            for artifact_id in flow_state.system_context.get("artifacts", {}).keys():
                evidence_refs.append(f"artifact:{artifact_id}")
            
            # Add gate summary references
            for i, summary in enumerate(flow_state.system_context.get("gate_summaries", [])):
                evidence_refs.append(f"gate_summary:{i}")
        
        # Limit to 10 references
        return evidence_refs[:10]
    
    # -------------------------------------------------------------------------
    # Public API Methods
    # -------------------------------------------------------------------------
    
    def get_narrative_for_stage(
        self,
        stage: ResearchStage,
        is_blocked: bool = False,
        blocking_reason: Optional[GateReasonCode] = None,
        system_context: Optional[Dict[str, Any]] = None,
        persona: ExplainPersona = None
    ) -> ResearchNarrativeV1:
        """
        Build narrative for specific stage (for testing/demo).
        
        Args:
            stage: Research stage
            is_blocked: Whether stage is blocked
            blocking_reason: Optional blocking reason
            system_context: Optional system context
            persona: Optional ExplainPersona for audience-specific content
            
        Returns:
            ResearchNarrativeV1: Narrative for specified stage
        """
        # Create mock flow state
        flow_state = ResearchFlowState(
            current_stage=stage,
            is_blocked=is_blocked,
            blocking_reason=blocking_reason,
            blocking_explain=None,
            allowed_actions=[],
            recommended_next_action=None,
            evidence_refs=[],
            system_context=system_context or {},
            evaluation_duration_ms=0,
        )
        
        return self.build_narrative(flow_state, persona)
    
    def validate_narrative_integrity(self, narrative: ResearchNarrativeV1) -> bool:
        """
        Validate narrative integrity.
        
        Args:
            narrative: Narrative to validate
            
        Returns:
            bool: True if narrative passes all integrity checks
        """
        try:
            # Validate narrative constraints
            narrative.validate_narrative()
            
            # Validate version matches
            if narrative.version != "v2.1.0":
                logger.warning(f"Narrative version mismatch: {narrative.version}")
                return False
            
            # Validate severity matches stage/blocking state
            expected_severity = self._determine_severity(
                narrative.stage != ResearchStage.DATA_READINESS,  # Simplified
                narrative.primary_reason_code
            )
            if narrative.severity != expected_severity:
                logger.warning(f"Severity mismatch: {narrative.severity} != {expected_severity}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Narrative integrity validation failed: {e}")
            return False
    
    def get_builder_info(self) -> Dict[str, Any]:
        """
        Get builder information.
        
        Returns:
            Dict with builder metadata
        """
        return {
            "builder_version": "v2.4.0",  # Updated for quality normalization
            "explain_dict_version": self._explain_dict_version,
            "supported_stages": [stage.value for stage in ResearchStage],
            "supported_action_ids": [action.value for action in NarrativeActionId],
            "supported_personas": [persona.value for persona in ExplainPersona],
            "default_persona": get_default_persona().value,
        }


# Singleton instance for easy access
_narrative_builder_singleton: Optional[ResearchNarrativeBuilder] = None


def get_narrative_builder() -> ResearchNarrativeBuilder:
    """
    Get singleton narrative builder instance.
    
    Returns:
        ResearchNarrativeBuilder: Singleton instance
    """
    global _narrative_builder_singleton
    
    if _narrative_builder_singleton is None:
        _narrative_builder_singleton = ResearchNarrativeBuilder()
    
    return _narrative_builder_singleton


def build_research_narrative(
    flow_state: ResearchFlowState,
    persona: ExplainPersona = None
) -> ResearchNarrativeV1:
    """
    Convenience function to build narrative from flow state.
    
    Args:
        flow_state: ResearchFlowState from kernel
        persona: Optional ExplainPersona for audience-specific content
        
    Returns:
        ResearchNarrativeV1: Frozen narrative model
    """
    builder = get_narrative_builder()
    return builder.build_narrative(flow_state, persona)


def get_stage_narrative(
    stage: ResearchStage,
    is_blocked: bool = False,
    blocking_reason: Optional[GateReasonCode] = None,
    system_context: Optional[Dict[str, Any]] = None,
    persona: ExplainPersona = None
) -> ResearchNarrativeV1:
    """
    Convenience function to get narrative for specific stage.
    
    Args:
        stage: Research stage
        is_blocked: Whether stage is blocked
        blocking_reason: Optional blocking reason
        system_context: Optional system context
        persona: Optional ExplainPersona for audience-specific content
        
    Returns:
        ResearchNarrativeV1: Narrative for specified stage
    """
    builder = get_narrative_builder()
    return builder.get_narrative_for_stage(stage, is_blocked, blocking_reason, system_context, persona)