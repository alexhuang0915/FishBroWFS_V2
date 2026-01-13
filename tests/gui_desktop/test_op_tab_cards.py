"""
Test that OP tab renders exactly 4 cards as specified in Phase 17B.
"""
import pytest
pytest.skip("UI feature not yet implemented", allow_module_level=True)

from PySide6.QtWidgets import QApplication, QGroupBox
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


def test_op_tab_has_four_cards(op_tab):
    """Verify OP tab renders exactly 4 cards."""
    # Find all QGroupBox widgets
    all_groups = op_tab.findChildren(QGroupBox)
    
    # Filter for the 4 main cards (exclude "Execution Log" and any other groups)
    card_titles = []
    cards = []
    for group in all_groups:
        title = group.title()
        if title in ["What to Run", "Context Feeds (Optional)", "Prepare Data", "Run & Publish"]:
            cards.append(group)
            card_titles.append(title)
    
    # Should have exactly 4 cards
    assert len(cards) == 4, f"Expected 4 cards, found {len(cards)}. All groups: {[g.title() for g in all_groups]}"
    
    # Verify card titles match Phase 17B spec
    expected_titles = [
        "What to Run",
        "Context Feeds (Optional)",
        "Prepare Data",
        "Run & Publish"
    ]
    
    assert sorted(card_titles) == sorted(expected_titles), \
        f"Card titles don't match spec. Found: {card_titles}, Expected: {expected_titles}"
    
    # Verify each card has the correct styling (border colors)
    for card in cards:
        style = card.styleSheet()
        title = card.title()
        # Check for border color indicators
        if title == "What to Run":
            assert "border: 2px solid #1a237e" in style, "Card 1 should have blue border"
        elif title == "Context Feeds (Optional)":
            assert "border: 2px solid #7b1fa2" in style, "Card 2 should have purple border"
        elif title == "Prepare Data":
            assert "border: 2px solid #0288d1" in style, "Card 3 should have light blue border"
        elif title == "Run & Publish":
            assert "border: 2px solid #2e7d32" in style, "Card 4 should have green border"


def test_card1_what_to_run_has_correct_elements(op_tab):
    """Verify Card 1: What to Run has all required UI elements."""
    cards = op_tab.findChildren(QGroupBox)
    card1 = None
    for card in cards:
        if card.title() == "What to Run":
            card1 = card
            break
    
    assert card1 is not None, "Card 1 'What to Run' not found"
    
    # Check for required elements
    assert hasattr(op_tab, 'strategy_cb'), "Missing strategy dropdown"
    assert hasattr(op_tab, 'primary_market_cb'), "Missing primary market dropdown"
    assert hasattr(op_tab, 'tf_cb'), "Missing timeframe dropdown"
    assert hasattr(op_tab, 'season_label'), "Missing season label"
    assert hasattr(op_tab, 'date_range_label'), "Missing date range label"
    
    # Verify dropdown contents
    assert op_tab.strategy_cb.count() == 3, "Strategy dropdown should have 3 items (S1, S2, S3)"
    assert op_tab.tf_cb.count() == 5, "Timeframe dropdown should have 5 items"
    
    # Verify labels
    assert op_tab.season_label.text() == "2026Q1", "Season should be 2026Q1"
    assert op_tab.date_range_label.text() == "Auto (full history)", "Date range should be 'Auto (full history)'"


def test_card2_context_feeds_has_multi_select(op_tab):
    """Verify Card 2: Context Feeds supports multi-select."""
    cards = op_tab.findChildren(QGroupBox)
    card2 = None
    for card in cards:
        if card.title() == "Context Feeds (Optional)":
            card2 = card
            break
    
    assert card2 is not None, "Card 2 'Context Feeds (Optional)' not found"
    
    # Check for required elements
    assert hasattr(op_tab, 'context_feeds_layout'), "Missing context feeds layout"
    assert hasattr(op_tab, 'selected_context_feeds'), "Missing selected_context_feeds set"
    
    # Verify it's a set for multi-select storage
    assert isinstance(op_tab.selected_context_feeds, set), "selected_context_feeds should be a set for multi-select"


