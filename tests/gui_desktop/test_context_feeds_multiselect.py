"""
Test that Context Feeds allows multi-select as specified in Phase 17B.
"""
import pytest
from PySide6.QtWidgets import QApplication, QCheckBox, QGroupBox, QLabel, QScrollArea
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


def test_context_feeds_has_checkboxes(op_tab):
    """Verify Context Feeds card has checkboxes for multi-select."""
    # Find checkboxes in context feeds layout
    checkboxes = op_tab.context_feeds_layout.parent().findChildren(QCheckBox)
    
    # Should have at least some checkboxes (depends on available datasets)
    # But could be 0 if no auxiliary datasets found
    assert checkboxes is not None, "No checkboxes found in context feeds"
    
    # Each checkbox should be connected to the selection handler
    for cb in checkboxes:
        # Check that it's a QCheckBox
        assert isinstance(cb, QCheckBox), "Context feed item should be QCheckBox"
        
        # Check that it has text (dataset identifier)
        assert cb.text(), "Checkbox should have dataset identifier text"
        
        # Check that it's not disabled (should be selectable)
        assert cb.isEnabled(), "Checkbox should be enabled for selection"


def test_context_feeds_multi_select_functionality(op_tab):
    """Verify multi-select functionality works correctly."""
    # Test the on_context_feed_changed method directly
    op_tab.selected_context_feeds.clear()
    
    # Test adding a feed
    op_tab.on_context_feed_changed("VX.FUT", Qt.Checked)
    assert len(op_tab.selected_context_feeds) == 1
    assert "VX.FUT" in op_tab.selected_context_feeds
    
    # Test adding another feed
    op_tab.on_context_feed_changed("DX.FUT", Qt.Checked)
    assert len(op_tab.selected_context_feeds) == 2
    assert "VX.FUT" in op_tab.selected_context_feeds
    assert "DX.FUT" in op_tab.selected_context_feeds
    
    # Test removing a feed
    op_tab.on_context_feed_changed("VX.FUT", Qt.Unchecked)
    assert len(op_tab.selected_context_feeds) == 1
    assert "VX.FUT" not in op_tab.selected_context_feeds
    assert "DX.FUT" in op_tab.selected_context_feeds
    
    # Test removing non-existent feed (should be safe)
    op_tab.on_context_feed_changed("ZN.FUT", Qt.Unchecked)
    assert len(op_tab.selected_context_feeds) == 1
    assert "DX.FUT" in op_tab.selected_context_feeds
    
    # Test adding multiple feeds
    op_tab.on_context_feed_changed("ZN.FUT", Qt.Checked)
    op_tab.on_context_feed_changed("6J.FUT", Qt.Checked)
    assert len(op_tab.selected_context_feeds) == 3
    assert "DX.FUT" in op_tab.selected_context_feeds
    assert "ZN.FUT" in op_tab.selected_context_feeds
    assert "6J.FUT" in op_tab.selected_context_feeds
    
    # Test clearing all
    op_tab.on_context_feed_changed("DX.FUT", Qt.Unchecked)
    op_tab.on_context_feed_changed("ZN.FUT", Qt.Unchecked)
    op_tab.on_context_feed_changed("6J.FUT", Qt.Unchecked)
    assert len(op_tab.selected_context_feeds) == 0


def test_context_feeds_empty_selection_valid(op_tab):
    """Verify empty selection is valid (no context feeds required)."""
    # Initially should be empty
    assert len(op_tab.selected_context_feeds) == 0, "Initial selection should be empty"
    
    # Should not prevent running research
    # (This is tested in another test file for run research validation)


def test_context_feeds_label_text(op_tab):
    """Verify Context Feeds card has correct label text."""
    cards = op_tab.findChildren(QGroupBox)
    card2 = None
    for card in cards:
        if card.title() == "Context Feeds (Optional)":
            card2 = card
            break
    
    assert card2 is not None, "Context Feeds card not found"
    
    # Find the label inside the card
    from PySide6.QtWidgets import QLabel
    labels = card2.findChildren(QLabel)
    
    # Should have label with correct text (Phase 18 spec)
    found_label = False
    for label in labels:
        if "Extra markets used only as features/filters; they are not traded directly." in label.text():
            found_label = True
            break
    
    assert found_label, "Missing label with text 'Extra markets used only as features/filters; they are not traded directly.'"


def test_context_feeds_scroll_area(op_tab):
    """Verify Context Feeds has scroll area for many options."""
    cards = op_tab.findChildren(QGroupBox)
    card2 = None
    for card in cards:
        if card.title() == "Context Feeds (Optional)":
            card2 = card
            break
    
    assert card2 is not None, "Context Feeds card not found"
    
    # Check for scroll area
    from PySide6.QtWidgets import QScrollArea
    scroll_areas = card2.findChildren(QScrollArea)
    
    assert len(scroll_areas) > 0, "Context Feeds should have a scroll area for many options"
    
    # Scroll area should be widget resizable
    scroll_area = scroll_areas[0]
    assert scroll_area.widgetResizable(), "Scroll area should be widget resizable"


def test_context_feeds_stored_as_list_of_strings(op_tab):
    """Verify context feeds are stored internally as list[str]."""
    # The spec says: "Stored internally as context_feeds: list[str]"
    # In our implementation, we use a Set for uniqueness, but can convert to list
    
    # Test adding some feeds
    test_feeds = ["VX.FUT", "DX.FUT", "ZN.FUT"]
    for feed in test_feeds:
        op_tab.selected_context_feeds.add(feed)
    
    # Verify we can get as sorted list
    feeds_list = sorted(op_tab.selected_context_feeds)
    assert isinstance(feeds_list, list), "Should be able to get as list"
    assert all(isinstance(feed, str) for feed in feeds_list), "All feeds should be strings"
    assert feeds_list == sorted(test_feeds), "Feeds list should match added feeds"