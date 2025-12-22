
"""Test strategy registry.

Phase 7: Test registry list/get/register behavior is deterministic.
"""

from __future__ import annotations

import pytest

from FishBroWFS_V2.strategy.registry import (
    register,
    get,
    list_strategies,
    unregister,
    clear,
    load_builtin_strategies,
)
from FishBroWFS_V2.strategy.spec import StrategySpec


def test_register_and_get() -> None:
    """Test register and get operations."""
    clear()
    
    # Create a test strategy
    def test_fn(context: dict, params: dict) -> dict:
        return {"intents": [], "debug": {}}
    
    spec = StrategySpec(
        strategy_id="test_strategy",
        version="v1",
        param_schema={"type": "object", "properties": {}},
        defaults={},
        fn=test_fn,
    )
    
    # Register
    register(spec)
    
    # Get
    retrieved = get("test_strategy")
    assert retrieved.strategy_id == "test_strategy"
    assert retrieved.version == "v1"
    
    # Cleanup
    unregister("test_strategy")


def test_register_duplicate_raises() -> None:
    """Test registering duplicate strategy_id raises ValueError."""
    clear()
    
    def test_fn(context: dict, params: dict) -> dict:
        return {"intents": [], "debug": {}}
    
    spec1 = StrategySpec(
        strategy_id="duplicate",
        version="v1",
        param_schema={},
        defaults={},
        fn=test_fn,
    )
    
    spec2 = StrategySpec(
        strategy_id="duplicate",
        version="v2",
        param_schema={},
        defaults={},
        fn=test_fn,
    )
    
    register(spec1)
    
    with pytest.raises(ValueError, match="already registered"):
        register(spec2)
    
    # Cleanup
    unregister("duplicate")


def test_get_nonexistent_raises() -> None:
    """Test getting nonexistent strategy raises KeyError."""
    clear()
    
    with pytest.raises(KeyError, match="not found"):
        get("nonexistent")


def test_list_strategies() -> None:
    """Test list_strategies returns sorted list."""
    clear()
    
    def test_fn(context: dict, params: dict) -> dict:
        return {"intents": [], "debug": {}}
    
    # Register multiple strategies
    spec_b = StrategySpec(
        strategy_id="b_strategy",
        version="v1",
        param_schema={},
        defaults={},
        fn=test_fn,
    )
    
    spec_a = StrategySpec(
        strategy_id="a_strategy",
        version="v1",
        param_schema={},
        defaults={},
        fn=test_fn,
    )
    
    spec_c = StrategySpec(
        strategy_id="c_strategy",
        version="v1",
        param_schema={},
        defaults={},
        fn=test_fn,
    )
    
    register(spec_b)
    register(spec_a)
    register(spec_c)
    
    # List should be sorted by strategy_id
    strategies = list_strategies()
    assert len(strategies) == 3
    assert strategies[0].strategy_id == "a_strategy"
    assert strategies[1].strategy_id == "b_strategy"
    assert strategies[2].strategy_id == "c_strategy"
    
    # Cleanup
    clear()


def test_load_builtin_strategies() -> None:
    """Test load_builtin_strategies registers built-in strategies."""
    clear()
    
    load_builtin_strategies()
    
    strategies = list_strategies()
    strategy_ids = [s.strategy_id for s in strategies]
    
    assert "sma_cross" in strategy_ids
    assert "breakout_channel" in strategy_ids
    assert "mean_revert_zscore" in strategy_ids
    
    # Verify they can be retrieved
    sma_spec = get("sma_cross")
    assert sma_spec.version == "v1"
    
    breakout_spec = get("breakout_channel")
    assert breakout_spec.version == "v1"
    
    zscore_spec = get("mean_revert_zscore")
    assert zscore_spec.version == "v1"
    
    # Cleanup
    clear()


