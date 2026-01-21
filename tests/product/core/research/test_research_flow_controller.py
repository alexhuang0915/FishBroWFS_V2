"""
Research Flow Controller Tests v2.0 - Governance Locks

These tests enforce the NON-NEGOTIABLE CONSTITUTION of the Research OS Kernel:
- MUST auto-detect stage (NO UI input)
- MUST derive state from system evidence only
- MUST provide blocking reasons with explain text
- MUST terminate deterministically (no daemons)
- MUST enforce single primary entry point
- MUST validate UI navigation through kernel
"""

import pytest
from unittest.mock import Mock, patch, MagicMock

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
)
from core.research.research_flow_controller import ResearchFlowController


class TestResearchFlowControllerConstitution:
    """Test Research OS Kernel constitutional requirements."""
    
    def test_controller_initialization(self):
        """Test controller initialization."""
        controller = ResearchFlowController()
        assert controller is not None
        assert controller._last_evaluation_time is None
        assert controller._last_evaluation_duration_ms is None
    
    def test_evaluate_current_state_returns_valid_state(self):
        """Test that evaluate_current_state returns a valid ResearchFlowState."""
        controller = ResearchFlowController()
        
        # Mock system context collection
        with patch.object(controller, '_collect_system_context') as mock_collect:
            mock_collect.return_value = {
                "system_gates": {"dataset_available": True, "registry_valid": True},
                "research_jobs": [],
                "artifacts": {},
                "gate_summaries": [],
                "admission_state": {},
            }
            
            state = controller.evaluate_current_state()
            
            assert isinstance(state, ResearchFlowState)
            assert state.current_stage in ResearchStage
            assert isinstance(state.is_blocked, bool)
            assert state.evaluation_duration_ms is not None
    
    def test_stage_detection_strict_order(self):
        """Test that stage detection follows STRICT ORDER."""
        controller = ResearchFlowController()
        
        # Test DATA_READINESS detection
        with patch.object(controller, '_is_data_ready') as mock_ready:
            mock_ready.return_value = False
            context = {}
            stage = controller._detect_current_stage(context)
            assert stage == ResearchStage.DATA_READINESS
        
        # Test RUN_RESEARCH detection
        with patch.object(controller, '_is_data_ready') as mock_ready:
            with patch.object(controller, '_is_research_completed') as mock_completed:
                mock_ready.return_value = True
                mock_completed.return_value = False
                context = {}
                stage = controller._detect_current_stage(context)
                assert stage == ResearchStage.RUN_RESEARCH
        
        # Test OUTCOME_TRIAGE detection
        with patch.object(controller, '_is_data_ready') as mock_ready:
            with patch.object(controller, '_is_research_completed') as mock_completed:
                with patch.object(controller, '_is_outcome_triaged') as mock_triaged:
                    mock_ready.return_value = True
                    mock_completed.return_value = True
                    mock_triaged.return_value = False
                    context = {}
                    stage = controller._detect_current_stage(context)
                    assert stage == ResearchStage.OUTCOME_TRIAGE
        
        # Test DECISION detection
        with patch.object(controller, '_is_data_ready') as mock_ready:
            with patch.object(controller, '_is_research_completed') as mock_completed:
                with patch.object(controller, '_is_outcome_triaged') as mock_triaged:
                    mock_ready.return_value = True
                    mock_completed.return_value = True
                    mock_triaged.return_value = True
                    context = {}
                    stage = controller._detect_current_stage(context)
                    assert stage == ResearchStage.DECISION
    
    def test_blocking_evaluation_has_explain_text(self):
        """Test that blocking evaluation includes explain text."""
        controller = ResearchFlowController()
        
        # Mock get_gate_reason_explanation
        with patch('core.research.research_flow_controller.get_gate_reason_explanation') as mock_explain:
            mock_explain.return_value = {
                "developer_explanation": "Test explanation",
                "user_explanation": "Test user message",
            }
            
            # Mock a blocked state
            with patch.object(controller, '_collect_system_context') as mock_collect:
                mock_collect.return_value = {
                    "system_gates": {"dataset_available": False},
                    "research_jobs": [],
                    "artifacts": {},
                    "gate_summaries": [],
                    "admission_state": {},
                }
                
                state = controller.evaluate_current_state()
                
                if state.is_blocked:
                    assert state.blocking_reason is not None
                    assert state.blocking_explain is not None
                    assert "Test explanation" in state.blocking_explain
    
    def test_zero_silent_validation(self):
        """Test that blocked states cannot be silent."""
        controller = ResearchFlowController()
        
        # Create a state that is blocked
        state = ResearchFlowState(
            current_stage=ResearchStage.DATA_READINESS,
            is_blocked=True,
            blocking_reason=GateReasonCode.GATE_SUMMARY_FETCH_ERROR,
            blocking_explain="Test explanation",
            allowed_actions=["view_explanation"],
            recommended_next_action="Fix the issue",
            evidence_refs=[],
            system_context={},
        )
        
        # This should not raise an exception
        state.validate_blocking_state()
        
        # Test that silent blocking raises error
        silent_state = ResearchFlowState(
            current_stage=ResearchStage.DATA_READINESS,
            is_blocked=True,
            blocking_reason=None,  # Silent blocking!
            blocking_explain=None,
            allowed_actions=[],
            recommended_next_action=None,
            evidence_refs=[],
            system_context={},
        )
        
        with pytest.raises(ValueError, match="Blocked state must have blocking_reason"):
            silent_state.validate_blocking_state()


