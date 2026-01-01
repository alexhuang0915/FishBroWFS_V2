"""
Deterministic allocation weights based on vol‑targeting (default) or risk‑parity.

Implements the weight clamping and redistribution logic described in Article IV.
"""
import math
from typing import Dict, List, Optional


# ========== Vol‑Targeting Model ==========

def allocate_weights_vol_target(
    strategy_keys: List[str],
    vol_ests: Dict[str, float],
    params,
) -> Dict[str, float]:
    """
    Compute weights using inverse‑volatility targeting with clamping.

    Steps:
      1. raw_i = 1 / max(vol_ests[i], vol_floor)
      2. normalize raw weights to sum = 1
      3. clamp each weight to [w_min, w_max] with proportional redistribution
      4. ensure final sum = 1 (within tolerance)

    Returns a dict mapping strategy_key → weight.
    """
    # Ensure deterministic ordering
    sorted_keys = sorted(strategy_keys)

    # Step 1: raw inverse volatility
    raw = {}
    for key in sorted_keys:
        vol = vol_ests.get(key, params.vol_floor)
        raw[key] = 1.0 / max(vol, params.vol_floor)

    # Step 2: normalize
    total = sum(raw.values())
    if total == 0:
        # fallback: equal weights
        return {key: 1.0 / len(sorted_keys) for key in sorted_keys}
    weights = {key: raw[key] / total for key in sorted_keys}

    # Step 3: clamp and redistribute
    weights = _clamp_and_redistribute(weights, params.w_min, params.w_max)

    # Step 4: verify sum ≈ 1
    total = sum(weights.values())
    if not math.isclose(total, 1.0, rel_tol=1e-9):
        # Renormalize one more time (should not happen if clamping logic is correct)
        weights = {k: v / total for k, v in weights.items()}

    return weights


def _clamp_and_redistribute(
    weights: Dict[str, float],
    w_min: float,
    w_max: float,
) -> Dict[str, float]:
    """
    Enforce w_min ≤ weight ≤ w_max via iterative proportional redistribution.

    Iteratively cap excess and raise deficit until all weights are within bounds,
    redistributing surplus/deficit proportionally among weights that have room.

    Returns a new weight dict with sum = 1 (within tolerance).
    """
    # Copy to avoid mutating input
    w = weights.copy()
    keys = list(w.keys())
    max_iter = 10
    tolerance = 1e-12

    for _ in range(max_iter):
        # Compute excess (weights above w_max) and deficit (weights below w_min)
        excess = 0.0
        for k in keys:
            if w[k] > w_max:
                excess += w[k] - w_max
                w[k] = w_max

        deficit = 0.0
        for k in keys:
            if w[k] < w_min:
                deficit += w_min - w[k]
                w[k] = w_min

        # If both excess and deficit are negligible, we're done
        if excess <= tolerance and deficit <= tolerance:
            break

        # Distribute excess proportionally to weights that are below w_max
        if excess > tolerance:
            below_max = {k: v for k, v in w.items() if v < w_max}
            if below_max:
                total_below = sum(below_max.values())
                # Distribute proportionally to current weight (or equally?)
                for k in below_max:
                    w[k] += excess * (below_max[k] / total_below)

        # Take deficit proportionally from weights that are above w_min
        if deficit > tolerance:
            above_min = {k: v for k, v in w.items() if v > w_min}
            if above_min:
                total_above = sum(above_min.values())
                for k in above_min:
                    w[k] -= deficit * (above_min[k] / total_above)

    # Final sanity check: clip any remaining out‑of‑bounds weights (should be minimal)
    for k in keys:
        if w[k] < w_min - tolerance or w[k] > w_max + tolerance:
            w[k] = max(w_min, min(w_max, w[k]))

    # Renormalize to ensure sum = 1
    total = sum(w.values())
    if total > 0:
        w = {k: v / total for k, v in w.items()}
    else:
        # fallback equal weights
        w = {k: 1.0 / len(keys) for k in keys}

    return w


# ========== Risk‑Parity Stub ==========

def allocate_weights_risk_parity(
    strategy_keys: List[str],
    vol_ests: Dict[str, float],
    cov_matrix: Optional[Dict[str, Dict[str, float]]] = None,
    params=None,
) -> Dict[str, float]:
    """
    Simple iterative risk‑parity allocation (requires covariance matrix).

    This is a placeholder; a full implementation would need the covariance matrix.
    """
    raise ValueError(
        "risk_parity allocation requires a covariance matrix; "
        "provide cov_matrix or use vol_target model"
    )


# ========== Main Allocation Function ==========

def allocate_weights(
    strategy_keys: List[str],
    vol_ests: Dict[str, float],
    params,
    cov_matrix: Optional[Dict[str, Dict[str, float]]] = None,
) -> Dict[str, float]:
    """
    Deterministic allocation based on the active risk model.

    Args:
        strategy_keys: list of strategy identity keys
        vol_ests: dict mapping key → annualized volatility estimate
        params: GovernanceParams instance
        cov_matrix: optional covariance matrix (required for risk_parity)

    Returns:
        dict mapping key → weight (sum = 1)
    """
    if params.risk_model == "vol_target":
        return allocate_weights_vol_target(strategy_keys, vol_ests, params)
    elif params.risk_model == "risk_parity":
        return allocate_weights_risk_parity(strategy_keys, vol_ests, cov_matrix, params)
    else:
        raise ValueError(
            f"Unknown risk_model '{params.risk_model}'. "
            f"Allowed: {params.allowed_risk_models}"
        )