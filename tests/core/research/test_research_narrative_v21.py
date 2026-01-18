"""
Research Narrative Layer v2.1 Governance Tests

Tests for the human-readable narrative layer that sits on top of Research OS Kernel.
Validates SSOT contracts, frozen models, length constraints, and integration with Explain Dictionary.

NON-NEGOTIABLE CONSTITUTION:
- Kernel remains SSOT for truth. Narrative must not change state.
- Narrative must be pure function of Kernel output (+ optional evidence lookups)
- Every narrative MUST output: headline, why, next_step
- Must support Developer View and Business View (reuse v1.4 dictionary style)
- Must be frozen models (ConfigDict(frozen=True))
- Must terminate deterministically (make check), no servers
"""

import pytest
from unittest.mock import Mock, patch

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
from core.research.research_narrative_builder import (
    ResearchNarrativeBuilder,
    build_research_narrative,
    get_narrative_builder,
    get_stage_narrative,
)


class TestResearchNarrativeV1Contracts:
    """Test SSOT contracts for ResearchNarrativeV1."""
    
    def test_model_is_frozen(self):
        """Test that ResearchNarrativeV1 model is frozen."""
        narrative = ResearchNarrativeV1(
            stage=ResearchStage.DATA_READINESS,
            severity="OK",
            headline="Test headline",
            why="Test why",
            primary_reason_code=GateReasonCode.GATE_ITEM_PARSE_ERROR,
            developer_view="Test developer view",
            business_view="Test business view",
            next_step_action=NarrativeActionId.OPEN_DATA_READINESS,
            next_step_label="Test next step",
        )
        
        # Verify model is frozen (cannot modify attributes)
        with pytest.raises(Exception):
            narrative.stage = ResearchStage.RUN_RESEARCH
        
        # Verify ConfigDict has frozen=True
        assert narrative.model_config.get("frozen") is True
    
    def test_version_must_be_v210(self):
        """Test that narrative version must be v2.1.0."""
        narrative = ResearchNarrativeV1(
            version="v2.1.0",
            stage=ResearchStage.DATA_READINESS,
            severity="OK",
            headline="Test headline",
            why="Test why",
            primary_reason_code=GateReasonCode.GATE_ITEM_PARSE_ERROR,
            developer_view="Test developer view",
            business_view="Test business view",
            next_step_action=NarrativeActionId.OPEN_DATA_READINESS,
            next_step_label="Test next step",
        )
        
        assert narrative.version == "v2.1.0"
    
    def test_length_constraints(self):
        """Test narrative length constraints."""
        # Valid narrative (within constraints)
        narrative = create_narrative(
            stage=ResearchStage.DATA_READINESS,
            severity="OK",
            headline="Short headline" * 5,  # ~70 chars
            why="Short why" * 20,  # ~200 chars
            primary_reason_code=GateReasonCode.GATE_ITEM_PARSE_ERROR,
            developer_view="Dev view" * 50,  # ~400 chars
            business_view="Business view" * 40,  # ~560 chars
            next_step_action=NarrativeActionId.OPEN_DATA_READINESS,
            next_step_label="Next step",
        )
        
        # Should not raise exception
        narrative.validate_narrative()
        
        # Test headline too long
        with pytest.raises(ValueError, match="Headline exceeds 120 characters"):
            create_narrative(
                stage=ResearchStage.DATA_READINESS,
                severity="OK",
                headline="x" * 121,  # 121 chars
                why="Test why",
                primary_reason_code=GateReasonCode.GATE_ITEM_PARSE_ERROR,
                developer_view="Test developer view",
                business_view="Test business view",
                next_step_action=NarrativeActionId.OPEN_DATA_READINESS,
                next_step_label="Test next step",
            )
    
    def test_severity_constraints(self):
        """Test severity constraints."""
        # Non-OK severity must have non-empty why
        with pytest.raises(ValueError, match="must have non-empty 'why'"):
            create_narrative(
                stage=ResearchStage.DATA_READINESS,
                severity="BLOCKED",
                headline="Test headline",
                why="",  # Empty why for BLOCKED severity
                primary_reason_code=GateReasonCode.GATE_ITEM_PARSE_ERROR,
                developer_view="Test developer view",
                business_view="Test business view",
                next_step_action=NarrativeActionId.OPEN_DATA_READINESS,
                next_step_label="Test next step",
            )
    
    def test_drilldown_actions_constraint(self):
        """Test drilldown actions constraint (max 5)."""
        # 6 actions should fail
        drilldown_actions = [
            {"action": f"action_{i}", "label": f"Label {i}"}
            for i in range(6)
        ]
        
        with pytest.raises(ValueError, match="Drilldown actions exceed maximum of 5"):
            create_narrative(
                stage=ResearchStage.DATA_READINESS,
                severity="OK",
                headline="Test headline",
                why="Test why",
                primary_reason_code=GateReasonCode.GATE_ITEM_PARSE_ERROR,
                developer_view="Test developer view",
                business_view="Test business view",
                next_step_action=NarrativeActionId.OPEN_DATA_READINESS,
                next_step_label="Test next step",
                drilldown_actions=drilldown_actions,
            )
    
    def test_evidence_refs_constraint(self):
        """Test evidence references constraint (max 10)."""
        # 11 evidence refs should fail
        evidence_refs = [f"evidence_{i}" for i in range(11)]
        
        with pytest.raises(ValueError, match="Evidence references exceed maximum of 10"):
            create_narrative(
                stage=ResearchStage.DATA_READINESS,
                severity="OK",
                headline="Test headline",
                why="Test why",
                primary_reason_code=GateReasonCode.GATE_ITEM_PARSE_ERROR,
                developer_view="Test developer view",
                business_view="Test business view",
                next_step_action=NarrativeActionId.OPEN_DATA_READINESS,
                next_step_label="Test next step",
                evidence_refs=evidence_refs,
            )


