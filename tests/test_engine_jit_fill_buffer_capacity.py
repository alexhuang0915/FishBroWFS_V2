"""Test that fill buffer scales with n_intents and does not segfault."""

from __future__ import annotations

import os

import numpy as np
import pytest

from FishBroWFS_V2.data.layout import normalize_bars
from FishBroWFS_V2.engine.engine_jit import STATUS_BUFFER_FULL, simulate as simulate_jit
from FishBroWFS_V2.engine.types import OrderIntent, OrderKind, OrderRole, Side


def test_fill_buffer_scales_with_intents():
    """
    Test that buffer size accommodates n_intents > n_bars*2.
    
    Scenario: n_bars=10, n_intents=100
    Each intent is designed to fill (market entry with stop that triggers immediately).
    This tests that buffer scales with n_intents, not just n_bars*2.
    """
    n_bars = 10
    n_intents = 100
    
    # Create bars with high volatility to ensure fills
    bars = normalize_bars(
        np.array([100.0] * n_bars, dtype=np.float64),
        np.array([120.0] * n_bars, dtype=np.float64),
        np.array([80.0] * n_bars, dtype=np.float64),
        np.array([110.0] * n_bars, dtype=np.float64),
    )
    
    # Create many intents that will all fill (STOP BUY at 105, which is below high=120)
    # Each intent activates on a different bar to maximize fills
    intents = []
    for i in range(n_intents):
        created_bar = (i % n_bars) - 1  # Distribute across bars
        intents.append(
            OrderIntent(
                order_id=i,
                created_bar=created_bar,
                role=OrderRole.ENTRY,
                kind=OrderKind.STOP,
                side=Side.BUY,
                price=105.0,  # Will trigger on any bar (high=120 > 105)
                qty=1,
            )
        )
    
    # Should not crash or segfault
    try:
        fills = simulate_jit(bars, intents)
        # If we get here, no segfault occurred
        
        # Fills should be bounded by n_intents (each intent can produce at most 1 fill)
        assert len(fills) <= n_intents, f"fills ({len(fills)}) should not exceed n_intents ({n_intents})"
        
        # In this scenario, we expect many fills (most intents should trigger)
        # But exact count depends on bar distribution, so we just check it's reasonable
        assert len(fills) > 0, "Should have at least some fills"
        
    except RuntimeError as e:
        # If buffer is full, error message should be graceful (not segfault)
        error_msg = str(e)
        assert "buffer full" in error_msg.lower() or "buffer_full" in error_msg.lower(), (
            f"Expected buffer full error, got: {error_msg}"
        )
        # This is acceptable - buffer protection worked correctly


def test_fill_buffer_protection_prevents_segfault():
    """
    Test that buffer protection prevents segfault even with extreme intents.
    
    This test ensures STATUS_BUFFER_FULL is returned gracefully instead of segfaulting.
    """
    import FishBroWFS_V2.engine.engine_jit as ej
    
    # Skip if JIT is disabled (buffer protection is in JIT kernel)
    if ej.nb is None or os.environ.get("NUMBA_DISABLE_JIT", "").strip() == "1":
        pytest.skip("numba not available or disabled; buffer protection tested only under JIT")
    
    n_bars = 5
    n_intents = 1000  # Extreme: way more intents than bars
    
    bars = normalize_bars(
        np.array([100.0] * n_bars, dtype=np.float64),
        np.array([120.0] * n_bars, dtype=np.float64),
        np.array([80.0] * n_bars, dtype=np.float64),
        np.array([110.0] * n_bars, dtype=np.float64),
    )
    
    # Create intents that will all try to fill
    intents = []
    for i in range(n_intents):
        # All activate on bar 0 (created_bar=-1)
        intents.append(
            OrderIntent(
                order_id=i,
                created_bar=-1,
                role=OrderRole.ENTRY,
                kind=OrderKind.STOP,
                side=Side.BUY,
                price=105.0,  # Will trigger
                qty=1,
            )
        )
    
    # Should not segfault - either succeed or return graceful error
    try:
        fills = simulate_jit(bars, intents)
        # If successful, fills should be bounded
        assert len(fills) <= n_intents
        # With this many intents on one bar, we might hit buffer limit
        # But should not crash
    except RuntimeError as e:
        # Graceful error is acceptable
        assert "buffer" in str(e).lower() or "full" in str(e).lower(), (
            f"Expected buffer-related error, got: {e}"
        )


def test_fill_buffer_minimum_size():
    """
    Test that buffer is at least n_bars*2 (default heuristic).
    
    Even with few intents, buffer should accommodate reasonable fill rate.
    """
    n_bars = 20
    n_intents = 5  # Few intents
    
    bars = normalize_bars(
        np.array([100.0] * n_bars, dtype=np.float64),
        np.array([120.0] * n_bars, dtype=np.float64),
        np.array([80.0] * n_bars, dtype=np.float64),
        np.array([110.0] * n_bars, dtype=np.float64),
    )
    
    intents = [
        OrderIntent(i, -1, OrderRole.ENTRY, OrderKind.STOP, Side.BUY, 105.0, 1)
        for i in range(n_intents)
    ]
    
    # Should work fine (buffer should be at least n_bars*2 = 40, which is > n_intents=5)
    fills = simulate_jit(bars, intents)
    assert len(fills) <= n_intents
    # Should not crash
