"""
Tests for GateSummaryDashboardTab (DP7 UI).
"""

import pytest
pytest.importorskip("PySide6")

from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from gui.desktop.tabs.gate_summary_dashboard_tab import GateSummaryDashboardTab
from gui.services.cross_job_gate_summary_service import (
    CrossJobGateSummaryMatrix,
    JobGateSummary,
)
from contracts.portfolio.gate_summary_schemas import (
    GateSummaryV1,
    GateStatus,
    GateItemV1,
)
from gui.desktop.widgets.sticky_verdict_bar import StickyVerdictBar


@pytest.fixture
def app():
    """Create QApplication instance for GUI tests."""
    # Check if QApplication already exists
    app_instance = QApplication.instance()
    if app_instance is None:
        app_instance = QApplication([])
    return app_instance


@pytest.fixture
def mock_matrix():
    """Create a mock cross-job gate summary matrix."""
    job_summary1 = JobGateSummary(
        job_id="job1_20250101_120000",
        job_data={
            "job_id": "job1_20250101_120000",
            "strategy_id": "s1",
            "instrument": "ES",
            "timeframe": "1m",
            "created_at": "2025-01-01T12:00:00Z",
        },
        gate_summary=GateSummaryV1(
            overall_status=GateStatus.PASS,
            overall_message="All gates passed",
            counts={"pass": 1, "warn": 0, "reject": 0, "skip": 0, "unknown": 0},
            gates=[
                GateItemV1(
                    gate_id="data_alignment",
                    gate_name="Data Alignment",
                    status=GateStatus.PASS,
                    message="Data aligned correctly",
                    reason_codes=["DATA_ALIGNED"],
                )
            ],
            evaluated_at_utc="2025-01-01T12:00:00Z",
            evaluator="test",
            source="test",
        ),
        fetched_at=datetime.now(timezone.utc),
    )
    
    job_summary2 = JobGateSummary(
        job_id="job2_20250101_130000",
        job_data={
            "job_id": "job2_20250101_130000",
            "strategy_id": "s2",
            "instrument": "NQ",
            "timeframe": "5m",
            "created_at": "2025-01-01T13:00:00Z",
        },
        gate_summary=GateSummaryV1(
            overall_status=GateStatus.WARN,
            overall_message="Some warnings",
            counts={"pass": 3, "warn": 2, "reject": 0, "skip": 0, "unknown": 0},
            gates=[
                GateItemV1(
                    gate_id="data_alignment",
                    gate_name="Data Alignment",
                    status=GateStatus.WARN,
                    message="Data alignment warning",
                    reason_codes=["DATA_ALIGNMENT_WARNING"],
                )
            ],
            evaluated_at_utc="2025-01-01T13:00:00Z",
            evaluator="test",
            source="test",
        ),
        fetched_at=datetime.now(timezone.utc),
    )
    
    return CrossJobGateSummaryMatrix(
        jobs=[job_summary1, job_summary2],
        summary_stats={"total": 2, "pass": 1, "warn": 1, "fail": 0, "unknown": 0},
        fetched_at=datetime.now(timezone.utc),
    )


