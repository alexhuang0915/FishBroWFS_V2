from __future__ import annotations

import numpy as np

from core.backtest.simulator import simulate_bar_engine, CostConfig


def _make_cost():
    return CostConfig(
        slippage_ticks_per_side=1.0,
        commission_per_side=1.0,
        tick_size=1.0,
        multiplier=1.0,
        fx_rate=1.0,
    )


def test_market_entry_exit_with_costs():
    ts = np.array([0, 1, 2], dtype="datetime64[s]")
    open_ = np.array([100.0, 100.0, 100.0])
    high = np.array([100.0, 100.0, 100.0])
    low = np.array([100.0, 100.0, 100.0])
    close = np.array([100.0, 100.0, 100.0])
    signals = {"target_dir": np.array([1, 0, 0], dtype=np.int64)}

    sim = simulate_bar_engine(
        ts=ts,
        open_=open_,
        high=high,
        low=low,
        close=close,
        signals=signals,
        cost=_make_cost(),
        initial_equity=10_000.0,
    )
    # Entry at open[1] with +1 tick slippage => 101
    # Exit at open[2] with -1 tick slippage => 99
    # PnL = -2, commissions = -2 => net = -4
    assert sim.trades == 1
    assert abs(sim.net + 4.0) < 1e-6


def test_stop_entry_not_triggered_no_trade():
    ts = np.array([0, 1, 2], dtype="datetime64[s]")
    open_ = np.array([100.0, 100.0, 100.0])
    high = np.array([100.0, 100.0, 100.0])
    low = np.array([100.0, 100.0, 100.0])
    close = np.array([100.0, 100.0, 100.0])
    signals = {
        "target_dir": np.array([1, 1, 1], dtype=np.int64),
        "long_stop": np.array([105.0, 105.0, 105.0]),
    }
    sim = simulate_bar_engine(
        ts=ts,
        open_=open_,
        high=high,
        low=low,
        close=close,
        signals=signals,
        cost=_make_cost(),
        initial_equity=10_000.0,
    )
    assert sim.trades == 0
    assert abs(sim.net) < 1e-6


def test_ambiguous_stop_entry_exit_no_trade():
    ts = np.array([0, 1, 2], dtype="datetime64[s]")
    open_ = np.array([100.0, 100.0, 100.0])
    high = np.array([100.0, 100.0, 110.0])
    low = np.array([100.0, 100.0, 90.0])
    close = np.array([100.0, 100.0, 100.0])
    signals = {
        "target_dir": np.array([1, -1, -1], dtype=np.int64),
        "short_stop": np.array([np.nan, 95.0, 95.0]),
        "exit_long_stop": np.array([np.nan, 95.0, 95.0]),
    }
    sim = simulate_bar_engine(
        ts=ts,
        open_=open_,
        high=high,
        low=low,
        close=close,
        signals=signals,
        cost=_make_cost(),
        initial_equity=10_000.0,
    )
    assert sim.trades == 0
    assert any("AMBIGUOUS_STOP_ENTRY_EXIT" in w for w in sim.warnings)
