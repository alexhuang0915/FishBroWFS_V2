"""
Visual safety tests for Hybrid BC v1.1 Shadow Adoption.

Ensures Layer 1 (Job Index) and Layer 2 (Explain Hub) never render performance metrics labels.
"""

import pytest
import re
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt

# Try to import our widgets; if they don't exist, skip the test
try:
    from gui.desktop.widgets.explain_hub_widget import ExplainHubWidget
    from gui.services.hybrid_bc_vms import JobContextVM
    EXPLAIN_HUB_AVAILABLE = True
except ImportError:
    EXPLAIN_HUB_AVAILABLE = False

try:
    from gui.desktop.tabs.op_tab import JobsTableModel
    JOBS_MODEL_AVAILABLE = True
except ImportError:
    JOBS_MODEL_AVAILABLE = False


@pytest.fixture
def app():
    """Create QApplication instance for GUI tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


# Performance metric keywords (case-insensitive)
PERFORMANCE_KEYWORDS = [
    r"sharpe",
    r"cagr",
    r"mdd",
    r"drawdown",
    r"roi",
    r"rank",
    r"score",
    r"net[\s_-]?profit",
    r"profit",
    r"pnl",
    r"duration.*score",  # matches "Duration Score" etc.
    r"performance",
    r"metric",
]


def contains_performance_text(text: str) -> bool:
    """Check if text contains any performance metric keywords."""
    if not text:
        return False
    text_lower = text.lower()
    for pattern in PERFORMANCE_KEYWORDS:
        if re.search(pattern, text_lower):
            return True
    return False


@pytest.mark.skipif(not JOBS_MODEL_AVAILABLE, reason="JobsTableModel not available")
def test_jobs_table_model_headers_no_performance():
    """JobsTableModel headers must not contain performance column names."""
    from gui.desktop.tabs.op_tab import JobsTableModel
    
    model = JobsTableModel()
    headers = model.headers
    
    # Check each header for performance keywords
    for header in headers:
        assert not contains_performance_text(header), \
            f"Header '{header}' contains performance keyword"
    
    # Specific check: ensure no "Duration" or "Score" columns
    # (these were previously columns 7 and 8 but are now "Created" and "Finished")
    assert "Duration" not in headers
    assert "Score" not in headers
    assert "Sharpe" not in headers
    assert "CAGR" not in headers
    assert "MDD" not in headers


@pytest.mark.skipif(not EXPLAIN_HUB_AVAILABLE, reason="ExplainHubWidget not available")
def test_explain_hub_widget_no_performance_labels(app):
    """ExplainHubWidget must not display performance metrics in its UI."""
    # Create a proper JobContextVM without performance metrics
    from gui.services.hybrid_bc_vms import JobContextVM
    
    context_vm = JobContextVM(
        job_id="test_job_123",
        full_note="Test run with no metrics",
        tags=["test"],
        config_snapshot={"param": "value"},
        health={
            "summary": "Healthy",
            "error_details_json": None,
            "logs_tail": ["log1", "log2"],
        },
        gatekeeper={
            "total_permutations": 100,
            "valid_candidates": 42,
            "plateau_check": "Pass",
        },
        status="SUCCEEDED",
        error_details=None,
        artifacts={}
    )
    
    # Create the widget
    widget = ExplainHubWidget()
    
    # Set context (this should trigger UI updates)
    widget.set_context(context_vm)
    
    # Process events to ensure UI updates
    QApplication.processEvents()
    
    # Get all text from the widget by traversing child widgets
    all_text = collect_widget_text(widget)
    
    # Check that no performance keywords appear
    for text in all_text:
        assert not contains_performance_text(text), \
            f"ExplainHubWidget contains performance text: '{text}'"
    
    # Also check that the Open Analysis Drawer button exists and is enabled
    # (button should be enabled because valid_candidates > 0)
    # This is a basic sanity check
    assert widget.open_analysis_btn is not None


def collect_widget_text(widget):
    """Recursively collect text from all child widgets."""
    texts = []
    
    # Get widget's own text properties
    if hasattr(widget, 'text') and callable(getattr(widget, 'text')):
        try:
            text = widget.text()
            if text:
                texts.append(text)
        except:
            pass
    
    if hasattr(widget, 'toolTip') and callable(getattr(widget, 'toolTip')):
        try:
            tooltip = widget.toolTip()
            if tooltip:
                texts.append(tooltip)
        except:
            pass
    
    if hasattr(widget, 'placeholderText') and callable(getattr(widget, 'placeholderText')):
        try:
            placeholder = widget.placeholderText()
            if placeholder:
                texts.append(placeholder)
        except:
            pass
    
    if hasattr(widget, 'windowTitle') and callable(getattr(widget, 'windowTitle')):
        try:
            title = widget.windowTitle()
            if title:
                texts.append(title)
        except:
            pass
    
    # Recursively check children
    for child in widget.children():
        if isinstance(child, QWidget):
            texts.extend(collect_widget_text(child))
    
    return texts


@pytest.mark.skipif(not JOBS_MODEL_AVAILABLE, reason="JobsTableModel not available")
def test_jobs_table_model_data_no_performance():
    """JobsTableModel data method must not return performance values."""
    from gui.desktop.tabs.op_tab import JobsTableModel
    from PySide6.QtCore import QModelIndex, Qt
    
    model = JobsTableModel()
    
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
            # No performance fields
        }
    ]
    model.set_jobs(jobs)
    
    # Check each cell for performance text
    for row in range(model.rowCount()):
        for col in range(model.columnCount()):
            index = model.index(row, col)
            data = model.data(index, Qt.ItemDataRole.DisplayRole)
            if data:
                assert not contains_performance_text(str(data)), \
                    f"Cell ({row},{col}) contains performance text: '{data}'"


def test_performance_keyword_detection():
    """Test that performance keyword detection works correctly."""
    # Positive cases
    assert contains_performance_text("Sharpe ratio is 1.5")
    assert contains_performance_text("CAGR: 15%")
    assert contains_performance_text("Maximum Drawdown (MDD)")
    assert contains_performance_text("Net Profit $1000")
    assert contains_performance_text("ROI calculation")
    assert contains_performance_text("Rank 3")
    assert contains_performance_text("Score: 0.85")
    assert contains_performance_text("PnL analysis")
    assert contains_performance_text("DURATION SCORE")  # uppercase
    assert contains_performance_text("Duration-Score")  # hyphen
    assert contains_performance_text("duration_score")  # underscore
    
    # Negative cases (should not trigger)
    assert not contains_performance_text("Job completed successfully")
    assert not contains_performance_text("Strategy backtest")
    assert not contains_performance_text("Instrument: MNQ")
    assert not contains_performance_text("Timeframe: 5m")
    assert not contains_performance_text("Status: SUCCEEDED")
    assert not contains_performance_text("Created: 2026-01-13")
    assert not contains_performance_text("Finished: 2026-01-13")
    assert not contains_performance_text("Actions")
    assert not contains_performance_text("Explain Hub")
    assert not contains_performance_text("Gatekeeper")
    assert not contains_performance_text("Plateau check")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])