
"""Test strategy contract purity.

Phase 7: Test that same input produces same output (deterministic).
"""

from __future__ import annotations

import numpy as np
import pytest

from FishBroWFS_V2.strategy.registry import get, load_builtin_strategies, clear
from FishBroWFS_V2.engine.types import OrderIntent


@pytest.fixture(autouse=True)
def setup_registry() -> None:
    """Setup registry before each test."""
    clear()
    load_builtin_strategies()
    yield
    clear()


def test_sma_cross_purity() -> None:
    """Test SMA cross strategy is deterministic."""
    spec = get("sma_cross")
    
    # Create test features
    sma_fast = np.array([10.0, 11.0, 12.0, 13.0, 14.0])
    sma_slow = np.array([15.0, 14.0, 13.0, 12.0, 11.0])  # Cross at index 3
    
    context = {
        "bar_index": 3,
        "order_qty": 1,
        "features": {
            "sma_fast": sma_fast,
            "sma_slow": sma_slow,
        },
    }
    
    params = {
        "fast_period": 10.0,
        "slow_period": 20.0,
    }
    
    # Run multiple times
    result1 = spec.fn(context, params)
    result2 = spec.fn(context, params)
    result3 = spec.fn(context, params)
    
    # All results should be identical
    assert result1 == result2 == result3
    
    # Check intents are identical
    intents1 = result1["intents"]
    intents2 = result2["intents"]
    intents3 = result3["intents"]
    
    assert len(intents1) == len(intents2) == len(intents3)
    
    if len(intents1) > 0:
        # Compare intent attributes
        for i, (i1, i2, i3) in enumerate(zip(intents1, intents2, intents3)):
            assert i1.order_id == i2.order_id == i3.order_id
            assert i1.created_bar == i2.created_bar == i3.created_bar
            assert i1.role == i2.role == i3.role
            assert i1.kind == i2.kind == i3.kind
            assert i1.side == i2.side == i3.side
            assert i1.price == i2.price == i3.price
            assert i1.qty == i2.qty == i3.qty


def test_breakout_channel_purity() -> None:
    """Test breakout channel strategy is deterministic."""
    spec = get("breakout_channel")
    
    # Create test features
    high = np.array([100.0, 101.0, 102.0, 103.0, 105.0])
    close = np.array([99.0, 100.0, 101.0, 102.0, 104.0])
    channel_high = np.array([102.0, 102.0, 102.0, 102.0, 102.0])
    
    context = {
        "bar_index": 4,
        "order_qty": 1,
        "features": {
            "high": high,
            "close": close,
            "channel_high": channel_high,
        },
    }
    
    params = {
        "channel_period": 20.0,
    }
    
    # Run multiple times
    result1 = spec.fn(context, params)
    result2 = spec.fn(context, params)
    
    # Results should be identical
    assert result1 == result2


def test_mean_revert_zscore_purity() -> None:
    """Test mean reversion z-score strategy is deterministic."""
    spec = get("mean_revert_zscore")
    
    # Create test features
    zscore = np.array([-1.0, -1.5, -2.0, -2.5, -3.0])
    close = np.array([100.0, 99.0, 98.0, 97.0, 96.0])
    
    context = {
        "bar_index": 2,
        "order_qty": 1,
        "features": {
            "zscore": zscore,
            "close": close,
        },
    }
    
    params = {
        "zscore_threshold": -2.0,
    }
    
    # Run multiple times
    result1 = spec.fn(context, params)
    result2 = spec.fn(context, params)
    
    # Results should be identical
    assert result1 == result2


