"""
Phase 8-GAMMA: Kernel exit gap semantics micro-tests.

Validates that Stage2 engine correctly fills STOP exits under:
- gap-through at open (open <= stop for SELL, open >= stop for BUY)
- intrabar touch (low <= stop <= high for SELL, low <= stop <= high for BUY)
- side correctness (sell stop for long exit, buy stop for short exit)
- position state (initial_pos) correctly passed to matcher.

These tests run the real Stage2 engine path (not internal mocks) using the same
simulation/harness as the ranking test.
"""

import numpy as np
import pytest

from engine.engine_types import BarArrays, OrderIntent, OrderRole, OrderKind, Side
from engine.engine_jit import simulate
from strategy.kernel import run_kernel, DonchianAtrParams


def make_bars(open_, high, low, close):
    """Create BarArrays from separate arrays."""
    return BarArrays(
        open=np.ascontiguousarray(open_, dtype=np.float64),
        high=np.ascontiguousarray(high, dtype=np.float64),
        low=np.ascontiguousarray(low, dtype=np.float64),
        close=np.ascontiguousarray(close, dtype=np.float64),
    )


def test_long_stop_gap_down_fills_at_open():
    """
    LONG position exit via SELL stop with gap down.
    
    Setup:
    - Bar 0: no fill (warmup)
    - Bar 1: entry fill (BUY stop) at price 95 (gap at open) creates long position
    - Bar 2: exit fill (SELL stop) at price 96 (gap at open) because open <= stop
    - Gap condition: open (95) <= stop (96) → fill at open (95)
    
    Expect: exit fill at bar 2, price = open (95).
    """
    # 4 bars: bar0 warmup, bar1 entry, bar2 exit, bar3 nothing
    open_ = np.array([100.0, 95.0, 95.0, 100.0], dtype=np.float64)
    high = np.array([101.0, 96.0, 96.0, 101.0], dtype=np.float64)
    low = np.array([99.0, 94.0, 94.0, 99.0], dtype=np.float64)
    close = np.array([100.5, 95.5, 95.5, 100.5], dtype=np.float64)
    bars = make_bars(open_, high, low, close)
    
    # Entry intent: BUY STOP at 95, created at bar0, activates at bar1
    entry_intent = OrderIntent(
        order_id=1,
        created_bar=0,
        role=OrderRole.ENTRY,
        kind=OrderKind.STOP,
        side=Side.BUY,
        price=95.0,
        qty=1,
    )
    # Exit intent: SELL STOP at 96, created at bar1 (after entry fill), activates at bar2
    exit_intent = OrderIntent(
        order_id=2,
        created_bar=1,
        role=OrderRole.EXIT,
        kind=OrderKind.STOP,
        side=Side.SELL,
        price=96.0,
        qty=1,
    )
    
    # Simulate entry intents first (initial_pos=0)
    entry_fills = simulate(bars, [entry_intent], initial_pos=0)
    assert len(entry_fills) == 1
    fill_entry = entry_fills[0]
    assert fill_entry.bar_index == 1  # fills at bar1 because open >= stop (gap)
    assert fill_entry.side == Side.BUY
    assert fill_entry.role == OrderRole.ENTRY
    assert fill_entry.price == 95.0  # open price
    
    # Simulate exit intents with initial_pos=1 (long)
    exit_fills = simulate(bars, [exit_intent], initial_pos=1)
    assert len(exit_fills) == 1
    fill_exit = exit_fills[0]
    assert fill_exit.bar_index == 2
    assert fill_exit.side == Side.SELL
    assert fill_exit.role == OrderRole.EXIT
    assert fill_exit.kind == OrderKind.STOP
    # Should fill at open because open <= stop (95 <= 96)
    assert fill_exit.price == 95.0  # open price of bar 2
    # Quantity matches
    assert fill_exit.qty == 1


