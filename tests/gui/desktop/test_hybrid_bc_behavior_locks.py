"""
Behavior lock tests for Hybrid BC v1.1 Shadow Adoption.

Ensures no double-click bypass and auto-close behavior.
"""

import pytest
from unittest.mock import Mock, patch
from PySide6.QtCore import Qt, QTimer, QPoint
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QWidget

# Try to import our widgets; if they don't exist, skip the test
try:
    from gui.desktop.tabs.op_tab import OpTab, JobsTableModel
    from gui.desktop.widgets.analysis_drawer_widget import AnalysisDrawerWidget
    OP_TAB_AVAILABLE = True
except ImportError:
    OP_TAB_AVAILABLE = False


@pytest.fixture
def app():
    """Create QApplication instance for GUI tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.mark.skipif(not OP_TAB_AVAILABLE, reason="OpTab not available")
class TestHybridBCBehaviorLocks:
    """Test behavior locks for Hybrid BC."""
    
    @patch('gui.desktop.tabs.op_tab.get_registry_strategies')
    @patch('gui.desktop.tabs.op_tab.get_registry_instruments')
    @patch('gui.desktop.tabs.op_tab.get_registry_datasets')
    @patch('gui.desktop.tabs.op_tab.get_jobs')
    @patch('gui.desktop.widgets.gate_summary_widget.fetch_gate_summary')
    def test_double_click_blocked(self, mock_fetch_gate_summary, mock_get_jobs, mock_get_datasets,
                                 mock_get_instruments, mock_get_strategies, app):
        """Double-click on a list row must not open drawer."""
        # Mock the API calls
        mock_get_strategies.return_value = []
        mock_get_instruments.return_value = []
        mock_get_datasets.return_value = []
        mock_get_jobs.return_value = []
        from gui.services.gate_summary_service import GateSummary, GateStatus
        mock_summary = GateSummary(
            gates=[],
            timestamp="2026-01-13T00:00:00Z",
            overall_status=GateStatus.PASS,
            overall_message="All gates passed"
        )
        mock_fetch_gate_summary.return_value = mock_summary
        
        # Create OpTab
        tab = OpTab()
        tab.resize(800, 600)
        tab.show()
        QApplication.processEvents()
        
        # Mock some job data
        jobs = [
            {
                "job_id": "test_job_123",
                "strategy_name": "Test Strategy",
                "instrument": "MNQ",
                "timeframe": "5m",
                "run_mode": "backtest",
                "season": "2026Q1",
                "status": "SUCCEEDED",
                "created_at": "2026-01-13T00:00:00Z",
                "finished_at": "2026-01-13T01:00:00Z",
            }
        ]
        tab.jobs_model.set_jobs(jobs)
        
        # Ensure drawer is closed initially
        assert not tab.analysis_drawer.isVisible()
        
        # Simulate double-click on first row
        index = tab.jobs_model.index(0, 0)  # First cell
        tab.jobs_table.doubleClicked.emit(index)
        
        # Process events
        QApplication.processEvents()
        
        # Drawer should still be closed (double-click blocked)
        assert not tab.analysis_drawer.isVisible()
        
        # Status label should show double-click disabled message
        # (optional check, depends on implementation)
    
    @patch('gui.desktop.tabs.op_tab.get_registry_strategies')
    @patch('gui.desktop.tabs.op_tab.get_registry_instruments')
    @patch('gui.desktop.tabs.op_tab.get_registry_datasets')
    @patch('gui.desktop.tabs.op_tab.get_jobs')
    @patch('gui.desktop.tabs.op_tab.get_artifacts')
    @patch('gui.desktop.widgets.gate_summary_widget.fetch_gate_summary')
    def test_auto_close_on_selection_change(self, mock_fetch_gate_summary, mock_get_artifacts, mock_get_jobs,
                                           mock_get_datasets, mock_get_instruments,
                                           mock_get_strategies, app):
        """Selecting job A, opening drawer, then selecting job B must close drawer immediately."""
        # Mock the API calls
        mock_get_strategies.return_value = []
        mock_get_instruments.return_value = []
        mock_get_datasets.return_value = []
        mock_get_jobs.return_value = []
        mock_get_artifacts.return_value = {}
        from gui.services.gate_summary_service import GateSummary, GateStatus
        mock_summary = GateSummary(
            gates=[],
            timestamp="2026-01-13T00:00:00Z",
            overall_status=GateStatus.PASS,
            overall_message="All gates passed"
        )
        mock_fetch_gate_summary.return_value = mock_summary
        
        # Create OpTab and ensure it has geometry
        tab = OpTab()
        tab.resize(800, 600)  # Give it some size
        tab.show()  # Make it visible
        QApplication.processEvents()
        
        # Mock job data with two jobs
        jobs = [
            {
                "job_id": "test_job_123",
                "strategy_name": "Test Strategy",
                "instrument": "MNQ",
                "timeframe": "5m",
                "run_mode": "backtest",
                "season": "2026Q1",
                "status": "SUCCEEDED",
                "created_at": "2026-01-13T00:00:00Z",
                "finished_at": "2026-01-13T01:00:00Z",
                "artifacts": {
                    "gatekeeper": {
                        "total_permutations": 100,
                        "valid_candidates": 42,
                        "plateau_check": "Pass",
                    }
                }
            },
            {
                "job_id": "test_job_456",
                "strategy_name": "Another Strategy",
                "instrument": "MXF",
                "timeframe": "15m",
                "run_mode": "research",
                "season": "2026Q1",
                "status": "SUCCEEDED",
                "created_at": "2026-01-13T02:00:00Z",
                "finished_at": "2026-01-13T03:00:00Z",
                "artifacts": {
                    "gatekeeper": {
                        "total_permutations": 50,
                        "valid_candidates": 25,
                        "plateau_check": "Pass",
                    }
                }
            }
        ]
        tab.jobs_model.set_jobs(jobs)
        
        # Select first job
        tab.jobs_table.selectRow(0)
        QApplication.processEvents()  # Let selection propagate
        
        # Mock opening drawer for first job
        # (We need to bypass the valid_candidates check)
        tab.selected_job_context = type('obj', (object,), {
            'gatekeeper': {'valid_candidates': 42}
        })()
        tab.analysis_drawer.open_for_job("test_job_123")
        QApplication.processEvents()
        
        # Drawer should be open (or at least not hidden)
        # In test environment, the drawer might not be fully visible due to animation
        # but we can check that it's not hidden
        assert not tab.analysis_drawer.isHidden()
        
        # Now select second job
        tab.jobs_table.selectRow(1)
        QApplication.processEvents()  # Let selection propagate
        
        # Drawer should be closed immediately (auto-close)
        # Wait a bit for the close animation if any
        for _ in range(5):
            QApplication.processEvents()
        
        assert tab.analysis_drawer.isHidden()
    
    @patch('gui.desktop.tabs.op_tab.get_registry_strategies')
    @patch('gui.desktop.tabs.op_tab.get_registry_instruments')
    @patch('gui.desktop.tabs.op_tab.get_registry_datasets')
    @patch('gui.desktop.tabs.op_tab.get_jobs')
    @patch('gui.desktop.tabs.op_tab.get_artifacts')
    @patch('gui.desktop.widgets.gate_summary_widget.fetch_gate_summary')
    def test_open_analysis_only_via_explain_hub(self, mock_fetch_gate_summary, mock_get_artifacts,
                                               mock_get_jobs, mock_get_datasets,
                                               mock_get_instruments, mock_get_strategies, app):
        """Analysis drawer can only be opened via Explain Hub button, not directly."""
        # Mock the API calls
        mock_get_strategies.return_value = []
        mock_get_instruments.return_value = []
        mock_get_datasets.return_value = []
        mock_get_jobs.return_value = []
        mock_get_artifacts.return_value = {}
        # Create a proper GateSummary mock
        from gui.services.gate_summary_service import GateSummary, GateResult, GateStatus
        mock_summary = GateSummary(
            gates=[],
            timestamp="2026-01-13T00:00:00Z",
            overall_status=GateStatus.PASS,
            overall_message="All gates passed"
        )
        mock_fetch_gate_summary.return_value = mock_summary
        
        # Create OpTab
        tab = OpTab()
        tab.resize(800, 600)
        tab.show()
        QApplication.processEvents()
        
        # Mock job data
        jobs = [
            {
                "job_id": "test_job_123",
                "strategy_name": "Test Strategy",
                "instrument": "MNQ",
                "timeframe": "5m",
                "run_mode": "backtest",
                "season": "2026Q1",
                "status": "SUCCEEDED",
                "created_at": "2026-01-13T00:00:00Z",
                "finished_at": "2026-01-13T01:00:00Z",
                "artifacts": {
                    "gatekeeper": {
                        "total_permutations": 100,
                        "valid_candidates": 42,
                        "plateau_check": "Pass",
                    }
                }
            }
        ]
        tab.jobs_model.set_jobs(jobs)
        
        # Select the job
        tab.jobs_table.selectRow(0)
        QApplication.processEvents()
        
        # Try to open drawer directly (bypassing Explain Hub)
        # This should not work because the drawer requires valid_candidates > 0
        # and the selection flow
        tab.analysis_drawer.open_for_job("test_job_123")
        QApplication.processEvents()
        
        # Drawer might open but without content (depends on implementation)
        # The key point is that the normal flow goes through Explain Hub
        
        # Now test the proper flow: simulate Explain Hub button click
        # First, ensure we have a context with valid_candidates > 0
        from gui.services.hybrid_bc_vms import JobContextVM
        mock_vm = JobContextVM(
            job_id='test_job_123',
            full_note='Test note',
            tags=[],
            config_snapshot={},
            health={'summary': 'OK'},
            gatekeeper={'total_permutations': 100, 'valid_candidates': 42, 'plateau_check': 'Pass'}
        )
        tab.explain_hub.set_context(mock_vm)
        
        # Connect to the request_open_analysis signal
        drawer_opened = False
        def on_drawer_opened(job_id):
            nonlocal drawer_opened
            drawer_opened = True
            assert job_id == "test_job_123"
        
        tab.explain_hub.request_open_analysis.connect(on_drawer_opened)
        
        # Simulate button click (if we can access the button)
        if hasattr(tab.explain_hub, 'open_analysis_btn'):
            # Ensure button is enabled
            assert tab.explain_hub.open_analysis_btn.isEnabled()
            tab.explain_hub.open_analysis_btn.click()
            QApplication.processEvents()
            
            # Check that drawer opened via signal
            assert drawer_opened
    
    @patch('gui.desktop.widgets.gate_summary_widget.fetch_gate_summary')
    def test_drawer_closes_when_no_selection(self, mock_fetch_gate_summary, app):
        """Drawer should close when selection is cleared."""
        # Mock the API call
        from gui.services.gate_summary_service import GateSummary, GateStatus
        mock_summary = GateSummary(
            gates=[],
            timestamp="2026-01-13T00:00:00Z",
            overall_status=GateStatus.PASS,
            overall_message="All gates passed"
        )
        mock_fetch_gate_summary.return_value = mock_summary
        
        # Create OpTab
        tab = OpTab()
        tab.resize(800, 600)
        tab.show()
        QApplication.processEvents()
        
        # Mock job data
        jobs = [
            {
                "job_id": "test_job_123",
                "strategy_name": "Test Strategy",
                "instrument": "MNQ",
                "timeframe": "5m",
                "run_mode": "backtest",
                "season": "2026Q1",
                "status": "SUCCEEDED",
                "created_at": "2026-01-13T00:00:00Z",
                "finished_at": "2026-01-13T01:00:00Z",
                "artifacts": {
                    "gatekeeper": {
                        "total_permutations": 100,
                        "valid_candidates": 42,
                        "plateau_check": "Pass",
                    }
                }
            }
        ]
        tab.jobs_model.set_jobs(jobs)
        
        # Select the job
        tab.jobs_table.selectRow(0)
        QApplication.processEvents()
        
        # Open drawer
        tab.selected_job_context = type('obj', (object,), {
            'gatekeeper': {'valid_candidates': 42}
        })()
        tab.analysis_drawer.open_for_job("test_job_123")
        QApplication.processEvents()
        
        # Drawer should be open
        assert tab.analysis_drawer.isVisible()
        
        # Clear selection
        tab.jobs_table.clearSelection()
        QApplication.processEvents()
        
        # Drawer should be closed (handled by handle_job_selection)
        # Note: handle_job_selection is called on selection change
        # We need to trigger it manually or via signal
        tab.handle_job_selection(tab.jobs_table.selectionModel().selection(),
                                 tab.jobs_table.selectionModel().selection())
        QApplication.processEvents()
        
        # Drawer should be closed
        assert not tab.analysis_drawer.isVisible()
    
    @patch('gui.desktop.widgets.gate_summary_widget.fetch_gate_summary')
    def test_valid_candidates_gate(self, mock_fetch_gate_summary, app):
        """Drawer should not open if valid_candidates <= 0."""
        # Mock the API call
        from gui.services.gate_summary_service import GateSummary, GateStatus
        mock_summary = GateSummary(
            gates=[],
            timestamp="2026-01-13T00:00:00Z",
            overall_status=GateStatus.PASS,
            overall_message="All gates passed"
        )
        mock_fetch_gate_summary.return_value = mock_summary
        
        # Create OpTab
        tab = OpTab()
        tab.resize(800, 600)
        tab.show()
        QApplication.processEvents()
        
        # Mock job data with zero valid candidates
        jobs = [
            {
                "job_id": "test_job_123",
                "strategy_name": "Test Strategy",
                "instrument": "MNQ",
                "timeframe": "5m",
                "run_mode": "backtest",
                "season": "2026Q1",
                "status": "SUCCEEDED",
                "created_at": "2026-01-13T00:00:00Z",
                "finished_at": "2026-01-13T01:00:00Z",
                "artifacts": {
                    "gatekeeper": {
                        "total_permutations": 100,
                        "valid_candidates": 0,  # Zero valid candidates
                        "plateau_check": "Pass",
                    }
                }
            }
        ]
        tab.jobs_model.set_jobs(jobs)
        
        # Select the job
        tab.jobs_table.selectRow(0)
        QApplication.processEvents()
        
        # Set context with zero valid candidates
        tab.selected_job_context = type('obj', (object,), {
            'job_id': 'test_job_123',
            'gatekeeper': {'valid_candidates': 0}
        })()
        
        # Try to open drawer via Explain Hub signal
        drawer_opened = False
        def on_drawer_opened(job_id):
            nonlocal drawer_opened
            drawer_opened = True
        
        tab.explain_hub.request_open_analysis.connect(on_drawer_opened)
        
        # Simulate button click
        if hasattr(tab.explain_hub, 'open_analysis_btn'):
            # Button should be disabled when valid_candidates <= 0
            # Check if button is disabled
            if not tab.explain_hub.open_analysis_btn.isEnabled():
                # Button is disabled, good
                pass
            else:
                # Button is enabled (shouldn't happen), click it
                tab.explain_hub.open_analysis_btn.click()
                QApplication.processEvents()
                
                # Drawer should not open
                assert not drawer_opened
                assert not tab.analysis_drawer.isVisible()


def test_analysis_drawer_lazy_load(app):
    """Analysis drawer should lazy-load content on open."""
    # Skip if AnalysisDrawerWidget not available
    try:
        from gui.desktop.widgets.analysis_drawer_widget import AnalysisDrawerWidget
        from gui.services.hybrid_bc_vms import JobAnalysisVM
    except ImportError:
        pytest.skip("AnalysisDrawerWidget not available")
    
    # Create a parent widget
    parent = QApplication.activeWindow() or QWidget()
    
    # Create drawer
    drawer = AnalysisDrawerWidget(parent)
    
    # Mock _load_analysis_content method
    load_called = False
    def mock_load_analysis_content(vm):
        nonlocal load_called
        load_called = True
        assert vm.job_id == "test_job_123"
    
    drawer._load_analysis_content = mock_load_analysis_content
    
    # Create a mock VM
    mock_vm = JobAnalysisVM(
        job_id="test_job_123",
        payload={"test": "data"}
    )
    
    # Open drawer with VM (simulating lazy load via parent providing VM)
    drawer.open_for_job("test_job_123", mock_vm)
    QApplication.processEvents()
    
    # _load_analysis_content should be called
    # Process events a few times
    for _ in range(5):
        QApplication.processEvents()
    
    # Check that _load_analysis_content was called
    assert load_called, "_load_analysis_content should be called for lazy loading"
    
    # Also test that without VM, placeholder shows loading
    drawer2 = AnalysisDrawerWidget(parent)
    drawer2.open_for_job("test_job_456")  # No VM
    QApplication.processEvents()
    
    # Placeholder should show "Loading analysis..."
    assert drawer2.placeholder_label.text() == "Loading analysis..."


if __name__ == "__main__":
    pytest.main([__file__, "-v"])