class TestGateSummaryDashboardTab:
    """Test suite for GateSummaryDashboardTab."""
    
    def test_tab_initialization(self, app):
        """Test tab initialization."""
        with patch("gui.desktop.tabs.gate_summary_dashboard_tab.get_cross_job_gate_summary_service") as mock_get_service:
            mock_service = Mock()
            mock_service.build_matrix.return_value = None  # Simulate no data
            mock_get_service.return_value = mock_service
            
            tab = GateSummaryDashboardTab()
            
            assert tab.service is mock_service
            # current_matrix may be None if build_matrix returns None
            # or may be a Mock if build_matrix returns default Mock
            # Either is acceptable as long as tab doesn't crash
            assert tab.log_signal is not None
    
    def test_setup_ui(self, app):
        """Test UI setup."""
        with patch("gui.desktop.tabs.gate_summary_dashboard_tab.get_cross_job_gate_summary_service"):
            tab = GateSummaryDashboardTab()
            
            # Check that UI components are created
            assert tab.title_label is not None
            assert tab.subtitle_label is not None
            assert tab.table_widget is not None
            assert tab.details_text is not None
            assert tab.refresh_btn is not None
            
            # Check table column count (7 columns in production)
            assert tab.table_widget.columnCount() == 7
            headers = [tab.table_widget.horizontalHeaderItem(i).text() for i in range(7)]
            assert headers == ["Job ID", "Gate Status", "Strategy", "Instrument", "Timeframe", "Actions", "Admission"]
    
    def test_setup_refresh_timer(self, app):
        """Test refresh timer setup."""
        with patch("gui.desktop.tabs.gate_summary_dashboard_tab.get_cross_job_gate_summary_service"):
            tab = GateSummaryDashboardTab()
            
            assert tab.refresh_timer is not None
            assert tab.refresh_timer.isActive()
    
    @patch("gui.desktop.tabs.gate_summary_dashboard_tab.get_cross_job_gate_summary_service")
    def test_refresh_data_success(self, mock_get_service, app, mock_matrix):
        """Test successful data refresh."""
        mock_service = Mock()
        mock_service.build_matrix.return_value = mock_matrix
        mock_get_service.return_value = mock_service
        
        tab = GateSummaryDashboardTab()
        
        # Reset mock call count (__init__ already called refresh_data once)
        mock_service.build_matrix.reset_mock()
        
        # Mock log signal
        log_calls = []
        tab.log_signal.connect(lambda msg: log_calls.append(msg))
        
        tab.refresh_data()
        
        # Verify service was called (now exactly once from our explicit call)
        mock_service.build_matrix.assert_called_once()
        
        # Verify matrix was stored
        assert tab.current_matrix is mock_matrix
        
        # Verify stats were updated
        assert tab.total_label.text() == "Total: 2"
        assert tab.pass_label.text() == "PASS: 1"
        assert tab.warn_label.text() == "WARN: 1"
        
        # Verify table was updated
        assert tab.table_widget.rowCount() == 2
        
        # Verify log signal was emitted
        assert len(log_calls) >= 1
        assert any("Refreshing gate summary dashboard" in msg for msg in log_calls)

    def test_gate_drawer_defaults_collapsed(self, app, mock_matrix):
        """GateDrawer should start collapsed."""
        with patch("gui.desktop.tabs.gate_summary_dashboard_tab.get_cross_job_gate_summary_service") as mock_get_service:
            mock_service = Mock()
            mock_service.build_matrix.return_value = mock_matrix
            mock_get_service.return_value = mock_service
            tab = GateSummaryDashboardTab()
            assert tab.gate_drawer.is_collapsed() is True
            assert not tab.gate_drawer.expanded_widget.isVisible()

    def test_gate_drawer_toggle_visibility(self, app, mock_matrix):
        """Toggling GateDrawer should show/hide the expanded content."""
        with patch("gui.desktop.tabs.gate_summary_dashboard_tab.get_cross_job_gate_summary_service") as mock_get_service:
            mock_service = Mock()
            mock_service.build_matrix.return_value = mock_matrix
            mock_get_service.return_value = mock_service
            tab = GateSummaryDashboardTab()
            drawer = tab.gate_drawer
            drawer.set_collapsed(False)
            assert drawer.is_collapsed() is False
            drawer.set_collapsed(True)
            assert drawer.is_collapsed() is True

    def test_sticky_verdict_bar_refresh_signal(self):
        """Sticky verdict bar should emit refresh_requested."""
        bar = StickyVerdictBar()
        triggered = []
        bar.refresh_requested.connect(lambda: triggered.append(True))
        bar.refresh_button.click()
        assert triggered
    
    @patch("gui.desktop.tabs.gate_summary_dashboard_tab.get_cross_job_gate_summary_service")
    def test_refresh_data_error(self, mock_get_service, app):
        """Test data refresh with error."""
        mock_service = Mock()
        mock_service.build_matrix.side_effect = Exception("Test error")
        mock_get_service.return_value = mock_service
        
        tab = GateSummaryDashboardTab()
        
        # Mock log signal
        log_calls = []
        tab.log_signal.connect(lambda msg: log_calls.append(msg))
        
        tab.refresh_data()
        
        # Verify error was logged
        assert any("Error refreshing dashboard" in msg for msg in log_calls)
    
    def test_update_stats(self, app, mock_matrix):
        """Test statistics label updates."""
        with patch("gui.desktop.tabs.gate_summary_dashboard_tab.get_cross_job_gate_summary_service"):
            tab = GateSummaryDashboardTab()
            tab.current_matrix = mock_matrix
            
            tab.update_stats()
            
            assert tab.total_label.text() == "Total: 2"
            assert tab.pass_label.text() == "PASS: 1"
            assert tab.warn_label.text() == "WARN: 1"
            assert tab.fail_label.text() == "FAIL: 0"
            assert tab.unknown_label.text() == "UNKNOWN: 0"
    
    def test_update_stats_no_matrix(self, app):
        """Test statistics update with no matrix."""
        with patch("gui.desktop.tabs.gate_summary_dashboard_tab.get_cross_job_gate_summary_service"):
            tab = GateSummaryDashboardTab()
            tab.current_matrix = None
            
            # Should not crash
            tab.update_stats()
    
    def test_update_table(self, app, mock_matrix):
        """Test table update with job data."""
        with patch("gui.desktop.tabs.gate_summary_dashboard_tab.get_cross_job_gate_summary_service"):
            tab = GateSummaryDashboardTab()
            tab.current_matrix = mock_matrix
            
            tab.update_table()
            
            # Verify table has correct number of rows
            assert tab.table_widget.rowCount() == 2
            
            # Verify first row data
            # Job ID truncated to 12 chars + "...": "job1_20250101_120000" -> "job1_2025010..."
            assert tab.table_widget.item(0, 0).text() == "job1_2025010..."
            assert tab.table_widget.item(0, 1).text() == "PASS"
            assert tab.table_widget.item(0, 2).text() == "s1"
            assert tab.table_widget.item(0, 3).text() == "ES"
            assert tab.table_widget.item(0, 4).text() == "1m"
            assert tab.table_widget.item(0, 5).text() == "Gate Summary"
            assert tab.table_widget.item(0, 6).text() == "Admission"
            
            # Verify second row data
            assert tab.table_widget.item(1, 1).text() == "WARN"
            assert tab.table_widget.item(1, 2).text() == "s2"
            assert tab.table_widget.item(1, 3).text() == "NQ"
            assert tab.table_widget.item(1, 4).text() == "5m"
            assert tab.table_widget.item(1, 5).text() == "Gate Summary"
            assert tab.table_widget.item(1, 6).text() == "Admission"
    
    def test_update_table_no_matrix(self, app):
        """Test table update with no matrix."""
        with patch("gui.desktop.tabs.gate_summary_dashboard_tab.get_cross_job_gate_summary_service"):
            tab = GateSummaryDashboardTab()
            tab.current_matrix = None
            
            tab.update_table()
            
            # Table should be empty
            assert tab.table_widget.rowCount() == 0
    
    def test_on_table_selection_changed(self, app, mock_matrix):
        """Test table selection change handler."""
        with patch("gui.desktop.tabs.gate_summary_dashboard_tab.get_cross_job_gate_summary_service"):
            tab = GateSummaryDashboardTab()
            tab.current_matrix = mock_matrix
            tab.update_table()
            
            # Select first row
            tab.table_widget.selectRow(0)
            
            # Trigger selection changed
            tab.on_table_selection_changed()
            
            # Verify details text is populated
            details = tab.details_text.toPlainText()
            assert "Job ID: job1_20250101_120000" in details
            assert "Overall Status: PASS" in details
            assert "Data Alignment" in details
    
    def test_on_table_selection_changed_no_selection(self, app):
        """Test selection change with no selection."""
        with patch("gui.desktop.tabs.gate_summary_dashboard_tab.get_cross_job_gate_summary_service"):
            tab = GateSummaryDashboardTab()
            
            # Clear any selection
            tab.table_widget.clearSelection()
            tab.on_table_selection_changed()
            
            # Details should be cleared
            assert tab.details_text.toPlainText() == ""
    
    def test_build_job_details(self, app, mock_matrix):
        """Test building job details text."""
        with patch("gui.desktop.tabs.gate_summary_dashboard_tab.get_cross_job_gate_summary_service"):
            tab = GateSummaryDashboardTab()
            
            job_summary = mock_matrix.jobs[0]
            details = tab.build_job_details(job_summary)
            
            # Verify key information is present
            assert "Job ID: job1_20250101_120000" in details
            assert "Overall Status: PASS" in details
            assert "Total Gates: 1" in details
            assert "Data Alignment" in details
            assert "DATA_ALIGNED" in details
    
    def test_log_method(self, app):
        """Test log method emits signal."""
        with patch("gui.desktop.tabs.gate_summary_dashboard_tab.get_cross_job_gate_summary_service"):
            tab = GateSummaryDashboardTab()
            
            log_calls = []
            tab.log_signal.connect(lambda msg: log_calls.append(msg))
            
            tab.log("Test message")
            
            assert len(log_calls) == 1
            assert log_calls[0] == "Test message"
    
    def test_refresh_button_click(self, app):
        """Test refresh button click."""
        with patch("gui.desktop.tabs.gate_summary_dashboard_tab.get_cross_job_gate_summary_service") as mock_get_service:
            mock_service = Mock()
            mock_service.build_matrix.return_value = Mock()
            mock_get_service.return_value = mock_service
            
            tab = GateSummaryDashboardTab()
            
            # Mock refresh_data to track calls
            refresh_calls = []
            original_refresh = tab.refresh_data
            tab.refresh_data = lambda: refresh_calls.append(1)
            
            # Click refresh button
            tab.refresh_btn.click()
            
            # Verify refresh_data was called
            assert len(refresh_calls) == 1
            
            # Restore original method
            tab.refresh_data = original_refresh

    def test_handle_explain_hub_action_gate_explain(self, app, mock_matrix):
        """Test handling gate explain action from ExplainHubTabs."""
        with patch("gui.desktop.tabs.gate_summary_dashboard_tab.get_cross_job_gate_summary_service"):
            tab = GateSummaryDashboardTab()
            tab.current_matrix = mock_matrix
            
            # Mock log signal
            log_calls = []
            tab.log_signal.connect(lambda msg: log_calls.append(msg))
            
            # Mock GateExplanationDialog import and instantiation
            with patch("gui.desktop.tabs.gate_summary_dashboard_tab.GateExplanationDialog") as mock_dialog_class:
                mock_dialog = Mock()
                mock_dialog_class.return_value = mock_dialog
                
                # Call action handler
                context = {"job_id": "job1_20250101_120000", "source": "ExplainHubTabs"}
                tab._handle_explain_hub_action("gate_explain://job1_20250101_120000", context)
                
                # Verify dialog was created and shown
                mock_dialog_class.assert_called_once()
                mock_dialog.exec.assert_called_once()
                
                # Verify log message
                assert any("Opened gate explanation" in msg for msg in log_calls)

    def test_handle_explain_hub_action_evidence(self, app, mock_matrix):
        """Test handling evidence viewer action from ExplainHubTabs."""
        with patch("gui.desktop.tabs.gate_summary_dashboard_tab.get_cross_job_gate_summary_service"):
            tab = GateSummaryDashboardTab()
            tab.current_matrix = mock_matrix
            
            # Mock log signal
            log_calls = []
            tab.log_signal.connect(lambda msg: log_calls.append(msg))
            
            # Mock EvidenceBrowserDialog import and instantiation
            with patch("gui.desktop.tabs.gate_summary_dashboard_tab.EvidenceBrowserDialog") as mock_dialog_class:
                mock_dialog = Mock()
                mock_dialog_class.return_value = mock_dialog
                
                # Call action handler
                context = {"job_id": "job1_20250101_120000", "source": "ExplainHubTabs"}
                tab._handle_explain_hub_action("evidence://job1_20250101_120000", context)
                
                # Verify dialog was created and shown
                mock_dialog_class.assert_called_once_with("job1_20250101_120000", parent=tab)
                mock_dialog.exec.assert_called_once()
                
                # Verify log message
                assert any("Opened evidence browser" in msg for msg in log_calls)

    def test_handle_explain_hub_action_artifact(self, app, mock_matrix):
        """Test handling artifact navigator action from ExplainHubTabs."""
        with patch("gui.desktop.tabs.gate_summary_dashboard_tab.get_cross_job_gate_summary_service"):
            tab = GateSummaryDashboardTab()
            tab.current_matrix = mock_matrix
            
            # Mock action router
            mock_action_router = Mock()
            tab.action_router = mock_action_router
            
            # Mock log signal
            log_calls = []
            tab.log_signal.connect(lambda msg: log_calls.append(msg))
            
            # Call action handler
            context = {"job_id": "job1_20250101_120000", "source": "ExplainHubTabs"}
            tab._handle_explain_hub_action("artifact://job1_20250101_120000", context)
            
            # Verify action router was called
            mock_action_router.handle_action.assert_called_once_with(
                "artifact://job1_20250101_120000",
                context
            )
            
            # Verify log message
            assert any("Opening artifact navigator" in msg for msg in log_calls)

    def test_handle_explain_hub_action_internal(self, app, mock_matrix):
        """Test handling internal navigation action from ExplainHubTabs."""
        with patch("gui.desktop.tabs.gate_summary_dashboard_tab.get_cross_job_gate_summary_service"):
            tab = GateSummaryDashboardTab()
            tab.current_matrix = mock_matrix
            
            # Mock action router
            mock_action_router = Mock()
            tab.action_router = mock_action_router
            
            # Mock log signal
            log_calls = []
            tab.log_signal.connect(lambda msg: log_calls.append(msg))
            
            # Call action handler
            context = {"job_id": "job1_20250101_120000", "source": "ExplainHubTabs"}
            tab._handle_explain_hub_action("internal://test", context)
            
            # Verify action router was called
            mock_action_router.handle_action.assert_called_once_with(
                "internal://test",
                context
            )
            
            # Verify log message
            assert any("Handling internal navigation" in msg for msg in log_calls)

    def test_handle_explain_hub_action_unknown(self, app, mock_matrix):
        """Test handling unknown action from ExplainHubTabs."""
        with patch("gui.desktop.tabs.gate_summary_dashboard_tab.get_cross_job_gate_summary_service"):
            tab = GateSummaryDashboardTab()
            tab.current_matrix = mock_matrix
            
            # Mock action router
            mock_action_router = Mock()
            tab.action_router = mock_action_router
            
            # Mock log signal
            log_calls = []
            tab.log_signal.connect(lambda msg: log_calls.append(msg))
            
            # Call action handler with unknown target
            context = {"job_id": "job1_20250101_120000", "source": "ExplainHubTabs"}
            tab._handle_explain_hub_action("unknown://action", context)
            
            # Verify action router was called
            mock_action_router.handle_action.assert_called_once_with(
                "unknown://action",
                context
            )
            
            # Verify log message
            assert any("Handling ExplainHub action" in msg for msg in log_calls)

    def test_handle_gate_explain_action_job_not_found(self, app, mock_matrix):
        """Test gate explain action when job is not found."""
        with patch("gui.desktop.tabs.gate_summary_dashboard_tab.get_cross_job_gate_summary_service"):
            tab = GateSummaryDashboardTab()
            tab.current_matrix = mock_matrix
            
            # Mock log signal
            log_calls = []
            tab.log_signal.connect(lambda msg: log_calls.append(msg))
            
            # Call with non-existent job ID
            context = {"job_id": "non_existent_job", "source": "ExplainHubTabs"}
            tab._handle_gate_explain_action("non_existent_job", context)
            
            # Verify error log
            assert any("not found for gate explanation" in msg for msg in log_calls)

    def test_handle_evidence_action_job_not_found(self, app, mock_matrix):
        """Test evidence action when job is not found."""
        with patch("gui.desktop.tabs.gate_summary_dashboard_tab.get_cross_job_gate_summary_service"):
            tab = GateSummaryDashboardTab()
            tab.current_matrix = mock_matrix
            
            # Mock log signal
            log_calls = []
            tab.log_signal.connect(lambda msg: log_calls.append(msg))
            
            # Mock EvidenceBrowserDialog to test error handling
            with patch("gui.desktop.tabs.gate_summary_dashboard_tab.EvidenceBrowserDialog") as mock_dialog_class:
                mock_dialog_class.side_effect = Exception("Test error")
                
                # Call action handler
                context = {"job_id": "job1_20250101_120000", "source": "ExplainHubTabs"}
                tab._handle_evidence_action("job1_20250101_120000", context)
                
                # Verify error was logged
                assert any("Error opening evidence browser" in msg for msg in log_calls)

    def test_route_through_action_router(self, app, mock_matrix):
        """Test routing action through ActionRouterService."""
        with patch("gui.desktop.tabs.gate_summary_dashboard_tab.get_cross_job_gate_summary_service"):
            tab = GateSummaryDashboardTab()
            tab.current_matrix = mock_matrix
            
            # Mock action router
            mock_action_router = Mock()
            mock_action_router.handle_action.return_value = True
            tab.action_router = mock_action_router
            
            # Mock log signal
            log_calls = []
            tab.log_signal.connect(lambda msg: log_calls.append(msg))
            
            # Call routing method
            context = {"job_id": "job1_20250101_120000", "source": "ExplainHubTabs"}
            tab._route_through_action_router("test://action", context)
            
            # Verify action router was called
            mock_action_router.handle_action.assert_called_once_with(
                "test://action",
                context
            )
            
            # Verify success log
            assert any("Action handled" in msg for msg in log_calls)

    def test_route_through_action_router_failure(self, app, mock_matrix):
        """Test routing action through ActionRouterService with failure."""
        with patch("gui.desktop.tabs.gate_summary_dashboard_tab.get_cross_job_gate_summary_service"):
            tab = GateSummaryDashboardTab()
            tab.current_matrix = mock_matrix
            
            # Mock action router that returns False (failure)
            mock_action_router = Mock()
            mock_action_router.handle_action.return_value = False
            tab.action_router = mock_action_router
            
            # Mock log signal
            log_calls = []
            tab.log_signal.connect(lambda msg: log_calls.append(msg))
            
            # Call routing method
            context = {"job_id": "job1_20250101_120000", "source": "ExplainHubTabs"}
            tab._route_through_action_router("test://action", context)
            
            # Verify action router was called
            mock_action_router.handle_action.assert_called_once_with(
                "test://action",
                context
            )
            
            # Verify failure log
            assert any("Action failed" in msg for msg in log_calls)

    def test_route_through_action_router_error(self, app, mock_matrix):
        """Test routing action through ActionRouterService with exception."""
        with patch("gui.desktop.tabs.gate_summary_dashboard_tab.get_cross_job_gate_summary_service"):
            tab = GateSummaryDashboardTab()
            tab.current_matrix = mock_matrix
            
            # Mock action router that raises exception
            mock_action_router = Mock()
            mock_action_router.handle_action.side_effect = Exception("Router error")
            tab.action_router = mock_action_router
            
            # Mock log signal
            log_calls = []
            tab.log_signal.connect(lambda msg: log_calls.append(msg))
            
            # Call routing method
            context = {"job_id": "job1_20250101_120000", "source": "ExplainHubTabs"}
            tab._route_through_action_router("test://action", context)
            
            # Verify action router was called
            mock_action_router.handle_action.assert_called_once_with(
                "test://action",
                context
            )
            
            # Verify error log
            assert any("Error routing action" in msg for msg in log_calls)

    def test_find_job_summary(self, app, mock_matrix):
        """Test finding job summary by ID."""
        with patch("gui.desktop.tabs.gate_summary_dashboard_tab.get_cross_job_gate_summary_service"):
            tab = GateSummaryDashboardTab()
            tab.current_matrix = mock_matrix
            
            # Find existing job
            result = tab._find_job_summary("job1_20250101_120000")
            assert result is not None
            assert result.job_id == "job1_20250101_120000"
            
            # Find non-existent job
            result = tab._find_job_summary("non_existent")
            assert result is None
            
            # Test with no matrix
            tab.current_matrix = None
            result = tab._find_job_summary("job1_20250101_120000")
            assert result is None

    def test_explain_hub_tabs_integration(self, app, mock_matrix):
        """Test ExplainHubTabs integration with action signal."""
        with patch("gui.desktop.tabs.gate_summary_dashboard_tab.get_cross_job_gate_summary_service"):
            tab = GateSummaryDashboardTab()
            tab.current_matrix = mock_matrix
            
            # Verify ExplainHubTabs widget exists
            assert hasattr(tab, 'explain_hub_tabs')
            assert tab.explain_hub_tabs is not None
            
            # Verify signal connection
            # This is done in setup_ui, but we can verify by checking if action_requested
            # signal is connected to _handle_explain_hub_action
            # We'll test by emitting a signal and checking if handler is called
            
            # Mock the handler
            handler_called = False
            handler_target = None
            handler_context = None
            
            def mock_handler(target, context):
                nonlocal handler_called, handler_target, handler_context
                handler_called = True
                handler_target = target
                handler_context = context
            
            # Temporarily replace the handler
            original_handler = tab._handle_explain_hub_action
            tab._handle_explain_hub_action = mock_handler
            
            try:
                # Emit action signal from ExplainHubTabs
                context = {"job_id": "job1_20250101_120000", "source": "ExplainHubTabs"}
                tab.explain_hub_tabs.action_requested.emit("gate_explain://job1_20250101_120000", context)
                
                # Verify handler was called
                assert handler_called
                assert handler_target == "gate_explain://job1_20250101_120000"
                assert handler_context == context
            finally:
                # Restore original handler
                tab._handle_explain_hub_action = original_handler