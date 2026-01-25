from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Dict, Any, List
import numpy as np


@dataclass(frozen=True)
class CostConfig:
    slippage_ticks_per_side: float
    commission_per_side: float
    tick_size: float
    multiplier: float
    fx_rate: float


@dataclass(frozen=True)
class SimulationResult:
    equity: np.ndarray
    trades: int
    net: float
    mdd: float
    warnings: list[str]


def simulate_bar_engine(
    *,
    ts: np.ndarray,
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    signals: Dict[str, Optional[np.ndarray]],
    cost: CostConfig,
    initial_equity: float = 10_000.0,
) -> SimulationResult:
    n = len(ts)
    if n == 0:
        return SimulationResult(equity=np.array([], dtype=np.float64), trades=0, net=0.0, mdd=0.0, warnings=[])

    target_dir = signals.get("target_dir")
    long_stop = signals.get("long_stop")
    short_stop = signals.get("short_stop")
    exit_long_stop = signals.get("exit_long_stop")
    exit_short_stop = signals.get("exit_short_stop")

    def _as_val(arr: Optional[np.ndarray], idx: int) -> Optional[float]:
        if arr is None:
            return None
        try:
            v = arr[idx]
        except Exception:
            return None
        if v is None:
            return None
        try:
            fv = float(v)
        except Exception:
            return None
        if np.isnan(fv):
            return None
        return fv

    def _apply_slippage(price: float, side: str) -> float:
        if cost.slippage_ticks_per_side <= 0:
            return price
        delta = cost.slippage_ticks_per_side * cost.tick_size
        if side == "buy":
            return price + delta
        return price - delta

    def _commission() -> float:
        return cost.commission_per_side * cost.fx_rate

    equity = np.zeros(n, dtype=np.float64)
    cash = float(initial_equity)
    pos = 0
    entry_price = 0.0
    trades = 0
    warnings: list[str] = []

    equity[0] = cash

    for i in range(1, n):
        s_idx = i - 1
        desired = 0
        if target_dir is not None:
            try:
                desired = int(target_dir[s_idx])
            except Exception:
                desired = 0

        long_stop_p = _as_val(long_stop, s_idx)
        short_stop_p = _as_val(short_stop, s_idx)
        exit_long_p = _as_val(exit_long_stop, s_idx)
        exit_short_p = _as_val(exit_short_stop, s_idx)

        bar_open = float(open_[i])
        bar_high = float(high[i])
        bar_low = float(low[i])

        entry_stop_side: Optional[str] = None
        entry_stop_price: Optional[float] = None
        if desired != 0:
            if desired > 0 and long_stop_p is not None:
                entry_stop_side = "long"
                entry_stop_price = long_stop_p
            elif desired < 0 and short_stop_p is not None:
                entry_stop_side = "short"
                entry_stop_price = short_stop_p

        entry_triggered = False
        entry_fill = None
        if entry_stop_side == "long" and entry_stop_price is not None:
            if bar_high >= entry_stop_price:
                entry_triggered = True
                entry_fill = bar_open if bar_open >= entry_stop_price else entry_stop_price
        elif entry_stop_side == "short" and entry_stop_price is not None:
            if bar_low <= entry_stop_price:
                entry_triggered = True
                entry_fill = bar_open if bar_open <= entry_stop_price else entry_stop_price

        exit_triggered = False
        exit_fill = None
        if pos > 0 and exit_long_p is not None:
            if bar_low <= exit_long_p:
                exit_triggered = True
                exit_fill = bar_open if bar_open <= exit_long_p else exit_long_p
        elif pos < 0 and exit_short_p is not None:
            if bar_high >= exit_short_p:
                exit_triggered = True
                exit_fill = bar_open if bar_open >= exit_short_p else exit_short_p

        # Same-bar stop entry + stop exit ambiguity => no trade.
        if entry_triggered and exit_triggered:
            warnings.append(f"AMBIGUOUS_STOP_ENTRY_EXIT at {i}")
        else:
            # Stop-exit first (protective)
            if exit_triggered:
                if pos > 0:
                    exit_price = _apply_slippage(float(exit_fill), "sell")
                    pnl = (exit_price - entry_price) * pos * cost.multiplier * cost.fx_rate
                    cash += pnl
                    cash -= _commission()
                elif pos < 0:
                    exit_price = _apply_slippage(float(exit_fill), "buy")
                    pnl = (entry_price - exit_price) * (-pos) * cost.multiplier * cost.fx_rate
                    cash += pnl
                    cash -= _commission()
                pos = 0
                trades += 1

            # Market exit if target_dir requests change (after stop-exit)
            if pos != desired and pos != 0:
                exit_price = _apply_slippage(bar_open, "sell" if pos > 0 else "buy")
                if pos > 0:
                    pnl = (exit_price - entry_price) * pos * cost.multiplier * cost.fx_rate
                else:
                    pnl = (entry_price - exit_price) * (-pos) * cost.multiplier * cost.fx_rate
                cash += pnl
                cash -= _commission()
                pos = 0
                trades += 1

            # Entry: if flat and desired !=0
            if pos == 0 and desired != 0:
                if entry_stop_side is None:
                    # Market entry
                    entry_price = _apply_slippage(bar_open, "buy" if desired > 0 else "sell")
                    cash -= _commission()
                    pos = 1 if desired > 0 else -1
                elif entry_triggered and entry_fill is not None:
                    entry_price = _apply_slippage(float(entry_fill), "buy" if desired > 0 else "sell")
                    cash -= _commission()
                    pos = 1 if desired > 0 else -1

        # Mark-to-market
        if pos == 0:
            equity[i] = cash
        else:
            equity[i] = cash + (float(close[i]) - entry_price) * pos * cost.multiplier * cost.fx_rate

    net = float(equity[-1] - equity[0]) if len(equity) >= 2 else 0.0
    mdd = _max_drawdown(equity)
    return SimulationResult(equity=equity, trades=trades, net=net, mdd=mdd, warnings=warnings)


def _max_drawdown(equity: np.ndarray) -> float:
    if equity.size == 0:
        return 0.0
    peak = np.maximum.accumulate(equity)
    dd = peak - equity
    return float(np.max(dd))