class TestResearchNarrativeBuilder:
    """Test Research Narrative Builder core logic."""
    
    def test_builder_initialization(self):
        """Test narrative builder initialization."""
        builder = ResearchNarrativeBuilder()
        assert builder is not None
        
        # Verify builder has explain dictionary version
        info = builder.get_builder_info()
        assert "builder_version" in info
        assert info["builder_version"] == "v2.1.0"
        assert "explain_dict_version" in info
    
    def test_build_narrative_from_flow_state(self):
        """Test building narrative from ResearchFlowState."""
        builder = ResearchNarrativeBuilder()
        
        # Create mock flow state
        flow_state = ResearchFlowState(
            current_stage=ResearchStage.DATA_READINESS,
            is_blocked=False,
            blocking_reason=None,
            blocking_explain=None,
            allowed_actions=["run_research"],
            recommended_next_action="Start research",
            evidence_refs=["evidence:test"],
            system_context={
                "system_gates": {"dataset_available": True},
                "research_jobs": [],
                "artifacts": {},
            },
            evaluation_duration_ms=100,
        )
        
        # Build narrative
        narrative = builder.build_narrative(flow_state)
        
        # Verify narrative properties
        assert isinstance(narrative, ResearchNarrativeV1)
        assert narrative.stage == ResearchStage.DATA_READINESS
        assert narrative.severity == "OK"
        assert narrative.headline is not None
        assert narrative.why is not None
        assert narrative.developer_view is not None
        assert narrative.business_view is not None
        assert narrative.next_step_label is not None
    
    def test_build_narrative_blocked_state(self):
        """Test building narrative for blocked state."""
        builder = ResearchNarrativeBuilder()
        
        # Create blocked flow state
        flow_state = ResearchFlowState(
            current_stage=ResearchStage.DATA_READINESS,
            is_blocked=True,
            blocking_reason=GateReasonCode.GATE_SUMMARY_FETCH_ERROR,
            blocking_explain="Failed to fetch gate summary",
            allowed_actions=["view_explanation"],
            recommended_next_action="Fix the issue",
            evidence_refs=[],
            system_context={
                "error": "Network timeout",
                "details": "Backend unavailable",
            },
            evaluation_duration_ms=50,
        )
        
        # Build narrative
        narrative = builder.build_narrative(flow_state)
        
        # Verify blocked narrative properties
        assert narrative.severity == "BLOCKED"
        assert narrative.primary_reason_code == GateReasonCode.GATE_SUMMARY_FETCH_ERROR
        assert "blocked" in narrative.headline.lower() or "fetch" in narrative.headline.lower()
    
    def test_determine_severity_logic(self):
        """Test severity determination logic."""
        builder = ResearchNarrativeBuilder()
        
        # Test cases
        test_cases = [
            # (is_blocked, blocking_reason, expected_severity)
            (False, None, "OK"),
            (True, GateReasonCode.GATE_SUMMARY_FETCH_ERROR, "BLOCKED"),
            (True, None, "WARN"),  # Silent blocking
        ]
        
        for is_blocked, blocking_reason, expected_severity in test_cases:
            severity = builder._determine_severity(is_blocked, blocking_reason)
            assert severity == expected_severity
    
    def test_get_primary_reason_code(self):
        """Test primary reason code determination."""
        builder = ResearchNarrativeBuilder()
        
        # Blocked state should use blocking_reason
        reason_code = builder._get_primary_reason_code(
            ResearchStage.DATA_READINESS,
            is_blocked=True,
            blocking_reason=GateReasonCode.GATE_SUMMARY_FETCH_ERROR,
        )
        assert reason_code == GateReasonCode.GATE_SUMMARY_FETCH_ERROR
        
        # Unblocked state should use stage-specific fallback
        reason_code = builder._get_primary_reason_code(
            ResearchStage.DATA_READINESS,
            is_blocked=False,
            blocking_reason=None,
        )
        assert reason_code is not None
    
    @patch("core.research.research_narrative_builder.get_gate_reason_explanation")
    def test_get_explanation_with_context(self, mock_get_explanation):
        """Test getting explanation with context variables."""
        builder = ResearchNarrativeBuilder()
        
        # Setup mock
        mock_get_explanation.return_value = {
            "developer_explanation": "Test explanation {stage}",
            "business_impact": "Business impact",
            "recommended_action": "Recommended action",
            "severity": "ERROR",
            "audience": "dev",
        }
        
        # Create flow state with context
        flow_state = ResearchFlowState(
            current_stage=ResearchStage.DATA_READINESS,
            is_blocked=True,
            blocking_reason=GateReasonCode.GATE_SUMMARY_FETCH_ERROR,
            blocking_explain=None,
            allowed_actions=[],
            recommended_next_action=None,
            evidence_refs=[],
            system_context={
                "error": "Network timeout",
                "details": "Backend unavailable",
            },
            evaluation_duration_ms=0,
        )
        
        # Get explanation
        explanation = builder._get_explanation_with_context(
            GateReasonCode.GATE_SUMMARY_FETCH_ERROR,
            flow_state,
        )
        
        # Verify explanation was called with context variables
        mock_get_explanation.assert_called_once()
        call_args = mock_get_explanation.call_args
        assert call_args[0][0] == GateReasonCode.GATE_SUMMARY_FETCH_ERROR.value
        assert "context_vars" in call_args[1]
        context_vars = call_args[1]["context_vars"]
        assert "stage" in context_vars
        assert "error" in context_vars
        assert context_vars["error"] == "Network timeout"
    
    def test_build_headline_length_constraint(self):
        """Test headline building with length constraint."""
        builder = ResearchNarrativeBuilder()
        
        # Create a long headline scenario
        headline = builder._build_headline(
            stage=ResearchStage.DATA_READINESS,
            is_blocked=True,
            blocking_reason=GateReasonCode.GATE_SUMMARY_FETCH_ERROR,
        )
        
        # Headline should be <= 120 chars
        assert len(headline) <= 120
        
        # If headline was truncated, it should end with "..."
        if len(headline) == 120:
            assert headline.endswith("...")
    
    def test_build_why_explanation_length_constraint(self):
        """Test why explanation building with length constraint."""
        builder = ResearchNarrativeBuilder()
        
        # Mock explanation with long text
        explanation = {
            "developer_explanation": "x" * 500,  # 500 chars
            "business_impact": "Business impact",
            "recommended_action": "Recommended action",
            "severity": "ERROR",
            "audience": "dev",
        }
        
        why = builder._build_why_explanation(
            stage=ResearchStage.DATA_READINESS,
            is_blocked=True,
            blocking_reason=GateReasonCode.GATE_SUMMARY_FETCH_ERROR,
            explanation=explanation,
        )
        
        # Why should be <= 400 chars
        assert len(why) <= 400
    
    def test_determine_next_step(self):
        """Test next step determination."""
        builder = ResearchNarrativeBuilder()
        
        # Test blocked state
        flow_state = ResearchFlowState(
            current_stage=ResearchStage.DATA_READINESS,
            is_blocked=True,
            blocking_reason=GateReasonCode.GATE_SUMMARY_FETCH_ERROR,
            blocking_explain=None,
            allowed_actions=[],
            recommended_next_action=None,
            evidence_refs=[],
            system_context={},
            evaluation_duration_ms=0,
        )
        
        action_id, label = builder._determine_next_step(
            ResearchStage.DATA_READINESS,
            is_blocked=True,
            blocking_reason=GateReasonCode.GATE_SUMMARY_FETCH_ERROR,
            flow_state=flow_state,
        )
        
        assert action_id == NarrativeActionId.OPEN_GATE_DASHBOARD
        assert label == "View blocking details"
        
        # Test unblocked DATA_READINESS stage
        action_id, label = builder._determine_next_step(
            ResearchStage.DATA_READINESS,
            is_blocked=False,
            blocking_reason=None,
            flow_state=flow_state,
        )
        
        assert action_id == NarrativeActionId.RUN_RESEARCH
        assert label == "Start research execution"
    
    def test_build_drilldown_actions(self):
        """Test drilldown actions building."""
        builder = ResearchNarrativeBuilder()
        
        flow_state = ResearchFlowState(
            current_stage=ResearchStage.DATA_READINESS,
            is_blocked=False,
            blocking_reason=None,
            blocking_explain=None,
            allowed_actions=[],
            recommended_next_action=None,
            evidence_refs=[],
            system_context={},
            evaluation_duration_ms=0,
        )
        
        actions = builder._build_drilldown_actions(
            ResearchStage.DATA_READINESS,
            is_blocked=False,
            blocking_reason=None,
            flow_state=flow_state,
        )
        
        # Should have stage-specific actions + common action
        assert len(actions) <= 5
        assert any("documentation" in action.get("action", "") for action in actions)
    
    def test_get_evidence_references(self):
        """Test evidence references extraction."""
        builder = ResearchNarrativeBuilder()
        
        flow_state = ResearchFlowState(
            current_stage=ResearchStage.DATA_READINESS,
            is_blocked=False,
            blocking_reason=None,
            blocking_explain=None,
            allowed_actions=[],
            recommended_next_action=None,
            evidence_refs=["existing:evidence"],
            system_context={
                "research_jobs": [{"job_id": "job1"}, {"job_id": "job2"}],
                "artifacts": {"artifact1": {}, "artifact2": {}},
                "gate_summaries": [{}, {}],
            },
            evaluation_duration_ms=0,
        )
        
        evidence_refs = builder._get_evidence_references(flow_state)
        
        # Should include all evidence references
        assert "existing:evidence" in evidence_refs
        assert "job:job1" in evidence_refs
        assert "job:job2" in evidence_refs
        assert "artifact:artifact1" in evidence_refs
        assert "artifact:artifact2" in evidence_refs
        assert "gate_summary:0" in evidence_refs
        assert "gate_summary:1" in evidence_refs
        
        # Should be limited to 10 references
        assert len(evidence_refs) <= 10
    
    def test_validate_narrative_integrity(self):
        """Test narrative integrity validation."""
        builder = ResearchNarrativeBuilder()
        
        # Create valid narrative
        narrative = create_narrative(
            stage=ResearchStage.DATA_READINESS,
            severity="OK",
            headline="Test headline",
            why="Test why",
            primary_reason_code=GateReasonCode.GATE_ITEM_PARSE_ERROR,
            developer_view="Test developer view",
            business_view="Test business view",
            next_step_action=NarrativeActionId.OPEN_DATA_READINESS,
            next_step_label="Test next step",
        )
        
        # Should pass validation
        assert builder.validate_narrative_integrity(narrative) is True
        
        # Create invalid narrative (wrong version)
        invalid_narrative = narrative.model_copy(update={"version": "v1.0.0"})
        assert builder.validate_narrative_integrity(invalid_narrative) is False


