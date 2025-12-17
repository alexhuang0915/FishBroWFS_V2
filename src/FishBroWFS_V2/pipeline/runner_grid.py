from __future__ import annotations

from typing import Dict, Tuple

import numpy as np
import os
import time

from FishBroWFS_V2.data.layout import normalize_bars
from FishBroWFS_V2.engine.types import BarArrays, Fill, OrderIntent, OrderKind, OrderRole, Side
from FishBroWFS_V2.pipeline.metrics_schema import (
    METRICS_COL_MAX_DD,
    METRICS_COL_NET_PROFIT,
    METRICS_COL_TRADES,
    METRICS_N_COLUMNS,
)
from FishBroWFS_V2.pipeline.param_sort import sort_params_cache_friendly
from FishBroWFS_V2.strategy.kernel import DonchianAtrParams, run_kernel


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


def _ensure_contiguous_bars(bars: BarArrays) -> BarArrays:
    if bars.open.flags["C_CONTIGUOUS"] and bars.high.flags["C_CONTIGUOUS"] and bars.low.flags["C_CONTIGUOUS"] and bars.close.flags["C_CONTIGUOUS"]:
        return bars
    return BarArrays(
        open=np.ascontiguousarray(bars.open, dtype=np.float64),
        high=np.ascontiguousarray(bars.high, dtype=np.float64),
        low=np.ascontiguousarray(bars.low, dtype=np.float64),
        close=np.ascontiguousarray(bars.close, dtype=np.float64),
    )


