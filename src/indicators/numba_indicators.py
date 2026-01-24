"""
Numba-accelerated technical indicators.
"""
import numpy as np
from numba import njit

@njit
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

@njit
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

@njit
def sma(arr: np.ndarray, window: int) -> np.ndarray:
    n = arr.shape[0]
    out = np.full(n, np.nan, dtype=np.float64)
    if window <= 0:
        return out
    for i in range(n):
        if i < window - 1:
            # For compatibility with legacy behavior, some implementations return mean of prefix
            # but standard SMA requires the full window. 
            # We'll stick to full window NaN for consistency with other indicators.
            continue
        slice_sum = 0.0
        for j in range(i - window + 1, i + 1):
            slice_sum += arr[j]
        out[i] = slice_sum / window
    return out

@njit
def hh(arr: np.ndarray, window: int) -> np.ndarray:
    return rolling_max(arr, window)

@njit
def ll(arr: np.ndarray, window: int) -> np.ndarray:
    return rolling_min(arr, window)

@njit
def atr_wilder(high, low, close, window):
    n = len(high)
    out = np.full(n, np.nan, dtype=np.float64)
    if window > n or window <= 0:
        return out
    tr = np.empty(n, dtype=np.float64)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        tr[i] = max(
            high[i] - low[i],
            abs(high[i] - close[i - 1]),
            abs(low[i] - close[i - 1]),
        )
    
    # Initial ATR is SMA of TR
    tr_sum = 0.0
    for i in range(window):
        tr_sum += tr[i]
    out[window - 1] = tr_sum / window
    
    # Subsequent ATR is Wilder's smoothing
    for i in range(window, n):
        out[i] = (out[i - 1] * (window - 1) + tr[i]) / window
    return out

@njit
def rolling_stdev(arr: np.ndarray, window: int) -> np.ndarray:
    n = arr.shape[0]
    out = np.full(n, np.nan, dtype=np.float64)
    if window <= 1:
        return out
    for i in range(n):
        if i < window - 1:
            continue
        
        sum_x = 0.0
        sum_x2 = 0.0
        for j in range(i - window + 1, i + 1):
            val = arr[j]
            sum_x += val
            sum_x2 += val * val
        
        mean = sum_x / window
        var = (sum_x2 / window) - (mean * mean)
        # Bessel's correction for sample stdev (ddof=1)
        # Var_sample = Var_pop * (N / (N-1))
        var_sample = var * (window / (window - 1))
        if var_sample < 0:
            var_sample = 0.0
        out[i] = np.sqrt(var_sample)
    return out

@njit
def bbands_pb(arr: np.ndarray, window: int) -> np.ndarray:
    n = arr.shape[0]
    out = np.full(n, np.nan, dtype=np.float64)
    if window <= 1:
        return out
    sma_vals = sma(arr, window)
    stdev_vals = rolling_stdev(arr, window)
    for i in range(n):
        if i < window - 1:
            continue
        upper = sma_vals[i] + 2.0 * stdev_vals[i]
        lower = sma_vals[i] - 2.0 * stdev_vals[i]
        denom = upper - lower
        if denom == 0.0:
            out[i] = np.nan
        else:
            out[i] = (arr[i] - lower) / denom
    return out

@njit
def bbands_width(arr: np.ndarray, window: int) -> np.ndarray:
    n = arr.shape[0]
    out = np.full(n, np.nan, dtype=np.float64)
    if window <= 1:
        return out
    sma_vals = sma(arr, window)
    stdev_vals = rolling_stdev(arr, window)
    for i in range(n):
        if i < window - 1:
            continue
        upper = sma_vals[i] + 2.0 * stdev_vals[i]
        lower = sma_vals[i] - 2.0 * stdev_vals[i]
        denom = sma_vals[i]
        if denom == 0.0:
            out[i] = np.nan
        else:
            out[i] = (upper - lower) / denom
    return out

