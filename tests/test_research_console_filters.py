"""Test research_console filters.

Phase 10: Test apply_filters() deterministic behavior.
"""

import pytest
from FishBroWFS_V2.gui.research_console import apply_filters


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


def test_apply_filters_case_insensitive_text():
    """Test case-insensitive text search."""
    rows = [
        {"run_id": "RUN_AAPL_001", "symbol": "AAPL", "strategy_id": "STRATEGY1", "decision": "KEEP"},
        {"run_id": "run_goog_002", "symbol": "GOOG", "strategy_id": "strategy2", "decision": "DROP"},
    ]
    
    result = apply_filters(rows, text="aapl", symbol=None, strategy_id=None, decision=None)
    assert len(result) == 1
    assert "aapl" in result[0]["run_id"].lower()
    
    result = apply_filters(rows, text="STRATEGY1", symbol=None, strategy_id=None, decision=None)
    assert len(result) == 1
    assert "strategy1" in result[0]["strategy_id"].lower()


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