class TestConvenienceFunctions:
    """Test convenience functions."""
    
    def test_get_narrative_builder_singleton(self):
        """Test singleton pattern for narrative builder."""
        builder1 = get_narrative_builder()
        builder2 = get_narrative_builder()
        
        # Should be the same instance
        assert builder1 is builder2
        
        # Should be ResearchNarrativeBuilder instance
        assert isinstance(builder1, ResearchNarrativeBuilder)
    
    def test_build_research_narrative_function(self):
        """Test build_research_narrative convenience function."""
        # Create mock flow state
        flow_state = ResearchFlowState(
            current_stage=ResearchStage.DATA_READINESS,
            is_blocked=False,
            blocking_reason=None,
            blocking_explain=None,
            allowed_actions=[],
            recommended_next_action=None,
            evidence_refs=[],
            system_context={},
            evaluation_duration_ms=0,
        )
        
        # Build narrative using convenience function
        narrative = build_research_narrative(flow_state)
        
        # Should return ResearchNarrativeV1
        assert isinstance(narrative, ResearchNarrativeV1)
        assert narrative.stage == ResearchStage.DATA_READINESS
    
    def test_get_stage_narrative_function(self):
        """Test get_stage_narrative convenience function."""
        # Get narrative for specific stage
        narrative = get_stage_narrative(
            stage=ResearchStage.DATA_READINESS,
            is_blocked=False,
            blocking_reason=None,
            system_context={"test": "value"},
        )
        
        # Should return ResearchNarrativeV1
        assert isinstance(narrative, ResearchNarrativeV1)
        assert narrative.stage == ResearchStage.DATA_READINESS
        assert narrative.severity == "OK"
    
    def test_get_stage_narrative_blocked(self):
        """Test get_stage_narrative for blocked state."""
        # Get narrative for blocked state
        narrative = get_stage_narrative(
            stage=ResearchStage.DATA_READINESS,
            is_blocked=True,
            blocking_reason=GateReasonCode.GATE_SUMMARY_FETCH_ERROR,
            system_context={"error": "Network timeout"},
        )
        
        # Should be blocked narrative
        assert narrative.severity == "BLOCKED"
        assert narrative.primary_reason_code == GateReasonCode.GATE_SUMMARY_FETCH_ERROR


