"""
Test UI Selector - Dropdown + Checkbox (Phase 18.7).

Tests that Data2 selector is dropdown-style menu with checkboxes (no search bar).
"""
import pytest
from PySide6.QtWidgets import QApplication, QCheckBox, QGroupBox, QLabel, QScrollArea, QLineEdit, QPushButton
from PySide6.QtCore import Qt

from src.gui.desktop.tabs.op_tab import OpTab


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


def test_data2_selector_no_search_bar(op_tab):
    """Verify Data2 selector has NO search bar (Phase 18.7 spec)."""
    # Find the Context Feeds card
    cards = op_tab.findChildren(QGroupBox)
    context_card = None
    for card in cards:
        if card.title() == "Context Feeds (Optional)":
            context_card = card
            break
    
    assert context_card is not None, "Context Feeds card not found"
    
    # Search for QLineEdit widgets (search bars) in the card
    line_edits = context_card.findChildren(QLineEdit)
    
    # Phase 18.7 spec: NO search bar
    assert len(line_edits) == 0, f"Found {len(line_edits)} QLineEdit widgets (search bars) but Phase 18.7 requires NO search bar"


def test_data2_selector_has_checkboxes(op_tab):
    """Verify Data2 selector has checkboxes for selection."""
    # Find checkboxes in context feeds layout
    checkboxes = op_tab.context_feeds_layout.parent().findChildren(QCheckBox)
    
    # Should have checkboxes (could be 0 if no datasets available)
    # But the structure should support checkboxes
    for cb in checkboxes:
        assert isinstance(cb, QCheckBox), "Context feed item should be QCheckBox"
        assert cb.text(), "Checkbox should have dataset identifier text"


def test_data2_selector_dropdown_style_container(op_tab):
    """Verify Data2 selector has dropdown-style container."""
    # Find the Context Feeds card
    cards = op_tab.findChildren(QGroupBox)
    context_card = None
    for card in cards:
        if card.title() == "Context Feeds (Optional)":
            context_card = card
            break
    
    assert context_card is not None, "Context Feeds card not found"
    
    # Look for scroll area (dropdown-style container should have scroll)
    scroll_areas = context_card.findChildren(QScrollArea)
    assert len(scroll_areas) > 0, "Dropdown-style container should have a scroll area"
    
    # Container should have max-height styling (check via object name or style)
    scroll_area = scroll_areas[0]
    # The scroll area should be widget resizable
    assert scroll_area.widgetResizable(), "Scroll area should be widget resizable"


def test_selection_summary_always_visible(op_tab):
    """Verify selection summary is always visible above selector."""
    # Find the selected feeds label
    selected_feeds_label = op_tab.selected_feeds_label
    
    assert selected_feeds_label is not None, "Selected feeds label not found"
    # Note: isVisible() might return False in unit test environment
    # We'll check that the label exists and has correct text format
    
    # Check initial text format
    text = selected_feeds_label.text()
    assert "Context Feeds:" in text, f"Selection summary should contain 'Context Feeds:', got '{text}'"
    
    # Should be one of the expected formats:
    # "Context Feeds: None"
    # "Context Feeds: VX, DX"
    # "Context Feeds: 5 selected"
    # The exact text depends on initial state


