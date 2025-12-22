
"""Test research_console filters.

Phase 10: Test apply_filters() deterministic behavior.
"""

import pytest
from FishBroWFS_V2.gui.research_console import apply_filters, _norm_optional_text, _norm_optional_choice


def test_norm_optional_text():
    """Test _norm_optional_text helper."""
    # None -> None
    assert _norm_optional_text(None) is None
    
    # Empty string -> None
    assert _norm_optional_text("") is None
    assert _norm_optional_text(" ") is None
    assert _norm_optional_text("\n\t") is None
    
    # Non-string -> string
    assert _norm_optional_text(123) == "123"
    assert _norm_optional_text(True) == "True"
    
    # String with whitespace -> trimmed
    assert _norm_optional_text("  hello  ") == "hello"
    assert _norm_optional_text("hello\n") == "hello"
    assert _norm_optional_text("\thello\t") == "hello"


def test_norm_optional_choice():
    """Test _norm_optional_choice helper."""
    # None -> None
    assert _norm_optional_choice(None) is None
    assert _norm_optional_choice(None, all_tokens=("ALL", "UNDECIDED")) is None
    
    # Empty/whitespace -> None
    assert _norm_optional_choice("") is None
    assert _norm_optional_choice(" ") is None
    assert _norm_optional_choice("\n\t") is None
    
    # ALL tokens -> None (case-insensitive)
    assert _norm_optional_choice("ALL") is None
    assert _norm_optional_choice("all") is None
    assert _norm_optional_choice(" All ") is None
    assert _norm_optional_choice("UNDECIDED", all_tokens=("ALL", "UNDECIDED")) is None
    assert _norm_optional_choice("undecided", all_tokens=("ALL", "UNDECIDED")) is None
    
    # Other values -> trimmed original
    assert _norm_optional_choice("AAPL") == "AAPL"
    assert _norm_optional_choice("  AAPL  ") == "AAPL"
    assert _norm_optional_choice("keep") == "keep"  # NOT uppercased
    assert _norm_optional_choice("KEEP") == "KEEP"


def test_apply_filters_empty_rows():
    """Test with empty rows."""
    rows = []
    result = apply_filters(rows, text=None, symbol=None, strategy_id=None, decision=None)
    assert result == []


def test_apply_filters_no_filters():
    """Test with no filters applied."""
    rows = [
        {"run_id": "run1", "symbol": "AAPL", "strategy_id": "strategy1", "decision": "KEEP"},
        {"run_id": "run2", "symbol": "GOOG", "strategy_id": "strategy2", "decision": "DROP"},
    ]
    result = apply_filters(rows, text=None, symbol=None, strategy_id=None, decision=None)
    assert result == rows


def test_apply_filters_text_normalize():
    """Test text filter normalization."""
    rows = [
        {"run_id": "run1", "symbol": "AAPL", "strategy_id": "strategy1", "decision": "KEEP"},
        {"run_id": "run2", "symbol": "GOOG", "strategy_id": "strategy2", "decision": "DROP"},
    ]
    
    # Empty string should not filter
    result = apply_filters(rows, text="", symbol=None, strategy_id=None, decision=None)
    assert len(result) == 2
    
    # Whitespace-only should not filter
    result = apply_filters(rows, text=" ", symbol=None, strategy_id=None, decision=None)
    assert len(result) == 2
    
    result = apply_filters(rows, text="\n\t", symbol=None, strategy_id=None, decision=None)
    assert len(result) == 2
    
    # Actual text should filter
    result = apply_filters(rows, text="run1", symbol=None, strategy_id=None, decision=None)
    assert len(result) == 1
    assert result[0]["run_id"] == "run1"


def test_apply_filters_choice_normalize():
    """Test choice filter normalization."""
    rows = [
        {"run_id": "run1", "symbol": "AAPL", "strategy_id": "strategy1", "decision": "KEEP"},
        {"run_id": "run2", "symbol": "GOOG", "strategy_id": "strategy2", "decision": "DROP"},
    ]
    
    # ALL should not filter (case-insensitive)
    result = apply_filters(rows, text=None, symbol="ALL", strategy_id=None, decision=None)
    assert len(result) == 2
    
    result = apply_filters(rows, text=None, symbol="all", strategy_id=None, decision=None)
    assert len(result) == 2
    
    result = apply_filters(rows, text=None, symbol=" All ", strategy_id=None, decision=None)
    assert len(result) == 2
    
    # Same for strategy_id
    result = apply_filters(rows, text=None, symbol=None, strategy_id="ALL", decision=None)
    assert len(result) == 2
    
    # Same for decision
    result = apply_filters(rows, text=None, symbol=None, strategy_id=None, decision="ALL")
    assert len(result) == 2