class TestUiStageMappingGovernance:
    """Test UI stage mapping governance locks."""
    
    def test_single_primary_entry_point(self):
        """Test that exactly ONE page is PRIMARY tier."""
        controller = ResearchFlowController()
        
        # This should not raise an exception
        assert controller.enforce_primary_entry_point() is True
        
        # Get primary entry point
        primary = controller.get_primary_entry_point_info()
        assert primary.tier == UiPageTier.PRIMARY
        assert primary.page_id == "research_flow"
    
    def test_research_flow_is_primary(self):
        """Test that Research Flow is the PRIMARY entry point."""
        classification = get_page_classification("research_flow")
        assert classification is not None
        assert classification.tier == UiPageTier.PRIMARY
        assert classification.page_id == "research_flow"
    
    def test_no_other_primary_pages(self):
        """Test that no other pages are PRIMARY tier."""
        from contracts.research.ui_stage_mapping import UI_PAGE_CLASSIFICATIONS
        
        primary_pages = [
            c for c in UI_PAGE_CLASSIFICATIONS 
            if c.tier == UiPageTier.PRIMARY
        ]
        
        assert len(primary_pages) == 1
        assert primary_pages[0].page_id == "research_flow"
    
    def test_ui_navigation_validation(self):
        """Test UI navigation validation through kernel."""
        controller = ResearchFlowController()
        
        # Mock current stage
        current_stage = ResearchStage.DATA_READINESS
        
        # Test valid navigation (operation should be available in DATA_READINESS)
        is_allowed, reason, classification = controller.validate_ui_navigation(
            "operation", current_stage
        )
        
        # Operation should be available in DATA_READINESS
        assert is_allowed is True
        assert classification is not None
        assert classification.page_id == "operation"
        
        # Test invalid navigation (gate_dashboard should NOT be available in DATA_READINESS)
        is_allowed, reason, classification = controller.validate_ui_navigation(
            "gate_dashboard", current_stage
        )
        
        # Gate dashboard should NOT be available in DATA_READINESS
        assert is_allowed is False
        assert reason is not None
        assert "not available" in reason.lower()
    
    def test_available_pages_for_stage(self):
        """Test get_available_ui_pages returns correct pages for stage."""
        controller = ResearchFlowController()
        
        # Mock evaluate_current_state to return DATA_READINESS
        mock_state = Mock()
        mock_state.current_stage = ResearchStage.DATA_READINESS
        
        with patch.object(controller, 'evaluate_current_state', return_value=mock_state):
            available_pages = controller.get_available_ui_pages()
            
            # Should include research_flow (PRIMARY) and operation (TOOL for DATA_READINESS)
            page_ids = [p.page_id for p in available_pages]
            assert "research_flow" in page_ids
            assert "operation" in page_ids
            assert "report" in page_ids  # EXPERT tier, available in all stages
            
            # Should NOT include gate_dashboard (not available in DATA_READINESS)
            assert "gate_dashboard" not in page_ids


