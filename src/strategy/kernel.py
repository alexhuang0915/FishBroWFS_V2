
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import os
import time

from engine.constants import KIND_STOP, ROLE_ENTRY, ROLE_EXIT, SIDE_BUY, SIDE_SELL
from engine.engine_jit import simulate as simulate_matcher
from engine.engine_jit import simulate_arrays as simulate_matcher_arrays
from engine.metrics_from_fills import compute_metrics_from_fills
from engine.engine_types import BarArrays, Fill, OrderIntent, OrderKind, OrderRole, Side
from indicators.numba_indicators import rolling_max, rolling_min, atr_wilder


# Stage P2-2 Step B1: Precomputed Indicators Pack
@dataclass(frozen=True)
class PrecomputedIndicators:
    """
    Pre-computed indicator arrays for shared computation optimization.
    
    These arrays are computed once per unique (channel_len, atr_len) combination
    and reused across multiple params to avoid redundant computation.
    """
    donch_hi: np.ndarray  # float64, shape (n_bars,) - Donchian high (rolling max)
    donch_lo: np.ndarray  # float64, shape (n_bars,) - Donchian low (rolling min)
    atr: np.ndarray       # float64, shape (n_bars,) - ATR Wilder


def _build_entry_intents_from_trigger(
    donch_prev: np.ndarray,
    channel_len: int,
    order_qty: int,
) -> Dict[str, object]:
    """
    Build entry intents from trigger array with sparse masking (Stage P2-1).
    
    Args:
        donch_prev: float64 array (n_bars,) - shifted donchian high (donch_prev[0]=NaN, donch_prev[1:]=donch_hi[:-1])
        channel_len: warmup period (same as indicator warmup)
        order_qty: order quantity
    
    Returns:
        dict with:
            - created_bar: int32 array (n_entry,) - created bar indices
            - price: float64 array (n_entry,) - entry prices
            - order_id: int32 array (n_entry,) - order IDs
            - role: uint8 array (n_entry,) - role (ENTRY)
            - kind: uint8 array (n_entry,) - kind (STOP)
            - side: uint8 array (n_entry,) - side (BUY)
            - qty: int32 array (n_entry,) - quantities
            - n_entry: int - number of entry intents
            - obs: dict - diagnostic observations
    """
    from config.dtypes import (
        INDEX_DTYPE,
        INTENT_ENUM_DTYPE,
        INTENT_PRICE_DTYPE,
    )
    
    n = int(donch_prev.shape[0])
    warmup = channel_len
    
    # Create index array for bars 1..n-1 (bar indices t, where created_bar = t-1)
    # i represents bar index t (from 1 to n-1)
    i = np.arange(1, n, dtype=INDEX_DTYPE)
    
    # Sparse mask: valid entries must be finite and past warmup
    # Check donch_prev[t] for each bar t in range(1, n)
    # Removed >0 check to match object-mode behavior (only NaN filter)
    valid_mask = (~np.isnan(donch_prev[1:])) & (i >= warmup)
    
    # Get indices of valid entries (flatnonzero returns indices into donch_prev[1:])
    # idx is 0-indexed into donch_prev[1:], so idx=0 corresponds to bar t=1
    idx = np.flatnonzero(valid_mask).astype(INDEX_DTYPE)
    
    n_entry = int(idx.shape[0])
    
    # CURSOR TASK 2: entry_valid_mask_sum must be sum(allow_mask) - for dense builder, it equals valid_mask_sum
    # Diagnostic observations
    obs = {
        "n_bars": n,
        "warmup": warmup,
        "valid_mask_sum": int(np.sum(valid_mask)),  # Dense valid bars (before trigger rate)
        "entry_valid_mask_sum": int(np.sum(valid_mask)),  # CURSOR TASK 2: For dense builder, equals valid_mask_sum
    }
    
    if n_entry == 0:
        return {
            "created_bar": np.empty(0, dtype=INDEX_DTYPE),
            "price": np.empty(0, dtype=INTENT_PRICE_DTYPE),
            "order_id": np.empty(0, dtype=INDEX_DTYPE),
            "role": np.empty(0, dtype=INTENT_ENUM_DTYPE),
            "kind": np.empty(0, dtype=INTENT_ENUM_DTYPE),
            "side": np.empty(0, dtype=INTENT_ENUM_DTYPE),
            "qty": np.empty(0, dtype=INDEX_DTYPE),
            "n_entry": 0,
            "obs": obs,
        }
    
    # Stage P2-3A: Gather sparse entries (only for valid_mask == True positions)
    # - idx is index into donch_prev[1:], so bar index t = idx + 1
    # - created_bar = t - 1 = idx (since t = idx + 1)
    # - price = donch_prev[t] = donch_prev[idx + 1] = donch_prev[1:][idx]
    # created_bar is already sorted (ascending) because idx comes from flatnonzero on sorted mask
    created_bar = idx.astype(INDEX_DTYPE)  # created_bar = t-1 = idx (when t = idx+1)
    price = donch_prev[1:][idx].astype(INTENT_PRICE_DTYPE)  # Gather from donch_prev[1:]
    
    # Stage P2-3A: Order ID maintains deterministic ordering
    # Order ID is sequential (1, 2, 3, ...) based on created_bar order
    # Since created_bar is already sorted, this preserves deterministic ordering
    order_id = np.arange(1, n_entry + 1, dtype=INDEX_DTYPE)
    role = np.full(n_entry, ROLE_ENTRY, dtype=INTENT_ENUM_DTYPE)
    kind = np.full(n_entry, KIND_STOP, dtype=INTENT_ENUM_DTYPE)
    side = np.full(n_entry, SIDE_BUY, dtype=INTENT_ENUM_DTYPE)
    qty = np.full(n_entry, int(order_qty), dtype=INDEX_DTYPE)
    
    return {
        "created_bar": created_bar,
        "price": price,
        "order_id": order_id,
        "role": role,
        "kind": kind,
        "side": side,
        "qty": qty,
        "n_entry": n_entry,
        "obs": obs,
    }