def test_apply_filters_undecided_semantics():
    """Test UNDECIDED decision filter semantics."""
    rows = [
        {"run_id": "run1", "symbol": "AAPL", "strategy_id": "s1", "decision": None},
        {"run_id": "run2", "symbol": "GOOG", "strategy_id": "s2", "decision": ""},
        {"run_id": "run3", "symbol": "MSFT", "strategy_id": "s3", "decision": " "},
        {"run_id": "run4", "symbol": "TSLA", "strategy_id": "s4", "decision": "KEEP"},
        {"run_id": "run5", "symbol": "NVDA", "strategy_id": "s5", "decision": "DROP"},
    ]
    
    # UNDECIDED should match None, empty string, and whitespace-only
    result = apply_filters(rows, text=None, symbol=None, strategy_id=None, decision="UNDECIDED")
    assert len(result) == 3
    run_ids = {r["run_id"] for r in result}
    assert run_ids == {"run1", "run2", "run3"}
    
    # Case-insensitive
    result = apply_filters(rows, text=None, symbol=None, strategy_id=None, decision="undecided")
    assert len(result) == 3
    
    result = apply_filters(rows, text=None, symbol=None, strategy_id=None, decision=" Undecided ")
    assert len(result) == 3


def test_apply_filters_case_insensitive():
    """Test case-insensitive filtering."""
    rows = [
        {"run_id": "RUN1", "symbol": "AAPL", "strategy_id": "STRATEGY1", "decision": "KEEP"},
        {"run_id": "run2", "symbol": "goog", "strategy_id": "strategy2", "decision": "drop"},
    ]
    
    # Symbol filter case-insensitive
    result = apply_filters(rows, text=None, symbol="aapl", strategy_id=None, decision=None)
    assert len(result) == 1
    assert result[0]["symbol"] == "AAPL"
    
    result = apply_filters(rows, text=None, symbol="AAPL", strategy_id=None, decision=None)
    assert len(result) == 1
    assert result[0]["symbol"] == "AAPL"
    
    # Strategy filter case-insensitive
    result = apply_filters(rows, text=None, symbol=None, strategy_id="strategy1", decision=None)
    assert len(result) == 1
    assert result[0]["strategy_id"] == "STRATEGY1"
    
    # Decision filter case-insensitive
    result = apply_filters(rows, text=None, symbol=None, strategy_id=None, decision="keep")
    assert len(result) == 1
    assert result[0]["decision"] == "KEEP"
    
    result = apply_filters(rows, text=None, symbol=None, strategy_id=None, decision="KEEP")
    assert len(result) == 1
    assert result[0]["decision"] == "KEEP"


def test_apply_filters_text_search():
    """Test text filter."""
    rows = [
        {"run_id": "run_aapl_001", "symbol": "AAPL", "strategy_id": "strategy1", "decision": "KEEP"},
        {"run_id": "run_goog_002", "symbol": "GOOG", "strategy_id": "strategy2", "decision": "DROP"},
        {"run_id": "run_aapl_003", "symbol": "AAPL", "strategy_id": "strategy3", "decision": "ARCHIVE"},
    ]
    
    # Search in run_id
    result = apply_filters(rows, text="aapl", symbol=None, strategy_id=None, decision=None)
    assert len(result) == 2
    assert all("aapl" in row["run_id"].lower() for row in result)
    
    # Search in symbol
    result = apply_filters(rows, text="goog", symbol=None, strategy_id=None, decision=None)
    assert len(result) == 1
    assert result[0]["symbol"] == "GOOG"
    
    # Search in strategy_id
    result = apply_filters(rows, text="strategy2", symbol=None, strategy_id=None, decision=None)
    assert len(result) == 1
    assert result[0]["strategy_id"] == "strategy2"
    
    # Search in note field
    rows_with_notes = [
        {"run_id": "run1", "symbol": "AAPL", "strategy_id": "s1", "decision": "KEEP", "note": "good results"},
        {"run_id": "run2", "symbol": "GOOG", "strategy_id": "s2", "decision": "DROP", "note": "bad performance"},
    ]
    result = apply_filters(rows_with_notes, text="good", symbol=None, strategy_id=None, decision=None)
    assert len(result) == 1
    assert result[0]["run_id"] == "run1"


def test_apply_filters_symbol_filter():
    """Test symbol filter."""
    rows = [
        {"run_id": "run1", "symbol": "AAPL", "strategy_id": "strategy1", "decision": "KEEP"},
        {"run_id": "run2", "symbol": "GOOG", "strategy_id": "strategy2", "decision": "DROP"},
        {"run_id": "run3", "symbol": "AAPL", "strategy_id": "strategy3", "decision": "ARCHIVE"},
    ]
    
    result = apply_filters(rows, text=None, symbol="AAPL", strategy_id=None, decision=None)
    assert len(result) == 2
    assert all(row["symbol"] == "AAPL" for row in result)


def test_apply_filters_strategy_filter():
    """Test strategy filter."""
    rows = [
        {"run_id": "run1", "symbol": "AAPL", "strategy_id": "strategy1", "decision": "KEEP"},
        {"run_id": "run2", "symbol": "GOOG", "strategy_id": "strategy2", "decision": "DROP"},
        {"run_id": "run3", "symbol": "AAPL", "strategy_id": "strategy1", "decision": "ARCHIVE"},
    ]
    
    result = apply_filters(rows, text=None, symbol=None, strategy_id="strategy1", decision=None)
    assert len(result) == 2
    assert all(row["strategy_id"] == "strategy1" for row in result)


