from __future__ import annotations

import numpy as np
import pytest

from FishBroWFS_V2.pipeline.runner_grid import run_grid
from tests.test_stage0_proxy_rank_corr import _generate_ohlc_for_corr


def test_stage2_params_influence_extremes() -> None:
    """
    Contract test: params must influence outcome.
    
    Root cause fuse: if different params produce identical metrics,
    Stage2 is broken and Spearman correlation will be meaningless.
    """
    # Generate OHLC data using same generator as Spearman test
    n_bars = 1500
    seed = 0
    open_, high, low, close = _generate_ohlc_for_corr(n_bars, seed=seed)
    
    # Two extreme params that should produce different outcomes
    params = np.array([
        [5.0, 5.0, 0.2],   # A: short channel, short ATR, tight stop
        [39.0, 49.0, 1.5], # B: long channel, long ATR, wide stop
    ], dtype=np.float64)
    
    # Run grid with debug enabled
    result = run_grid(
        open_=open_,
        high=high,
        low=low,
        close=close,
        params_matrix=params,
        commission=0.0,
        slip=0.0,
        order_qty=1,
        sort_params=False,
        force_close_last=True,
        return_debug=True,
    )
    
    metrics = result["metrics"]
    debug_fills_first = result.get("debug_fills_first")
    
    # Extract metrics for both params
    net_profit_a = float(metrics[0, 0])  # net_profit
    net_profit_b = float(metrics[1, 0])
    trades_a = int(metrics[0, 1])  # trades
    trades_b = int(metrics[1, 1])
    
    # Extract debug info
    if debug_fills_first is not None:
        entry_bar_a_raw = debug_fills_first[0, 0]
        entry_price_a_raw = debug_fills_first[0, 1]
        exit_bar_a_raw = debug_fills_first[0, 2]
        exit_price_a_raw = debug_fills_first[0, 3]
        
        entry_bar_b_raw = debug_fills_first[1, 0]
        entry_price_b_raw = debug_fills_first[1, 1]
        exit_bar_b_raw = debug_fills_first[1, 2]
        exit_price_b_raw = debug_fills_first[1, 3]
        
        # Handle NaN values
        entry_bar_a = int(entry_bar_a_raw) if np.isfinite(entry_bar_a_raw) else -1
        entry_price_a = float(entry_price_a_raw) if np.isfinite(entry_price_a_raw) else np.nan
        exit_bar_a = int(exit_bar_a_raw) if np.isfinite(exit_bar_a_raw) else -1
        exit_price_a = float(exit_price_a_raw) if np.isfinite(exit_price_a_raw) else np.nan
        
        entry_bar_b = int(entry_bar_b_raw) if np.isfinite(entry_bar_b_raw) else -1
        entry_price_b = float(entry_price_b_raw) if np.isfinite(entry_price_b_raw) else np.nan
        exit_bar_b = int(exit_bar_b_raw) if np.isfinite(exit_bar_b_raw) else -1
        exit_price_b = float(exit_price_b_raw) if np.isfinite(exit_price_b_raw) else np.nan
        
        debug_msg = (
            f"Param A [5, 5, 0.2]: entry_bar={entry_bar_a}, entry_price={entry_price_a:.4f}, "
            f"exit_bar={exit_bar_a}, exit_price={exit_price_a:.4f}, "
            f"net_profit={net_profit_a:.4f}, trades={trades_a}\n"
            f"Param B [39, 49, 1.5]: entry_bar={entry_bar_b}, entry_price={entry_price_b:.4f}, "
            f"exit_bar={exit_bar_b}, exit_price={exit_price_b:.4f}, "
            f"net_profit={net_profit_b:.4f}, trades={trades_b}"
        )
    else:
        debug_msg = (
            f"Param A [5, 5, 0.2]: net_profit={net_profit_a:.4f}, trades={trades_a}\n"
            f"Param B [39, 49, 1.5]: net_profit={net_profit_b:.4f}, trades={trades_b}"
        )
        # Fallback: use metrics only
        entry_bar_a = entry_bar_b = -1
        entry_price_a = entry_price_b = np.nan
        exit_bar_a = exit_bar_b = -1
        exit_price_a = exit_price_b = np.nan
    
    # Assert at least one difference exists
    # This is the "root cause fuse" - if all identical, Stage2 is broken
    entry_price_diff = abs(entry_price_a - entry_price_b) if (np.isfinite(entry_price_a) and np.isfinite(entry_price_b)) else 0.0
    exit_price_diff = abs(exit_price_a - exit_price_b) if (np.isfinite(exit_price_a) and np.isfinite(exit_price_b)) else 0.0
    
    assert (
        entry_bar_a != entry_bar_b or
        entry_price_diff > 1e-6 or
        exit_bar_a != exit_bar_b or
        exit_price_diff > 1e-6 or
        abs(net_profit_a - net_profit_b) > 1e-6
    ), (
        f"Params A and B produced identical outcomes - Stage2 is broken!\n"
        f"{debug_msg}\n"
        f"This indicates params are not being used correctly in signal/stop calculation."
    )
