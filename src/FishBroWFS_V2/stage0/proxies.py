from __future__ import annotations

"""
Stage 0 v1 Trinity: Trend + Volatility + Activity Proxies

This module provides three proxy scoring functions for ranking parameter grids
before full backtest (Stage 2). These are NOT backtests - they are cheap heuristics.

Proxy Contract:
  - Stage0 is ranking proxy, NOT equal to backtest
  - NaN/warmup rules: start = max(required_lookbacks)
  - Correlation contract: Spearman ρ ≥ 0.4 (enforced by tests)

Design:
  - All proxies return float64 (n_params,) scores where higher is better
  - Input: OHLC arrays (np.ndarray), params: float64 2D array (n_params, k)
  - Must provide *_py (pure Python) and *_nb (Numba njit) versions
  - Wrapper functions select nb/py based on NUMBA_DISABLE_JIT kill-switch
"""

from typing import Tuple

import numpy as np
import os

try:
    import numba as nb
except Exception:  # pragma: no cover
    nb = None  # type: ignore

from FishBroWFS_V2.indicators.numba_indicators import atr_wilder


def _validate_inputs(
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    params_matrix: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Validate and ensure contiguous arrays."""
    o = np.asarray(open_, dtype=np.float64)
    h = np.asarray(high, dtype=np.float64)
    l = np.asarray(low, dtype=np.float64)
    c = np.asarray(close, dtype=np.float64)
    pm = np.asarray(params_matrix, dtype=np.float64)

    if o.ndim != 1 or h.ndim != 1 or l.ndim != 1 or c.ndim != 1:
        raise ValueError("OHLC arrays must be 1D")
    if pm.ndim != 2:
        raise ValueError("params_matrix must be 2D")
    if not (o.shape[0] == h.shape[0] == l.shape[0] == c.shape[0]):
        raise ValueError("OHLC arrays must have same length")

    if not o.flags["C_CONTIGUOUS"]:
        o = np.ascontiguousarray(o)
    if not h.flags["C_CONTIGUOUS"]:
        h = np.ascontiguousarray(h)
    if not l.flags["C_CONTIGUOUS"]:
        l = np.ascontiguousarray(l)
    if not c.flags["C_CONTIGUOUS"]:
        c = np.ascontiguousarray(c)
    if not pm.flags["C_CONTIGUOUS"]:
        pm = np.ascontiguousarray(pm)

    return o, h, l, c, pm


# ============================================================================
# Proxy #1: Trend Proxy (MA / slope)
# ============================================================================


def trend_proxy_py(
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    params_matrix: np.ndarray,
) -> np.ndarray:
    """
    Trend proxy: mean(sign(sma_fast - sma_slow)) or mean((sma_fast - sma_slow) / close)

    Args:
        open_, high, low, close: float64 1D arrays (n_bars,)
        params_matrix: float64 2D array (n_params, >=2)
            - col0: fast_len
            - col1: slow_len

    Returns:
        scores: float64 1D array (n_params,)
    """
    o, h, l, c, pm = _validate_inputs(open_, high, low, close, params_matrix)
    n = c.shape[0]
    n_params = pm.shape[0]

    if pm.shape[1] < 2:
        raise ValueError("params_matrix must have at least 2 columns: fast_len, slow_len")

    scores = np.empty(n_params, dtype=np.float64)

    for i in range(n_params):
        fast = int(pm[i, 0])
        slow = int(pm[i, 1])

        # Invalid params: return -inf
        if fast <= 0 or slow <= 0 or fast >= n or slow >= n:
            scores[i] = -np.inf
            continue

        # Compute SMAs
        sma_fast = _sma_py(c, fast)
        sma_slow = _sma_py(c, slow)

        # Warmup: start at max(fast, slow)
        start = max(fast, slow)
        if start >= n:
            scores[i] = -np.inf
            continue

        # Compute trend score: mean((sma_fast - sma_slow) / close)
        acc = 0.0
        count = 0
        for t in range(start, n):
            diff = sma_fast[t] - sma_slow[t]
            if not np.isnan(diff) and c[t] > 0:
                acc += diff / c[t]
                count += 1

        if count == 0:
            scores[i] = -np.inf
        else:
            scores[i] = acc / count

    return scores


def trend_proxy_nb(
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    params_matrix: np.ndarray,
) -> np.ndarray:
    """Numba version of trend_proxy."""
    if nb is None:  # pragma: no cover
        raise RuntimeError("numba not available")
    return _trend_proxy_kernel(open_, high, low, close, params_matrix)


def trend_proxy(
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    params_matrix: np.ndarray,
) -> np.ndarray:
    """Wrapper: select nb/py based on NUMBA_DISABLE_JIT."""
    if nb is not None and os.environ.get("NUMBA_DISABLE_JIT", "").strip() != "1":
        return trend_proxy_nb(open_, high, low, close, params_matrix)
    return trend_proxy_py(open_, high, low, close, params_matrix)


# ============================================================================
# Proxy #2: Volatility Proxy (ATR / Range)
# ============================================================================


def vol_proxy_py(
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    params_matrix: np.ndarray,
) -> np.ndarray:
    """
    Volatility proxy: effective stop distance = ATR(atr_len) * stop_mult.
    
    Score prefers moderate stop distance (avoids extremely tiny or huge stops).

    Args:
        open_, high, low, close: float64 1D arrays (n_bars,)
        params_matrix: float64 2D array (n_params, >=2)
            - col0: atr_len
            - col1: stop_mult

    Returns:
        scores: float64 1D array (n_params,)
    """
    o, h, l, c, pm = _validate_inputs(open_, high, low, close, params_matrix)
    n = c.shape[0]
    n_params = pm.shape[0]

    if pm.shape[1] < 2:
        raise ValueError("params_matrix must have at least 2 columns: atr_len, stop_mult")

    scores = np.empty(n_params, dtype=np.float64)

    for i in range(n_params):
        atr_len = int(pm[i, 0])
        stop_mult = float(pm[i, 1])

        # Invalid params: return -inf
        if atr_len <= 0 or atr_len >= n or stop_mult <= 0.0:
            scores[i] = -np.inf
            continue

        # Compute ATR using Wilder's method
        atr = atr_wilder(h, l, c, atr_len)

        # Warmup: start at atr_len
        start = max(atr_len, 1)
        if start >= n:
            scores[i] = -np.inf
            continue

        # Compute stop distance: ATR * stop_mult
        stop_dist_sum = 0.0
        stop_dist_count = 0
        for t in range(start, n):
            if not np.isnan(atr[t]) and atr[t] > 0:
                stop_dist = atr[t] * stop_mult
                stop_dist_sum += stop_dist
                stop_dist_count += 1

        if stop_dist_count == 0:
            scores[i] = -np.inf
        else:
            stop_dist_mean = stop_dist_sum / float(stop_dist_count)
            # Score: -log1p(stop_mean) - penalize larger stops; deterministic; no target/median
            scores[i] = -np.log1p(stop_dist_mean)

    return scores


def vol_proxy_nb(
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    params_matrix: np.ndarray,
) -> np.ndarray:
    """Numba version of vol_proxy."""
    if nb is None:  # pragma: no cover
        raise RuntimeError("numba not available")
    return _vol_proxy_kernel(open_, high, low, close, params_matrix)


def vol_proxy(
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    params_matrix: np.ndarray,
) -> np.ndarray:
    """Wrapper: select nb/py based on NUMBA_DISABLE_JIT."""
    if nb is not None and os.environ.get("NUMBA_DISABLE_JIT", "").strip() != "1":
        return vol_proxy_nb(open_, high, low, close, params_matrix)
    return vol_proxy_py(open_, high, low, close, params_matrix)


# ============================================================================
# Proxy #3: Activity Proxy (Trade Count / trigger density)
# ============================================================================


def activity_proxy_py(
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    params_matrix: np.ndarray,
) -> np.ndarray:
    """
    Activity proxy: channel breakout trigger count.
    
    Counts crossings where close[t-1] <= channel_hi[t-1] and close[t] > channel_hi[t].
    Aligned with Stage2 kernel which uses channel breakout entry.

    Args:
        open_, high, low, close: float64 1D arrays (n_bars,)
        params_matrix: float64 2D array (n_params, >=1)
            - col0: channel_len
            - col1: atr_len (not used, kept for compatibility)

    Returns:
        scores: float64 1D array (n_params,)
    """
    o, h, l, c, pm = _validate_inputs(open_, high, low, close, params_matrix)
    n = c.shape[0]
    n_params = pm.shape[0]

    if pm.shape[1] < 1:
        raise ValueError("params_matrix must have at least 1 column: channel_len")

    scores = np.empty(n_params, dtype=np.float64)

    for i in range(n_params):
        channel_len = int(pm[i, 0])

        # Invalid params: return -inf
        if channel_len <= 0 or channel_len >= n:
            scores[i] = -np.inf
            continue

        # Compute channel_hi = rolling_max(high, channel_len)
        channel_hi = np.full(n, np.nan, dtype=np.float64)
        for t in range(n):
            start_idx = max(0, t - channel_len + 1)
            window_high = h[start_idx : t + 1]
            if window_high.size > 0:
                channel_hi[t] = np.max(window_high)

        # Warmup: start at channel_len
        start = channel_len
        if start >= n - 1:
            scores[i] = -np.inf
            continue

        # Count breakout triggers: high[t] > ch[t-1] AND high[t-1] <= ch[t-1]
        # Compare to previous channel high to avoid equality lock
        # Start from start+1 to ensure we have t-1 available
        triggers = 0
        for t in range(start + 1, n):
            if np.isnan(channel_hi[t-1]):
                continue
            # Trigger when high crosses above previous channel high
            if high[t] > channel_hi[t-1] and high[t-1] <= channel_hi[t-1]:
                triggers += 1

        n_effective = n - start
        if n_effective == 0:
            scores[i] = -np.inf
        else:
            # Activity score: raw count of triggers (or triggers per bar)
            # Using raw count for simplicity and robustness
            scores[i] = float(triggers)

    return scores


def activity_proxy_nb(
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    params_matrix: np.ndarray,
) -> np.ndarray:
    """Numba version of activity_proxy."""
    if nb is None:  # pragma: no cover
        raise RuntimeError("numba not available")
    return _activity_proxy_kernel(open_, high, low, close, params_matrix)


def activity_proxy(
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    params_matrix: np.ndarray,
) -> np.ndarray:
    """Wrapper: select nb/py based on NUMBA_DISABLE_JIT."""
    if nb is not None and os.environ.get("NUMBA_DISABLE_JIT", "").strip() != "1":
        return activity_proxy_nb(open_, high, low, close, params_matrix)
    return activity_proxy_py(open_, high, low, close, params_matrix)


# ============================================================================
# Helper functions (SMA)
# ============================================================================


def _sma_py(x: np.ndarray, length: int) -> np.ndarray:
    """Simple Moving Average (pure Python)."""
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


# ============================================================================
# Numba kernels
# ============================================================================

if nb is not None:

    @nb.njit(cache=False)
    def _sma_nb(x: np.ndarray, length: int) -> np.ndarray:
        """Simple Moving Average (Numba)."""
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
    def _trend_proxy_kernel(
        open_: np.ndarray,
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
        params_matrix: np.ndarray,
    ) -> np.ndarray:
        """Numba kernel for trend proxy."""
        n = close.shape[0]
        n_params = params_matrix.shape[0]
        scores = np.empty(n_params, dtype=np.float64)

        for i in range(n_params):
            fast = int(params_matrix[i, 0])
            slow = int(params_matrix[i, 1])

            if fast <= 0 or slow <= 0 or fast >= n or slow >= n:
                scores[i] = -np.inf
                continue

            sma_fast = _sma_nb(close, fast)
            sma_slow = _sma_nb(close, slow)

            start = fast if fast > slow else slow
            if start >= n:
                scores[i] = -np.inf
                continue

            acc = 0.0
            count = 0
            for t in range(start, n):
                diff = sma_fast[t] - sma_slow[t]
                if not np.isnan(diff) and close[t] > 0.0:
                    acc += diff / close[t]
                    count += 1

            if count == 0:
                scores[i] = -np.inf
            else:
                scores[i] = acc / float(count)

        return scores

    @nb.njit(cache=False)
    def _atr_wilder_nb(high: np.ndarray, low: np.ndarray, close: np.ndarray, window: int) -> np.ndarray:
        """ATR Wilder (Numba version, inline for njit compatibility)."""
        n = high.shape[0]
        out = np.empty(n, dtype=np.float64)
        for i in range(n):
            out[i] = np.nan

        if window <= 0 or n == 0 or window > n:
            return out

        tr = np.empty(n, dtype=np.float64)
        tr[0] = high[0] - low[0]
        for i in range(1, n):
            a = high[i] - low[i]
            b = abs(high[i] - close[i - 1])
            c = abs(low[i] - close[i - 1])
            tr[i] = a if a >= b and a >= c else (b if b >= c else c)

        s = 0.0
        end = window if window < n else n
        for i in range(end):
            s += tr[i]
        out[end - 1] = s / float(window)

        for i in range(window, n):
            out[i] = (out[i - 1] * float(window - 1) + tr[i]) / float(window)

        return out

    @nb.njit(cache=False)
    def _rolling_max_nb(arr: np.ndarray, window: int) -> np.ndarray:
        """Rolling maximum (Numba, inline for njit compatibility)."""
        n = arr.shape[0]
        out = np.empty(n, dtype=np.float64)
        for i in range(n):
            out[i] = np.nan
        if window <= 0:
            return out
        for i in range(n):
            start = i - window + 1
            if start < 0:
                start = 0
            m = arr[start]
            for j in range(start + 1, i + 1):
                v = arr[j]
                if v > m:
                    m = v
            out[i] = m
        return out

    @nb.njit(cache=False)
    def _vol_proxy_kernel(
        open_: np.ndarray,
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
        params_matrix: np.ndarray,
    ) -> np.ndarray:
        """Numba kernel for vol proxy with stop_mult."""
        n = close.shape[0]
        n_params = params_matrix.shape[0]
        scores = np.empty(n_params, dtype=np.float64)

        for i in range(n_params):
            atr_len = int(params_matrix[i, 0])
            stop_mult = float(params_matrix[i, 1])

            if atr_len <= 0 or atr_len >= n or stop_mult <= 0.0:
                scores[i] = -np.inf
                continue

            atr = _atr_wilder_nb(high, low, close, atr_len)

            start = atr_len if atr_len > 1 else 1
            if start >= n:
                scores[i] = -np.inf
                continue

            # Compute stop distance: ATR * stop_mult
            stop_dist_sum = 0.0
            stop_dist_count = 0
            for t in range(start, n):
                if not np.isnan(atr[t]) and atr[t] > 0.0:
                    stop_dist = atr[t] * stop_mult
                    stop_dist_sum += stop_dist
                    stop_dist_count += 1

            if stop_dist_count == 0:
                scores[i] = -np.inf
            else:
                stop_dist_mean = stop_dist_sum / float(stop_dist_count)
                # Score: -log1p(stop_mean) - penalize larger stops; deterministic; no target/median
                scores[i] = -np.log1p(stop_dist_mean)

        return scores

    @nb.njit(cache=False)
    def _sign_nb(v: float) -> float:
        """Sign function (Numba)."""
        if v > 0.0:
            return 1.0
        if v < 0.0:
            return -1.0
        return 0.0

    @nb.njit(cache=False)
    def _activity_proxy_kernel(
        open_: np.ndarray,
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
        params_matrix: np.ndarray,
    ) -> np.ndarray:
        """Numba kernel for activity proxy: channel breakout triggers."""
        n = close.shape[0]
        n_params = params_matrix.shape[0]
        scores = np.empty(n_params, dtype=np.float64)

        for i in range(n_params):
            channel_len = int(params_matrix[i, 0])

            if channel_len <= 0 or channel_len >= n:
                scores[i] = -np.inf
                continue

            # Compute channel_hi = rolling_max(high, channel_len)
            channel_hi = _rolling_max_nb(high, channel_len)

            start = channel_len
            if start >= n - 1:
                scores[i] = -np.inf
                continue

            # Count breakout triggers: high[t] > ch[t-1] AND high[t-1] <= ch[t-1]
            # Compare to previous channel high to avoid equality lock
            # Start from start+1 to ensure we have t-1 available
            triggers = 0
            for t in range(start + 1, n):
                if np.isnan(channel_hi[t-1]):
                    continue
                # Trigger when high crosses above previous channel high
                if high[t] > channel_hi[t-1] and high[t-1] <= channel_hi[t-1]:
                    triggers += 1

            n_effective = n - start
            if n_effective == 0:
                scores[i] = -np.inf
            else:
                # Activity score: raw count of triggers (or triggers per bar)
                # Using raw count for simplicity and robustness
                scores[i] = float(triggers)

        return scores
