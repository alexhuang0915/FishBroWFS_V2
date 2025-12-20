import numpy as np

from FishBroWFS_V2.strategy.kernel import DonchianAtrParams, run_kernel, _max_drawdown
from FishBroWFS_V2.engine.types import BarArrays


def _bars():
    # Small synthetic OHLC series
    o = np.array([100, 101, 102, 103, 104, 105], dtype=np.float64)
    h = np.array([101, 102, 103, 104, 106, 107], dtype=np.float64)
    l = np.array([99, 100, 101, 102, 103, 104], dtype=np.float64)
    c = np.array([100.5, 101.5, 102.5, 103.5, 105.5, 106.5], dtype=np.float64)
    return BarArrays(open=o, high=h, low=l, close=c)


def test_no_trade_case_does_not_crash_and_returns_zero_metrics():
    bars = _bars()
    params = DonchianAtrParams(channel_len=99999, atr_len=3, stop_mult=2.0)

    out = run_kernel(bars, params, commission=0.0, slip=0.0, order_qty=1)
    pnl = out["pnl"]
    equity = out["equity"]
    metrics = out["metrics"]

    assert isinstance(pnl, np.ndarray)
    assert pnl.size == 0
    assert isinstance(equity, np.ndarray)
    assert equity.size == 0
    assert metrics["net_profit"] == 0.0
    assert metrics["trades"] == 0
    assert metrics["max_dd"] == 0.0


def test_vectorized_metrics_are_self_consistent():
    bars = _bars()
    params = DonchianAtrParams(channel_len=2, atr_len=2, stop_mult=1.0)

    out = run_kernel(bars, params, commission=0.0, slip=0.0, order_qty=1)
    pnl = out["pnl"]
    equity = out["equity"]
    metrics = out["metrics"]

    # If zero trades, still must be consistent
    if pnl.size == 0:
        assert metrics["net_profit"] == 0.0
        assert metrics["trades"] == 0
        assert metrics["max_dd"] == 0.0
        return

    # Vectorized checks
    np.testing.assert_allclose(equity, np.cumsum(pnl), rtol=0.0, atol=0.0)
    assert metrics["trades"] == int(pnl.size)
    assert metrics["net_profit"] == float(np.sum(pnl))
    assert metrics["max_dd"] == _max_drawdown(equity)


def test_costs_are_parameterized_not_hardcoded():
    bars = _bars()
    params = DonchianAtrParams(channel_len=2, atr_len=2, stop_mult=1.0)

    out0 = run_kernel(bars, params, commission=0.0, slip=0.0, order_qty=1)
    out1 = run_kernel(bars, params, commission=1.25, slip=0.75, order_qty=1)

    pnl0 = out0["pnl"]
    pnl1 = out1["pnl"]

    # Either both empty or both non-empty; if empty, pass
    if pnl0.size == 0:
        assert pnl1.size == 0
        return

    # Costs increase => pnl decreases by 2*(commission+slip) per trade
    per_trade_delta = 2.0 * (1.25 + 0.75)
    np.testing.assert_allclose(pnl1, pnl0 - per_trade_delta, rtol=0.0, atol=1e-12)

