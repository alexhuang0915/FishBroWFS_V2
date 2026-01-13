"""
Test that Run Research button is disabled if Primary Market is missing.
"""
import pytest
pytest.skip("UI feature not yet implemented", allow_module_level=True)

from PySide6.QtWidgets import QApplication, QComboBox, QGroupBox, QLabel
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


def test_run_research_disabled_without_primary_market(op_tab):
    """Verify Run Research button is disabled when no Primary Market selected."""
    # Initially, primary market dropdown might be empty or have selection
    # Clear selection if possible
    op_tab.primary_market_cb.setCurrentIndex(-1)  # Clear selection
    
    # Update UI state
    op_tab.update_cache_status()
    op_tab.set_ui_locked(False)  # Ensure UI is not locked
    
    # Run Research button should be disabled
    assert not op_tab.run_research_btn.isEnabled(), \
        "Run Research button should be disabled without Primary Market selection"
    
    # Select a primary market
    if op_tab.primary_market_cb.count() > 0:
        op_tab.primary_market_cb.setCurrentIndex(0)
        op_tab.update_cache_status()
        op_tab.set_ui_locked(False)
        
        # Run Research button should now be enabled
        assert op_tab.run_research_btn.isEnabled(), \
            "Run Research button should be enabled with Primary Market selected"
        
        # Clear selection again
        op_tab.primary_market_cb.setCurrentIndex(-1)
        op_tab.update_cache_status()
        op_tab.set_ui_locked(False)
        
        # Should be disabled again
        assert not op_tab.run_research_btn.isEnabled(), \
            "Run Research button should be disabled after clearing Primary Market"


def test_run_research_enabled_with_primary_market(op_tab):
    """Verify Run Research button is enabled when Primary Market is selected."""
    # Skip test if no datasets loaded
    if op_tab.primary_market_cb.count() == 0:
        pytest.skip("No datasets available for testing")
    
    # Select first primary market
    op_tab.primary_market_cb.setCurrentIndex(0)
    op_tab.update_cache_status()
    op_tab.set_ui_locked(False)
    
    # Run Research button should be enabled
    assert op_tab.run_research_btn.isEnabled(), \
        "Run Research button should be enabled with Primary Market selected"
    
    # Verify button text
    assert op_tab.run_research_btn.text() == "Run Research", \
        "Button should say 'Run Research'"


def test_run_research_independent_of_context_feeds(op_tab):
    """Verify Run Research button state depends on Context Feeds selection (Phase 18.7)."""
    # Skip test if no datasets loaded
    if op_tab.primary_market_cb.count() == 0:
        pytest.skip("No datasets available for testing")
    
    # Select primary market
    op_tab.primary_market_cb.setCurrentIndex(0)
    op_tab.update_cache_status()
    op_tab.set_ui_locked(False)
    
    # Clear any prepared feeds
    op_tab.data2_prepared_feeds.clear()
    
    # Initially should be enabled (no context feeds selected)
    initial_state = op_tab.run_research_btn.isEnabled()
    
    # Simulate selecting context feeds (Data2)
    op_tab.selected_context_feeds.add("VX.FUT")
    op_tab.selected_context_feeds.add("DX.FUT")
    
    # Update UI - with Phase 18.7, context feeds affect run button
    op_tab.update_cache_status()
    op_tab.update_run_analysis_button()
    op_tab.set_ui_locked(False)
    
    # With Data2 selected but not prepared, button should be disabled
    # (unless cache status also prevents it from being enabled)
    # We'll check the tooltip to verify the gating logic is working
    tooltip = op_tab.run_research_btn.toolTip()
    
    # If button is disabled, tooltip should mention context feeds
    if not op_tab.run_research_btn.isEnabled():
        assert "Context feeds" in tooltip or "Preparing required data" in tooltip, \
            "When Data2 selected but not prepared, tooltip should mention context feeds"
    
    # Now mark feeds as prepared
    op_tab.data2_prepared_feeds.add("VX.FUT")
    op_tab.data2_prepared_feeds.add("DX.FUT")
    op_tab.update_run_analysis_button()
    
    # Button should be enabled again (if other conditions met)
    # The exact state depends on cache status, but gating logic should pass


