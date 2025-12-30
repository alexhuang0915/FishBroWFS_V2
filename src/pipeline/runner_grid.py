
from __future__ import annotations

from typing import Dict, Tuple

import numpy as np
import os
import time

from data.layout import normalize_bars
from engine.types import BarArrays, Fill, OrderIntent, OrderKind, OrderRole, Side
from pipeline.metrics_schema import (
    METRICS_COL_MAX_DD,
    METRICS_COL_NET_PROFIT,
    METRICS_COL_TRADES,
    METRICS_N_COLUMNS,
)
from pipeline.param_sort import sort_params_cache_friendly
from strategy.kernel import DonchianAtrParams, PrecomputedIndicators, run_kernel
from indicators.numba_indicators import rolling_max, rolling_min, atr_wilder


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
    profile_grid = os.environ.get("FISHBRO_PROFILE_GRID", "").strip() == "1"
    profile_kernel = os.environ.get("FISHBRO_PROFILE_KERNEL", "").strip() == "1"
    
    # Stage P2-1.8: Bridge (B) - if user turns on GRID profiling, kernel timing must be enabled too.
    # This provides stable UX: grid breakdown automatically enables kernel timing.
    # Only restore if we set it ourselves, to avoid polluting external caller's environment.
    _set_kernel_profile = False
    if profile_grid and not profile_kernel:
        os.environ["FISHBRO_PROFILE_KERNEL"] = "1"
        _set_kernel_profile = True
    
    # Treat either flag as "profile mode" for grid aggregation.
    profile = profile_grid or profile_kernel
    
    sim_only = os.environ.get("FISHBRO_PERF_SIM_ONLY", "").strip() == "1"
    t0 = time.perf_counter()

    bars = _ensure_contiguous_bars(normalize_bars(open_, high, low, close))
    t_prep1 = time.perf_counter()

    if params_matrix.ndim != 2 or params_matrix.shape[1] < 3:
        raise ValueError("params_matrix must be (n, >=3)")

    from config.dtypes import INDEX_DTYPE
    from config.dtypes import PRICE_DTYPE_STAGE2
    
    # runner_grid is used in Stage2, so keep float64 for params_matrix (conservative)
    pm = np.asarray(params_matrix, dtype=PRICE_DTYPE_STAGE2)
    if sort_params:
        pm_sorted, order = sort_params_cache_friendly(pm)
        # Convert order to INDEX_DTYPE (int32) for memory optimization
        order = order.astype(INDEX_DTYPE)
    else:
        pm_sorted = pm
        order = np.arange(pm.shape[0], dtype=INDEX_DTYPE)
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
    
    # Stage P2-2 Step A: Memoization potential assessment - unique counts
    # Extract channel_len and atr_len values (as int32 for unique counting)
    ch_vals = pm_sorted[:, 0].astype(np.int32, copy=False)
    atr_vals = pm_sorted[:, 1].astype(np.int32, copy=False)
    
    perf["unique_channel_len_count"] = int(np.unique(ch_vals).size)
    perf["unique_atr_len_count"] = int(np.unique(atr_vals).size)
    
    # Pack pair to int64 key: (ch<<32) | atr
    pair_keys = (ch_vals.astype(np.int64) << 32) | (atr_vals.astype(np.int64) & 0xFFFFFFFF)
    perf["unique_ch_atr_pair_count"] = int(np.unique(pair_keys).size)
    
    # Stage P2-2 Step B3: Pre-compute indicators for unique channel_len and atr_len
    unique_ch = np.unique(ch_vals)
    unique_atr = np.unique(atr_vals)
    
    # Build caches for precomputed indicators
    donch_cache_hi: Dict[int, np.ndarray] = {}
    donch_cache_lo: Dict[int, np.ndarray] = {}
    atr_cache: Dict[int, np.ndarray] = {}
    
    # Pre-compute timing (if profiling enabled)
    t_precompute_start = time.perf_counter() if profile else 0.0
    
    # Pre-compute Donchian indicators for unique channel_len values
    for ch_len in unique_ch:
        ch_len_int = int(ch_len)
        clamped_ch = max(1, ch_len_int)
        donch_cache_hi[ch_len_int] = rolling_max(bars.high, clamped_ch)
        donch_cache_lo[ch_len_int] = rolling_min(bars.low, clamped_ch)
    
    # Pre-compute ATR indicators for unique atr_len values
    for atr_len in unique_atr:
        atr_len_int = int(atr_len)
        clamped_atr = max(1, atr_len_int)
        atr_cache[atr_len_int] = atr_wilder(bars.high, bars.low, bars.close, clamped_atr)
    
    t_precompute_end = time.perf_counter() if profile else 0.0
    
    # Stage P2-2 Step B4: Memory observation fields
    precomp_bytes_donchian = sum(arr.nbytes for arr in donch_cache_hi.values()) + sum(arr.nbytes for arr in donch_cache_lo.values())
    precomp_bytes_atr = sum(arr.nbytes for arr in atr_cache.values())
    precomp_bytes_total = precomp_bytes_donchian + precomp_bytes_atr
    
    perf["precomp_unique_channel_len_count"] = int(len(unique_ch))
    perf["precomp_unique_atr_len_count"] = int(len(unique_atr))
    perf["precomp_bytes_donchian"] = int(precomp_bytes_donchian)
    perf["precomp_bytes_atr"] = int(precomp_bytes_atr)
    perf["precomp_bytes_total"] = int(precomp_bytes_total)
    if profile:
        perf["t_precompute_indicators_s"] = float(t_precompute_end - t_precompute_start)
    
    # CURSOR TASK 3: Grid 層把 intent sparse 傳到底
    # Read FISHBRO_PERF_TRIGGER_RATE as intent_sparse_rate and pass to kernel
    intent_sparse_rate_env = os.environ.get("FISHBRO_PERF_TRIGGER_RATE", "").strip()
    intent_sparse_rate = 1.0
    if intent_sparse_rate_env:
        try:
            intent_sparse_rate = float(intent_sparse_rate_env)
            if not (0.0 <= intent_sparse_rate <= 1.0):
                intent_sparse_rate = 1.0
        except ValueError:
            intent_sparse_rate = 1.0
    
    # Stage P2-3: Param-subsample (deterministic selection)
    # FISHBRO_PERF_PARAM_SUBSAMPLE_RATE controls param subsampling (separate from trigger_rate)
    # FISHBRO_PERF_TRIGGER_RATE is for bar/intent-level sparsity (handled in kernel)
    param_subsample_rate_env = os.environ.get("FISHBRO_PERF_PARAM_SUBSAMPLE_RATE", "").strip()
    param_subsample_seed_env = os.environ.get("FISHBRO_PERF_PARAM_SUBSAMPLE_SEED", "").strip()
    
    param_subsample_rate = 1.0
    if param_subsample_rate_env:
        try:
            param_subsample_rate = float(param_subsample_rate_env)
            if not (0.0 <= param_subsample_rate <= 1.0):
                param_subsample_rate = 1.0
        except ValueError:
            param_subsample_rate = 1.0
    
    param_subsample_seed = 42
    if param_subsample_seed_env:
        try:
            param_subsample_seed = int(param_subsample_seed_env)
        except ValueError:
            param_subsample_seed = 42
    
    # Stage P2-3: Determine selected params (deterministic)
    # CURSOR TASK 1: Use "pos" (sorted space position) for selection, "orig" (original index) for scatter-back
    if param_subsample_rate < 1.0:
        k = max(1, int(round(n * param_subsample_rate)))
        rng = np.random.default_rng(param_subsample_seed)
        # Generate deterministic permutation
        perm = rng.permutation(n)
        selected_pos = np.sort(perm[:k]).astype(INDEX_DTYPE)  # Sort to maintain deterministic loop order
    else:
        selected_pos = np.arange(n, dtype=INDEX_DTYPE)
    
    # CURSOR TASK 1: Map selected_pos (sorted space) to selected_orig (original space)
    selected_orig = order[selected_pos].astype(np.int64)  # Map sorted positions to original indices
    
    selected_params_count = len(selected_pos)
    selected_params_ratio = float(selected_params_count) / float(n) if n > 0 else 0.0
    
    # Create metrics_computed_mask: boolean array indicating which rows were computed
    metrics_computed_mask = np.zeros(n, dtype=bool)
    for orig_i in selected_orig:
        metrics_computed_mask[orig_i] = True
    
    # Add param subsample info to perf
    perf["param_subsample_rate_configured"] = float(param_subsample_rate)
    perf["selected_params_count"] = int(selected_params_count)
    perf["selected_params_ratio"] = float(selected_params_ratio)
    perf["metrics_rows_computed"] = int(selected_params_count)
    perf["metrics_computed_mask"] = metrics_computed_mask.tolist()  # Convert to list for JSON serialization
    
    # Stage P2-1.8: Initialize granular timing and count accumulators (only if profile enabled)
    if profile:
        # Stage P2-2 Step A: Micro-profiling timing keys
        perf["t_ind_donchian_s"] = 0.0
        perf["t_ind_atr_s"] = 0.0
        perf["t_build_entry_intents_s"] = 0.0
        perf["t_simulate_entry_s"] = 0.0
        perf["t_calc_exits_s"] = 0.0
        perf["t_simulate_exit_s"] = 0.0
        perf["t_total_kernel_s"] = 0.0
        perf["entry_fills_total"] = 0
        perf["exit_intents_total"] = 0
        perf["exit_fills_total"] = 0
    result: Dict[str, object] = {"metrics": metrics, "order": order, "perf": perf}

    if sim_only:
        # Debug mode: bypass strategy/orchestration and only benchmark matcher simulate.
        # This provides A/B evidence: if sim-only is fast, bottleneck is in kernel (indicators/intents).
        from engine import engine_jit

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
    # Stage P2-1.5: Entry sparse observability (accumulate across params)
    entry_valid_mask_sum = 0
    entry_intents_total = 0
    n_bars_for_entry_obs = None  # Will be set from first kernel result
    # Stage P2-3: Sparse builder observability (accumulate across params)
    allowed_bars_total = 0  # Total allowed bars (before trigger rate filtering)
    intents_generated_total = 0  # Total intents generated (after trigger rate filtering)
    
    # CURSOR TASK 1: Collect metrics_subset (will be scattered back after loop)
    metrics_subset = np.zeros((len(selected_pos), METRICS_N_COLUMNS), dtype=np.float64)
    debug_fills_first_subset = None
    if return_debug:
        debug_fills_first_subset = np.full((len(selected_pos), 6), np.nan, dtype=np.float64)
    
    # Stage P2-3: Only loop selected params (param-subsample)
    # CURSOR TASK 1: Use selected_pos (sorted space) to access pm_sorted, selected_orig for scatter-back
    for subset_idx, pos in enumerate(selected_pos):
        # Initialize row for this iteration (will be written at loop end regardless of any continue/early exit)
        row = np.array([0.0, 0, 0.0], dtype=np.float64)
        
        # CURSOR TASK 1: Use pos (sorted space position) to access params_sorted
        ch = int(pm_sorted[pos, 0])
        atr = int(pm_sorted[pos, 1])
        sm = float(pm_sorted[pos, 2])

        # Stage P2-2 Step B3: Lookup precomputed indicators and create PrecomputedIndicators pack
        precomp_pack = PrecomputedIndicators(
            donch_hi=donch_cache_hi[ch],
            donch_lo=donch_cache_lo[ch],
            atr=atr_cache[atr],
        )

        # Stage P2-1.8: Kernel profiling is already enabled at function start if profile=True
        # No need to set FISHBRO_PROFILE_KERNEL here again
        out = run_kernel(
            bars,
            DonchianAtrParams(channel_len=ch, atr_len=atr, stop_mult=sm),
            commission=float(commission),
            slip=float(slip),
            order_qty=int(order_qty),
            return_debug=return_debug,
            precomp=precomp_pack,
            intent_sparse_rate=intent_sparse_rate,  # CURSOR TASK 3: Pass intent sparse rate
        )
        obs = out.get("_obs", None)  # type: ignore
        if isinstance(obs, dict):
            # Phase 3.0-B: Trust kernel's evidence fields, do not recompute
            if intent_mode is None and isinstance(obs.get("intent_mode"), str):
                intent_mode = str(obs.get("intent_mode"))
            # Use intents_total directly from kernel (Source of Truth), not recompute from entry+exit
            intents_total += int(obs.get("intents_total", 0))
            fills_total += int(obs.get("fills_total", 0))
            
            # CURSOR TASK 2: Accumulate entry_valid_mask_sum (after intent sparse)
            # entry_valid_mask_sum must be sum(allow_mask) - not dense valid bars, not multiplied by params
            if "entry_valid_mask_sum" in obs:
                entry_valid_mask_sum += int(obs.get("entry_valid_mask_sum", 0))
            elif "allowed_bars" in obs:
                # Fallback: use allowed_bars if entry_valid_mask_sum not present
                entry_valid_mask_sum += int(obs.get("allowed_bars", 0))
            # CURSOR TASK 2: entry_intents_total should come from obs["entry_intents_total"] (set by kernel)
            if "entry_intents_total" in obs:
                entry_intents_total += int(obs.get("entry_intents_total", 0))
            elif "entry_intents" in obs:
                # Fallback: use entry_intents if entry_intents_total not present
                entry_intents_total += int(obs.get("entry_intents", 0))
            elif "n_entry" in obs:
                # Fallback: use n_entry if entry_intents_total not present
                entry_intents_total += int(obs.get("n_entry", 0))
            # Capture n_bars from first kernel result (should be same for all params)
            if n_bars_for_entry_obs is None and "n_bars" in obs:
                n_bars_for_entry_obs = int(obs.get("n_bars", 0))
            
            # Stage P2-3: Accumulate sparse builder observability (from new builder_sparse)
            if "allowed_bars" in obs:
                allowed_bars_total += int(obs.get("allowed_bars", 0))
            if "intents_generated" in obs:
                intents_generated_total += int(obs.get("intents_generated", 0))
            elif "n_entry" in obs:
                # Fallback: if intents_generated not present, use n_entry
                intents_generated_total += int(obs.get("n_entry", 0))
            
            # Stage P2-1.8: Accumulate timing keys from _obs (timing is now in _obs, not _perf)
            # Timing keys have pattern: t_*_s
            for key, value in obs.items():
                if key.startswith("t_") and key.endswith("_s"):
                    if key not in perf:
                        perf[key] = 0.0
                    perf[key] = float(perf[key]) + float(value)
            
            # Stage P2-1.8: Accumulate downstream counts from _obs
            if "entry_fills_total" in obs:
                perf["entry_fills_total"] = int(perf.get("entry_fills_total", 0)) + int(obs.get("entry_fills_total", 0))
            if "exit_intents_total" in obs:
                perf["exit_intents_total"] = int(perf.get("exit_intents_total", 0)) + int(obs.get("exit_intents_total", 0))
            if "exit_fills_total" in obs:
                perf["exit_fills_total"] = int(perf.get("exit_fills_total", 0)) + int(obs.get("exit_fills_total", 0))
        
        # Stage P2-1.8: Fallback - also check _perf for backward compatibility
        # Handle cases where old kernel versions put timing in _perf instead of _obs
        # Only use fallback if _obs doesn't have timing keys
        obs_has_timing = isinstance(obs, dict) and any(k.startswith("t_") and k.endswith("_s") for k in obs.keys())
        if not obs_has_timing:
            kernel_perf = out.get("_perf", None)
            if isinstance(kernel_perf, dict):
                # Accumulate timings across params (for grid-level aggregation)
                # Note: For grid-level, we sum timings across params
                for key, value in kernel_perf.items():
                    if key.startswith("t_") and key.endswith("_s"):
                        if key not in perf:
                            perf[key] = 0.0
                        perf[key] = float(perf[key]) + float(value)

        # Get metrics from kernel output (always available, even if profile missing)
        m = out.get("metrics", {})
        if not isinstance(m, dict):
            # Fallback: kernel didn't return metrics dict, use zeros
            m_net_profit = 0.0
            m_trades = 0
            m_max_dd = 0.0
        else:
            m_net_profit = float(m.get("net_profit", 0.0))
            m_trades = int(m.get("trades", 0))
            m_max_dd = float(m.get("max_dd", 0.0))
            # Clean NaN/Inf at source
            m_net_profit = float(np.nan_to_num(m_net_profit, nan=0.0, posinf=0.0, neginf=0.0))
            m_max_dd = float(np.nan_to_num(m_max_dd, nan=0.0, posinf=0.0, neginf=0.0))
        
        # Get fills count for debug assert
        fills_this_param = out.get("fills", [])
        fills_count_this_param = len(fills_this_param) if isinstance(fills_this_param, list) else 0
        
        # Collect debug data if requested
        if return_debug:
            debug_info = out.get("_debug", {})
            entry_bar = debug_info.get("entry_bar", -1)
            entry_price = debug_info.get("entry_price", np.nan)
            exit_bar = debug_info.get("exit_bar", -1)
            exit_price = debug_info.get("exit_price", np.nan)
        
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
                    original_net_profit = m_net_profit
                    original_trades = m_trades
                    
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
                    
                    # Update row with forced close metrics
                    row = np.array([new_net_profit, new_trades, new_max_dd], dtype=np.float64)
                    
                    # Update debug subset with final metrics after force_close_last
                    if return_debug:
                        debug_fills_first_subset[subset_idx, 0] = entry_bar
                        debug_fills_first_subset[subset_idx, 1] = entry_price
                        debug_fills_first_subset[subset_idx, 2] = exit_bar
                        debug_fills_first_subset[subset_idx, 3] = exit_price
                        debug_fills_first_subset[subset_idx, 4] = new_net_profit
                        debug_fills_first_subset[subset_idx, 5] = float(new_trades)
                else:
                    # No unpaired entries, use original metrics
                    row = np.array([m_net_profit, m_trades, m_max_dd], dtype=np.float64)
                    
                    # Store debug data in subset
                    if return_debug:
                        debug_fills_first_subset[subset_idx, 0] = entry_bar
                        debug_fills_first_subset[subset_idx, 1] = entry_price
                        debug_fills_first_subset[subset_idx, 2] = exit_bar
                        debug_fills_first_subset[subset_idx, 3] = exit_price
                        debug_fills_first_subset[subset_idx, 4] = m_net_profit
                        debug_fills_first_subset[subset_idx, 5] = float(m_trades)
            else:
                # No fills, use original metrics
                row = np.array([m_net_profit, m_trades, m_max_dd], dtype=np.float64)
                
                # Store debug data in subset (no fills case)
                if return_debug:
                    debug_fills_first_subset[subset_idx, 0] = entry_bar
                    debug_fills_first_subset[subset_idx, 1] = entry_price
                    debug_fills_first_subset[subset_idx, 2] = exit_bar
                    debug_fills_first_subset[subset_idx, 3] = exit_price
                    debug_fills_first_subset[subset_idx, 4] = m_net_profit
                    debug_fills_first_subset[subset_idx, 5] = float(m_trades)
        else:
            # Zero-trade safe: kernel guarantees valid numbers (0.0/0)
            row = np.array([m_net_profit, m_trades, m_max_dd], dtype=np.float64)
            
            # Store debug data in subset
            if return_debug:
                debug_fills_first_subset[subset_idx, 0] = entry_bar
                debug_fills_first_subset[subset_idx, 1] = entry_price
                debug_fills_first_subset[subset_idx, 2] = exit_bar
                debug_fills_first_subset[subset_idx, 3] = exit_price
                debug_fills_first_subset[subset_idx, 4] = m_net_profit
                debug_fills_first_subset[subset_idx, 5] = float(m_trades)
        
        # HARD CONTRACT: Always write metrics_subset at loop end, regardless of any continue/early exit
        metrics_subset[subset_idx, :] = row
        
        # Debug assert: if trades > 0 (completed trades), metrics must be non-zero
        # Note: entry fills without exits yield trades=0 and all-zero metrics, which is valid
        if os.environ.get("FISHBRO_DEBUG_ASSERT", "").strip() == "1":
            if m_trades > 0:
                assert np.any(np.abs(metrics_subset[subset_idx, :]) > 0), (
                    f"subset_idx={subset_idx}: trades={m_trades} > 0, "
                    f"but metrics_subset[{subset_idx}, :]={metrics_subset[subset_idx, :]} is all zeros"
                )
        
        # Handle profile timing accumulation (after metrics written)
        if profile:
            kp = out.get("_profile", None)  # type: ignore
            if not isinstance(kp, dict):
                any_profile_missing = True
                # Continue after metrics already written
                continue
            t_ind += float(kp.get("indicators_s", 0.0))
            # include both entry+exit intent generation as "intent generation"
            t_intgen += float(kp.get("intent_gen_s", 0.0)) + float(kp.get("exit_intent_gen_s", 0.0))
            t_sim += float(kp.get("simulate_entry_s", 0.0)) + float(kp.get("simulate_exit_s", 0.0))
    
    # CURSOR TASK 2: Handle NaN before scatter-back (avoid computed_non_zero being eaten by NaN)
    # Note: Already handled at source (m_net_profit, m_max_dd), but double-check here for safety
    metrics_subset = np.nan_to_num(metrics_subset, nan=0.0, posinf=0.0, neginf=0.0)
    
    # CURSOR TASK 3: Assert that if fills_total > 0, metrics_subset should have non-zero values
    # This helps catch cases where metrics computation was skipped or returned zeros
    # Only assert if FISHBRO_DEBUG_ASSERT=1 (not triggered by profile, as tests often enable profile)
    if os.environ.get("FISHBRO_DEBUG_ASSERT", "").strip() == "1":
        metrics_subset_abs_sum = float(np.sum(np.abs(metrics_subset)))
        assert fills_total == 0 or metrics_subset_abs_sum > 0, (
            f"CURSOR TASK B violation: fills_total={fills_total} > 0 but metrics_subset_abs_sum={metrics_subset_abs_sum} == 0. "
            f"This indicates metrics computation was skipped or returned zeros."
        )
    
    # CURSOR TASK 3: Add perf debug field (metrics_subset_nonzero_rows)
    metrics_subset_nonzero_rows = int(np.sum(np.any(np.abs(metrics_subset) > 1e-10, axis=1)))
    perf["metrics_subset_nonzero_rows"] = metrics_subset_nonzero_rows
    
    # === HARD CONTRACT: scatter metrics back to original param space ===
    # CRITICAL: This must happen after all metrics computation and before any return
    # Variables: selected_pos (sorted-space index), order (sorted_pos -> original_index), metrics_subset (computed metrics)
    # For each selected param: metrics[orig_param_idx] must be written with non-zero values
    for subset_i, pos in enumerate(selected_pos):
        orig_i = int(order[int(pos)])
        metrics[orig_i, :] = metrics_subset[subset_i, :]
        
        if return_debug and debug_fills_first is not None and debug_fills_first_subset is not None:
            debug_fills_first[orig_i, :] = debug_fills_first_subset[subset_i, :]
    
    # CRITICAL: After scatter-back, metrics must not be modified (no metrics = np.zeros, no metrics[:] = 0, no result["metrics"] = metrics_subset)
    
    # CURSOR TASK 2: Add perf debug fields (for diagnostic)
    perf["intent_sparse_rate_effective"] = float(intent_sparse_rate)
    perf["fills_total"] = int(fills_total)
    perf["metrics_subset_abs_sum"] = float(np.sum(np.abs(metrics_subset)))
    
    # CURSOR TASK A: Add entry_intents_total (subsample run) for diagnostic
    # This helps distinguish: entry_intents_total > 0 but fills_total == 0 → matcher/engine issue
    # vs entry_intents_total == 0 → builder didn't generate intents
    perf["entry_intents_total"] = int(entry_intents_total)

    # Phase 3.0-E: Ensure intent_mode is never None
    # If no kernel results (n == 0), default to "arrays" (default kernel path)
    # Otherwise, intent_mode should have been set from first kernel result
    if intent_mode is None:
        # Edge case: n == 0 (no params) - use default "arrays" since run_kernel defaults to array path
        intent_mode = "arrays"

    if not profile:
        # Return minimal perf with evidence fields only
        # Stage P2-1.8: Preserve accumulated timings (already in perf dict from loop)
        perf["intent_mode"] = intent_mode
        perf["intents_total"] = int(intents_total)
        # fills_total already set in scatter-back section (line 592), but ensure it's here too for clarity
        if "fills_total" not in perf:
            perf["fills_total"] = int(fills_total)
        # CURSOR TASK 3: Add intent sparse rate and entry observability to perf
        perf["intent_sparse_rate"] = float(intent_sparse_rate)
        perf["entry_valid_mask_sum"] = int(entry_valid_mask_sum)  # CURSOR TASK 2: After intent sparse (sum(allow_mask))
        perf["entry_intents_total"] = int(entry_intents_total)
        
        # Stage P2-1.5: Add entry sparse observability (always include, even if 0)
        perf["intents_total_reported"] = int(intents_total)  # Preserve original for comparison
        if n_bars_for_entry_obs is not None and n_bars_for_entry_obs > 0:
            perf["entry_intents_per_bar_avg"] = float(entry_intents_total / n_bars_for_entry_obs)
        else:
            # Fallback: use bars.open.shape[0] if n_bars_for_entry_obs not available
            perf["entry_intents_per_bar_avg"] = float(entry_intents_total / max(1, bars.open.shape[0]))
        
        # Stage P2-3: Add sparse builder observability (for scaling verification)
        perf["allowed_bars"] = int(allowed_bars_total)
        perf["intents_generated"] = int(intents_generated_total)
        perf["selected_params"] = int(selected_params_count)
        
        # CURSOR TASK 2: Ensure debug fields are present in non-profile branch too
        if "intent_sparse_rate_effective" not in perf:
            perf["intent_sparse_rate_effective"] = float(intent_sparse_rate)
        if "fills_total" not in perf:
            perf["fills_total"] = int(fills_total)
        if "metrics_subset_abs_sum" not in perf:
            perf["metrics_subset_abs_sum"] = float(np.sum(np.abs(metrics_subset)))
        
        result["perf"] = perf
        if return_debug and debug_fills_first is not None:
            result["debug_fills_first"] = debug_fills_first
        return result

    from engine import engine_jit

    jt = engine_jit.get_jit_truth()
    numba_env = os.environ.get("NUMBA_DISABLE_JIT", "")
    sigs = jt.get("kernel_signatures") or []

    # Best-effort: avoid leaking this env to callers
    # Only clean up if we set it ourselves (Task A: bridge logic)
    if _set_kernel_profile:
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

    # Stage P2-1.8: Create summary dict and merge into accumulated perf (preserve t_*_s from loop)
    perf_summary = {
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
    
    # CURSOR TASK 3: Add intent sparse rate and entry observability to perf
    perf_summary["intent_sparse_rate"] = float(intent_sparse_rate)
    perf_summary["entry_valid_mask_sum"] = int(entry_valid_mask_sum)  # CURSOR TASK 2: After intent sparse
    perf_summary["entry_intents_total"] = int(entry_intents_total)
    
    # Stage P2-1.5: Add entry sparse observability and preserve original intents_total
    perf_summary["intents_total_reported"] = int(intents_total)  # Preserve original for comparison
    if n_bars_for_entry_obs is not None and n_bars_for_entry_obs > 0:
        perf_summary["entry_intents_per_bar_avg"] = float(entry_intents_total / n_bars_for_entry_obs)
    else:
        # Fallback: use bars.open.shape[0] if n_bars_for_entry_obs not available
        perf_summary["entry_intents_per_bar_avg"] = float(entry_intents_total / max(1, bars.open.shape[0]))
    
    # Stage P2-3: Add sparse builder observability (for scaling verification)
    perf_summary["allowed_bars"] = int(allowed_bars_total)  # Total allowed bars across all params
    perf_summary["intents_generated"] = int(intents_generated_total)  # Total intents generated across all params
    perf_summary["selected_params"] = int(selected_params_count)  # Number of params actually computed
    
    # CURSOR TASK 2: Ensure debug fields are present in profile branch too
    perf_summary["intent_sparse_rate_effective"] = float(intent_sparse_rate)
    perf_summary["fills_total"] = int(fills_total)
    perf_summary["metrics_subset_abs_sum"] = float(np.sum(np.abs(metrics_subset)))
    
    # Keep accumulated per-kernel timings already stored in `perf` (t_*_s, entry_fills_total, etc.)
    perf.update(perf_summary)

    result["perf"] = perf
    if return_debug and debug_fills_first is not None:
        result["debug_fills_first"] = debug_fills_first
    return result