@dataclass(frozen=True)
class DonchianAtrParams:
    channel_len: int
    atr_len: int
    stop_mult: float


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


def run_kernel_object_mode(
    bars: BarArrays,
    params: DonchianAtrParams,
    *,
    commission: float,
    slip: float,
    order_qty: int = 1,
    precomp: Optional[PrecomputedIndicators] = None,
) -> Dict[str, object]:
    """
    Golden Kernel (GKV): single-source-of-truth kernel for Phase 3A and future Phase 3B.

    Strategy (minimal):
      - Entry: Buy Stop at Donchian High (rolling max of HIGH over channel_len) at bar close -> next bar active.
      - Exit: Sell Stop at (entry_fill_price - stop_mult * ATR_wilder) active from next bar after entry_fill.

    Costs:
      - commission (absolute per trade)
      - slip (absolute per trade)
      Costs are applied on each round-trip fill (entry and exit each incur cost).

    Returns:
      dict with:
        - fills: List[Fill]
        - pnl: np.ndarray (float64, per-round-trip pnl, can be empty)
        - equity: np.ndarray (float64, cumsum of pnl, can be empty)
        - metrics: dict (net_profit, trades, max_dd)
    """
    profile = os.environ.get("FISHBRO_PROFILE_KERNEL", "").strip() == "1"
    t0 = time.perf_counter() if profile else 0.0

    # --- Compute indicators (kernel level; wrapper must ensure contiguous arrays) ---
    ch = int(params.channel_len)
    atr_n = int(params.atr_len)
    stop_mult = float(params.stop_mult)

    if ch <= 0 or atr_n <= 0:
        # invalid params -> zero trades, deterministic
        pnl = np.empty(0, dtype=np.float64)
        equity = np.empty(0, dtype=np.float64)
        # Evidence fields (Source of Truth) - Phase 3.0-A: must not be null
        # Red Team requirement: if fallback to objects mode, must leave fingerprint
        return {
            "fills": [],
            "pnl": pnl,
            "equity": equity,
            "metrics": {"net_profit": 0.0, "trades": 0, "max_dd": 0.0},
            "_obs": {
                "intent_mode": "objects",
                "intents_total": 0,
                "fills_total": 0,
            },
        }

    # Stage P2-2 Step B2: Use precomputed indicators if available, otherwise compute
    if precomp is not None:
        donch_hi = precomp.donch_hi
        atr = precomp.atr
    else:
        donch_hi = rolling_max(bars.high, ch)  # includes current bar
        atr = atr_wilder(bars.high, bars.low, bars.close, atr_n)
    t_ind = time.perf_counter() if profile else 0.0

    # --- Build order intents (next-bar active) ---
    intents: List[OrderIntent] = []
    # CURSOR TASK 5: Use deterministic order ID generation (pure function)
    from engine.order_id import generate_order_id

    # We create entry intents for each bar t where indicator exists:
    # created_bar=t, active at t+1. price=donch_hi[t]
    n = int(bars.open.shape[0])
    for t in range(n):
        px = float(donch_hi[t])
        if np.isnan(px):
            continue
        # CURSOR TASK 5: Generate deterministic order_id
        oid = generate_order_id(
            created_bar=t,
            param_idx=0,  # Single param kernel
            role=ROLE_ENTRY,
            kind=KIND_STOP,
            side=SIDE_BUY,
        )
        intents.append(
            OrderIntent(
                order_id=oid,
                created_bar=t,
                role=OrderRole.ENTRY,
                kind=OrderKind.STOP,
                side=Side.BUY,
                price=px,
                qty=order_qty,
            )
        )
    t_intents = time.perf_counter() if profile else 0.0

    # Run matcher (JIT or python via kill-switch)
    fills: List[Fill] = simulate_matcher(bars, intents)
    t_sim1 = time.perf_counter() if profile else 0.0

    # --- Convert fills -> round-trip pnl (vectorized style, no python trade loops as truth) ---
    # For this minimal kernel we assume:
    # - Only LONG trades (BUY entry, SELL exit) will be produced once we add exits.
    # Phase 3A GKV: We implement exits by post-processing: when entry fills, schedule a sell stop from next bar.
    # To preserve Homology, we do a second matcher pass with generated exit intents.
    # This keeps all fill semantics inside the matcher (constitution).
    exit_intents: List[OrderIntent] = []
    for f in fills:
        if f.role != OrderRole.ENTRY:
            continue
        # exit stop price = entry_price - stop_mult * atr at entry bar
        ebar = int(f.bar_index)
        if ebar < 0 or ebar >= n:
            continue
        a = float(atr[ebar])
        if np.isnan(a):
            continue
        stop_px = float(f.price - stop_mult * a)
        # CURSOR TASK 5: Generate deterministic order_id for exit
        exit_oid = generate_order_id(
            created_bar=ebar,
            param_idx=0,  # Single param kernel
            role=ROLE_EXIT,
            kind=KIND_STOP,
            side=SIDE_SELL,
        )
        exit_intents.append(
            OrderIntent(
                order_id=exit_oid,
                created_bar=ebar,  # active next bar
                role=OrderRole.EXIT,
                kind=OrderKind.STOP,
                side=Side.SELL,
                price=stop_px,
                qty=order_qty,
            )
        )
    t_exit_intents = time.perf_counter() if profile else 0.0

    if exit_intents:
        fills2 = simulate_matcher(bars, exit_intents)
        t_sim2 = time.perf_counter() if profile else 0.0
        fills_all = fills + fills2
        # deterministic order: sort by (bar_index, role(ENTRY first), kind, order_id)
        fills_all.sort(key=lambda x: (x.bar_index, 0 if x.role == OrderRole.ENTRY else 1, 0 if x.kind == OrderKind.STOP else 1, x.order_id))
    else:
        fills_all = fills
        t_sim2 = t_sim1 if profile else 0.0

    # CURSOR TASK 1: Compute metrics from fills (unified source of truth)
    net_profit, trades, max_dd, equity = compute_metrics_from_fills(
        fills=fills_all,
        commission=commission,
        slip=slip,
        qty=order_qty,
    )
    
    # For backward compatibility, compute pnl array from equity (if needed)
    if equity.size > 0:
        pnl = np.diff(np.concatenate([[0.0], equity]))
    else:
        pnl = np.empty(0, dtype=np.float64)
    
    metrics = {
        "net_profit": net_profit,
        "trades": trades,
        "max_dd": max_dd,
    }
    out = {"fills": fills_all, "pnl": pnl, "equity": equity, "metrics": metrics}

    # Evidence fields (Source of Truth) - Phase 3.0-A
    # Red Team requirement: if fallback to objects mode, must leave fingerprint
    intents_total = int(len(intents) + len(exit_intents))  # Total intents (entry + exit, merged)
    fills_total = int(len(fills_all))  # fills_all is List[Fill], use len()
    
    # Always-on observability payload (no timing assumptions).
    out["_obs"] = {
        "intent_mode": "objects",
        "intents_total": intents_total,
        "fills_total": fills_total,
        "entry_intents": int(len(intents)),
        "exit_intents": int(len(exit_intents)),
    }

    if profile:
        out["_profile"] = {
            "intent_mode": "objects",
            "indicators_s": float(t_ind - t0),
            "intent_gen_s": float(t_intents - t_ind),
            "simulate_entry_s": float(t_sim1 - t_intents),
            "exit_intent_gen_s": float(t_exit_intents - t_sim1),
            "simulate_exit_s": float(t_sim2 - t_exit_intents),
            "kernel_total_s": float(t_sim2 - t0),
            "entry_intents": int(len(intents)),
            "exit_intents": int(len(exit_intents)),
        }
    return out