class TestIntegrationWithExplainDictionary:
    """Test integration with Explain Dictionary v1.4+."""
    
    @patch("core.research.research_narrative_builder.get_gate_reason_explanation")
    def test_explain_dictionary_integration(self, mock_get_explanation):
        """Test that narrative builder uses Explain Dictionary."""
        builder = ResearchNarrativeBuilder()
        
        # Setup mock to return explanation
        mock_get_explanation.return_value = {
            "developer_explanation": "Test explanation from dictionary",
            "business_impact": "Test business impact",
            "recommended_action": "Test recommended action",
            "severity": "ERROR",
            "audience": "both",
        }
        
        # Create flow state
        flow_state = ResearchFlowState(
            current_stage=ResearchStage.DATA_READINESS,
            is_blocked=True,
            blocking_reason=GateReasonCode.GATE_SUMMARY_FETCH_ERROR,
            blocking_explain=None,
            allowed_actions=[],
            recommended_next_action=None,
            evidence_refs=[],
            system_context={},
            evaluation_duration_ms=0,
        )
        
        # Build narrative
        narrative = builder.build_narrative(flow_state)
        
        # Verify Explain Dictionary was called
        mock_get_explanation.assert_called_once()
        
        # Narrative should incorporate dictionary content
        assert narrative is not None
        assert narrative.developer_view is not None
        assert narrative.business_view is not None
    
    def test_explain_dictionary_context_variables(self):
        """Test that context variables are passed to Explain Dictionary."""
        builder = ResearchNarrativeBuilder()
        
        # We'll test this by checking the internal method
        flow_state = ResearchFlowState(
            current_stage=ResearchStage.DATA_READINESS,
            is_blocked=True,
            blocking_reason=GateReasonCode.GATE_SUMMARY_FETCH_ERROR,
            blocking_explain=None,
            allowed_actions=[],
            recommended_next_action=None,
            evidence_refs=[],
            system_context={
                "error": "Network timeout",
                "details": "Backend unavailable on port 8080",
            },
            evaluation_duration_ms=150,
        )
        
        # Get explanation with context
        explanation = builder._get_explanation_with_context(
            GateReasonCode.GATE_SUMMARY_FETCH_ERROR,
            flow_state,
        )
        
        # Explanation should be a dict (either from mock or real dictionary)
        assert isinstance(explanation, dict)
        assert "developer_explanation" in explanation
        assert "business_impact" in explanation
        assert "recommended_action" in explanation


