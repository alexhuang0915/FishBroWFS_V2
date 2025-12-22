
from __future__ import annotations

import numpy as np

from FishBroWFS_V2.pipeline.runner_grid import run_grid


def test_perf_evidence_chain_exists() -> None:
    """
    Phase 3.0-D: Contract Test - Evidence Chain Existence
    
    Purpose: Lock down that evidence fields always exist and are non-null.
    This test only verifies evidence existence, not timing or strategy quality.
    """
    # Use minimal data: bars=50, params=3
    n_bars = 50
    n_params = 3
    
    # Generate synthetic OHLC data
    rng = np.random.default_rng(42)
    close = 100.0 + np.cumsum(rng.standard_normal(n_bars)).astype(np.float64)
    high = close + np.abs(rng.standard_normal(n_bars)) * 2.0
    low = close - np.abs(rng.standard_normal(n_bars)) * 2.0
    open_ = (high + low) / 2 + rng.standard_normal(n_bars) * 0.5
    
    # Ensure high >= max(open, close) and low <= min(open, close)
    high = np.maximum(high, np.maximum(open_, close))
    low = np.minimum(low, np.minimum(open_, close))
    
    # Generate minimal params: [channel_len, atr_len, stop_mult]
    params = np.array(
        [
            [10, 5, 1.0],
            [15, 7, 1.5],
            [20, 10, 2.0],
        ],
        dtype=np.float64,
    )
    
    # Run grid runner (array path)
    # Note: perf field is always present in runner output (Phase 3.0-B)
    out = run_grid(
        open_=open_,
        high=high,
        low=low,
        close=close,
        params_matrix=params,
        commission=0.0,
        slip=0.0,
        order_qty=1,
        sort_params=False,
    )
    
    # Verify perf field exists
    assert "perf" in out, "perf field must exist in runner output"
    perf = out["perf"]
    assert isinstance(perf, dict), "perf must be a dict"
    
    # Phase 3.0-D: Assert evidence fields exist and are non-null
    # 1. intent_mode must be "arrays"
    assert "intent_mode" in perf, "intent_mode must exist in perf"
    assert perf["intent_mode"] == "arrays", (
        f"intent_mode expected 'arrays' but got '{perf['intent_mode']}'"
    )
    
    # 2. intents_total must exist, be non-null, and > 0
    assert "intents_total" in perf, "intents_total must exist in perf"
    assert perf["intents_total"] is not None, "intents_total must not be None"
    assert isinstance(perf["intents_total"], (int, np.integer)), (
        f"intents_total must be an integer, got {type(perf['intents_total'])}"
    )
    assert int(perf["intents_total"]) > 0, (
        f"intents_total must be > 0, got {perf['intents_total']}"
    )
    
    # 3. fills_total must exist and be non-null (can be 0, but not None)
    assert "fills_total" in perf, "fills_total must exist in perf"
    assert perf["fills_total"] is not None, "fills_total must not be None"
    assert isinstance(perf["fills_total"], (int, np.integer)), (
        f"fills_total must be an integer, got {type(perf['fills_total'])}"
    )
    # fills_total can be 0 (no trades), but must not be None


