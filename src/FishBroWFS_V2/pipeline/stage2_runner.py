
"""Stage2 runner - full backtest on Top-K parameters.

Stage2 runs full backtests using the unified simulate_run() entry point.
It computes complete metrics including net_profit, trades, max_dd, etc.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np

from FishBroWFS_V2.data.layout import normalize_bars
from FishBroWFS_V2.engine.types import BarArrays, Fill
from FishBroWFS_V2.strategy.kernel import DonchianAtrParams, run_kernel


@dataclass(frozen=True)
class Stage2Result:
    """
    Stage2 result - full backtest metrics.
    
    Contains complete backtest results including:
    - param_id: parameter index
    - net_profit: total net profit
    - trades: number of trades
    - max_dd: maximum drawdown
    - fills: list of fills (optional, for detailed analysis)
    - equity: equity curve (optional)
    - meta: optional metadata
    """
    param_id: int
    net_profit: float
    trades: int
    max_dd: float
    fills: Optional[List[Fill]] = None
    equity: Optional[np.ndarray] = None
    meta: Optional[dict] = None


def _max_drawdown(equity: np.ndarray) -> float:
    """Compute max drawdown from equity curve."""
    if equity.size == 0:
        return 0.0
    peak = np.maximum.accumulate(equity)
    dd = equity - peak
    mdd = float(np.min(dd))  # negative or 0
    return mdd


def run_stage2(
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    params_matrix: np.ndarray,
    param_ids: List[int],
    *,
    commission: float,
    slip: float,
    order_qty: int = 1,
) -> List[Stage2Result]:
    """
    Run Stage2 full backtest on selected parameters.
    
    Args:
        open_, high, low, close: OHLC arrays (float64, 1D, same length)
        params_matrix: float64 2D array (n_params, >=3)
            - col0: channel_len
            - col1: atr_len
            - col2: stop_mult
        param_ids: List of parameter indices to run (Top-K selection)
        commission: commission per trade (absolute)
        slip: slippage per trade (absolute)
        order_qty: order quantity (default: 1)
        
    Returns:
        List of Stage2Result, one per selected parameter.
        Results are in same order as param_ids.
        
    Note:
        - Only runs backtests for parameters in param_ids (Top-K subset)
        - Uses unified simulate_run() entry point (Cursor kernel)
        - Computes full metrics including PnL
    """
    bars = normalize_bars(open_, high, low, close)
    
    # Ensure contiguous arrays
    if not bars.open.flags["C_CONTIGUOUS"]:
        bars = BarArrays(
            open=np.ascontiguousarray(bars.open, dtype=np.float64),
            high=np.ascontiguousarray(bars.high, dtype=np.float64),
            low=np.ascontiguousarray(bars.low, dtype=np.float64),
            close=np.ascontiguousarray(bars.close, dtype=np.float64),
        )
    
    results: List[Stage2Result] = []
    
    for param_id in param_ids:
        if param_id < 0 or param_id >= params_matrix.shape[0]:
            # Invalid param_id - create empty result
            results.append(
                Stage2Result(
                    param_id=param_id,
                    net_profit=0.0,
                    trades=0,
                    max_dd=0.0,
                    fills=None,
                    equity=None,
                    meta=None,
                )
            )
            continue
        
        # Extract parameters
        params_row = params_matrix[param_id]
        channel_len = int(params_row[0])
        atr_len = int(params_row[1])
        stop_mult = float(params_row[2])
        
        # Build DonchianAtrParams
        kernel_params = DonchianAtrParams(
            channel_len=channel_len,
            atr_len=atr_len,
            stop_mult=stop_mult,
        )
        
        # Run kernel (uses unified simulate_run internally)
        kernel_result = run_kernel(
            bars,
            kernel_params,
            commission=commission,
            slip=slip,
            order_qty=order_qty,
        )
        
        # Extract metrics
        net_profit = float(kernel_result["metrics"]["net_profit"])
        trades = int(kernel_result["metrics"]["trades"])
        max_dd = float(kernel_result["metrics"]["max_dd"])
        
        # Extract optional fields
        fills = kernel_result.get("fills")
        equity = kernel_result.get("equity")
        
        results.append(
            Stage2Result(
                param_id=param_id,
                net_profit=net_profit,
                trades=trades,
                max_dd=max_dd,
                fills=fills,
                equity=equity,
                meta=None,
            )
        )
    
    return results


