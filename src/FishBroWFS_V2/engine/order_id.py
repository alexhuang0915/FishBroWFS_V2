"""
Deterministic Order ID Generation (CURSOR TASK 5)

Provides pure function for generating deterministic order IDs that do not depend
on generation order or counters. Used by both object-mode and array-mode kernels.
"""
from __future__ import annotations

import numpy as np

from FishBroWFS_V2.config.dtypes import INDEX_DTYPE
from FishBroWFS_V2.engine.constants import KIND_STOP, ROLE_ENTRY, ROLE_EXIT, SIDE_BUY, SIDE_SELL


def generate_order_id(
    created_bar: int,
    param_idx: int = 0,
    role: int = ROLE_ENTRY,
    kind: int = KIND_STOP,
    side: int = SIDE_BUY,
) -> int:
    """
    Generate deterministic order ID from intent attributes.
    
    Uses reversible packing to ensure deterministic IDs that do not depend on
    generation order or counters. This ensures parity between object-mode and
    array-mode kernels.
    
    Formula:
        order_id = created_bar * 1_000_000 + param_idx * 100 + role_code * 10 + kind_code * 2 + side_code_bit
    
    Args:
        created_bar: Bar index where intent is created (0-indexed)
        param_idx: Parameter index (0-indexed, default 0 for single-param kernels)
        role: Role code (ROLE_ENTRY or ROLE_EXIT)
        kind: Kind code (KIND_STOP or KIND_LIMIT)
        side: Side code (SIDE_BUY or SIDE_SELL)
    
    Returns:
        Deterministic order ID (int32)
    
    Note:
        - Maximum created_bar: 2,147,483 (within int32 range)
        - Maximum param_idx: 21,474,836 (within int32 range)
        - This packing scheme ensures uniqueness for typical use cases
    """
    # Map role to code: ENTRY=0, EXIT=1
    role_code = 0 if role == ROLE_ENTRY else 1
    
    # Map kind to code: STOP=0, LIMIT=1 (assuming KIND_STOP=0, KIND_LIMIT=1)
    kind_code = 0 if kind == KIND_STOP else 1
    
    # Map side to bit: BUY=0, SELL=1
    side_bit = 0 if side == SIDE_BUY else 1
    
    # Pack: created_bar * 1_000_000 + param_idx * 100 + role_code * 10 + kind_code * 2 + side_bit
    order_id = (
        created_bar * 1_000_000 +
        param_idx * 100 +
        role_code * 10 +
        kind_code * 2 +
        side_bit
    )
    
    return int(order_id)


def generate_order_ids_array(
    created_bar: np.ndarray,
    param_idx: int = 0,
    role: np.ndarray | None = None,
    kind: np.ndarray | None = None,
    side: np.ndarray | None = None,
) -> np.ndarray:
    """
    Generate deterministic order IDs for array of intents.
    
    Vectorized version of generate_order_id for array-mode kernels.
    
    Args:
        created_bar: Array of created bar indices (int32, shape (n,))
        param_idx: Parameter index (default 0 for single-param kernels)
        role: Array of role codes (uint8, shape (n,)). If None, defaults to ROLE_ENTRY.
        kind: Array of kind codes (uint8, shape (n,)). If None, defaults to KIND_STOP.
        side: Array of side codes (uint8, shape (n,)). If None, defaults to SIDE_BUY.
    
    Returns:
        Array of deterministic order IDs (int32, shape (n,))
    """
    n = len(created_bar)
    
    # Default values if not provided
    if role is None:
        role = np.full(n, ROLE_ENTRY, dtype=np.uint8)
    if kind is None:
        kind = np.full(n, KIND_STOP, dtype=np.uint8)
    if side is None:
        side = np.full(n, SIDE_BUY, dtype=np.uint8)
    
    # Map to codes
    role_code = np.where(role == ROLE_ENTRY, 0, 1).astype(np.int32)
    kind_code = np.where(kind == KIND_STOP, 0, 1).astype(np.int32)
    side_bit = np.where(side == SIDE_BUY, 0, 1).astype(np.int32)
    
    # Pack: created_bar * 1_000_000 + param_idx * 100 + role_code * 10 + kind_code * 2 + side_bit
    order_id = (
        created_bar.astype(np.int32) * 1_000_000 +
        param_idx * 100 +
        role_code * 10 +
        kind_code * 2 +
        side_bit
    )
    
    return order_id.astype(INDEX_DTYPE)