def test_apply_filters_decision_filter():
    """Test decision filter."""
    rows = [
        {"run_id": "run1", "symbol": "AAPL", "strategy_id": "strategy1", "decision": "KEEP"},
        {"run_id": "run2", "symbol": "GOOG", "strategy_id": "strategy2", "decision": "DROP"},
        {"run_id": "run3", "symbol": "AAPL", "strategy_id": "strategy1", "decision": "KEEP"},
        {"run_id": "run4", "symbol": "MSFT", "strategy_id": "strategy3", "decision": "ARCHIVE"},
    ]
    
    result = apply_filters(rows, text=None, symbol=None, strategy_id=None, decision="KEEP")
    assert len(result) == 2
    assert all(row["decision"] == "KEEP" for row in result)
    
    result = apply_filters(rows, text=None, symbol=None, strategy_id=None, decision="DROP")
    assert len(result) == 1
    assert result[0]["decision"] == "DROP"
    
    result = apply_filters(rows, text=None, symbol=None, strategy_id=None, decision="ARCHIVE")
    assert len(result) == 1
    assert result[0]["decision"] == "ARCHIVE"


def test_apply_filters_combined_filters():
    """Test multiple filters combined."""
    rows = [
        {"run_id": "run_aapl_001", "symbol": "AAPL", "strategy_id": "strategy1", "decision": "KEEP"},
        {"run_id": "run_aapl_002", "symbol": "AAPL", "strategy_id": "strategy2", "decision": "DROP"},
        {"run_id": "run_goog_001", "symbol": "GOOG", "strategy_id": "strategy1", "decision": "KEEP"},
        {"run_id": "run_goog_002", "symbol": "GOOG", "strategy_id": "strategy2", "decision": "ARCHIVE"},
    ]
    
    # Symbol + Decision filter
    result = apply_filters(
        rows, 
        text=None, 
        symbol="AAPL", 
        strategy_id=None, 
        decision="KEEP"
    )
    assert len(result) == 1
    assert result[0]["symbol"] == "AAPL"
    assert result[0]["decision"] == "KEEP"
    
    # Text + Strategy filter
    result = apply_filters(
        rows,
        text="goog",
        symbol=None,
        strategy_id="strategy1",
        decision=None
    )
    assert len(result) == 1
    assert "goog" in result[0]["run_id"].lower()
    assert result[0]["strategy_id"] == "strategy1"
    
    # All three filters combined
    result = apply_filters(
        rows,
        text="aapl",
        symbol="AAPL",
        strategy_id="strategy1",
        decision="KEEP"
    )
    assert len(result) == 1
    assert result[0]["run_id"] == "run_aapl_001"


def test_apply_filters_missing_fields():
    """Test with rows missing some fields."""
    rows = [
        {"run_id": "run1", "symbol": "AAPL", "strategy_id": "strategy1", "decision": "KEEP"},
        {"run_id": "run2", "symbol": None, "strategy_id": "strategy2", "decision": "DROP"},
        {"run_id": "run3", "symbol": "AAPL", "strategy_id": None, "decision": "ARCHIVE"},
        {"run_id": "run4", "symbol": "GOOG", "strategy_id": "strategy1", "decision": None},
    ]
    
    # Filter by symbol (should exclude rows with None symbol)
    result = apply_filters(rows, text=None, symbol="AAPL", strategy_id=None, decision=None)
    assert len(result) == 2
    assert all(row["symbol"] == "AAPL" for row in result)
    
    # Filter by strategy (should exclude rows with None strategy_id)
    result = apply_filters(rows, text=None, symbol=None, strategy_id="strategy1", decision=None)
    assert len(result) == 2
    assert all(row["strategy_id"] == "strategy1" for row in result)
    
    # Filter by decision (should exclude rows with None decision)
    result = apply_filters(rows, text=None, symbol=None, strategy_id=None, decision="KEEP")
    assert len(result) == 1
    assert result[0]["decision"] == "KEEP"


def test_apply_filters_deterministic():
    """Test that filters are deterministic (same input = same output)."""
    rows = [
        {"run_id": "run1", "symbol": "AAPL", "strategy_id": "strategy1", "decision": "KEEP"},
        {"run_id": "run2", "symbol": "GOOG", "strategy_id": "strategy2", "decision": "DROP"},
        {"run_id": "run3", "symbol": "AAPL", "strategy_id": "strategy1", "decision": "ARCHIVE"},
    ]
    
    # Run filter multiple times
    result1 = apply_filters(rows, text="aapl", symbol=None, strategy_id=None, decision="KEEP")
    result2 = apply_filters(rows, text="aapl", symbol=None, strategy_id=None, decision="KEEP")
    result3 = apply_filters(rows, text="aapl", symbol=None, strategy_id=None, decision="KEEP")
    
    assert result1 == result2 == result3
    assert len(result1) == 1
    assert result1[0]["run_id"] == "run1"