def test_long_stop_intrabar_touch_fills_at_stop():
    """
    LONG position exit via SELL stop with intrabar touch (no gap).
    
    Setup:
    - Bar 0: warmup
    - Bar 1: entry fill (BUY stop) at price 95 (gap at open)
    - Bar 2: exit fill (SELL stop) at price 96, open=97, high=99, low=94
    - Intrabar condition: low (94) <= stop (96) <= high (99) → fill at stop price (96)
    - No gap because open (97) > stop (96)
    
    Expect: exit fill at bar 2, price = stop (96).
    """
    open_ = np.array([100.0, 95.0, 97.0, 100.0], dtype=np.float64)
    high = np.array([101.0, 96.0, 99.0, 101.0], dtype=np.float64)
    low = np.array([99.0, 94.0, 94.0, 99.0], dtype=np.float64)
    close = np.array([100.5, 95.5, 95.5, 100.5], dtype=np.float64)
    bars = make_bars(open_, high, low, close)
    
    entry_intent = OrderIntent(
        order_id=1,
        created_bar=0,
        role=OrderRole.ENTRY,
        kind=OrderKind.STOP,
        side=Side.BUY,
        price=95.0,
        qty=1,
    )
    exit_intent = OrderIntent(
        order_id=2,
        created_bar=1,
        role=OrderRole.EXIT,
        kind=OrderKind.STOP,
        side=Side.SELL,
        price=96.0,
        qty=1,
    )
    
    entry_fills = simulate(bars, [entry_intent], initial_pos=0)
    assert len(entry_fills) == 1
    fill_entry = entry_fills[0]
    assert fill_entry.bar_index == 1
    assert fill_entry.price == 95.0
    
    exit_fills = simulate(bars, [exit_intent], initial_pos=1)
    assert len(exit_fills) == 1
    fill_exit = exit_fills[0]
    assert fill_exit.bar_index == 2
    assert fill_exit.side == Side.SELL
    assert fill_exit.role == OrderRole.EXIT
    # Should fill at stop price because low <= stop <= high and open > stop (no gap)
    assert fill_exit.price == 96.0
    assert fill_exit.qty == 1


def test_short_stop_gap_up_fills_at_open():
    """
    SHORT position exit via BUY stop with gap up.
    
    Setup:
    - Bar 0: warmup
    - Bar 1: entry fill (SELL stop) at price 105 (gap at open) creates short position
    - Bar 2: exit fill (BUY stop) at price 104 (gap at open) because open >= stop
    - Gap condition: open (105) >= stop (104) → fill at open (105)
    
    Expect: exit fill at bar 2, price = open (105).
    """
    open_ = np.array([100.0, 105.0, 105.0, 100.0], dtype=np.float64)
    high = np.array([101.0, 106.0, 106.0, 101.0], dtype=np.float64)
    low = np.array([99.0, 104.0, 104.0, 99.0], dtype=np.float64)
    close = np.array([100.5, 105.5, 105.5, 100.5], dtype=np.float64)
    bars = make_bars(open_, high, low, close)
    
    # Entry intent: SELL STOP at 105, created at bar0, activates at bar1
    entry_intent = OrderIntent(
        order_id=1,
        created_bar=0,
        role=OrderRole.ENTRY,
        kind=OrderKind.STOP,
        side=Side.SELL,
        price=105.0,
        qty=1,
    )
    # Exit intent: BUY STOP at 104, created at bar1, activates at bar2
    exit_intent = OrderIntent(
        order_id=2,
        created_bar=1,
        role=OrderRole.EXIT,
        kind=OrderKind.STOP,
        side=Side.BUY,
        price=104.0,
        qty=1,
    )
    
    entry_fills = simulate(bars, [entry_intent], initial_pos=0)
    assert len(entry_fills) == 1
    fill_entry = entry_fills[0]
    assert fill_entry.bar_index == 1
    assert fill_entry.side == Side.SELL
    assert fill_entry.price == 105.0  # open price
    
    exit_fills = simulate(bars, [exit_intent], initial_pos=-1)  # short position
    assert len(exit_fills) == 1
    fill_exit = exit_fills[0]
    assert fill_exit.bar_index == 2
    assert fill_exit.side == Side.BUY
    assert fill_exit.role == OrderRole.EXIT
    # Should fill at open because open >= stop (105 >= 104)
    assert fill_exit.price == 105.0  # open price of bar 2
    assert fill_exit.qty == 1


def test_short_stop_intrabar_touch_fills_at_stop():
    """
    SHORT position exit via BUY stop with intrabar touch.
    
    Setup:
    - Bar 0: warmup
    - Bar 1: entry fill (SELL stop) at price 105 (gap at open)
    - Bar 2: exit fill (BUY stop) at price 104, open=103, high=107, low=102
    - Intrabar condition: low (102) <= stop (104) <= high (107) → fill at stop price (104)
    - No gap because open (103) < stop (104)
    
    Expect: exit fill at bar 2, price = stop (104).
    """
    open_ = np.array([100.0, 105.0, 103.0, 100.0], dtype=np.float64)
    high = np.array([101.0, 106.0, 107.0, 101.0], dtype=np.float64)
    low = np.array([99.0, 104.0, 102.0, 99.0], dtype=np.float64)
    close = np.array([100.5, 105.5, 105.5, 100.5], dtype=np.float64)
    bars = make_bars(open_, high, low, close)
    
    entry_intent = OrderIntent(
        order_id=1,
        created_bar=0,
        role=OrderRole.ENTRY,
        kind=OrderKind.STOP,
        side=Side.SELL,
        price=105.0,
        qty=1,
    )
    exit_intent = OrderIntent(
        order_id=2,
        created_bar=1,
        role=OrderRole.EXIT,
        kind=OrderKind.STOP,
        side=Side.BUY,
        price=104.0,
        qty=1,
    )
    
    entry_fills = simulate(bars, [entry_intent], initial_pos=0)
    assert len(entry_fills) == 1
    fill_entry = entry_fills[0]
    assert fill_entry.bar_index == 1
    assert fill_entry.price == 105.0
    
    exit_fills = simulate(bars, [exit_intent], initial_pos=-1)
    assert len(exit_fills) == 1
    fill_exit = exit_fills[0]
    assert fill_exit.bar_index == 2
    assert fill_exit.side == Side.BUY
    assert fill_exit.role == OrderRole.EXIT
    # Should fill at stop price because low <= stop <= high and open < stop (no gap)
    assert fill_exit.price == 104.0
    assert fill_exit.qty == 1