def test_card3_prepare_data_has_cache_status(op_tab):
    """Verify Card 3: Prepare Data has cache status monitoring."""
    cards = op_tab.findChildren(QGroupBox)
    card3 = None
    for card in cards:
        if card.title() == "Prepare Data":
            card3 = card
            break
    
    assert card3 is not None, "Card 3 'Prepare Data' not found"
    
    # Check for required elements
    assert hasattr(op_tab, 'bars_status_label'), "Missing bars status label"
    assert hasattr(op_tab, 'features_status_label'), "Missing features status label"
    assert hasattr(op_tab, 'prepare_bars_btn'), "Missing prepare bars button"
    assert hasattr(op_tab, 'prepare_features_btn'), "Missing prepare features button"
    assert hasattr(op_tab, 'prepare_all_btn'), "Missing prepare all button"
    
    # Verify initial states
    assert op_tab.bars_cache_status in ["UNKNOWN", "READY", "MISSING"], "Invalid bars cache status"
    assert op_tab.features_cache_status in ["UNKNOWN", "READY", "MISSING"], "Invalid features cache status"


def test_card4_run_publish_has_state_gated_buttons(op_tab):
    """Verify Card 4: Run & Publish has state-gated buttons."""
    cards = op_tab.findChildren(QGroupBox)
    card4 = None
    for card in cards:
        if card.title() == "Run & Publish":
            card4 = card
            break
    
    assert card4 is not None, "Card 4 'Run & Publish' not found"
    
    # Check for required elements
    assert hasattr(op_tab, 'run_research_btn'), "Missing run research button"
    assert hasattr(op_tab, 'publish_btn'), "Missing publish button"
    assert hasattr(op_tab, 'summary_panel'), "Missing summary panel"
    assert hasattr(op_tab, 'artifact_status_label'), "Missing artifact status label"
    
    # Verify initial states
    assert op_tab.run_research_btn.text() == "Run Research", "Run button should say 'Run Research'"
    assert op_tab.publish_btn.text() == "Publish to Registry", "Publish button should say 'Publish to Registry'"
    assert op_tab.publish_btn.toolTip() == "Publishing makes this run a governed strategy version available for allocation.", \
        "Publish button should have correct tooltip"
    
    # Verify summary panel is initially hidden
    assert not op_tab.summary_panel.isVisible(), "Summary panel should be initially hidden"


def test_no_dataset_data1_data2_fields(op_tab):
    """Verify Dataset/Data1/Data2 fields are eliminated."""
    # Check that old terminology is not present in UI
    from PySide6.QtWidgets import QLabel, QComboBox
    
    # Get all text from labels and comboboxes
    all_text = ""
    
    # Check card titles
    cards = op_tab.findChildren(QGroupBox)
    for card in cards:
        all_text += card.title() + " "
    
    # Check all labels
    labels = op_tab.findChildren(QLabel)
    for label in labels:
        all_text += label.text() + " "
    
    # Check combobox items
    comboboxes = op_tab.findChildren(QComboBox)
    for cb in comboboxes:
        for i in range(cb.count()):
            all_text += cb.itemText(i) + " "
    
    # Old terminology should NOT appear
    forbidden_terms = ["Dataset", "Data1", "Data2", "dataset_id", "data1", "data2"]
    for term in forbidden_terms:
        assert term not in all_text, f"Forbidden term '{term}' found in UI: {all_text}"
    
    # New terminology SHOULD appear (check in a more targeted way)
    # Check for "Primary Market" label
    primary_market_found = False
    for label in labels:
        if "Primary Market" in label.text():
            primary_market_found = True
            break
    
    assert primary_market_found, "Label with 'Primary Market' not found in UI"
    
    # Check for "Context Feeds" in card title
    context_feeds_found = False
    for card in cards:
        if "Context Feeds" in card.title():
            context_feeds_found = True
            break
    
    assert context_feeds_found, "Card with 'Context Feeds' not found in UI"