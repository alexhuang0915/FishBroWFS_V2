"""
Perf Harness Scenario Control (P2-1.6)

Provides trigger rate masking for perf harness to control sparse trigger density.
"""
from __future__ import annotations

import numpy as np


def apply_trigger_rate_mask(
    trigger: np.ndarray,
    trigger_rate: float,
    warmup: int = 0,
    seed: int = 42,
) -> np.ndarray:
    """
    Apply deterministic trigger rate mask to trigger array.
    
    This function masks trigger array to control sparse trigger density for perf testing.
    Only applies masking when trigger_rate < 1.0. When trigger_rate == 1.0, returns
    original array unchanged (preserves baseline behavior).
    
    Args:
        trigger: Input trigger array (e.g., donch_prev) of shape (n_bars,)
        trigger_rate: Rate of triggers to keep (0.0 to 1.0). Must be in [0, 1].
        warmup: Warmup period. Positions before warmup that are already NaN are preserved.
        seed: Random seed for deterministic masking.
    
    Returns:
        Masked trigger array with same dtype as input. Positions not kept are set to NaN.
    
    Rules:
        - If trigger_rate == 1.0: return original array unchanged
        - Otherwise: use RNG to determine which positions to keep
        - Respect warmup: positions < warmup that are already NaN remain NaN
        - Positions >= warmup are subject to masking
        - Keep dtype unchanged
    """
    if trigger_rate < 0.0 or trigger_rate > 1.0:
        raise ValueError(f"trigger_rate must be in [0, 1], got {trigger_rate}")
    
    # Fast path: no masking needed
    if trigger_rate == 1.0:
        return trigger
    
    # Create a copy to avoid modifying input
    masked = trigger.copy()
    
    # Use deterministic RNG
    rng = np.random.default_rng(seed)
    
    # Generate keep mask: positions to keep based on trigger_rate
    # Only apply masking to positions >= warmup that are currently finite
    n = len(trigger)
    keep_mask = np.ones(n, dtype=bool)  # Default: keep all
    
    # For positions >= warmup, apply random masking
    if warmup < n:
        # Generate random values for positions >= warmup
        random_vals = rng.random(n - warmup)
        keep_mask[warmup:] = random_vals < trigger_rate
    
    # Preserve existing NaN positions (they should remain NaN)
    # Only mask positions that are currently finite and not kept
    finite_mask = np.isfinite(masked)
    
    # Apply masking: set non-kept finite positions to NaN
    # But preserve warmup period (positions < warmup remain unchanged)
    to_mask = finite_mask & (~keep_mask)
    masked[to_mask] = np.nan
    
    return masked
