from __future__ import annotations

"""
Stage 0 v0: MA Directional Efficiency Proxy

This module intentionally does NOT depend on:
  - engine/* (matcher, fills, intents)
  - strategy/kernel
  - pipeline/runner_grid

It is a cheap scoring function to rank massive parameter grids before Stage 2.

Proxy idea (directional efficiency):
  dir[t] = sign(SMA_fast[t] - SMA_slow[t])
  ret[t] = close[t] - close[t-1]
  score = sum(dir[t] * ret[t]) / (std(ret) + eps)

Notes:
  - This is NOT a backtest. No orders, no fills, no costs.
  - Recall > precision. False negatives are acceptable at Stage 0.
"""

from typing import Tuple

import numpy as np
import os

try:
    import numba as nb
except Exception:  # pragma: no cover
    nb = None  # type: ignore


def _validate_inputs(close: np.ndarray, params_matrix: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """
    Validate and normalize inputs for Stage0 proxy scoring.
    
    Accepts float32 or float64, but converts to float32 for Stage0 optimization.
    """
    from FishBroWFS_V2.config.dtypes import PRICE_DTYPE_STAGE0
    
    c = np.asarray(close, dtype=PRICE_DTYPE_STAGE0)
    if c.ndim != 1:
        raise ValueError("close must be 1D")
    pm = np.asarray(params_matrix, dtype=PRICE_DTYPE_STAGE0)
    if pm.ndim != 2:
        raise ValueError("params_matrix must be 2D")
    if pm.shape[1] < 2:
        raise ValueError("params_matrix must have at least 2 columns: fast, slow")
    if c.shape[0] < 3:
        raise ValueError("close must have at least 3 bars for Stage0 scoring")
    if not c.flags["C_CONTIGUOUS"]:
        c = np.ascontiguousarray(c, dtype=PRICE_DTYPE_STAGE0)
    if not pm.flags["C_CONTIGUOUS"]:
        pm = np.ascontiguousarray(pm, dtype=PRICE_DTYPE_STAGE0)
    return c, pm


def stage0_score_ma_proxy(close: np.ndarray, params_matrix: np.ndarray) -> np.ndarray:
    """
    Compute Stage 0 proxy scores for a parameter matrix.

    Args:
        close: float32 or float64 1D array (n_bars,) - will be converted to float32
        params_matrix: float32 or float64 2D array (n_params, >=2) - will be converted to float32
            - col0: fast_len
            - col1: slow_len
            - additional columns allowed and ignored by v0

    Returns:
        scores: float64 1D array (n_params,) where higher is better
    """
    c, pm = _validate_inputs(close, params_matrix)

    # If numba is available and JIT is not disabled, use nopython kernel.
    if nb is not None and os.environ.get("NUMBA_DISABLE_JIT", "").strip() != "1":
        return _stage0_kernel(c, pm)

    # Fallback: pure numpy/python (correctness only, not intended for scale).
    ret = c[1:] - c[:-1]
    denom = np.std(ret) + 1e-12
    scores = np.empty(pm.shape[0], dtype=np.float64)
    for i in range(pm.shape[0]):
        fast = int(pm[i, 0])
        slow = int(pm[i, 1])
        if fast <= 0 or slow <= 0 or fast >= c.shape[0] or slow >= c.shape[0]:
            scores[i] = -np.inf
            continue
        f = _sma_py(c, fast)
        s = _sma_py(c, slow)
        # Skip NaN warmup region: SMA length L is valid from index (L-1) onward.
        # Here we conservatively start at max(fast, slow) to ensure both are non-NaN.
        start = max(fast, slow)
        acc = 0.0
        for t in range(start, c.shape[0]):
            d = np.sign(f[t] - s[t])
            acc += d * ret[t - 1]
        scores[i] = acc / denom
    return scores


def _sma_py(x: np.ndarray, length: int) -> np.ndarray:
    n = x.shape[0]
    out = np.full(n, np.nan, dtype=np.float64)
    if length <= 0:
        return out
    csum = np.cumsum(x, dtype=np.float64)
    for i in range(n):
        j = i - length + 1
        if j < 0:
            continue
        total = csum[i] - (csum[j - 1] if j > 0 else 0.0)
        out[i] = total / float(length)
    return out


if nb is not None:

    @nb.njit(cache=False)
    def _sma_nb(x: np.ndarray, length: int) -> np.ndarray:
        n = x.shape[0]
        out = np.empty(n, dtype=np.float64)
        for i in range(n):
            out[i] = np.nan
        if length <= 0:
            return out
        csum = np.empty(n, dtype=np.float64)
        acc = 0.0
        for i in range(n):
            acc += float(x[i])
            csum[i] = acc
        for i in range(n):
            j = i - length + 1
            if j < 0:
                continue
            total = csum[i] - (csum[j - 1] if j > 0 else 0.0)
            out[i] = total / float(length)
        return out

    @nb.njit(cache=False)
    def _sign_nb(v: float) -> float:
        if v > 0.0:
            return 1.0
        if v < 0.0:
            return -1.0
        return 0.0

    @nb.njit(cache=False)
    def _std_nb(x: np.ndarray) -> float:
        # simple two-pass std for stability
        n = x.shape[0]
        if n <= 1:
            return 0.0
        mu = 0.0
        for i in range(n):
            mu += float(x[i])
        mu /= float(n)
        var = 0.0
        for i in range(n):
            d = float(x[i]) - mu
            var += d * d
        var /= float(n)
        return np.sqrt(var)

    @nb.njit(cache=False)
    def _stage0_kernel(close: np.ndarray, params_matrix: np.ndarray) -> np.ndarray:
        n = close.shape[0]
        n_params = params_matrix.shape[0]

        # ret[t] = close[t] - close[t-1] for t in [1..n-1]
        ret = np.empty(n - 1, dtype=np.float64)
        for t in range(1, n):
            ret[t - 1] = float(close[t]) - float(close[t - 1])

        denom = _std_nb(ret) + 1e-12
        scores = np.empty(n_params, dtype=np.float64)

        for i in range(n_params):
            fast = int(params_matrix[i, 0])
            slow = int(params_matrix[i, 1])

            # invalid lengths => hard reject
            if fast <= 0 or slow <= 0 or fast >= n or slow >= n:
                scores[i] = -np.inf
                continue

            f = _sma_nb(close, fast)
            s = _sma_nb(close, slow)

            start = fast if fast > slow else slow
            acc = 0.0
            for t in range(start, n):
                d = _sign_nb(f[t] - s[t])
                acc += d * ret[t - 1]

            scores[i] = acc / denom

        return scores