class TestNarrativeLayerConstitution:
    """Test NON-NEGOTIABLE CONSTITUTION rules."""
    
    def test_pure_function_requirement(self):
        """Test that narrative builder is pure function (no side effects)."""
        builder = ResearchNarrativeBuilder()
        
        # Create identical flow states
        flow_state1 = ResearchFlowState(
            current_stage=ResearchStage.DATA_READINESS,
            is_blocked=False,
            blocking_reason=None,
            blocking_explain=None,
            allowed_actions=[],
            recommended_next_action=None,
            evidence_refs=[],
            system_context={"value": 42},
            evaluation_duration_ms=100,
        )
        
        flow_state2 = ResearchFlowState(
            current_stage=ResearchStage.DATA_READINESS,
            is_blocked=False,
            blocking_reason=None,
            blocking_explain=None,
            allowed_actions=[],
            recommended_next_action=None,
            evidence_refs=[],
            system_context={"value": 42},
            evaluation_duration_ms=100,
        )
        
        # Build narratives for identical states
        narrative1 = builder.build_narrative(flow_state1)
        narrative2 = builder.build_narrative(flow_state2)
        
        # Narratives should be identical (deterministic)
        assert narrative1.headline == narrative2.headline
        assert narrative1.why == narrative2.why
        assert narrative1.next_step_label == narrative2.next_step_label
    
    def test_no_state_modification(self):
        """Test that narrative builder does not modify input state."""
        builder = ResearchNarrativeBuilder()
        
        # Create flow state with specific values
        original_context = {"value": 42, "test": "original"}
        flow_state = ResearchFlowState(
            current_stage=ResearchStage.DATA_READINESS,
            is_blocked=False,
            blocking_reason=None,
            blocking_explain=None,
            allowed_actions=[],
            recommended_next_action=None,
            evidence_refs=[],
            system_context=original_context.copy(),  # Make a copy
            evaluation_duration_ms=100,
        )
        
        # Build narrative
        narrative = builder.build_narrative(flow_state)
        
        # Input state should not be modified
        assert flow_state.system_context == original_context
        assert flow_state.current_stage == ResearchStage.DATA_READINESS
        assert flow_state.is_blocked is False
        
        # Narrative should be a new object
        assert narrative is not flow_state
    
    def test_termination_requirement(self):
        """Test that narrative builder terminates deterministically."""
        builder = ResearchNarrativeBuilder()
        
        # Create simple flow state
        flow_state = ResearchFlowState(
            current_stage=ResearchStage.DATA_READINESS,
            is_blocked=False,
            blocking_reason=None,
            blocking_explain=None,
            allowed_actions=[],
            recommended_next_action=None,
            evidence_refs=[],
            system_context={},
            evaluation_duration_ms=0,
        )
        
        # Build narrative (should complete quickly)
        import time
        start_time = time.time()
        
        narrative = builder.build_narrative(flow_state)
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Should complete in reasonable time (not a daemon)
        assert duration < 1.0  # Less than 1 second
        
        # Should return valid narrative
        assert isinstance(narrative, ResearchNarrativeV1)
    
    def test_frozen_model_requirement(self):
        """Test that narrative models are frozen."""
        narrative = create_narrative(
            stage=ResearchStage.DATA_READINESS,
            severity="OK",
            headline="Test headline",
            why="Test why",
            primary_reason_code=GateReasonCode.GATE_ITEM_PARSE_ERROR,
            developer_view="Test developer view",
            business_view="Test business view",
            next_step_action=NarrativeActionId.OPEN_DATA_READINESS,
            next_step_label="Test next step",
        )
        
        # Verify model is frozen
        assert narrative.model_config.get("frozen") is True
        
        # Attempt to modify should raise exception
        with pytest.raises(Exception):
            narrative.headline = "Modified headline"
    
    def test_length_constraints_enforced(self):
        """Test that all length constraints are enforced."""
        builder = ResearchNarrativeBuilder()
        
        # Create flow state
        flow_state = ResearchFlowState(
            current_stage=ResearchStage.DATA_READINESS,
            is_blocked=False,
            blocking_reason=None,
            blocking_explain=None,
            allowed_actions=[],
            recommended_next_action=None,
            evidence_refs=[],
            system_context={},
            evaluation_duration_ms=0,
        )
        
        # Build narrative
        narrative = builder.build_narrative(flow_state)
        
        # Verify length constraints
        assert len(narrative.headline) <= 120
        assert len(narrative.why) <= 400
        assert len(narrative.developer_view) <= 800
        assert len(narrative.business_view) <= 800
        assert len(narrative.drilldown_actions) <= 5
        assert len(narrative.evidence_refs) <= 10
        
        # Validate narrative
        narrative.validate_narrative()  # Should not raise exception


