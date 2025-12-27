
"""
Stage P2-2 Step B: Bit-exact test for precomputed indicators.

Verifies that using precomputed indicators produces identical results
to computing indicators inline in the kernel.
"""
from __future__ import annotations

from dataclasses import asdict, is_dataclass

import numpy as np

from engine.types import BarArrays, Fill
from strategy.kernel import DonchianAtrParams, PrecomputedIndicators, run_kernel_arrays
from indicators.numba_indicators import rolling_max, rolling_min, atr_wilder


def _fill_to_tuple(f: Fill) -> tuple:
    """
    Convert Fill to a comparable tuple representation.
    
    Uses dataclasses.asdict for dataclass instances, falls back to __dict__ or repr.
    Returns sorted tuple to ensure deterministic comparison.
    """
    if is_dataclass(f):
        d = asdict(f)
    else:
        # fallback: __dict__ (for normal classes)
        d = dict(getattr(f, "__dict__", {}))
        if not d:
            # last resort: repr
            return (repr(f),)
    # Fixed ordering to avoid dict order differences
    return tuple(sorted(d.items()))


def test_indicators_precompute_bit_exact() -> None:
    """
    Test that precomputed indicators produce bit-exact results.
    
    Strategy:
    - Generate random bars
    - Choose a channel_len and atr_len
    - Run kernel twice:
      A: Without precomputation (precomp=None)
      B: With precomputation (precomp=PrecomputedIndicators(...))
    - Compare: donch_hi/lo/atr arrays, metrics, fills, equity
    """
    # Generate random bars
    rng = np.random.default_rng(42)
    n_bars = 500
    close = 100.0 + np.cumsum(rng.standard_normal(n_bars))
    high = close + np.abs(rng.standard_normal(n_bars)) * 2.0
    low = close - np.abs(rng.standard_normal(n_bars)) * 2.0
    open_ = (high + low) / 2
    
    high = np.maximum(high, np.maximum(open_, close))
    low = np.minimum(low, np.minimum(open_, close))
    
    bars = BarArrays(
        open=open_.astype(np.float64),
        high=high.astype(np.float64),
        low=low.astype(np.float64),
        close=close.astype(np.float64),
    )
    
    # Choose test parameters
    ch_len = 20
    atr_len = 10
    params = DonchianAtrParams(channel_len=ch_len, atr_len=atr_len, stop_mult=1.0)
    
    # Pre-compute indicators (same logic as runner_grid)
    donch_hi_precomp = rolling_max(bars.high, ch_len)
    donch_lo_precomp = rolling_min(bars.low, ch_len)
    atr_precomp = atr_wilder(bars.high, bars.low, bars.close, atr_len)
    
    precomp = PrecomputedIndicators(
        donch_hi=donch_hi_precomp,
        donch_lo=donch_lo_precomp,
        atr=atr_precomp,
    )
    
    # Run A: Without precomputation
    result_a = run_kernel_arrays(
        bars=bars,
        params=params,
        commission=0.0,
        slip=0.0,
        order_qty=1,
        precomp=None,
    )
    
    # Run B: With precomputation
    result_b = run_kernel_arrays(
        bars=bars,
        params=params,
        commission=0.0,
        slip=0.0,
        order_qty=1,
        precomp=precomp,
    )
    
    # Verify indicators are bit-exact (if we could access them)
    # Note: We can't directly access internal arrays, but we verify outputs
    
    # Verify metrics are identical
    metrics_a = result_a["metrics"]
    metrics_b = result_b["metrics"]
    assert metrics_a["net_profit"] == metrics_b["net_profit"], "net_profit must be identical"
    assert metrics_a["trades"] == metrics_b["trades"], "trades must be identical"
    assert metrics_a["max_dd"] == metrics_b["max_dd"], "max_dd must be identical"
    
    # Verify fills are identical
    fills_a = result_a["fills"]
    fills_b = result_b["fills"]
    assert len(fills_a) == len(fills_b), "fills count must be identical"
    for i, (fill_a, fill_b) in enumerate(zip(fills_a, fills_b)):
        assert _fill_to_tuple(fill_a) == _fill_to_tuple(fill_b), f"fill[{i}] must be identical"
    
    # Verify equity arrays are bit-exact
    equity_a = result_a["equity"]
    equity_b = result_b["equity"]
    assert equity_a.shape == equity_b.shape, "equity shape must be identical"
    np.testing.assert_array_equal(equity_a, equity_b, "equity must be bit-exact")
    
    # Verify pnl arrays are bit-exact
    pnl_a = result_a["pnl"]
    pnl_b = result_b["pnl"]
    assert pnl_a.shape == pnl_b.shape, "pnl shape must be identical"
    np.testing.assert_array_equal(pnl_a, pnl_b, "pnl must be bit-exact")
    
    # Verify observability counts are identical
    obs_a = result_a.get("_obs", {})
    obs_b = result_b.get("_obs", {})
    assert obs_a.get("intents_total") == obs_b.get("intents_total"), "intents_total must be identical"
    assert obs_a.get("fills_total") == obs_b.get("fills_total"), "fills_total must be identical"