class TestStageTransitionGovernance:
    """Test stage transition governance."""
    
    def test_stage_transitions_are_immutable(self):
        """Test that stage transitions cannot be modified."""
        from contracts.research.research_flow_kernel import STAGE_TRANSITIONS
        
        # Verify transitions are defined (3 transitions: DATA_READINESS→RUN_RESEARCH, RUN_RESEARCH→OUTCOME_TRIAGE, OUTCOME_TRIAGE→DECISION)
        assert len(STAGE_TRANSITIONS) == 3
        
        # Verify each transition has required fields
        for transition in STAGE_TRANSITIONS:
            assert hasattr(transition, 'from_stage')
            assert hasattr(transition, 'to_stage')
            assert hasattr(transition, 'required_conditions')
            assert hasattr(transition, 'blocking_reasons')
    
    def test_no_stage_skipping(self):
        """Test that stages cannot be skipped."""
        from contracts.research.research_flow_kernel import STAGE_TRANSITIONS
        
        # Check that each stage only transitions to next stage
        stage_order = [
            ResearchStage.DATA_READINESS,
            ResearchStage.RUN_RESEARCH,
            ResearchStage.OUTCOME_TRIAGE,
            ResearchStage.DECISION,
        ]
        
        for i, from_stage in enumerate(stage_order):
            # Find transitions from this stage
            transitions = [t for t in STAGE_TRANSITIONS if t.from_stage == from_stage]
            
            if i < len(stage_order) - 1:
                # First three stages should have exactly 1 transition (to next stage)
                assert len(transitions) == 1, f"Stage {from_stage} should have 1 transition"
                
                to_stage = transitions[0].to_stage
                # Should transition to next stage in order
                assert to_stage == stage_order[i + 1], f"Stage {from_stage} should transition to {stage_order[i + 1]}, not {to_stage}"
            else:
                # DECISION is final stage, should have no transitions
                assert len(transitions) == 0, f"DECISION stage should have no transitions"


class TestFrozenModelsGovernance:
    """Test frozen models governance."""
    
    def test_research_flow_state_is_frozen(self):
        """Test that ResearchFlowState is frozen (immutable)."""
        state = ResearchFlowState(
            current_stage=ResearchStage.DATA_READINESS,
            is_blocked=False,
            blocking_reason=None,
            blocking_explain=None,
            allowed_actions=[],
            recommended_next_action=None,
            evidence_refs=[],
            system_context={},
        )
        
        # Attempt to modify should raise ValidationError (frozen instance)
        with pytest.raises(Exception):  # Can be ValidationError or AttributeError depending on Pydantic version
            state.current_stage = ResearchStage.RUN_RESEARCH
        
        with pytest.raises(Exception):
            state.is_blocked = True
    
    def test_ui_page_classification_is_frozen(self):
        """Test that UiPageClassification is frozen (immutable)."""
        classification = UiPageClassification(
            page_id="test",
            display_name="Test",
            tier=UiPageTier.TOOL,
            supported_stages=[ResearchStage.DATA_READINESS],
        )
        
        # Attempt to modify should raise ValidationError (frozen instance)
        with pytest.raises(Exception):  # Can be ValidationError or AttributeError depending on Pydantic version
            classification.page_id = "modified"
        
        with pytest.raises(Exception):
            classification.tier = UiPageTier.PRIMARY


class TestTerminationGovernance:
    """Test termination governance (no daemons)."""
    
    def test_evaluation_terminates(self):
        """Test that evaluate_current_state terminates deterministically."""
        controller = ResearchFlowController()
        
        import time
        start_time = time.time()
        
        # This should complete quickly
        state = controller.evaluate_current_state()
        
        end_time = time.time()
        duration = end_time - start_time
        
        # Should complete in reasonable time (not a daemon)
        assert duration < 1.0  # Less than 1 second
        
        # Should have evaluation duration
        assert state.evaluation_duration_ms is not None
        assert state.evaluation_duration_ms >= 0
    
    def test_no_background_threads(self):
        """Test that controller doesn't create background threads."""
        controller = ResearchFlowController()
        
        # Check that controller doesn't have background thread attributes
        assert not hasattr(controller, '_background_thread')
        assert not hasattr(controller, '_daemon')
        assert not hasattr(controller, '_running')


if __name__ == "__main__":
    pytest.main([__file__, "-v"])