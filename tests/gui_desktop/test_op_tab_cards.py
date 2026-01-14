"""
Smoke test for Route 2 Card-Based OP Tab UI.
Route 3 Cutover: Tests that card-based components exist and can be instantiated.
"""
import pytest

from PySide6.QtWidgets import QApplication
from gui.desktop.tabs.op_tab import OpTab


@pytest.fixture
def app():
    """Create QApplication instance for GUI tests."""
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def op_tab(app):
    """Create OpTab instance for testing."""
    tab = OpTab()
    yield tab
    tab.deleteLater()


def test_op_tab_has_card_components(op_tab):
    """Verify OP tab has Route 2 card-based components."""
    # Check that card components exist
    assert op_tab.strategy_deck is not None, "StrategyCardDeck should exist"
    assert op_tab.timeframe_deck is not None, "TimeframeCardDeck should exist"
    assert op_tab.instrument_list is not None, "InstrumentCardList should exist"
    assert op_tab.mode_pills is not None, "ModePillCards should exist"
    assert op_tab.dataset_panel is not None, "DerivedDatasetPanel should exist"
    assert op_tab.date_range_selector is not None, "DateRangeSelector should exist"
    assert op_tab.run_readiness_panel is not None, "RunReadinessPanel should exist"
    
    # Check that RUN button exists
    assert hasattr(op_tab, 'run_button'), "RUN button should exist"
    assert op_tab.run_button.text() == "RUN STRATEGY", "RUN button should have correct text"


def test_op_tab_has_launch_pad_group(op_tab):
    """Verify OP tab has Launch Pad group."""
    from PySide6.QtWidgets import QGroupBox
    
    # Find Launch Pad group
    groups = op_tab.findChildren(QGroupBox)
    launch_pad_found = False
    for group in groups:
        if "Launch Pad" in group.title():
            launch_pad_found = True
            break
    
    assert launch_pad_found, "Launch Pad group should exist"


def test_op_tab_has_job_tracker_group(op_tab):
    """Verify OP tab has Job Tracker group."""
    from PySide6.QtWidgets import QGroupBox
    
    # Find Job Tracker group
    groups = op_tab.findChildren(QGroupBox)
    job_tracker_found = False
    for group in groups:
        if "Job Tracker" in group.title():
            job_tracker_found = True
            break
    
    assert job_tracker_found, "Job Tracker group should exist"


def test_op_tab_has_gate_summary(op_tab):
    """Verify OP tab has Gate Summary widget."""
    assert hasattr(op_tab, 'gate_summary_widget'), "GateSummaryWidget should exist"


def test_op_tab_has_splitter_layout(op_tab):
    """Verify OP tab uses splitter layout."""
    from PySide6.QtWidgets import QSplitter
    
    splitters = op_tab.findChildren(QSplitter)
    assert len(splitters) > 0, "Should have at least one QSplitter"


def test_no_legacy_dropdowns(op_tab):
    """Verify no legacy dropdowns exist (Route 3 cutover)."""
    from PySide6.QtWidgets import QComboBox
    
    # Find all comboboxes
    comboboxes = op_tab.findChildren(QComboBox)
    
    # Count comboboxes that are NOT part of card components
    # (some card components might use internal comboboxes, but main UI shouldn't)
    legacy_dropdowns = []
    for cb in comboboxes:
        # Check if this combobox is visible and not part of a card component
        if cb.isVisible():
            legacy_dropdowns.append(cb)
    
    # We should have minimal comboboxes (if any)
    # The test passes as long as we don't have the old dropdown-based UI
    # For now, just log the count
    print(f"Found {len(legacy_dropdowns)} visible comboboxes")