
"""Test that engine fill buffer handles extreme intents without crashing."""

from __future__ import annotations

import numpy as np
import pytest

from data.layout import normalize_bars
from engine.engine_jit import STATUS_BUFFER_FULL, STATUS_OK, simulate as simulate_jit
from engine.types import OrderIntent, OrderKind, OrderRole, Side


def test_engine_fill_buffer_capacity_extreme_intents() -> None:
    """
    Test that engine handles extreme intents (many intents, few bars) without crashing.
    
    Scenario: bars=10, intents=500
    Each intent is designed to fill (STOP BUY that triggers immediately).
    """
    n_bars = 10
    n_intents = 500

    # Create bars with high volatility to ensure fills
    bars = normalize_bars(
        np.array([100.0] * n_bars, dtype=np.float64),
        np.array([120.0] * n_bars, dtype=np.float64),
        np.array([80.0] * n_bars, dtype=np.float64),
        np.array([110.0] * n_bars, dtype=np.float64),
    )

    # Create many intents that will all fill (STOP BUY at 105, which is below high=120)
    # Distribute across bars to maximize fills
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
        
        # Should have some fills (most intents should trigger)
        assert len(fills) > 0, "Should have at least some fills"
        
    except RuntimeError as e:
        # If buffer is full, error message should be graceful (not segfault)
        error_msg = str(e)
        assert "buffer full" in error_msg.lower() or "buffer_full" in error_msg.lower(), (
            f"Expected buffer full error, got: {error_msg}"
        )
        # This is acceptable - buffer protection worked correctly