def run_kernel_arrays(
    bars: BarArrays,
    params: DonchianAtrParams,
    *,
    commission: float,
    slip: float,
    order_qty: int = 1,
    return_debug: bool = False,
    precomp: Optional[PrecomputedIndicators] = None,
    intent_sparse_rate: float = 1.0,  # CURSOR TASK 3: Intent sparse rate from grid
) -> Dict[str, object]:
    """
    Array/SoA intent mode: generates intents as arrays and calls engine_jit.simulate_arrays().
    This avoids OrderIntent object construction in the hot path.
    
    Args:
        precomp: Optional pre-computed indicators. If provided, skips indicator computation
                 and uses precomputed arrays. If None, computes indicators normally (backward compatible).
    """
    profile = os.environ.get("FISHBRO_PROFILE_KERNEL", "").strip() == "1"
    t0 = time.perf_counter() if profile else 0.0
    
    # Stage P2-1.8: Initialize granular timers for breakdown
    from perf.timers import PerfTimers
    timers = PerfTimers()
    timers.start("t_total_kernel")
    
    # Task 1A: Define required timing keys (contract enforcement)
    REQUIRED_TIMING_KEYS = (
        "t_calc_indicators_s",
        "t_build_entry_intents_s",
        "t_simulate_entry_s",
        "t_calc_exits_s",
        "t_simulate_exit_s",
        "t_total_kernel_s",
    )

    ch = int(params.channel_len)
    atr_n = int(params.atr_len)
    stop_mult = float(params.stop_mult)

    if ch <= 0 or atr_n <= 0:
        timers.stop("t_total_kernel")
        timing_dict = timers.as_dict_seconds()
        # Task 1B: Ensure all required timing keys exist (setdefault 0.0)
        for k in REQUIRED_TIMING_KEYS:
            timing_dict.setdefault(k, 0.0)
        pnl = np.empty(0, dtype=np.float64)
        equity = np.empty(0, dtype=np.float64)
        # Evidence fields (Source of Truth) - Phase 3.0-A: must not be null
        # Task 1C: Fix early return - inject timing_dict into _obs
        result = {
            "fills": [],
            "pnl": pnl,
            "equity": equity,
            "metrics": {"net_profit": 0.0, "trades": 0, "max_dd": 0.0},
            "_obs": {
                "intent_mode": "arrays",
                "intents_total": 0,
                "fills_total": 0,
                "entry_intents_total": 0,
                "entry_fills_total": 0,
                "exit_intents_total": 0,
                "exit_fills_total": 0,
                **timing_dict,  # Task 1C: Include timing keys in _obs
            },
            "_perf": timing_dict,
        }
        return result

    # Stage P2-2 Step B2: Use precomputed indicators if available, otherwise compute
    if precomp is not None:
        # Use precomputed indicators (skip computation, timing will be ~0)
        donch_hi = precomp.donch_hi
        donch_lo = precomp.donch_lo
        atr = precomp.atr
        # Still record timing (will be ~0 since we skipped computation)
        timers.start("t_ind_donchian")
        timers.stop("t_ind_donchian")
        timers.start("t_ind_atr")
        timers.stop("t_ind_atr")
    else:
        # Stage P2-2 Step A: Micro-profiling - Split indicators timing
        # t_ind_donchian_s: Donchian rolling max/min (highest/lowest)
        timers.start("t_ind_donchian")
        donch_hi = rolling_max(bars.high, ch)
        donch_lo = rolling_min(bars.low, ch)  # Also compute low for consistency
        timers.stop("t_ind_donchian")
        
        # t_ind_atr_s: ATR Wilder (TR + RMA/ATR)
        timers.start("t_ind_atr")
        atr = atr_wilder(bars.high, bars.low, bars.close, atr_n)
        timers.stop("t_ind_atr")
    
    t_ind = time.perf_counter() if profile else 0.0

    # Stage P2-1.8: t_build_entry_intents_s - Build entry intents (shift, mask, build)
    timers.start("t_build_entry_intents")
    # Fix 2: Shift donchian for next-bar active (created_bar = t-1, price = donch_hi[t-1])
    # Entry orders generated at bar t-1 close, active at bar t, stop price = donch_hi[t-1]
    donch_prev = np.empty_like(donch_hi)
    donch_prev[0] = np.nan
    donch_prev[1:] = donch_hi[:-1]

    # Stage P2-3A: Check if we should use Numba-accelerated sparse builder
    use_numba_builder = os.environ.get("FISHBRO_FORCE_SPARSE_BUILDER", "").strip() == "1"
    
    # CURSOR TASK 3: Use intent_sparse_rate from grid (passed as parameter)
    # Fallback to env var if not provided (for backward compatibility)
    trigger_rate = intent_sparse_rate
    if trigger_rate == 1.0:  # Only check env if not explicitly passed
        trigger_rate_env = os.environ.get("FISHBRO_PERF_TRIGGER_RATE", "").strip()
        if trigger_rate_env:
            try:
                trigger_rate = float(trigger_rate_env)
                if not (0.0 <= trigger_rate <= 1.0):
                    trigger_rate = 1.0
            except ValueError:
                trigger_rate = 1.0
    
    # Debug instrumentation: track first entry/exit per param (only if return_debug=True)
    if return_debug:
        dbg_entry_bar = -1
        dbg_entry_price = np.nan
        dbg_exit_bar = -1
        dbg_exit_price = np.nan
    else:
        dbg_entry_bar = None
        dbg_entry_price = None
        dbg_exit_bar = None
        dbg_exit_price = None

    # Build entry intents (choose builder based on env flags)
    use_dense_builder = os.environ.get("FISHBRO_USE_DENSE_BUILDER", "").strip() == "1"
    
    if use_numba_builder:
        # Stage P2-3A: Use Numba-accelerated sparse builder (trigger_rate integrated)
        from strategy.entry_builder_nb import build_entry_intents_numba
        entry_intents_result = build_entry_intents_numba(
            donch_prev=donch_prev,
            channel_len=ch,
            order_qty=order_qty,
            trigger_rate=trigger_rate,
            seed=42,  # Fixed seed for deterministic selection
        )
        entry_builder_impl = "numba_single_pass"
    elif use_dense_builder:
        # Reference dense builder (for comparison/testing)
        entry_intents_result = _build_entry_intents_from_trigger(
            donch_prev=donch_prev,
            channel_len=ch,
            order_qty=order_qty,
        )
        entry_builder_impl = "python_dense_reference"
    else:
        # Default: Use new sparse builder (supports trigger_rate natively)
        from strategy.builder_sparse import build_intents_sparse
        entry_intents_result = build_intents_sparse(
            donch_prev=donch_prev,
            channel_len=ch,
            order_qty=order_qty,
            trigger_rate=trigger_rate,  # CURSOR TASK 3: Use intent_sparse_rate
            seed=42,  # Fixed seed for deterministic selection
            use_dense=False,  # Use sparse mode (default)
        )
        entry_builder_impl = "python_sparse_default"
    timers.stop("t_build_entry_intents")
    
    created_bar = entry_intents_result["created_bar"]
    price = entry_intents_result["price"]
    # CURSOR TASK 5: Use deterministic order ID generation (pure function)
    # Override order_id from builder with deterministic version
    from engine.order_id import generate_order_ids_array
    order_id = generate_order_ids_array(
        created_bar=created_bar,
        param_idx=0,  # Single param kernel (param_idx not available here)
        role=entry_intents_result.get("role"),
        kind=entry_intents_result.get("kind"),
        side=entry_intents_result.get("side"),
    )
    role = entry_intents_result["role"]
    kind = entry_intents_result["kind"]
    side = entry_intents_result["side"]
    qty = entry_intents_result["qty"]
    n_entry = entry_intents_result["n_entry"]
    obs_extra = entry_intents_result["obs"]
    
    # Stage P2-3A: Add builder implementation info to obs
    obs_extra = dict(obs_extra)  # Ensure mutable
    obs_extra["entry_builder_impl"] = entry_builder_impl
    
    if n_entry == 0:
        # No valid entry intents
        timers.stop("t_total_kernel")
        timing_dict = timers.as_dict_seconds()
        # Task 1B: Ensure all required timing keys exist (setdefault 0.0)
        for k in REQUIRED_TIMING_KEYS:
            timing_dict.setdefault(k, 0.0)
        pnl = np.empty(0, dtype=np.float64)
        equity = np.empty(0, dtype=np.float64)
        metrics = {"net_profit": 0.0, "trades": 0, "max_dd": 0.0}
        intents_total = 0
        fills_total = 0
        
        # CURSOR TASK 1: Set intents_total = entry_intents_total + exit_intents_total (accounting consistency)
        entry_intents_total_val = int(n_entry)  # 0 in this case
        exit_intents_total_val = 0  # No exit intents when n_entry == 0
        intents_total = entry_intents_total_val + exit_intents_total_val  # CURSOR TASK 1: Always sum
        
        # CURSOR TASK 4: Get entry_valid_mask_sum for MVP contract (bar-level indicator)
        entry_valid_mask_sum = int(obs_extra.get("entry_valid_mask_sum", obs_extra.get("valid_mask_sum", 0)))
        n_bars_val = int(obs_extra.get("n_bars", bars.open.shape[0]))
        warmup_val = int(obs_extra.get("warmup", ch))
        valid_mask_sum_val = int(obs_extra.get("valid_mask_sum", entry_valid_mask_sum))
        
        result = {
            "fills": [],
            "pnl": pnl,
            "equity": equity,
            "metrics": metrics,
            "_obs": {
                "intent_mode": "arrays",
                "intents_total": intents_total,  # CURSOR TASK 1: entry_intents_total + exit_intents_total
                "intents_total_reported": intents_total,  # Same as intents_total (0 in this case)
                "fills_total": fills_total,
                "entry_intents_total": entry_intents_total_val,  # CURSOR TASK 4: Required key
                "exit_intents_total": exit_intents_total_val,  # CURSOR TASK 1: Required for accounting consistency
                "entry_fills_total": 0,
                "exit_fills_total": 0,
                "n_bars": n_bars_val,  # CURSOR TASK 4: Required key
                "warmup": warmup_val,  # CURSOR TASK 4: Required key
                "valid_mask_sum": valid_mask_sum_val,  # CURSOR TASK 4: Required key
                "entry_valid_mask_sum": entry_valid_mask_sum,  # CURSOR TASK 4: Required key
                **obs_extra,  # Include diagnostic observations from entry intent builder
                **timing_dict,  # Stage P2-1.8: Include timing keys in _obs
            },
            "_perf": timing_dict,  # Keep _perf for backward compatibility
        }
        if return_debug:
            result["_debug"] = {
                "entry_bar": dbg_entry_bar,
                "entry_price": dbg_entry_price,
                "exit_bar": dbg_exit_bar,
                "exit_price": dbg_exit_price,
            }
        
        # --- P2-1.6 Observability alias (kernel-native) ---
        obs = result.setdefault("_obs", {})
        # Canonical entry sparse keys expected by perf/tests
        # CURSOR TASK 2: entry_valid_mask_sum should come from obs_extra (builder), not valid_mask_sum
        if "entry_valid_mask_sum" not in obs:
            obs.setdefault("entry_valid_mask_sum", int(obs.get("entry_valid_mask_sum", 0)))
        # entry_intents_total should already be set above (n_entry = 0 in this case)
        if "entry_intents_total" not in obs:
            obs["entry_intents_total"] = int(n_entry)
        
        return result

    # Arrays are already built by _build_entry_intents_from_trigger
    t_intents = time.perf_counter() if profile else 0.0

    # CURSOR TASK 2: Simulate entry intents first (parity with object-mode)
    # This ensures exit intents are only generated after entry fills occur
    timers.start("t_simulate_entry")
    entry_fills: List[Fill] = simulate_matcher_arrays(
        bars,
        order_id=order_id,
        created_bar=created_bar,
        role=role,
        kind=kind,
        side=side,
        price=price,
        qty=qty,
        ttl_bars=1,
    )
    timers.stop("t_simulate_entry")
    t_sim1 = time.perf_counter() if profile else 0.0

    # CURSOR TASK 2: Build exit intents from entry fills (not from entry intents)
    # This matches object-mode behavior: exit intents only generated after entry fills
    timers.start("t_calc_exits")
    from config.dtypes import (
        INDEX_DTYPE,
        INTENT_ENUM_DTYPE,
        INTENT_PRICE_DTYPE,
    )
    
    # Build exit intents for each entry fill (parity with object-mode)
    exit_intents_list = []
    n_bars = int(bars.open.shape[0])
    for f in entry_fills:
        if f.role != OrderRole.ENTRY or f.side != Side.BUY:
            continue
        ebar = int(f.bar_index)
        if ebar < 0 or ebar >= n_bars:
            continue
        # Get ATR at entry fill bar
        atr_e = float(atr[ebar])
        if np.isnan(atr_e):
            # Invalid ATR (NaN): skip this entry (no exit intent)
            # Match object-mode behavior (only check NaN, not <= 0)
            continue
        # Compute exit stop price from entry fill price
        exit_stop = float(f.price - stop_mult * atr_e)
        exit_intents_list.append({
            "created_bar": ebar,  # Same as entry fill bar (allows same-bar entry then exit)
            "price": exit_stop,
        })
    
    exit_intents_count = len(exit_intents_list)
    timers.stop("t_calc_exits")
    t_exit_intents = time.perf_counter() if profile else 0.0

    # CURSOR TASK 2 & 3: Simulate exit intents, then merge fills
    # Sort intents properly (created_bar, order_id) before simulate
    timers.start("t_simulate_exit")
    if exit_intents_count > 0:
        # Build exit intent arrays
        exit_created = np.asarray([ei["created_bar"] for ei in exit_intents_list], dtype=INDEX_DTYPE)
        exit_price = np.asarray([ei["price"] for ei in exit_intents_list], dtype=INTENT_PRICE_DTYPE)
        # CURSOR TASK 5: Use deterministic order ID generation for exit intents
        from engine.order_id import generate_order_id
        exit_order_id_list = []
        for i, ebar in enumerate(exit_created):
            exit_oid = generate_order_id(
                created_bar=int(ebar),
                param_idx=0,  # Single param kernel
                role=ROLE_EXIT,
                kind=KIND_STOP,
                side=SIDE_SELL,
            )
            exit_order_id_list.append(exit_oid)
        exit_order_id = np.asarray(exit_order_id_list, dtype=INDEX_DTYPE)
        exit_role = np.full(exit_intents_count, ROLE_EXIT, dtype=INTENT_ENUM_DTYPE)
        exit_kind = np.full(exit_intents_count, KIND_STOP, dtype=INTENT_ENUM_DTYPE)
        exit_side = np.full(exit_intents_count, SIDE_SELL, dtype=INTENT_ENUM_DTYPE)
        exit_qty = np.full(exit_intents_count, int(order_qty), dtype=INDEX_DTYPE)
        
        # CURSOR TASK 3: Sort exit intents by created_bar, then order_id
        exit_sort_idx = np.lexsort((exit_order_id, exit_created))
        exit_order_id = exit_order_id[exit_sort_idx]
        exit_created = exit_created[exit_sort_idx]
        exit_price = exit_price[exit_sort_idx]
        exit_role = exit_role[exit_sort_idx]
        exit_kind = exit_kind[exit_sort_idx]
        exit_side = exit_side[exit_sort_idx]
        exit_qty = exit_qty[exit_sort_idx]
        
        # Simulate exit intents
        exit_fills: List[Fill] = simulate_matcher_arrays(
            bars,
            order_id=exit_order_id,
            created_bar=exit_created,
            role=exit_role,
            kind=exit_kind,
            side=exit_side,
            price=exit_price,
            qty=exit_qty,
            ttl_bars=1,
        )
        
        # Merge entry and exit fills, sort by (bar_index, role, kind, order_id)
        fills_all = entry_fills + exit_fills
        fills_all.sort(
            key=lambda x: (
                x.bar_index,
                0 if x.role == OrderRole.ENTRY else 1,
                0 if x.kind == OrderKind.STOP else 1,
                x.order_id,
            )
        )
    else:
        fills_all = entry_fills
    
    timers.stop("t_simulate_exit")
    t_sim2 = time.perf_counter() if profile else 0.0
    
    # Count entry and exit fills
    entry_fills_count = sum(1 for f in entry_fills if f.role == OrderRole.ENTRY and f.side == Side.BUY)
    if exit_intents_count > 0:
        exit_fills_count = sum(1 for f in fills_all if f.role == OrderRole.EXIT and f.side == Side.SELL)
    else:
        exit_fills_count = 0

    # Capture first entry fill for debug
    if return_debug and len(fills_all) > 0:
        first_entry = None
        for f in fills_all:
            if f.role == OrderRole.ENTRY and f.side == Side.BUY:
                first_entry = f
                break
        if first_entry is not None:
            dbg_entry_bar = int(first_entry.bar_index)
            dbg_entry_price = float(first_entry.price)

    # Capture first exit fill for debug
    if return_debug and len(fills_all) > 0:
        first_exit = None
        for f in fills_all:
            if f.role == OrderRole.EXIT and f.side == Side.SELL:
                first_exit = f
                break
        if first_exit is not None:
            dbg_exit_bar = int(first_exit.bar_index)
            dbg_exit_price = float(first_exit.price)

    # CURSOR TASK 1: Compute metrics from fills (unified source of truth)
    net_profit, trades, max_dd, equity = compute_metrics_from_fills(
        fills=fills_all,
        commission=commission,
        slip=slip,
        qty=order_qty,
    )
    
    # For backward compatibility, compute pnl array from equity (if needed)
    if equity.size > 0:
        pnl = np.diff(np.concatenate([[0.0], equity]))
    else:
        pnl = np.empty(0, dtype=np.float64)
    
    metrics = {
        "net_profit": net_profit,
        "trades": trades,
        "max_dd": max_dd,
    }
    out = {"fills": fills_all, "pnl": pnl, "equity": equity, "metrics": metrics}

    # Evidence fields (Source of Truth) - Phase 3.0-A
    raw_intents_total = int(n_entry + exit_intents_count)  # Total raw intents (entry + exit)
    fills_total = int(len(fills_all))  # fills_all is List[Fill], use len()
    timers.stop("t_total_kernel")
    
    # Stage P2-1.8: Get timing dict and merge into _obs for aggregation
    timing_dict = timers.as_dict_seconds()
    # Task 1B: Ensure all required timing keys exist (setdefault 0.0)
    for k in REQUIRED_TIMING_KEYS:
        timing_dict.setdefault(k, 0.0)
    
    # CURSOR TASK 1: Set intents_total = entry_intents_total + exit_intents_total (accounting consistency)
    entry_intents_total_val = int(n_entry)
    exit_intents_total_val = int(exit_intents_count)
    intents_total = entry_intents_total_val + exit_intents_total_val  # CURSOR TASK 1: Always sum
    
    # CURSOR TASK 4: Get entry_valid_mask_sum for MVP contract (bar-level indicator)
    entry_valid_mask_sum = int(obs_extra.get("entry_valid_mask_sum", obs_extra.get("valid_mask_sum", 0)))
    
    # CURSOR TASK 2: Ensure entry_intents_total is set correctly (from n_entry, not valid_mask_sum)
    # Override any value from obs_extra with actual n_entry
    obs_extra_final = dict(obs_extra)  # Copy to avoid modifying original
    obs_extra_final["entry_intents_total"] = entry_intents_total_val  # Always use actual n_entry
    
    # CURSOR TASK 4: Ensure all required obs keys exist
    n_bars_val = int(obs_extra_final.get("n_bars", bars.open.shape[0]))
    warmup_val = int(obs_extra_final.get("warmup", ch))
    valid_mask_sum_val = int(obs_extra_final.get("valid_mask_sum", entry_valid_mask_sum))
    
    out["_obs"] = {
        "intent_mode": "arrays",
        "intents_total": intents_total,  # CURSOR TASK 1: entry_intents_total + exit_intents_total
        "intents_total_reported": raw_intents_total,  # Raw intent count (same as intents_total for accounting)
        "fills_total": fills_total,
        "entry_intents": int(n_entry),
        "exit_intents": int(exit_intents_count),
        "n_bars": n_bars_val,  # CURSOR TASK 4: Required key
        "warmup": warmup_val,  # CURSOR TASK 4: Required key
        "valid_mask_sum": valid_mask_sum_val,  # CURSOR TASK 4: Required key (dense valid mask sum)
        "entry_valid_mask_sum": entry_valid_mask_sum,  # CURSOR TASK 4: Required key (after sparse)
        "entry_intents_total": entry_intents_total_val,  # CURSOR TASK 4: Required key
        "exit_intents_total": exit_intents_total_val,  # CURSOR TASK 1: Required for accounting consistency
        "entry_fills_total": int(entry_fills_count),
        "exit_fills_total": int(exit_fills_count),
        **obs_extra_final,  # Include diagnostic observations from entry intent builder
        **timing_dict,  # Stage P2-1.8: Include timing keys in _obs for aggregation
    }
    out["_perf"] = timing_dict  # Keep _perf for backward compatibility
    if return_debug:
        out["_debug"] = {
            "entry_bar": dbg_entry_bar,
            "entry_price": dbg_entry_price,
            "exit_bar": dbg_exit_bar,
            "exit_price": dbg_exit_price,
        }
    if profile:
        # CURSOR TASK 2: Separate simulate calls (entry then exit), timing reflects actual calls
        out["_profile"] = {
            "intent_mode": "arrays",
            "indicators_s": float(t_ind - t0),
            "intent_gen_s": float(t_intents - t_ind),
            "simulate_entry_s": float(t_sim1 - t_intents),  # Entry simulation time
            "exit_intent_gen_s": float(t_exit_intents - t_sim1),  # Exit intent generation time
            "simulate_exit_s": float(t_sim2 - t_exit_intents),  # Exit simulation time
            "kernel_total_s": float(t_sim2 - t0),
            "entry_intents": int(n_entry),
            "exit_intents": int(exit_intents_count),
        }
    
    # --- P2-1.6 Observability alias (kernel-native) ---
    obs = out.setdefault("_obs", {})
    # Canonical entry sparse keys expected by perf/tests
    # CURSOR TASK 2: entry_valid_mask_sum should come from obs_extra (builder), not valid_mask_sum
    if "entry_valid_mask_sum" not in obs:
        obs.setdefault("entry_valid_mask_sum", int(obs.get("entry_valid_mask_sum", 0)))
    # entry_intents_total should already be set from obs_extra (n_entry)
    if "entry_intents_total" not in obs:
        obs["entry_intents_total"] = int(n_entry)
    
    return out


def run_kernel(
    bars: BarArrays,
    params: DonchianAtrParams,
    *,
    commission: float,
    slip: float,
    order_qty: int = 1,
    return_debug: bool = False,
    precomp: Optional[PrecomputedIndicators] = None,
    intent_sparse_rate: float = 1.0,  # CURSOR TASK 3: Intent sparse rate from grid
) -> Dict[str, object]:
    # Default to arrays path for perf; object mode remains as a correctness reference.
    mode = os.environ.get("FISHBRO_KERNEL_INTENT_MODE", "").strip().lower()
    if mode == "objects":
        return run_kernel_object_mode(
            bars,
            params,
            commission=commission,
            slip=slip,
            order_qty=order_qty,
        )
    return run_kernel_arrays(
        bars,
        params,
        commission=commission,
        slip=slip,
        order_qty=order_qty,
        return_debug=return_debug,
        precomp=precomp,
    )



