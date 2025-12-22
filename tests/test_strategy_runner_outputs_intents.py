
"""Test strategy runner outputs valid intents.

Phase 7: Test that runner returns valid OrderIntent schema.
"""

from __future__ import annotations

import numpy as np
import pytest

from FishBroWFS_V2.strategy.runner import run_strategy
from FishBroWFS_V2.strategy.registry import load_builtin_strategies, clear
from FishBroWFS_V2.engine.types import OrderIntent, OrderRole, OrderKind, Side


@pytest.fixture(autouse=True)
def setup_registry() -> None:
    """Setup registry before each test."""
    clear()
    load_builtin_strategies()
    yield
    clear()


def test_runner_outputs_intents_schema() -> None:
    """Test runner outputs valid OrderIntent schema."""
    # Create test features
    sma_fast = np.array([10.0, 11.0, 12.0, 13.0, 14.0])
    sma_slow = np.array([15.0, 14.0, 13.0, 12.0, 11.0])
    
    features = {
        "sma_fast": sma_fast,
        "sma_slow": sma_slow,
    }
    
    params = {
        "fast_period": 10.0,
        "slow_period": 20.0,
    }
    
    context = {
        "bar_index": 3,
        "order_qty": 1,
    }
    
    # Run strategy
    intents = run_strategy("sma_cross", features, params, context)
    
    # Verify intents is a list
    assert isinstance(intents, list)
    
    # Verify each intent is OrderIntent
    for intent in intents:
        assert isinstance(intent, OrderIntent)
        
        # Verify required fields
        assert isinstance(intent.order_id, int)
        assert isinstance(intent.created_bar, int)
        assert isinstance(intent.role, OrderRole)
        assert isinstance(intent.kind, OrderKind)
        assert isinstance(intent.side, Side)
        assert isinstance(intent.price, float)
        assert isinstance(intent.qty, int)
        
        # Verify values are reasonable
        assert intent.order_id > 0
        assert intent.created_bar >= 0
        assert intent.price > 0
        assert intent.qty > 0


def test_runner_uses_defaults() -> None:
    """Test runner uses default parameters when missing."""
    features = {
        "sma_fast": np.array([10.0, 11.0]),
        "sma_slow": np.array([15.0, 14.0]),
    }
    
    # Missing params - should use defaults
    params = {}
    
    context = {
        "bar_index": 1,
        "order_qty": 1,
    }
    
    # Should not raise - defaults should be used
    intents = run_strategy("sma_cross", features, params, context)
    assert isinstance(intents, list)


def test_runner_allows_extra_params() -> None:
    """Test runner allows extra parameters (logs warning but doesn't fail)."""
    features = {
        "sma_fast": np.array([10.0, 11.0]),
        "sma_slow": np.array([15.0, 14.0]),
    }
    
    # Extra param not in schema
    params = {
        "fast_period": 10.0,
        "slow_period": 20.0,
        "extra_param": 999.0,  # Not in schema
    }
    
    context = {
        "bar_index": 1,
        "order_qty": 1,
    }
    
    # Should not raise - extra params allowed
    intents = run_strategy("sma_cross", features, params, context)
    assert isinstance(intents, list)


def test_runner_invalid_output_raises() -> None:
    """Test runner raises ValueError for invalid strategy output."""
    from FishBroWFS_V2.strategy.registry import register
    from FishBroWFS_V2.strategy.spec import StrategySpec
    
    # Create a bad strategy that returns invalid output
    def bad_strategy(context: dict, params: dict) -> dict:
        return {"invalid": "output"}  # Missing "intents" key
    
    bad_spec = StrategySpec(
        strategy_id="bad_strategy",
        version="v1",
        param_schema={},
        defaults={},
        fn=bad_strategy,
    )
    
    register(bad_spec)
    
    with pytest.raises(ValueError, match="must contain 'intents' key"):
        run_strategy("bad_strategy", {}, {}, {"bar_index": 0})
    
    # Cleanup
    from FishBroWFS_V2.strategy.registry import unregister
    unregister("bad_strategy")