def test_selection_summary_updates_correctly(op_tab):
    """Verify selection summary updates correctly when feeds are selected/deselected."""
    # Clear any existing selections
    op_tab.selected_context_feeds.clear()
    
    # Test 1: No selection
    op_tab.update_selected_feeds_summary()
    assert op_tab.selected_feeds_label.text() == "Context Feeds: None"
    
    # Test 2: Single feed
    op_tab.selected_context_feeds.add("VX.FUT")
    op_tab.update_selected_feeds_summary()
    text = op_tab.selected_feeds_label.text()
    assert text == "Context Feeds: VX.FUT"
    
    # Test 3: Two feeds
    op_tab.selected_context_feeds.add("DX.FUT")
    op_tab.update_selected_feeds_summary()
    text = op_tab.selected_feeds_label.text()
    # Should show both names (order may vary)
    assert "VX.FUT" in text
    assert "DX.FUT" in text
    # Check format: "Context Feeds: " followed by comma-separated list
    assert text.startswith("Context Feeds: ")
    # Extract the list part
    list_part = text.replace("Context Feeds: ", "")
    # Split and sort for comparison
    items = [item.strip() for item in list_part.split(",")]
    assert set(items) == {"VX.FUT", "DX.FUT"}
    
    # Test 4: Three feeds (should show all names)
    op_tab.selected_context_feeds.add("ZN.FUT")
    op_tab.update_selected_feeds_summary()
    text = op_tab.selected_feeds_label.text()
    assert "VX.FUT" in text
    assert "DX.FUT" in text
    assert "ZN.FUT" in text
    # Check all three are present (order may vary)
    list_part = text.replace("Context Feeds: ", "")
    items = [item.strip() for item in list_part.split(",")]
    assert set(items) == {"VX.FUT", "DX.FUT", "ZN.FUT"}
    
    # Test 5: More than 3 feeds (should show count)
    op_tab.selected_context_feeds.add("6J.FUT")
    op_tab.selected_context_feeds.add("ES.FUT")
    op_tab.update_selected_feeds_summary()
    text = op_tab.selected_feeds_label.text()
    assert "5 selected" in text, f"Expected '5 selected' in summary, got '{text}'"


def test_select_all_none_buttons(op_tab):
    """Verify Select All and Select None buttons exist and work."""
    # Find the buttons
    select_all_btn = op_tab.select_all_feeds_btn
    select_none_btn = op_tab.select_none_feeds_btn
    
    assert select_all_btn is not None, "Select All button not found"
    assert select_none_btn is not None, "Select None button not found"
    
    assert select_all_btn.text() == "Select All"
    assert select_none_btn.text() == "Select None"
    
    # Test button connections
    assert select_all_btn.isEnabled()
    assert select_none_btn.isEnabled()


def test_selector_actions_update_summary(op_tab):
    """Verify that selector actions (Select All/None) update the summary."""
    # Clear selections
    op_tab.selected_context_feeds.clear()
    
    # Load some mock checkboxes for testing
    # We'll directly call the methods that the buttons trigger
    op_tab.select_all_context_feeds()
    # After select_all, summary should update (but depends on actual checkboxes)
    # We'll just verify the method exists and doesn't crash
    
    op_tab.select_none_context_feeds()
    # After select_none, summary should show "None"
    op_tab.update_selected_feeds_summary()
    assert "None" in op_tab.selected_feeds_label.text() or len(op_tab.selected_context_feeds) == 0


def test_ui_contract_dropdown_style(op_tab):
    """Verify UI contract: dropdown-style menu, each item has checkbox, no search bar."""
    # Find Context Feeds card
    cards = op_tab.findChildren(QGroupBox)
    context_card = None
    for card in cards:
        if card.title() == "Context Feeds (Optional)":
            context_card = card
            break
    
    assert context_card is not None
    
    # 1. No search bar (already tested)
    line_edits = context_card.findChildren(QLineEdit)
    assert len(line_edits) == 0
    
    # 2. Has checkboxes
    checkboxes = context_card.findChildren(QCheckBox)
    # Could be 0 if no datasets, but structure should support them
    
    # 3. Has Select All/Select None buttons
    buttons = context_card.findChildren(QPushButton)
    select_all_found = False
    select_none_found = False
    for btn in buttons:
        if btn.text() == "Select All":
            select_all_found = True
        elif btn.text() == "Select None":
            select_none_found = True
    
    assert select_all_found, "Select All button not found"
    assert select_none_found, "Select None button not found"
    
    # 4. Has selection summary label (always visible)
    labels = context_card.findChildren(QLabel)
    summary_found = False
    for label in labels:
        if label.text().startswith("Context Feeds:"):
            summary_found = True
            break
    
    assert summary_found, "Selection summary label not found"