def test_trade_closes_equity_updates_smoke(monkeypatch):
    """
    Smoke test that a complete trade cycle (entry + exit) via stop orders
    results in trades > 0 and equity non-empty.
    
    Uses run_kernel (the real Stage2 engine path) with a minimal
    parameter set to ensure the kernel's internal equity/trade accounting works.
    """
    # Force object mode and 100% trigger density to maximize chance of trades
    monkeypatch.setenv("FISHBRO_KERNEL_INTENT_MODE", "objects")
    monkeypatch.setenv("FISHBRO_PERF_TRIGGER_RATE", "1.0")
    monkeypatch.setenv("FISHBRO_PERF_PARAM_SUBSAMPLE_RATE", "1.0")
    
    # 60 bars, with a guaranteed entry and exit pattern.
    n_bars = 60
    open_ = np.full(n_bars, 100.0, dtype=np.float64)
    high = np.full(n_bars, 101.0, dtype=np.float64)
    low = np.full(n_bars, 99.0, dtype=np.float64)
    close = np.full(n_bars, 100.5, dtype=np.float64)
    
    # Ensure warmup passes (channel_len=10, atr_len=5)
    # Create a spike at bar 30 (high=200) and also ensure next bar open=200 (gap)
    # This will cause donchian high at bar 30 = 200, entry intent created at bar 30,
    # activates at bar 31, open=200 (gap) -> entry fill at bar 31 open.
    spike_bar = 30
    entry_fill_bar = spike_bar + 1
    open_[entry_fill_bar] = 200.0
    high[entry_fill_bar] = 200.0
    low[entry_fill_bar] = 199.0
    close[entry_fill_bar] = 199.5
    # Also need high at spike bar to be 200 for donchian high
    high[spike_bar] = 200.0
    low[spike_bar] = 199.0
    
    # Create a crash at bar 40 to trigger exit stop (sell stop)
    # Exit stop price = entry_price - stop_mult * atr
    # We'll set low at bar 40 extremely low to guarantee sell stop trigger
    exit_bar = 40
    low[exit_bar] = 50.0
    high[exit_bar] = 51.0
    open_[exit_bar] = 51.0
    close[exit_bar] = 50.5
    
    bars = make_bars(open_, high, low, close)
    # Use small channel_len and atr_len to ensure warmup passes
    params = DonchianAtrParams(channel_len=10, atr_len=5, stop_mult=2.0)
    
    # Run kernel (default mode depends on env, but should work)
    result = run_kernel(
        bars,
        params,
        commission=0.0,
        slip=0.0,
        order_qty=1,
    )
    
    # Debug: print result keys and fills count
    import sys
    print(f"[DEBUG] Result keys: {list(result.keys())}", file=sys.stderr)
    if "fills" in result:
        print(f"[DEBUG] Fills count: {len(result['fills'])}", file=sys.stderr)
        for f in result["fills"]:
            print(f"[DEBUG] Fill: {f}", file=sys.stderr)
    if "_obs" in result:
        print(f"[DEBUG] Obs: {result['_obs']}", file=sys.stderr)
    
    # Must have at least one trade (entry + exit)
    trades = result["metrics"]["trades"]
    assert trades > 0, f"Expected trades > 0, got {trades}"
    # Equity array must be non-empty
    equity = result["equity"]
    assert equity is not None and len(equity) > 0, "Equity array empty"
    # Equity must be finite
    assert np.isfinite(equity).all(), "Non-finite values in equity"
    # Net profit should reflect the trade
    net_profit = result["metrics"]["net_profit"]
    assert np.isfinite(net_profit), "Net profit not finite"
    
    # Optional: verify that fills contain both entry and exit
    fills = result["fills"]
    if fills is not None and len(fills) >= 2:
        # At least one entry and one exit fill
        entry_fills = [f for f in fills if f.role == OrderRole.ENTRY]
        exit_fills = [f for f in fills if f.role == OrderRole.EXIT]
        assert len(entry_fills) >= 1, "No entry fills"
        assert len(exit_fills) >= 1, "No exit fills"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])