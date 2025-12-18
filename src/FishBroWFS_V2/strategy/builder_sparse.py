"""
Sparse Intent Builder (P2-3)

Provides sparse intent generation with trigger rate control for performance testing.
Supports both sparse (default) and dense (reference) modes.
"""
from __future__ import annotations

from typing import Dict

import numpy as np

from FishBroWFS_V2.config.dtypes import (
    INDEX_DTYPE,
    INTENT_ENUM_DTYPE,
    INTENT_PRICE_DTYPE,
)
from FishBroWFS_V2.engine.constants import KIND_STOP, ROLE_ENTRY, SIDE_BUY


def build_intents_sparse(
    donch_prev: np.ndarray,
    channel_len: int,
    order_qty: int,
    trigger_rate: float = 1.0,
    seed: int = 42,
    use_dense: bool = False,
) -> Dict[str, object]:
    """
    Build entry intents from trigger array with sparse masking support.
    
    This is the main sparse builder that supports trigger rate control for performance testing.
    When trigger_rate < 1.0, it deterministically selects a subset of valid triggers.
    
    Args:
        donch_prev: float64 array (n_bars,) - shifted donchian high (donch_prev[0]=NaN, donch_prev[1:]=donch_hi[:-1])
        channel_len: warmup period (same as indicator warmup)
        order_qty: order quantity
        trigger_rate: Rate of triggers to keep (0.0 to 1.0). Default 1.0 (all triggers).
        seed: Random seed for deterministic trigger selection. Default 42.
        use_dense: If True, use dense builder (reference implementation). Default False (sparse).
    
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
            - obs: dict - diagnostic observations (includes allowed_bars, intents_generated)
    """
    n = int(donch_prev.shape[0])
    warmup = channel_len
    
    # Create index array for bars 1..n-1 (bar indices t, where created_bar = t-1)
    i = np.arange(1, n, dtype=INDEX_DTYPE)
    
    # Valid bar mask: entries must be finite, positive, and past warmup
    valid_bar_mask = (~np.isnan(donch_prev[1:])) & (donch_prev[1:] > 0) & (i >= warmup)
    
    # CURSOR TASK 1: Generate bar_allow mask based on trigger_rate
    # rate <= 0.0 → 全 False
    # rate >= 1.0 → 全 True
    # else → rng.random(n_bars) < rate
    if use_dense or trigger_rate >= 1.0:
        # Dense mode or full rate: all bars allowed
        bar_allow = np.ones(n - 1, dtype=bool)  # n-1 because we skip first bar
    elif trigger_rate <= 0.0:
        # Zero rate: no bars allowed
        bar_allow = np.zeros(n - 1, dtype=bool)
    else:
        # Sparse mode: deterministically select bars based on trigger_rate
        rng = np.random.default_rng(seed)
        random_vals = rng.random(n - 1)  # Random values for bars 1..n-1
        bar_allow = random_vals < trigger_rate
    
    # Combine valid_bar_mask with bar_allow to get final allow_mask
    allow_mask = valid_bar_mask & bar_allow
    
    # Count valid bars (before trigger rate filtering) - this is the baseline
    valid_bars_count = int(np.sum(valid_bar_mask))
    
    # Count allowed bars (after intent sparse filtering) - this is what actually gets intents
    allowed_bars_after_sparse = int(np.sum(allow_mask))
    
    # Get indices of allowed entries (flatnonzero returns indices into donch_prev[1:])
    idx_selected = np.flatnonzero(allow_mask).astype(INDEX_DTYPE)
    intents_generated = allowed_bars_after_sparse
    n_entry = int(idx_selected.shape[0])
    
    # CURSOR TASK 2: entry_valid_mask_sum must be sum(allow_mask) (after intent sparse)
    # Diagnostic observations
    obs = {
        "n_bars": n,
        "warmup": warmup,
        "valid_mask_sum": valid_bars_count,  # Dense valid bars (before trigger rate)
        "entry_valid_mask_sum": allowed_bars_after_sparse,  # CURSOR TASK 2: After intent sparse (sum(allow_mask))
        "allowed_bars": valid_bars_count,  # Always equals valid_mask_sum (baseline, for comparison)
        "intents_generated": intents_generated,  # Actual intents generated (equals allowed_bars_after_sparse)
        "trigger_rate_applied": float(trigger_rate),
        "builder_mode": "dense" if use_dense else "sparse",
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
    
    # Gather sparse entries (only for selected positions)
    # - idx_selected is index into donch_prev[1:], so bar index t = idx_selected + 1
    # - created_bar = t - 1 = idx_selected (since t = idx_selected + 1)
    # - price = donch_prev[t] = donch_prev[idx_selected + 1] = donch_prev[1:][idx_selected]
    created_bar = idx_selected.astype(INDEX_DTYPE)  # created_bar = t-1 = idx_selected
    price = donch_prev[1:][idx_selected].astype(INTENT_PRICE_DTYPE)  # Gather from donch_prev[1:]
    
    # Order ID maintains deterministic ordering
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


def build_intents_dense(
    donch_prev: np.ndarray,
    channel_len: int,
    order_qty: int,
) -> Dict[str, object]:
    """
    Dense builder (reference implementation).
    
    This is a wrapper around build_intents_sparse with use_dense=True for clarity.
    Use this when you need the reference dense behavior.
    
    Args:
        donch_prev: float64 array (n_bars,) - shifted donchian high
        channel_len: warmup period
        order_qty: order quantity
    
    Returns:
        Same format as build_intents_sparse (with all valid triggers).
    """
    return build_intents_sparse(
        donch_prev=donch_prev,
        channel_len=channel_len,
        order_qty=order_qty,
        trigger_rate=1.0,
        seed=42,
        use_dense=True,
    )
