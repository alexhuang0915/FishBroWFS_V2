from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import os
import time

from FishBroWFS_V2.engine.constants import KIND_STOP, ROLE_ENTRY, ROLE_EXIT, SIDE_BUY, SIDE_SELL
from FishBroWFS_V2.engine.engine_jit import simulate as simulate_matcher
from FishBroWFS_V2.engine.engine_jit import simulate_arrays as simulate_matcher_arrays
from FishBroWFS_V2.engine.types import BarArrays, Fill, OrderIntent, OrderKind, OrderRole, Side
from FishBroWFS_V2.indicators.numba_indicators import rolling_max, rolling_min, atr_wilder


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
    from FishBroWFS_V2.config.dtypes import (
        INDEX_DTYPE,
        INTENT_ENUM_DTYPE,
        INTENT_PRICE_DTYPE,
    )
    
    n = int(donch_prev.shape[0])
    warmup = channel_len
    
    # Create index array for bars 1..n-1 (bar indices t, where created_bar = t-1)
    # i represents bar index t (from 1 to n-1)
    i = np.arange(1, n, dtype=INDEX_DTYPE)
    
    # Sparse mask: valid entries must be finite, positive, and past warmup
    # Check donch_prev[t] for each bar t in range(1, n)
    valid_mask = (~np.isnan(donch_prev[1:])) & (donch_prev[1:] > 0) & (i >= warmup)
    
    # Get indices of valid entries (flatnonzero returns indices into donch_prev[1:])
    # idx is 0-indexed into donch_prev[1:], so idx=0 corresponds to bar t=1
    idx = np.flatnonzero(valid_mask).astype(INDEX_DTYPE)
    
    n_entry = int(idx.shape[0])
    
    # Diagnostic observations
    obs = {
        "n_bars": n,
        "warmup": warmup,
        "valid_mask_sum": int(np.sum(valid_mask)),
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
    
    # Gather sparse entries:
    # - idx is index into donch_prev[1:], so bar index t = idx + 1
    # - created_bar = t - 1 = idx (since t = idx + 1)
    # - price = donch_prev[t] = donch_prev[idx + 1] = donch_prev[1:][idx]
    created_bar = idx.astype(INDEX_DTYPE)  # created_bar = t-1 = idx (when t = idx+1)
    price = donch_prev[1:][idx].astype(INTENT_PRICE_DTYPE)  # Gather from donch_prev[1:]
    
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
    oid = 1

    # We create entry intents for each bar t where indicator exists:
    # created_bar=t, active at t+1. price=donch_hi[t]
    n = int(bars.open.shape[0])
    for t in range(n):
        px = float(donch_hi[t])
        if np.isnan(px):
            continue
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
        oid += 1
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
        exit_intents.append(
            OrderIntent(
                order_id=oid,
                created_bar=ebar,  # active next bar
                role=OrderRole.EXIT,
                kind=OrderKind.STOP,
                side=Side.SELL,
                price=stop_px,
                qty=order_qty,
            )
        )
        oid += 1
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

    # Extract entry/exit prices for round trips (vectorized with arrays, but pairing is minimal 1:1 sequential)
    # Pairing rule for GKV v1: take fills in chronological order, pair BUY(ENTRY) then SELL(EXIT).
    entry_prices = []
    exit_prices = []
    for f in fills_all:
        if f.role == OrderRole.ENTRY and f.side == Side.BUY:
            entry_prices.append(float(f.price))
        elif f.role == OrderRole.EXIT and f.side == Side.SELL:
            exit_prices.append(float(f.price))

    k = min(len(entry_prices), len(exit_prices))
    if k == 0:
        pnl = np.empty(0, dtype=np.float64)
        equity = np.empty(0, dtype=np.float64)
        metrics = {"net_profit": 0.0, "trades": 0, "max_dd": 0.0}
        # Evidence fields (Source of Truth) - Phase 3.0-A: must not be null
        # Red Team requirement: if fallback to objects mode, must leave fingerprint
        intents_total = int(len(intents) + len(exit_intents))
        fills_total = int(len(fills_all))
        return {
            "fills": fills_all,
            "pnl": pnl,
            "equity": equity,
            "metrics": metrics,
            "_obs": {
                "intent_mode": "objects",
                "intents_total": intents_total,
                "fills_total": fills_total,
            },
        }

    ep = np.asarray(entry_prices[:k], dtype=np.float64)
    xp = np.asarray(exit_prices[:k], dtype=np.float64)

    # Costs applied per fill (entry + exit)
    costs = (float(commission) + float(slip)) * 2.0
    pnl = (xp - ep) * float(order_qty) - costs
    equity = np.cumsum(pnl)

    metrics = {
        "net_profit": float(np.sum(pnl)) if pnl.size else 0.0,
        "trades": int(pnl.size),
        "max_dd": _max_drawdown(equity),
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
    from FishBroWFS_V2.perf.timers import PerfTimers
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

    # Stage P2-1.6: Apply trigger rate mask (perf harness scenario control)
    # Only applies when FISHBRO_PERF_TRIGGER_RATE is set and < 1.0
    trigger_rate_env = os.environ.get("FISHBRO_PERF_TRIGGER_RATE", "").strip()
    if trigger_rate_env:
        try:
            trigger_rate = float(trigger_rate_env)
            if 0.0 <= trigger_rate <= 1.0:
                from FishBroWFS_V2.perf.scenario_control import apply_trigger_rate_mask
                donch_prev = apply_trigger_rate_mask(
                    trigger=donch_prev,
                    trigger_rate=trigger_rate,
                    warmup=ch,  # Use channel_len as warmup period
                    seed=42,  # Fixed seed for deterministic masking
                )
        except (ValueError, ImportError):
            # If parsing fails or import fails, continue without masking
            pass

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

    # Build entry intents with sparse masking
    entry_intents_result = _build_entry_intents_from_trigger(
        donch_prev=donch_prev,
        channel_len=ch,
        order_qty=order_qty,
    )
    timers.stop("t_build_entry_intents")
    
    created_bar = entry_intents_result["created_bar"]
    price = entry_intents_result["price"]
    order_id = entry_intents_result["order_id"]
    role = entry_intents_result["role"]
    kind = entry_intents_result["kind"]
    side = entry_intents_result["side"]
    qty = entry_intents_result["qty"]
    n_entry = entry_intents_result["n_entry"]
    obs_extra = entry_intents_result["obs"]
    
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
        
        result = {
            "fills": [],
            "pnl": pnl,
            "equity": equity,
            "metrics": metrics,
            "_obs": {
                "intent_mode": "arrays",
                "intents_total": intents_total,
                "fills_total": fills_total,
                "entry_intents_total": 0,
                "entry_fills_total": 0,
                "exit_intents_total": 0,
                "exit_fills_total": 0,
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
        if "valid_mask_sum" in obs:
            obs.setdefault("entry_valid_mask_sum", int(obs["valid_mask_sum"]))
            obs.setdefault("entry_intents_total", int(obs["valid_mask_sum"]))
        
        return result

    # Arrays are already built by _build_entry_intents_from_trigger
    t_intents = time.perf_counter() if profile else 0.0

    # Stage P2-1.8: t_simulate_entry_s - Simulate entry intents
    timers.start("t_simulate_entry")
    fills: List[Fill] = simulate_matcher_arrays(
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
    
    # Count entry fills
    entry_fills_count = sum(1 for f in fills if f.role == OrderRole.ENTRY and f.side == Side.BUY)

    # Capture first entry fill for debug
    if return_debug and len(fills) > 0:
        first_entry = None
        for f in fills:
            if f.role == OrderRole.ENTRY and f.side == Side.BUY:
                first_entry = f
                break
        if first_entry is not None:
            dbg_entry_bar = int(first_entry.bar_index)
            dbg_entry_price = float(first_entry.price)

    # Stage P2-1.8: t_calc_exits_s - Build Exit intents (using atr_len + stop_mult)
    timers.start("t_calc_exits")
    # Fix 3: Stage B - Build Exit intents (using atr_len + stop_mult)
    # For each entry fill, compute exit stop = entry_price - stop_mult * ATR[entry_bar]
    exit_intents_list = []
    for f in fills:
        if f.role != OrderRole.ENTRY or f.side != Side.BUY:
            continue
        ebar = int(f.bar_index)
        if ebar < 0 or ebar >= int(bars.open.shape[0]):
            continue
        # Get ATR at entry bar
        atr_e = float(atr[ebar])
        if not np.isfinite(atr_e) or atr_e <= 0:
            # Invalid ATR: skip this entry (no exit intent)
            continue
        # Compute exit stop price
        exit_stop = float(f.price - stop_mult * atr_e)
        exit_intents_list.append({
            "created_bar": ebar,  # Allow same-bar entry then exit (matcher handles)
            "price": exit_stop,
            "entry_bar": ebar,
            "entry_price": float(f.price),
        })
    
    exit_intents_count = len(exit_intents_list)
    timers.stop("t_calc_exits")
    t_exit_intents = time.perf_counter() if profile else 0.0

    # Stage P2-1.8: t_simulate_exit_s - Simulate exit intents
    timers.start("t_simulate_exit")
    # Stage C: Simulate exit intents
    if exit_intents_count > 0:
        from FishBroWFS_V2.config.dtypes import (
            INDEX_DTYPE,
            INTENT_ENUM_DTYPE,
            INTENT_PRICE_DTYPE,
        )
        
        exit_created = np.asarray([ei["created_bar"] for ei in exit_intents_list], dtype=INDEX_DTYPE)
        exit_price = np.asarray([ei["price"] for ei in exit_intents_list], dtype=INTENT_PRICE_DTYPE)
        exit_order_id = np.arange(n_entry + 1, n_entry + 1 + exit_intents_count, dtype=INDEX_DTYPE)
        exit_role = np.full(exit_intents_count, ROLE_EXIT, dtype=INTENT_ENUM_DTYPE)
        exit_kind = np.full(exit_intents_count, KIND_STOP, dtype=INTENT_ENUM_DTYPE)
        exit_side = np.full(exit_intents_count, SIDE_SELL, dtype=INTENT_ENUM_DTYPE)
        exit_qty = np.full(exit_intents_count, int(order_qty), dtype=INDEX_DTYPE)
        fills2 = simulate_matcher_arrays(
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
        exit_fills_count = sum(1 for f in fills2 if f.role == OrderRole.EXIT and f.side == Side.SELL)
        fills_all = fills + fills2
        fills_all.sort(
            key=lambda x: (
                x.bar_index,
                0 if x.role == OrderRole.ENTRY else 1,
                0 if x.kind == OrderKind.STOP else 1,
                x.order_id,
            )
        )
    else:
        fills_all = fills
        exit_fills_count = 0
    timers.stop("t_simulate_exit")
    t_sim2 = time.perf_counter() if profile else 0.0

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

    # Stage C: Combine & Metrics - Match entry/exit fills
    entry_prices = []
    exit_prices = []
    for f in fills_all:
        if f.role == OrderRole.ENTRY and f.side == Side.BUY:
            entry_prices.append(float(f.price))
        elif f.role == OrderRole.EXIT and f.side == Side.SELL:
            exit_prices.append(float(f.price))

    k = min(len(entry_prices), len(exit_prices))
    if k == 0:
        pnl = np.empty(0, dtype=np.float64)
        equity = np.empty(0, dtype=np.float64)
        metrics = {"net_profit": 0.0, "trades": 0, "max_dd": 0.0}
        # Evidence fields (Source of Truth) - Phase 3.0-A: must not be null
        intents_total = int(n_entry + exit_intents_count)
        fills_total = int(len(fills_all))
        timers.stop("t_total_kernel")
        timing_dict = timers.as_dict_seconds()
        # Task 1B: Ensure all required timing keys exist (setdefault 0.0)
        for k in REQUIRED_TIMING_KEYS:
            timing_dict.setdefault(k, 0.0)
        result = {
            "fills": fills_all,
            "pnl": pnl,
            "equity": equity,
            "metrics": metrics,
            "_obs": {
                "intent_mode": "arrays",
                "intents_total": intents_total,
                "fills_total": fills_total,
                "entry_intents_total": int(n_entry),
                "entry_fills_total": int(entry_fills_count),
                "exit_intents_total": int(exit_intents_count),
                "exit_fills_total": int(exit_fills_count),
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
        if "valid_mask_sum" in obs:
            obs.setdefault("entry_valid_mask_sum", int(obs["valid_mask_sum"]))
            obs.setdefault("entry_intents_total", int(obs["valid_mask_sum"]))
        
        return result

    ep = np.asarray(entry_prices[:k], dtype=np.float64)
    xp = np.asarray(exit_prices[:k], dtype=np.float64)

    costs = (float(commission) + float(slip)) * 2.0
    pnl = (xp - ep) * float(order_qty) - costs
    equity = np.cumsum(pnl)

    metrics = {
        "net_profit": float(np.sum(pnl)) if pnl.size else 0.0,
        "trades": int(pnl.size),
        "max_dd": _max_drawdown(equity),
    }
    out = {"fills": fills_all, "pnl": pnl, "equity": equity, "metrics": metrics}

    # Evidence fields (Source of Truth) - Phase 3.0-A
    intents_total = int(n_entry + exit_intents_count)  # Total intents (entry + exit, merged)
    fills_total = int(len(fills_all))  # fills_all is List[Fill], use len()
    timers.stop("t_total_kernel")
    
    # Stage P2-1.8: Get timing dict and merge into _obs for aggregation
    timing_dict = timers.as_dict_seconds()
    # Task 1B: Ensure all required timing keys exist (setdefault 0.0)
    for k in REQUIRED_TIMING_KEYS:
        timing_dict.setdefault(k, 0.0)
    
    out["_obs"] = {
        "intent_mode": "arrays",
        "intents_total": intents_total,
        "fills_total": fills_total,
        "entry_intents": int(n_entry),
        "exit_intents": int(exit_intents_count),
        "entry_intents_total": int(n_entry),
        "entry_fills_total": int(entry_fills_count),
        "exit_intents_total": int(exit_intents_count),
        "exit_fills_total": int(exit_fills_count),
        **obs_extra,  # Include diagnostic observations from entry intent builder
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
        out["_profile"] = {
            "intent_mode": "arrays",
            "indicators_s": float(t_ind - t0),
            "intent_gen_s": float(t_intents - t_ind),
            "simulate_entry_s": float(t_sim1 - t_intents),
            "exit_intent_gen_s": float(t_exit_intents - t_sim1),
            "simulate_exit_s": float(t_sim2 - t_exit_intents),
            "kernel_total_s": float(t_sim2 - t0),
            "entry_intents": int(n_entry),
            "exit_intents": int(exit_intents_count),
        }
    
    # --- P2-1.6 Observability alias (kernel-native) ---
    obs = out.setdefault("_obs", {})
    # Canonical entry sparse keys expected by perf/tests
    if "valid_mask_sum" in obs:
        obs.setdefault("entry_valid_mask_sum", int(obs["valid_mask_sum"]))
        obs.setdefault("entry_intents_total", int(obs["valid_mask_sum"]))
    
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

