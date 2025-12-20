"""OOM cost model for memory and computation estimation.

Provides conservative estimates for memory usage and operations
to enable OOM gate decisions before stage execution.
"""

from __future__ import annotations

from typing import Any, Dict

import numpy as np


def _bytes_of_array(a: Any) -> int:
    """
    Get bytes of numpy array.
    
    Args:
        a: Array-like object
        
    Returns:
        Number of bytes (0 if not ndarray)
    """
    if isinstance(a, np.ndarray):
        return int(a.nbytes)
    return 0


def estimate_memory_bytes(
    cfg: Dict[str, Any],
    work_factor: float = 2.0,
) -> int:
    """
    Estimate memory usage in bytes (conservative upper bound).
    
    Memory estimation includes:
    - Price arrays: open/high/low/close (if present)
    - Params matrix: params_total * param_dim * 8 bytes (if present)
    - Working buffers: conservative multiplier (work_factor)
    
    Note: This is a conservative estimate. Actual usage may be lower,
    but gate uses this to prevent OOM failures.
    
    Args:
        cfg: Configuration dictionary containing:
            - bars: Number of bars
            - params_total: Total parameters
            - param_subsample_rate: Subsample rate
            - open_, high, low, close: Optional OHLC arrays
            - params_matrix: Optional parameter matrix
        work_factor: Conservative multiplier for working buffers (default: 2.0)
        
    Returns:
        Estimated memory in bytes
    """
    mem = 0
    
    # Price arrays (if present)
    for k in ("open_", "open", "high", "low", "close"):
        mem += _bytes_of_array(cfg.get(k))
    
    # Params matrix
    mem += _bytes_of_array(cfg.get("params_matrix"))
    
    # Conservative working buffers
    # Note: This is a conservative multiplier to account for:
    # - Intermediate computation buffers
    # - Indicator arrays (donchian, ATR, etc.)
    # - Intent arrays
    # - Fill arrays
    mem = int(mem * float(work_factor))
    
    # Note: We do NOT reduce mem by subsample_rate here because:
    # 1. Some allocations are per-bar (not per-param)
    # 2. Working buffers may scale differently
    # 3. Conservative estimate is safer for OOM prevention
    
    return mem


def estimate_ops(cfg: Dict[str, Any]) -> int:
    """
    Estimate operations count (coarse approximation).
    
    Baseline: per-bar per-effective-param operations.
    This is a coarse estimate for cost tracking.
    
    Args:
        cfg: Configuration dictionary containing:
            - bars: Number of bars
            - params_total: Total parameters
            - param_subsample_rate: Subsample rate
            
    Returns:
        Estimated operations count
    """
    bars = int(cfg.get("bars", 0))
    params_total = int(cfg.get("params_total", 0))
    subsample_rate = float(cfg.get("param_subsample_rate", 1.0))
    
    # Effective params after subsample (floor rule)
    params_effective = int(params_total * subsample_rate)
    
    # Baseline: per-bar per-effective-param step (coarse)
    ops = int(bars * params_effective)
    
    return ops


def estimate_time_s(cfg: Dict[str, Any]) -> float | None:
    """
    Estimate execution time in seconds (optional).
    
    This is a placeholder for future time estimation.
    Currently returns None.
    
    Args:
        cfg: Configuration dictionary
        
    Returns:
        Estimated time in seconds (None if not available)
    """
    # Placeholder for future implementation
    return None


def summarize_estimates(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """
    Summarize all estimates in a JSON-serializable dict.
    
    Args:
        cfg: Configuration dictionary
        
    Returns:
        Dictionary with estimates:
        - mem_est_bytes: Memory estimate in bytes
        - mem_est_mb: Memory estimate in MB
        - ops_est: Operations estimate
        - time_est_s: Time estimate in seconds (None if not available)
    """
    mem_b = estimate_memory_bytes(cfg)
    ops = estimate_ops(cfg)
    time_s = estimate_time_s(cfg)
    
    return {
        "mem_est_bytes": mem_b,
        "mem_est_mb": mem_b / (1024.0 * 1024.0),
        "ops_est": ops,
        "time_est_s": time_s,
    }