def run_grid(
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    params_matrix: np.ndarray,
    *,
    commission: float,
    slip: float,
    order_qty: int = 1,
    sort_params: bool = True,
    force_close_last: bool = False,
    return_debug: bool = False,
) -> Dict[str, object]:
    """
    Phase 3B v1: Dynamic Grid Runner (homology locked).

    params_matrix: shape (n, >=3) float64
      col0 channel_len (int-like)
      col1 atr_len (int-like)
      col2 stop_mult (float)

    Args:
        force_close_last: If True, force close any open positions at the last bar
            using close[-1] as exit price. This ensures trades > 0 when fills exist.

    Returns:
      dict with:
        - metrics: np.ndarray shape (n, 3) float64 columns:
            [net_profit, trades, max_dd] (see pipeline.metrics_schema for column indices)
        - order: np.ndarray indices mapping output rows back to original params (or identity)
    """
    profile = os.environ.get("FISHBRO_PROFILE_GRID", "").strip() == "1"
    sim_only = os.environ.get("FISHBRO_PERF_SIM_ONLY", "").strip() == "1"
    t0 = time.perf_counter()

    bars = _ensure_contiguous_bars(normalize_bars(open_, high, low, close))
    t_prep1 = time.perf_counter()

    if params_matrix.ndim != 2 or params_matrix.shape[1] < 3:
        raise ValueError("params_matrix must be (n, >=3)")

    pm = np.asarray(params_matrix, dtype=np.float64)
    if sort_params:
        pm_sorted, order = sort_params_cache_friendly(pm)
    else:
        pm_sorted = pm
        order = np.arange(pm.shape[0], dtype=np.int64)
    t_sort = time.perf_counter()

    n = pm_sorted.shape[0]
    metrics = np.zeros((n, METRICS_N_COLUMNS), dtype=np.float64)
    
    # Debug arrays: per-param first trade snapshot (only if return_debug=True)
    if return_debug:
        debug_fills_first = np.full((n, 6), np.nan, dtype=np.float64)
        # Columns: entry_bar, entry_price, exit_bar, exit_price, net_profit, trades
    else:
        debug_fills_first = None

    # Initialize result dict early (minimal structure)
    perf: Dict[str, object] = {}
    result: Dict[str, object] = {"metrics": metrics, "order": order, "perf": perf}

    if sim_only:
        # Debug mode: bypass strategy/orchestration and only benchmark matcher simulate.
        # This provides A/B evidence: if sim-only is fast, bottleneck is in kernel (indicators/intents).
        from FishBroWFS_V2.engine import engine_jit

        intents_per_bar = int(os.environ.get("FISHBRO_SIM_ONLY_INTENTS_PER_BAR", "2"))
        intents: list[OrderIntent] = []
        oid = 1
        nbars = int(bars.open.shape[0])
        for t in range(1, nbars):
            for _ in range(intents_per_bar):
                intents.append(
                    OrderIntent(
                        order_id=oid,
                        created_bar=t - 1,
                        role=OrderRole.ENTRY,
                        kind=OrderKind.STOP,
                        side=Side.BUY,
                        price=float(bars.high[t - 1]),
                        qty=1,
                    )
                )
                oid += 1
                intents.append(
                    OrderIntent(
                        order_id=oid,
                        created_bar=t - 1,
                        role=OrderRole.EXIT,
                        kind=OrderKind.STOP,
                        side=Side.SELL,
                        price=float(bars.low[t - 1]),
                        qty=1,
                    )
                )
                oid += 1

        t_sim0 = time.perf_counter()
        _fills = engine_jit.simulate(bars, intents)
        t_sim1 = time.perf_counter()
        jt = engine_jit.get_jit_truth()
        numba_env = os.environ.get("NUMBA_DISABLE_JIT", "")
        sigs = jt.get("kernel_signatures") or []
        perf = {
            "t_features": float(t_prep1 - t0),
            "t_indicators": None,
            "t_intent_gen": None,
            "t_simulate": float(t_sim1 - t_sim0),
            "simulate_impl": "jit" if jt.get("jit_path_used") else "py",
            "jit_path_used": bool(jt.get("jit_path_used")),
            "simulate_signatures_count": int(len(sigs)),
            "numba_disable_jit_env": str(numba_env),
            "intents_total": int(len(intents)),
            "intents_per_bar_avg": float(len(intents) / float(max(1, bars.open.shape[0]))),
            "fills_total": int(len(_fills)),
            "intent_mode": "objects",
        }
        result["perf"] = perf
        if return_debug and debug_fills_first is not None:
            result["debug_fills_first"] = debug_fills_first
        return result

    # Homology: only call run_kernel, never compute strategy/metrics here.
    # Perf observability is env-gated so default usage stays unchanged.
    t_ind = 0.0
    t_intgen = 0.0
    t_sim = 0.0
    intents_total = 0
    fills_total = 0
    any_profile_missing = False
    intent_mode: str | None = None
    for i in range(n):
        ch = int(pm_sorted[i, 0])
        atr = int(pm_sorted[i, 1])
        sm = float(pm_sorted[i, 2])

        if profile:
            # enable kernel profiling (cheap, coarse) so we can attribute time and counts
            os.environ["FISHBRO_PROFILE_KERNEL"] = "1"
        out = run_kernel(
            bars,
            DonchianAtrParams(channel_len=ch, atr_len=atr, stop_mult=sm),
            commission=float(commission),
            slip=float(slip),
            order_qty=int(order_qty),
            return_debug=return_debug,
        )
        obs = out.get("_obs", None)  # type: ignore
        if isinstance(obs, dict):
            # Phase 3.0-B: Trust kernel's evidence fields, do not recompute
            if intent_mode is None and isinstance(obs.get("intent_mode"), str):
                intent_mode = str(obs.get("intent_mode"))
            # Use intents_total directly from kernel (Source of Truth), not recompute from entry+exit
            intents_total += int(obs.get("intents_total", 0))
            fills_total += int(obs.get("fills_total", 0))

        if profile:
            kp = out.get("_profile", None)  # type: ignore
            if not isinstance(kp, dict):
                any_profile_missing = True
                continue
            t_ind += float(kp.get("indicators_s", 0.0))
            # include both entry+exit intent generation as "intent generation"
            t_intgen += float(kp.get("intent_gen_s", 0.0)) + float(kp.get("exit_intent_gen_s", 0.0))
            t_sim += float(kp.get("simulate_entry_s", 0.0)) + float(kp.get("simulate_exit_s", 0.0))

        m = out["metrics"]
        
        # Collect debug data if requested
        if return_debug:
            debug_info = out.get("_debug", {})
            entry_bar = debug_info.get("entry_bar", -1)
            entry_price = debug_info.get("entry_price", np.nan)
            exit_bar = debug_info.get("exit_bar", -1)
            exit_price = debug_info.get("exit_price", np.nan)
            
            # Handle force_close_last: update exit_bar/exit_price if forced close
            # (will be updated below if force_close_last triggers)
        
        # Handle force_close_last: if still in position, force close at last bar
        if force_close_last:
            fills = out.get("fills", [])
            if isinstance(fills, list) and len(fills) > 0:
                # Count entry and exit fills
                entry_fills = [f for f in fills if f.role == OrderRole.ENTRY and f.side == Side.BUY]
                exit_fills = [f for f in fills if f.role == OrderRole.EXIT and f.side == Side.SELL]
                
                # If there are unpaired entries, force close at last bar
                if len(entry_fills) > len(exit_fills):
                    n_unpaired = len(entry_fills) - len(exit_fills)
                    last_bar_idx = int(bars.open.shape[0] - 1)
                    last_close_price = float(bars.close[last_bar_idx])
                    
                    # Create forced exit fills for unpaired entries
                    # Use entry prices from the unpaired entries
                    unpaired_entry_prices = [float(f.price) for f in entry_fills[-n_unpaired:]]
                    
                    # Calculate additional pnl from forced closes
                    forced_pnl = []
                    costs_per_trade = (float(commission) + float(slip)) * 2.0
                    for entry_price in unpaired_entry_prices:
                        # PnL = (exit_price - entry_price) * qty - costs
                        trade_pnl = (last_close_price - entry_price) * float(order_qty) - costs_per_trade
                        forced_pnl.append(trade_pnl)
                    
                    # Update metrics with forced closes
                    original_net_profit = float(m["net_profit"])
                    original_trades = int(m["trades"])
                    
                    # Add forced close trades
                    new_net_profit = original_net_profit + sum(forced_pnl)
                    new_trades = original_trades + n_unpaired
                    
                    # Update debug exit info for force_close_last
                    if return_debug and n_unpaired > 0:
                        exit_bar = last_bar_idx
                        exit_price = last_close_price
                    
                    # Recalculate equity and max_dd
                    forced_pnl_arr = np.asarray(forced_pnl, dtype=np.float64)
                    if original_trades > 0 and "equity" in out:
                        original_equity = out["equity"]
                        if isinstance(original_equity, np.ndarray) and original_equity.size > 0:
                            # Append forced pnl to existing equity curve
                            # Start from last equity value
                            start_equity = float(original_equity[-1])
                            forced_equity = np.cumsum(forced_pnl_arr) + start_equity
                            new_equity = np.concatenate([original_equity, forced_equity])
                        else:
                            # No previous equity array, start from 0
                            new_equity = np.cumsum(forced_pnl_arr)
                    else:
                        # No previous trades, start from 0
                        new_equity = np.cumsum(forced_pnl_arr)
                    
                    new_max_dd = _max_drawdown(new_equity)
                    
                    metrics[i, METRICS_COL_NET_PROFIT] = new_net_profit
                    metrics[i, METRICS_COL_TRADES] = new_trades
                    metrics[i, METRICS_COL_MAX_DD] = new_max_dd
                    
                    # Update debug with final metrics after force_close_last
                    if return_debug:
                        debug_fills_first[i, 0] = entry_bar
                        debug_fills_first[i, 1] = entry_price
                        debug_fills_first[i, 2] = exit_bar
                        debug_fills_first[i, 3] = exit_price
                        debug_fills_first[i, 4] = new_net_profit
                        debug_fills_first[i, 5] = float(new_trades)
                else:
                    # No unpaired entries, use original metrics
                    metrics[i, METRICS_COL_NET_PROFIT] = float(m["net_profit"])
                    metrics[i, METRICS_COL_TRADES] = float(m["trades"])
                    metrics[i, METRICS_COL_MAX_DD] = float(m["max_dd"])
                    
                    # Store debug data
                    if return_debug:
                        debug_fills_first[i, 0] = entry_bar
                        debug_fills_first[i, 1] = entry_price
                        debug_fills_first[i, 2] = exit_bar
                        debug_fills_first[i, 3] = exit_price
                        debug_fills_first[i, 4] = float(m["net_profit"])
                        debug_fills_first[i, 5] = float(m["trades"])
            else:
                # No fills, use original metrics
                metrics[i, METRICS_COL_NET_PROFIT] = float(m["net_profit"])
                metrics[i, METRICS_COL_TRADES] = int(m["trades"])
                metrics[i, METRICS_COL_MAX_DD] = float(m["max_dd"])
                
                # Store debug data (no fills case)
                if return_debug:
                    debug_fills_first[i, 0] = entry_bar
                    debug_fills_first[i, 1] = entry_price
                    debug_fills_first[i, 2] = exit_bar
                    debug_fills_first[i, 3] = exit_price
                    debug_fills_first[i, 4] = float(m["net_profit"])
                    debug_fills_first[i, 5] = float(m["trades"])
        else:
            # Zero-trade safe: kernel guarantees valid numbers (0.0/0)
            metrics[i, METRICS_COL_NET_PROFIT] = float(m["net_profit"])
            metrics[i, METRICS_COL_TRADES] = int(m["trades"])
            metrics[i, METRICS_COL_MAX_DD] = float(m["max_dd"])
            
            # Store debug data
            if return_debug:
                debug_fills_first[i, 0] = entry_bar
                debug_fills_first[i, 1] = entry_price
                debug_fills_first[i, 2] = exit_bar
                debug_fills_first[i, 3] = exit_price
                debug_fills_first[i, 4] = float(m["net_profit"])
                debug_fills_first[i, 5] = float(m["trades"])

    # Phase 3.0-E: Ensure intent_mode is never None
    # If no kernel results (n == 0), default to "arrays" (default kernel path)
    # Otherwise, intent_mode should have been set from first kernel result
    if intent_mode is None:
        # Edge case: n == 0 (no params) - use default "arrays" since run_kernel defaults to array path
        intent_mode = "arrays"

    if not profile:
        # Return minimal perf with evidence fields only
        perf = {
            "intent_mode": intent_mode,
            "intents_total": int(intents_total),
            "fills_total": int(fills_total),
        }
        result["perf"] = perf
        if return_debug and debug_fills_first is not None:
            result["debug_fills_first"] = debug_fills_first
        return result

    from FishBroWFS_V2.engine import engine_jit

    jt = engine_jit.get_jit_truth()
    numba_env = os.environ.get("NUMBA_DISABLE_JIT", "")
    sigs = jt.get("kernel_signatures") or []

    # Best-effort: avoid leaking this env to callers
    try:
        del os.environ["FISHBRO_PROFILE_KERNEL"]
    except KeyError:
        pass

    # Phase 3.0-E: Ensure intent_mode is never None
    # If no kernel results (n == 0), default to "arrays" (default kernel path)
    # Otherwise, intent_mode should have been set from first kernel result
    if intent_mode is None:
        # Edge case: n == 0 (no params) - use default "arrays" since run_kernel defaults to array path
        intent_mode = "arrays"

    perf = {
        "t_features": float(t_prep1 - t0),
        # current architecture: indicators are computed inside run_kernel per param
        "t_indicators": None if any_profile_missing else float(t_ind),
        "t_intent_gen": None if any_profile_missing else float(t_intgen),
        "t_simulate": None if any_profile_missing else float(t_sim),
        "simulate_impl": "jit" if jt.get("jit_path_used") else "py",
        "jit_path_used": bool(jt.get("jit_path_used")),
        "simulate_signatures_count": int(len(sigs)),
        "numba_disable_jit_env": str(numba_env),
        # Phase 3.0-B: Use kernel's evidence fields directly (Source of Truth), not recomputed
        "intent_mode": intent_mode,
        "intents_total": int(intents_total),
        "fills_total": int(fills_total),
        "intents_per_bar_avg": float(intents_total / float(max(1, bars.open.shape[0]))),
    }

    result["perf"] = perf
    if return_debug and debug_fills_first is not None:
        result["debug_fills_first"] = debug_fills_first
    return result