class TestUICompatibility:
    """Test compatibility with UI requirements."""
    
    def test_ui_summary_method(self):
        """Test get_ui_summary method for UI consumption."""
        narrative = create_narrative(
            stage=ResearchStage.DATA_READINESS,
            severity="OK",
            headline="Test headline for UI",
            why="Test why explanation for UI",
            primary_reason_code=GateReasonCode.GATE_ITEM_PARSE_ERROR,
            developer_view="Detailed developer view",
            business_view="Detailed business view",
            next_step_action=NarrativeActionId.OPEN_DATA_READINESS,
            next_step_label="Open data readiness panel",
        )
        
        # Get UI summary
        ui_summary = narrative.get_ui_summary()
        
        # Should contain required fields for UI
        assert "headline" in ui_summary
        assert "why" in ui_summary
        assert "next_step" in ui_summary
        assert "severity" in ui_summary
        
        # Fields should match narrative
        assert ui_summary["headline"] == narrative.headline
        assert ui_summary["why"] == narrative.why
        assert ui_summary["next_step"] == narrative.next_step_label
        assert ui_summary["severity"] == narrative.severity
    
    def test_stable_action_ids(self):
        """Test that action IDs are stable for UI mapping."""
        # All action IDs should be strings
        for action_id in NarrativeActionId:
            assert isinstance(action_id.value, str)
            
            # Should be in lowercase with underscores
            assert action_id.value.islower() or "_" in action_id.value
            
            # Should not contain spaces (stable for UI mapping)
            assert " " not in action_id.value
        
        # Verify specific action IDs exist
        expected_actions = [
            "open_data_readiness",
            "run_research",
            "open_gate_dashboard",
            "open_report",
            "open_audit",
            "build_portfolio",
            "open_admission",
            "retry_last",
        ]
        
        for expected_action in expected_actions:
            assert NarrativeActionId(expected_action) is not None
    
    def test_to_dict_serialization(self):
        """Test narrative serialization to dict."""
        narrative = create_narrative(
            stage=ResearchStage.DATA_READINESS,
            severity="OK",
            headline="Test headline",
            why="Test why",
            primary_reason_code=GateReasonCode.GATE_ITEM_PARSE_ERROR,
            developer_view="Test developer view",
            business_view="Test business view",
            next_step_action=NarrativeActionId.OPEN_DATA_READINESS,
            next_step_label="Test next step",
        )
        
        # Convert to dict
        narrative_dict = narrative.to_dict()
        
        # Should contain all required fields
        assert "version" in narrative_dict
        assert "stage" in narrative_dict
        assert "severity" in narrative_dict
        assert "headline" in narrative_dict
        assert "why" in narrative_dict
        assert "primary_reason_code" in narrative_dict
        assert "developer_view" in narrative_dict
        assert "business_view" in narrative_dict
        assert "next_step_action" in narrative_dict
        assert "next_step_label" in narrative_dict
        assert "drilldown_actions" in narrative_dict
        assert "evidence_refs" in narrative_dict
        
        # Values should match
        assert narrative_dict["stage"] == narrative.stage.value
        assert narrative_dict["severity"] == narrative.severity
        assert narrative_dict["headline"] == narrative.headline
        assert narrative_dict["why"] == narrative.why
        assert narrative_dict["primary_reason_code"] == narrative.primary_reason_code.value
        assert narrative_dict["next_step_action"] == narrative.next_step_action.value
        assert narrative_dict["next_step_label"] == narrative.next_step_label


if __name__ == "__main__":
    pytest.main([__file__, "-v"])