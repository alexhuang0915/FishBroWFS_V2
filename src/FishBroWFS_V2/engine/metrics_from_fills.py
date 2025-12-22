
from __future__ import annotations

from typing import List, Tuple

import numpy as np

from FishBroWFS_V2.engine.types import Fill, OrderRole, Side


def _max_drawdown(equity: np.ndarray) -> float:
    """
    Vectorized max drawdown on an equity curve.
    Handles empty arrays gracefully.
    """
    if equity.size == 0:
        return 0.0
    peak = np.maximum.accumulate(equity)
    dd = equity - peak
    mdd = float(np.min(dd))  # negative or 0
    return mdd


def compute_metrics_from_fills(
    fills: List[Fill],
    commission: float,
    slip: float,
    qty: int,
) -> Tuple[float, int, float, np.ndarray]:
    """
    Compute metrics from fills list.
    
    This is the unified source of truth for metrics computation from fills.
    Both object-mode and array-mode kernels should use this helper to ensure parity.
    
    Args:
        fills: List of Fill objects (can be empty)
        commission: Commission cost per trade (absolute)
        slip: Slippage cost per trade (absolute)
        qty: Order quantity (used for PnL calculation)
    
    Returns:
        Tuple of (net_profit, trades, max_dd, equity):
            - net_profit: float - Total net profit (sum of all round-trip PnL)
            - trades: int - Number of trades (equals pnl.size, not entry fills count)
            - max_dd: float - Maximum drawdown from equity curve
            - equity: np.ndarray - Cumulative equity curve (cumsum of per-trade PnL)
    
    Note:
        - trades is defined as pnl.size (number of completed round-trip trades)
        - Only LONG trades are supported (BUY entry, SELL exit)
        - Costs are applied per fill (entry + exit each incur cost)
        - Metrics are derived from pnl/equity, not from fills count
    """
    # Extract entry/exit prices for round trips
    # Pairing rule: take fills in chronological order, pair BUY(ENTRY) then SELL(EXIT)
    entry_prices = []
    exit_prices = []
    for f in fills:
        if f.role == OrderRole.ENTRY and f.side == Side.BUY:
            entry_prices.append(float(f.price))
        elif f.role == OrderRole.EXIT and f.side == Side.SELL:
            exit_prices.append(float(f.price))
    
    # Match entry/exit pairs (take minimum to handle unpaired entries)
    k = min(len(entry_prices), len(exit_prices))
    if k == 0:
        # No complete round trips: no pnl, so trades = 0
        return (0.0, 0, 0.0, np.empty(0, dtype=np.float64))
    
    ep = np.asarray(entry_prices[:k], dtype=np.float64)
    xp = np.asarray(exit_prices[:k], dtype=np.float64)
    
    # Costs applied per fill (entry + exit)
    costs = (float(commission) + float(slip)) * 2.0
    pnl = (xp - ep) * float(qty) - costs
    equity = np.cumsum(pnl)
    
    # CURSOR TASK 1: trades must equal pnl.size (Source of Truth)
    trades = int(pnl.size)
    net_profit = float(np.sum(pnl)) if pnl.size else 0.0
    max_dd = _max_drawdown(equity)
    
    return (net_profit, trades, max_dd, equity)


