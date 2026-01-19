"""
GUI tests for ExplainHubTabs widget (v2.2-B).
"""

import pytest
pytest.importorskip("PySide6")

from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone

from PySide6.QtWidgets import QApplication, QPushButton, QTabWidget
from PySide6.QtCore import Qt

from gui.services.cross_job_gate_summary_service import JobGateSummary
from contracts.research.research_narrative import ResearchNarrativeV1, NarrativeActionId
from contracts.research.research_flow_kernel import ResearchStage, GateReasonCode
from contracts.portfolio.gate_summary_schemas import GateSummaryV1, GateItemV1, GateStatus
from gui.desktop.widgets.explain_hub_tabs import ExplainHubTabs


@pytest.fixture
def app():
    """Create QApplication instance for GUI tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def sample_job_gate_summary():
    """Create a sample JobGateSummary for testing."""
    gate_summary = GateSummaryV1(
        schema_version="v1",
        overall_status=GateStatus.PASS,
        overall_message="All gates passed",
        gates=[
            GateItemV1(
                gate_id="data_alignment",
                gate_name="Data Alignment",
                status=GateStatus.PASS,
                message="Data aligned correctly",
                reason_codes=["DATA_ALIGNED"],
                evaluated_at_utc="2024-01-01T00:00:00Z",
                evaluator="test",
            ),
            GateItemV1(
                gate_id="ranking_explain",
                gate_name="Ranking Explain",
                status=GateStatus.PASS,
                message="Ranking explain report available",
                reason_codes=["RANKING_EXPLAIN_READY"],
                evaluated_at_utc="2024-01-01T00:00:00Z",
                evaluator="ranking_explain_builder",
            ),
        ],
        evaluated_at_utc="2024-01-01T00:00:00Z",
        evaluator="test",
        source="test",
        counts={"pass": 2, "warn": 0, "reject": 0, "skip": 0, "unknown": 0},
    )
    
    job_data = {
        "job_id": "test_job_123",
        "job_type": "RUN_RESEARCH_WFS",
        "status": "COMPLETED",
        "created_at": "2024-01-01T00:00:00Z",
        "artifacts": {
            "ranking_explain_report.json": {"path": "outputs/jobs/test_job_123/ranking_explain_report.json"}
        }
    }
    
    return JobGateSummary(
        job_id="test_job_123",
        job_data=job_data,
        gate_summary=gate_summary,
    )


@pytest.fixture
def sample_research_narrative():
    """Create a sample ResearchNarrativeV1 for testing."""
    return ResearchNarrativeV1(
        stage=ResearchStage.DECISION,
        severity="OK",
        headline="Research completed successfully - ready for portfolio decisions",
        why="All gates passed, data quality validated, and ranking explain available for review.",
        primary_reason_code=GateReasonCode.GATE_SUMMARY_PARSE_ERROR,
        developer_view="Developer details: all gates passed and evidence is available.",
        business_view="Research outcomes show strong potential for portfolio inclusion with clear explainability.",
        next_step_action=NarrativeActionId.BUILD_PORTFOLIO,
        next_step_label="Proceed to portfolio allocation decisions",
        drilldown_actions=[
            {
                "action": "view_ranking_explain",
                "label": "View Ranking Explain Report",
                "url": "/api/v1/jobs/test_job_123/ranking_explain",
            },
            {
                "action": "open_portfolio_view",
                "label": "Open Portfolio View",
                "url": "/portfolio/test_job_123",
            },
        ],
    )


class TestExplainHubTabs:
    """Test suite for ExplainHubTabs widget."""

    def test_initialization(self, app):
        """Widget initializes with three tabs."""
        widget = ExplainHubTabs()
        
        # Should have tab widget
        assert hasattr(widget, 'tab_widget')
        assert isinstance(widget.tab_widget, QTabWidget)
        
        # Should have three tabs
        assert widget.tab_widget.count() == 3
        assert widget.tab_widget.tabText(0) == "Narrative"
        assert widget.tab_widget.tabText(1) == "Dev"
        assert widget.tab_widget.tabText(2) == "Biz"
        
        # Should have status label
        assert hasattr(widget, 'status_label')
        assert widget.status_label.text() == "No job selected"
        
        # Current state should be empty
        assert widget.current_job_id is None
        assert widget.current_job_summary is None
        assert widget.current_narrative is None

    def test_update_for_job_success(self, app, sample_job_gate_summary):
        """update_for_job successfully updates widget with job data."""
        widget = ExplainHubTabs()
        
        # Mock the narrative building
        mock_narrative = Mock(spec=ResearchNarrativeV1)
        mock_narrative.severity = "OK"
        mock_narrative.stage = ResearchStage.DECISION
        mock_narrative.headline = "Test headline"
        mock_narrative.why = "Test why"
        mock_narrative.next_step_label = "Test next step"
        mock_narrative.business_view = "Test business view"
        mock_narrative.drilldown_actions = []
        
        with patch.object(widget, '_build_narrative_for_job', return_value=mock_narrative) as mock_build:
            with patch.object(widget, '_update_narrative_tab') as mock_update_narrative:
                with patch.object(widget, '_update_dev_tab') as mock_update_dev:
                    with patch.object(widget, '_update_biz_tab') as mock_update_biz:
                        # Connect to signal to verify emission
                        signal_called = False
                        captured_narrative = None
                        def on_narrative_loaded(narrative):
                            nonlocal signal_called, captured_narrative
                            signal_called = True
                            captured_narrative = narrative
                        widget.narrative_loaded.connect(on_narrative_loaded)
                        
                        # Call update_for_job
                        widget.update_for_job("test_job_123", sample_job_gate_summary)
                        
                        # Verify state updated
                        assert widget.current_job_id == "test_job_123"
                        assert widget.current_job_summary is sample_job_gate_summary
                        assert widget.current_narrative is mock_narrative
                        
                        # Verify status label updated
                        assert "Job:" in widget.status_label.text()
                        assert "test_job_123"[:12] in widget.status_label.text()
                        
                        # Verify methods called
                        mock_build.assert_called_once_with(sample_job_gate_summary)
                        mock_update_narrative.assert_called_once_with(mock_narrative)
                        mock_update_dev.assert_called_once_with(sample_job_gate_summary)
                        mock_update_biz.assert_called_once_with(mock_narrative, sample_job_gate_summary)
                        
                        # Verify signal emitted
                        assert signal_called
                        assert captured_narrative is mock_narrative

    def test_update_for_job_error(self, app, sample_job_gate_summary):
        """update_for_job handles errors gracefully."""
        widget = ExplainHubTabs()
        
        # Mock error in narrative building
        with patch.object(widget, '_build_narrative_for_job', side_effect=Exception("Test error")):
            with patch.object(widget, '_show_error') as mock_show_error:
                # Call update_for_job
                widget.update_for_job("test_job_123", sample_job_gate_summary)
                
                # Verify error handling
                mock_show_error.assert_called_once()
                call_args = mock_show_error.call_args[0][0]
                assert "Test error" in call_args
                
                # State should still be updated
                assert widget.current_job_id == "test_job_123"
                assert widget.current_job_summary is sample_job_gate_summary
                # Narrative should be None due to error
                assert widget.current_narrative is None

    def test_build_narrative_for_job(self, app, sample_job_gate_summary):
        """_build_narrative_for_job creates ResearchNarrativeV1 from job data."""
        widget = ExplainHubTabs()
        
        # Mock get_stage_narrative
        mock_narrative = Mock(spec=ResearchNarrativeV1)
        with patch('gui.desktop.widgets.explain_hub_tabs.get_stage_narrative', return_value=mock_narrative) as mock_get_narrative:
            result = widget._build_narrative_for_job(sample_job_gate_summary)
            
            # Verify get_stage_narrative called with correct arguments
            mock_get_narrative.assert_called_once()
            call_kwargs = mock_get_narrative.call_args[1]
            
            assert call_kwargs['stage'] == ResearchStage.DECISION  # Based on job_type and status
            assert call_kwargs['is_blocked'] is False  # Gate status is PASS
            assert call_kwargs['blocking_reason'] is None
            assert 'system_context' in call_kwargs
            
            # Verify result
            assert result is mock_narrative

    def test_determine_research_stage(self, app):
        """_determine_research_stage correctly determines stage based on job data."""
        widget = ExplainHubTabs()
        
        # Test cases
        test_cases = [
            # (job_type, job_status, gate_status, expected_stage)
            ("RUN_RESEARCH_WFS", "COMPLETED", GateStatus.PASS, ResearchStage.DECISION),
            ("RUN_RESEARCH_WFS", "COMPLETED", GateStatus.REJECT, ResearchStage.OUTCOME_TRIAGE),
            ("RUN_RESEARCH_WFS", "RUNNING", GateStatus.PASS, ResearchStage.RUN_RESEARCH),
            ("RUN_RESEARCH_WFS", "RUNNING", GateStatus.REJECT, ResearchStage.RUN_RESEARCH),
            ("OTHER_TYPE", "COMPLETED", GateStatus.PASS, ResearchStage.DATA_READINESS),
        ]
        
        for job_type, job_status, gate_status, expected_stage in test_cases:
            job_data = {"job_type": job_type, "status": job_status}
            gate_summary = GateSummaryV1(
                schema_version="v1",
                overall_status=gate_status,
                overall_message="Test",
                gates=[],
                evaluated_at_utc="2024-01-01T00:00:00Z",
                evaluator="test",
                source="test",
                counts={"pass": 0, "warn": 0, "reject": 0, "skip": 0, "unknown": 0},
            )
            
            result = widget._determine_research_stage(job_data, gate_summary)
            assert result == expected_stage, f"Failed for {job_type}/{job_status}/{gate_status}"

    def test_update_narrative_tab(self, app, sample_research_narrative):
        """_update_narrative_tab updates UI with narrative content."""
        widget = ExplainHubTabs()
        
        # Call method
        widget._update_narrative_tab(sample_research_narrative)
        
        # Verify UI updated
        assert widget.severity_value.text() == sample_research_narrative.severity
        assert widget.stage_value.text() == sample_research_narrative.stage.value.replace("_", " ").title()
        assert widget.headline_text.text() == sample_research_narrative.headline
        assert widget.why_text.toPlainText() == sample_research_narrative.why
        assert widget.next_step_text.text() == sample_research_narrative.next_step_label
        
        # Verify actions updated
        assert (not widget.actions_group.isHidden()) == bool(sample_research_narrative.drilldown_actions)

    def test_update_actions(self, app):
        """_update_actions creates action buttons."""
        widget = ExplainHubTabs()
        
        # Create test actions
        actions = [
            {"action": "test1", "label": "Test Action 1", "url": "/test1"},
            {"action": "test2", "label": "Test Action 2", "url": "/test2"},
        ]
        
        # Call method
        widget._update_actions(actions)
        
        # Verify actions group is visible
        assert not widget.actions_group.isHidden()
        
        # Verify buttons created
        buttons = widget.actions_container.findChildren(QPushButton)
        assert len(buttons) == 2
        assert buttons[0].text() == "Test Action 1"
        assert buttons[1].text() == "Test Action 2"
        
        # Verify action data stored
        assert buttons[0].property("action_data") == actions[0]
        assert buttons[1].property("action_data") == actions[1]

    def test_update_dev_tab(self, app, sample_job_gate_summary):
        """_update_dev_tab updates Dev tab with technical details."""
        widget = ExplainHubTabs()
        
        # Mock helper methods
        with patch.object(widget, '_format_gate_summary', return_value="Formatted gate summary") as mock_format_gate:
            with patch.object(widget, '_format_job_data', return_value="Formatted job data") as mock_format_job:
                with patch.object(widget, '_get_explain_dictionary', return_value=None) as mock_get_explain:
                    # Call method
                    widget._update_dev_tab(sample_job_gate_summary)
                    
                    # Verify methods called
                    mock_format_gate.assert_called_once_with(sample_job_gate_summary.gate_summary)
                    mock_format_job.assert_called_once_with(sample_job_gate_summary.job_data)
                    mock_get_explain.assert_called_once_with(sample_job_gate_summary.job_id)
                    
                    # Verify UI updated
                    assert widget.gate_summary_text.toPlainText() == "Formatted gate summary"
                    assert widget.job_data_text.toPlainText() == "Formatted job data"
                    assert not widget.explain_group.isVisible()  # No explain data

    def test_format_gate_summary(self, app):
        """_format_gate_summary formats gate summary for display."""
        widget = ExplainHubTabs()
        
        gate_summary = GateSummaryV1(
            schema_version="v1",
            overall_status=GateStatus.PASS,
            overall_message="All gates passed",
            gates=[
                GateItemV1(
                    gate_id="test_gate",
                    gate_name="Test Gate",
                    status=GateStatus.PASS,
                    message="Test message",
                    reason_codes=["TEST_CODE"],
                    evaluated_at_utc="2024-01-01T00:00:00Z",
                    evaluator="test",
                )
            ],
            evaluated_at_utc="2024-01-01T00:00:00Z",
            evaluator="test",
            source="test",
            counts={"pass": 1, "warn": 0, "reject": 0, "skip": 0, "unknown": 0},
        )
        
        result = widget._format_gate_summary(gate_summary)
        
        # Verify formatting
        assert "Overall Status: PASS" in result
        assert "Overall Message: All gates passed" in result
        assert "Test Gate (test_gate)" in result
        assert "Status: PASS" in result
        assert "Message: Test message" in result
        assert "Reason Codes: TEST_CODE" in result

    def test_format_job_data(self, app):
        """_format_job_data formats job data as JSON."""
        widget = ExplainHubTabs()
        
        job_data = {
            "job_id": "test_job",
            "status": "COMPLETED",
            "nested": {"key": "value"}
        }
        
        result = widget._format_job_data(job_data)
        
        # Should be valid JSON
        import json
        parsed = json.loads(result)
        assert parsed["job_id"] == "test_job"
        assert parsed["status"] == "COMPLETED"
        assert parsed["nested"]["key"] == "value"

    def test_update_biz_tab(self, app, sample_research_narrative, sample_job_gate_summary):
        """_update_biz_tab updates Biz tab with business implications."""
        widget = ExplainHubTabs()
        
        # Mock helper methods
        with patch.object(widget, '_generate_recommendations', return_value="Test recommendations") as mock_gen_rec:
            with patch.object(widget, '_generate_risk_assessment', return_value="Test risk assessment") as mock_gen_risk:
                # Call method
                widget._update_biz_tab(sample_research_narrative, sample_job_gate_summary)
                
                # Verify methods called
                mock_gen_rec.assert_called_once_with(sample_research_narrative, sample_job_gate_summary.gate_summary)
                mock_gen_risk.assert_called_once_with(sample_research_narrative, sample_job_gate_summary.gate_summary)
                
                # Verify UI updated
                assert widget.biz_view_text.toPlainText() == sample_research_narrative.business_view
                assert widget.recommendations_text.text() == "Test recommendations"
                assert widget.risk_text.text() == "Test risk assessment"

    def test_generate_recommendations(self, app):
        """_generate_recommendations generates business recommendations."""
        widget = ExplainHubTabs()
        
        # Test with OK severity and DECISION stage
        narrative = Mock(spec=ResearchNarrativeV1)
        narrative.severity = "OK"
        narrative.stage = ResearchStage.DECISION
        
        gate_summary = Mock(spec=GateSummaryV1)
        gate_summary.overall_status = GateStatus.PASS
        
        result = widget._generate_recommendations(narrative, gate_summary)
        
        # Should contain recommendations for OK severity and DECISION stage
        assert "Proceed to next stage" in result
        assert "Monitor performance" in result
        assert "Make portfolio allocation decisions" in result
        
        # Test with BLOCKED severity
        narrative.severity = "BLOCKED"
        narrative.stage = ResearchStage.OUTCOME_TRIAGE
        gate_summary.overall_status = GateStatus.REJECT
        
        result = widget._generate_recommendations(narrative, gate_summary)
        assert "Immediate action required" in result
        assert "Review gate failures" in result

    def test_generate_risk_assessment(self, app):
        """_generate_risk_assessment generates risk assessment."""
        widget = ExplainHubTabs()
        
        # Test with PASS gate status and OK severity
        narrative = Mock(spec=ResearchNarrativeV1)
        narrative.severity = "OK"
        narrative.stage = ResearchStage.DECISION
        
        gate_summary = Mock(spec=GateSummaryV1)
        gate_summary.overall_status = GateStatus.PASS
        
        result = widget._generate_risk_assessment(narrative, gate_summary)
        
        # Should contain risk assessment for PASS status
        assert "LOW RISK" in result
        assert "Standard operational risks" in result
        
        # Test with REJECT gate status and BLOCKED severity
        narrative.severity = "BLOCKED"
        gate_summary.overall_status = GateStatus.REJECT
        
        result = widget._generate_risk_assessment(narrative, gate_summary)
        assert "HIGH RISK" in result
        assert "Critical gate failures" in result

    def test_clear(self, app, sample_job_gate_summary, sample_research_narrative):
        """clear resets widget to initial state."""
        widget = ExplainHubTabs()
        
        # First update with job data
        with patch.object(widget, '_build_narrative_for_job', return_value=sample_research_narrative):
            widget.update_for_job("test_job_123", sample_job_gate_summary)
        
        # Verify state is set
        assert widget.current_job_id == "test_job_123"
        assert widget.current_job_summary is sample_job_gate_summary
        assert widget.current_narrative is sample_research_narrative
        assert "Job:" in widget.status_label.text()
        
        # Clear widget
        widget.clear()
        
        # Verify state reset
        assert widget.current_job_id is None
        assert widget.current_job_summary is None
        assert widget.current_narrative is None
        assert widget.status_label.text() == "No job selected"
        
        # Verify UI reset
        assert widget.severity_value.text() == "—"
        assert widget.stage_value.text() == "—"
        assert widget.headline_text.text() == "Select a job to view narrative"
        assert widget.why_text.toPlainText() == ""
        assert widget.next_step_text.text() == "—"
        assert not widget.actions_group.isVisible()
        
        assert widget.gate_summary_text.toPlainText() == ""
        assert widget.job_data_text.toPlainText() == ""
        assert not widget.explain_group.isVisible()
        
        assert widget.biz_view_text.toPlainText() == ""
        assert widget.recommendations_text.text() == "—"
        assert widget.risk_text.text() == "—"

    def test_show_error(self, app):
        """_show_error displays error state."""
        widget = ExplainHubTabs()
        
        error_message = "Test error message"
        widget._show_error(error_message)
        
        # Verify status label shows error
        assert "Error:" in widget.status_label.text()
        assert error_message[:50] in widget.status_label.text()
        assert "color: #F44336" in widget.status_label.styleSheet()
        
        # Verify UI shows error state
        assert widget.headline_text.text() == "Error loading narrative"
        assert error_message in widget.why_text.toPlainText()
        assert widget.next_step_text.text() == "Check system logs and try again"
        
        assert error_message in widget.gate_summary_text.toPlainText()
        assert "Error loading job data" in widget.job_data_text.toPlainText()
        
        assert error_message in widget.biz_view_text.toPlainText()
        assert "Unable to generate recommendations" in widget.recommendations_text.text()
        assert "Risk assessment unavailable" in widget.risk_text.text()

    def test_action_button_initial_state(self, app):
        """Action buttons should be disabled initially."""
        widget = ExplainHubTabs()
        
        # Verify action buttons exist and are disabled
        assert hasattr(widget, 'gate_explain_btn')
        assert hasattr(widget, 'evidence_viewer_btn')
        assert hasattr(widget, 'artifact_nav_btn')
        
        assert not widget.gate_explain_btn.isEnabled()
        assert not widget.evidence_viewer_btn.isEnabled()
        assert not widget.artifact_nav_btn.isEnabled()

    def test_update_action_buttons(self, app):
        """_update_action_buttons enables/disables action buttons."""
        widget = ExplainHubTabs()
        
        # Test enabling buttons
        widget._update_action_buttons(True)
        assert widget.gate_explain_btn.isEnabled()
        assert widget.evidence_viewer_btn.isEnabled()
        assert widget.artifact_nav_btn.isEnabled()
        
        # Test disabling buttons
        widget._update_action_buttons(False)
        assert not widget.gate_explain_btn.isEnabled()
        assert not widget.evidence_viewer_btn.isEnabled()
        assert not widget.artifact_nav_btn.isEnabled()

    def test_on_gate_explain_clicked(self, app, sample_job_gate_summary):
        """_on_gate_explain_clicked emits action signal."""
        widget = ExplainHubTabs()
        
        # Set up widget with job data
        widget.current_job_id = "test_job_123"
        widget.current_job_summary = sample_job_gate_summary
        
        # Connect to signal to verify emission
        signal_called = False
        captured_target = None
        captured_context = None
        
        def on_action_requested(target, context):
            nonlocal signal_called, captured_target, captured_context
            signal_called = True
            captured_target = target
            captured_context = context
        
        widget.action_requested.connect(on_action_requested)
        
        # Call the method
        widget._on_gate_explain_clicked()
        
        # Verify signal emitted
        assert signal_called
        assert captured_target == "gate_explain://test_job_123"
        assert captured_context["job_id"] == "test_job_123"
        assert captured_context["source"] == "ExplainHubTabs"
        assert captured_context["tab"] == "Dev"
        assert "gate_summary" in captured_context

    def test_on_evidence_viewer_clicked(self, app):
        """_on_evidence_viewer_clicked emits action signal."""
        widget = ExplainHubTabs()
        
        # Set up widget with job data
        widget.current_job_id = "test_job_123"
        
        # Connect to signal to verify emission
        signal_called = False
        captured_target = None
        captured_context = None
        
        def on_action_requested(target, context):
            nonlocal signal_called, captured_target, captured_context
            signal_called = True
            captured_target = target
            captured_context = context
        
        widget.action_requested.connect(on_action_requested)
        
        # Call the method
        widget._on_evidence_viewer_clicked()
        
        # Verify signal emitted
        assert signal_called
        assert captured_target == "evidence://test_job_123"
        assert captured_context["job_id"] == "test_job_123"
        assert captured_context["source"] == "ExplainHubTabs"
        assert captured_context["tab"] == "Dev"

    def test_on_artifact_nav_clicked(self, app):
        """_on_artifact_nav_clicked emits action signal."""
        widget = ExplainHubTabs()
        
        # Set up widget with job data
        widget.current_job_id = "test_job_123"
        
        # Connect to signal to verify emission
        signal_called = False
        captured_target = None
        captured_context = None
        
        def on_action_requested(target, context):
            nonlocal signal_called, captured_target, captured_context
            signal_called = True
            captured_target = target
            captured_context = context
        
        widget.action_requested.connect(on_action_requested)
        
        # Call the method
        widget._on_artifact_nav_clicked()
        
        # Verify signal emitted
        assert signal_called
        assert captured_target == "artifact://test_job_123"
        assert captured_context["job_id"] == "test_job_123"
        assert captured_context["source"] == "ExplainHubTabs"
        assert captured_context["tab"] == "Dev"

    def test_route_action(self, app):
        """_route_action routes action through ActionRouterService."""
        widget = ExplainHubTabs()
        widget.current_job_id = "test_job_123"
        
        # Mock current_narrative and current_job_summary
        widget.current_narrative = Mock(spec=ResearchNarrativeV1)
        widget.current_narrative.stage = ResearchStage.DECISION
        widget.current_narrative.severity = "OK"
        widget.current_narrative.next_step_action = None
        
        widget.current_job_summary = Mock()
        widget.current_job_summary.gate_summary = Mock()
        widget.current_job_summary.gate_summary.overall_status = GateStatus.PASS
        widget.current_job_summary.gate_summary.total_gates = 2
        
        # Connect to signal to verify emission
        signal_called = False
        captured_target = None
        captured_context = None
        
        def on_action_requested(target, context):
            nonlocal signal_called, captured_target, captured_context
            signal_called = True
            captured_target = target
            captured_context = context
        
        widget.action_requested.connect(on_action_requested)
        
        # Test action data
        action_data = {
            "action": "view_ranking_explain",
            "label": "View Ranking Explain Report",
            "url": "/api/v1/jobs/test_job_123/ranking_explain"
        }
        
        # Call method
        widget._route_action("view_ranking_explain", action_data)
        
        # Verify signal emitted
        assert signal_called
        assert captured_target == "view_ranking_explain"  # Default mapping
        assert captured_context["job_id"] == "test_job_123"
        assert captured_context["action_data"] == action_data
        assert captured_context["source"] == "ExplainHubTabs"
        assert captured_context["tab"] == "Narrative"  # Default tab
        assert "narrative" in captured_context
        assert "gate_summary" in captured_context

    def test_map_action_to_target(self, app):
        """_map_action_to_target maps action types to targets."""
        widget = ExplainHubTabs()
        widget.current_job_id = "test_job_123"
        
        # Test common mappings
        test_cases = [
            ("open_gate_dashboard", "gate_dashboard"),
            ("open_data_readiness", "data_readiness"),
            ("view_evidence", "evidence://test_job_123"),
            ("explain_gate", "gate_explain://test_job_123"),
            ("open_artifact", "artifact://test_job_123"),
            ("http://example.com", "http://example.com"),
            ("internal://test", "internal://test"),
            ("unknown_action", "unknown_action"),  # Default mapping
        ]
        
        for action_type, expected_target in test_cases:
            action_data = {"action": action_type, "label": "Test"}
            result = widget._map_action_to_target(action_type, action_data)
            assert result == expected_target, f"Failed for {action_type}"

    def test_update_for_job_enables_action_buttons(self, app, sample_job_gate_summary):
        """update_for_job enables action buttons when job is loaded."""
        widget = ExplainHubTabs()
        
        # Mock narrative building
        mock_narrative = Mock(spec=ResearchNarrativeV1)
        with patch.object(widget, '_build_narrative_for_job', return_value=mock_narrative):
            with patch.object(widget, '_update_narrative_tab'):
                with patch.object(widget, '_update_dev_tab'):
                    with patch.object(widget, '_update_biz_tab'):
                        # Call update_for_job
                        widget.update_for_job("test_job_123", sample_job_gate_summary)
                        
                        # Verify action buttons are enabled
                        assert widget.gate_explain_btn.isEnabled()
                        assert widget.evidence_viewer_btn.isEnabled()
                        assert widget.artifact_nav_btn.isEnabled()

    def test_clear_disables_action_buttons(self, app, sample_job_gate_summary, sample_research_narrative):
        """clear disables action buttons."""
        widget = ExplainHubTabs()
        
        # First update with job data
        with patch.object(widget, '_build_narrative_for_job', return_value=sample_research_narrative):
            widget.update_for_job("test_job_123", sample_job_gate_summary)
        
        # Verify buttons are enabled
        assert widget.gate_explain_btn.isEnabled()
        assert widget.evidence_viewer_btn.isEnabled()
        assert widget.artifact_nav_btn.isEnabled()
        
        # Clear widget
        widget.clear()
        
        # Verify buttons are disabled
        assert not widget.gate_explain_btn.isEnabled()
        assert not widget.evidence_viewer_btn.isEnabled()
        assert not widget.artifact_nav_btn.isEnabled()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])