@njit
def atr_channel_upper(high: np.ndarray, low: np.ndarray, close: np.ndarray, window: int) -> np.ndarray:
    n = close.shape[0]
    out = np.full(n, np.nan, dtype=np.float64)
    if window <= 0:
        return out
    sma_vals = sma(close, window)
    atr_vals = atr_wilder(high, low, close, window)
    for i in range(n):
        if i < window - 1:
            continue
        out[i] = sma_vals[i] + atr_vals[i]
    return out

@njit
def atr_channel_lower(high: np.ndarray, low: np.ndarray, close: np.ndarray, window: int) -> np.ndarray:
    n = close.shape[0]
    out = np.full(n, np.nan, dtype=np.float64)
    if window <= 0:
        return out
    sma_vals = sma(close, window)
    atr_vals = atr_wilder(high, low, close, window)
    for i in range(n):
        if i < window - 1:
            continue
        out[i] = sma_vals[i] - atr_vals[i]
    return out

@njit
def atr_channel_pos(high: np.ndarray, low: np.ndarray, close: np.ndarray, window: int) -> np.ndarray:
    n = close.shape[0]
    out = np.full(n, np.nan, dtype=np.float64)
    if window <= 0:
        return out
    sma_vals = sma(close, window)
    atr_vals = atr_wilder(high, low, close, window)
    for i in range(n):
        if i < window - 1:
            continue
        upper = sma_vals[i] + atr_vals[i]
        lower = sma_vals[i] - atr_vals[i]
        denom = upper - lower
        if denom == 0.0:
            out[i] = np.nan
        else:
            out[i] = (close[i] - lower) / denom
    return out

@njit
def donchian_width(high: np.ndarray, low: np.ndarray, close: np.ndarray, window: int) -> np.ndarray:
    n = close.shape[0]
    out = np.full(n, np.nan, dtype=np.float64)
    if window <= 0:
        return out
    hh_vals = hh(high, window)
    ll_vals = ll(low, window)
    for i in range(n):
        if i < window - 1:
            continue
        denom = close[i]
        if denom == 0.0:
            out[i] = np.nan
        else:
            out[i] = (hh_vals[i] - ll_vals[i]) / denom
    return out

@njit
def dist_to_hh(high: np.ndarray, close: np.ndarray, window: int) -> np.ndarray:
    n = close.shape[0]
    out = np.full(n, np.nan, dtype=np.float64)
    if window <= 0:
        return out
    hh_vals = hh(high, window)
    for i in range(n):
        if i < window - 1:
            continue
        denom = hh_vals[i]
        if denom == 0.0:
            out[i] = np.nan
        else:
            out[i] = (close[i] / denom) - 1.0
    return out

@njit
def dist_to_ll(low: np.ndarray, close: np.ndarray, window: int) -> np.ndarray:
    n = close.shape[0]
    out = np.full(n, np.nan, dtype=np.float64)
    if window <= 0:
        return out
    ll_vals = ll(low, window)
    for i in range(n):
        if i < window - 1:
            continue
        denom = ll_vals[i]
        if denom == 0.0:
            out[i] = np.nan
        else:
            out[i] = (close[i] / denom) - 1.0
    return out

@njit
def percentile_rank(arr: np.ndarray, window: int) -> np.ndarray:
    n = arr.shape[0]
    out = np.full(n, np.nan, dtype=np.float64)
    if window <= 0:
        return out
    for i in range(n):
        start = i - window + 1
        if start < 0:
            # Prefix behavior: rank within available data
            start = 0
        
        cur = arr[i]
        cnt = 0
        denom = i - start + 1
        for j in range(start, i + 1):
            if arr[j] <= cur:
                cnt += 1
        out[i] = cnt / float(denom)
    return out

@njit
def vx_percentile(arr: np.ndarray, window: int) -> np.ndarray:
    return percentile_rank(arr, window)