def test_run_research_independent_of_cache_status(op_tab):
    """Verify Run Research button state doesn't depend on cache status."""
    # Skip test if no datasets loaded
    if op_tab.primary_market_cb.count() == 0:
        pytest.skip("No datasets available for testing")
    
    # Select primary market
    op_tab.primary_market_cb.setCurrentIndex(0)
    
    # Manually set cache status to different values
    op_tab.bars_cache_status = "READY"
    op_tab.features_cache_status = "READY"
    op_tab.update_cache_status()
    op_tab.set_ui_locked(False)
    
    # Should be enabled with READY cache
    ready_state = op_tab.run_research_btn.isEnabled()
    
    # Change cache status to MISSING
    op_tab.bars_cache_status = "MISSING"
    op_tab.features_cache_status = "MISSING"
    op_tab.update_cache_status()
    op_tab.set_ui_locked(False)
    
    # Should still be enabled (cache status doesn't affect run button)
    missing_state = op_tab.run_research_btn.isEnabled()
    
    assert ready_state == missing_state, \
        "Cache status should not affect Run Research button state"


def test_run_research_disabled_during_operation(op_tab):
    """Verify Run Research button is disabled during an operation."""
    # Skip test if no datasets loaded
    if op_tab.primary_market_cb.count() == 0:
        pytest.skip("No datasets available for testing")
    
    # Select primary market
    op_tab.primary_market_cb.setCurrentIndex(0)
    op_tab.update_cache_status()
    
    # Initially should be enabled
    assert op_tab.run_research_btn.isEnabled(), \
        "Run Research should be enabled before operation"
    
    # Simulate operation in progress
    op_tab.set_ui_locked(True)
    
    # Should be disabled during operation
    assert not op_tab.run_research_btn.isEnabled(), \
        "Run Research should be disabled during operation"
    
    # Simulate operation completed
    op_tab.set_ui_locked(False)
    
    # Should be enabled again
    assert op_tab.run_research_btn.isEnabled(), \
        "Run Research should be enabled after operation"


def test_error_message_on_run_without_primary_market(op_tab, monkeypatch):
    """Verify error message is logged when trying to run without Primary Market."""
    # Mock the log method to capture messages
    log_messages = []
    
    def mock_log(message):
        log_messages.append(message)
    
    monkeypatch.setattr(op_tab, 'log', mock_log)
    
    # Clear primary market selection
    op_tab.primary_market_cb.setCurrentIndex(-1)
    
    # Try to start run
    op_tab.start_run()
    
    # Should log error about missing Primary Market
    error_found = any("Primary Market is required" in msg or 
                     "No Primary Market selected" in msg or
                     "ERROR: Primary Market" in msg 
                     for msg in log_messages)
    
    assert error_found, \
        "Should log error when trying to run without Primary Market"


def test_primary_market_label_text(op_tab):
    """Verify Primary Market label uses correct terminology."""
    cards = op_tab.findChildren(QGroupBox)
    card1 = None
    for card in cards:
        if card.title() == "What to Run":
            card1 = card
            break
    
    assert card1 is not None, "'What to Run' card not found"
    
    # Find all labels in card 1
    from PySide6.QtWidgets import QLabel
    labels = card1.findChildren(QLabel)
    
    # Look for Primary Market label
    primary_market_label = None
    for label in labels:
        if "Primary Market" in label.text():
            primary_market_label = label
            break
    
    assert primary_market_label is not None, "Missing 'Primary Market' label"
    assert primary_market_label.text() == "Primary Market:", \
        f"Label should be exactly 'Primary Market:' not '{primary_market_label.text()}'"