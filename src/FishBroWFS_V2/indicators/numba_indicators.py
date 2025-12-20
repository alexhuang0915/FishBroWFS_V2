from __future__ import annotations

import numpy as np

try:
    import numba as nb
except Exception:  # pragma: no cover
    nb = None  # type: ignore


# ----------------------------
# Rolling Max / Min
# ----------------------------
# Design choice (v1):
# - Simple loop scan for window <= ~50 is cache-friendly and predictable.
# - Correctness first; no deque optimization in v1.


if nb is not None:

    @nb.njit(cache=False)
    def rolling_max(arr: np.ndarray, window: int) -> np.ndarray:
        n = arr.shape[0]
        out = np.full(n, np.nan, dtype=np.float64)
        if window <= 0:
            return out
        for i in range(n):
            if i < window - 1:
                continue
            start = i - window + 1
            m = arr[start]
            for j in range(start + 1, i + 1):
                v = arr[j]
                if v > m:
                    m = v
            out[i] = m
        return out

    @nb.njit(cache=False)
    def rolling_min(arr: np.ndarray, window: int) -> np.ndarray:
        n = arr.shape[0]
        out = np.full(n, np.nan, dtype=np.float64)
        if window <= 0:
            return out
        for i in range(n):
            if i < window - 1:
                continue
            start = i - window + 1
            m = arr[start]
            for j in range(start + 1, i + 1):
                v = arr[j]
                if v < m:
                    m = v
            out[i] = m
        return out

else:
    # Fallback pure-python (used only if numba unavailable)
    def rolling_max(arr: np.ndarray, window: int) -> np.ndarray:  # type: ignore
        n = arr.shape[0]
        out = np.full(n, np.nan, dtype=np.float64)
        if window <= 0:
            return out
        for i in range(n):
            if i < window - 1:
                continue
            start = i - window + 1
            out[i] = np.max(arr[start : i + 1])
        return out

    def rolling_min(arr: np.ndarray, window: int) -> np.ndarray:  # type: ignore
        n = arr.shape[0]
        out = np.full(n, np.nan, dtype=np.float64)
        if window <= 0:
            return out
        for i in range(n):
            if i < window - 1:
                continue
            start = i - window + 1
            out[i] = np.min(arr[start : i + 1])
        return out


# ----------------------------
# ATR (Wilder's RMA)
# ----------------------------
# Definition:
# TR[t] = max(high[t]-low[t], abs(high[t]-close[t-1]), abs(low[t]-close[t-1]))
# ATR[t] = (ATR[t-1]*(n-1) + TR[t]) / n
# Notes:
# - Recursive; must keep state.
# - First ATR uses simple average of first n TRs.


if nb is not None:

    @nb.njit(cache=False)
    def atr_wilder(high: np.ndarray, low: np.ndarray, close: np.ndarray, window: int) -> np.ndarray:
        n = high.shape[0]
        out = np.full(n, np.nan, dtype=np.float64)
        if window <= 0 or n == 0:
            return out
        if window > n:
            return out

        # TR computation
        tr = np.empty(n, dtype=np.float64)
        tr[0] = high[0] - low[0]
        for i in range(1, n):
            a = high[i] - low[i]
            b = abs(high[i] - close[i - 1])
            c = abs(low[i] - close[i - 1])
            tr[i] = a if a >= b and a >= c else (b if b >= c else c)

        # initial ATR: simple average of first window TRs
        s = 0.0
        end = window if window < n else n
        for i in range(end):
            s += tr[i]
        # here window <= n guaranteed
        out[end - 1] = s / window

        # Wilder smoothing
        for i in range(window, n):
            out[i] = (out[i - 1] * (window - 1) + tr[i]) / window

        return out

else:
    def atr_wilder(high: np.ndarray, low: np.ndarray, close: np.ndarray, window: int) -> np.ndarray:  # type: ignore
        n = high.shape[0]
        out = np.full(n, np.nan, dtype=np.float64)
        if window <= 0 or n == 0:
            return out
        if window > n:
            return out

        tr = np.empty(n, dtype=np.float64)
        tr[0] = high[0] - low[0]
        for i in range(1, n):
            tr[i] = max(
                high[i] - low[i],
                abs(high[i] - close[i - 1]),
                abs(low[i] - close[i - 1]),
            )

        end = min(window, n)
        # window <= n guaranteed
        out[end - 1] = np.mean(tr[:end])
        for i in range(window, n):
            out[i] = (out[i - 1] * (window - 1) + tr[i]) / window
        return out

