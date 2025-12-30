from __future__ import annotations

import numpy as np
from numba import njit, float64


@njit(cache=True)
def safe_div(a: float64, b: float64) -> float64:
    """
    Safe division with DIV0_RET_NAN policy.
    
    Returns:
        a / b if b != 0 and result is finite
        NaN if b == 0 or result is inf/-inf
    """
    if b == 0.0:
        return np.nan
    result = a / b
    if np.isinf(result):
        return np.nan
    return result


@njit(cache=True)
def safe_div_array(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """
    Element‑wise safe division for arrays of equal length.
    """
    n = a.shape[0]
    out = np.empty(n, dtype=np.float64)
    for i in range(n):
        out[i] = safe_div(a[i], b[i])
    return out


@njit(cache=True)
def rolling_max(arr: np.ndarray, window: int) -> np.ndarray:
    n = arr.shape[0]
    out = np.empty(n, dtype=np.float64)
    if window <= 0:
        for i in range(n):
            out[i] = np.nan
        return out
    for i in range(n):
        if i < window - 1:
            out[i] = np.nan
            continue
        start = i - window + 1
        m = arr[start]
        for j in range(start + 1, i + 1):
            v = arr[j]
            if v > m:
                m = v
        out[i] = m
    return out


@njit(cache=True)
def rolling_min(arr: np.ndarray, window: int) -> np.ndarray:
    n = arr.shape[0]
    out = np.empty(n, dtype=np.float64)
    if window <= 0:
        for i in range(n):
            out[i] = np.nan
        return out
    for i in range(n):
        if i < window - 1:
            out[i] = np.nan
            continue
        start = i - window + 1
        m = arr[start]
        for j in range(start + 1, i + 1):
            v = arr[j]
            if v < m:
                m = v
        out[i] = m
    return out


@njit(cache=True)
def sma(arr: np.ndarray, window: int) -> np.ndarray:
    n = arr.shape[0]
    out = np.empty(n, dtype=np.float64)
    s = 0.0
    for i in range(n):
        s += arr[i]
        if i >= window:
            s -= arr[i - window]
        denom = window if i >= window - 1 else (i + 1)
        out[i] = s / float(denom)
    return out


@njit(cache=True)
def hh(arr: np.ndarray, window: int) -> np.ndarray:
    # Highest High over trailing window (causal)
    return rolling_max(arr, window)


@njit(cache=True)
def ll(arr: np.ndarray, window: int) -> np.ndarray:
    # Lowest Low over trailing window (causal)
    return rolling_min(arr, window)


@njit(cache=True)
def atr_wilder(high: np.ndarray, low: np.ndarray, close: np.ndarray, window: int) -> np.ndarray:
    """
    Wilder ATR (causal).
    TR[i] = max(high-low, abs(high-close_prev), abs(low-close_prev))
    ATR[window-1] = mean(TR[:window])
    ATR[i] = (ATR[i-1]*(window-1) + TR[i]) / window for i >= window
    Returns NaN for i < window-1.
    """
    n = close.shape[0]
    out = np.empty(n, dtype=np.float64)
    # Fill with NaN
    for i in range(n):
        out[i] = np.nan
    
    if window <= 0 or window > n:
        return out
    
    # Compute TR array
    tr = np.empty(n, dtype=np.float64)
    prev_close = close[0]
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        h = high[i]
        l = low[i]
        tr_val = h - l
        a = h - prev_close
        if a < 0:
            a = -a
        b = l - prev_close
        if b < 0:
            b = -b
        if a > tr_val:
            tr_val = a
        if b > tr_val:
            tr_val = b
        tr[i] = tr_val
        prev_close = close[i]
    
    # Compute first ATR as mean of first window TR values
    sum_tr = 0.0
    for i in range(window):
        sum_tr += tr[i]
    out[window - 1] = sum_tr / float(window)
    
    # Wilder smoothing for subsequent bars
    for i in range(window, n):
        out[i] = (out[i - 1] * (window - 1) + tr[i]) / float(window)
    
    return out


@njit(cache=True)
def rsi(close: np.ndarray, window: int) -> np.ndarray:
    """
    Classic RSI using Wilder smoothing (causal).
    Output in [0, 100].
    """
    n = close.shape[0]
    out = np.empty(n, dtype=np.float64)

    gain = 0.0
    loss = 0.0

    out[0] = 50.0
    for i in range(1, n):
        chg = close[i] - close[i - 1]
        g = chg if chg > 0 else 0.0
        l = -chg if chg < 0 else 0.0

        if i <= window:
            gain += g
            loss += l
            avg_g = gain / float(i)
            avg_l = loss / float(i)
        else:
            # Wilder smoothing
            avg_g = (avg_g * (window - 1) + g) / float(window)
            avg_l = (avg_l * (window - 1) + l) / float(window)

        if avg_l == 0.0:
            out[i] = 100.0
        else:
            rs = avg_g / avg_l
            out[i] = 100.0 - (100.0 / (1.0 + rs))

    return out


@njit(cache=True)
def vx_percentile(arr: np.ndarray, window: int) -> np.ndarray:
    """
    Rolling percentile rank of current value within trailing window (causal).
    Returns in [0,1].
    NOTE: O(n*window) but OK for offline feature build.
    
    DEPRECATED: Legacy name for backward compatibility. Use `percentile_rank` instead.
    This function is kept as an alias to maintain compatibility with existing code.
    """
    n = arr.shape[0]
    out = np.empty(n, dtype=np.float64)
    
    if window <= 0:
        out[:] = np.nan
        return out

    for i in range(n):
        start = i - window + 1
        if start < 0:
            start = 0
        cur = arr[i]
        cnt = 0
        denom = i - start + 1
        for j in range(start, i + 1):
            if arr[j] <= cur:
                cnt += 1
        out[i] = cnt / float(denom)

    return out


@njit(cache=True)
def ema(arr: np.ndarray, window: int) -> np.ndarray:
    """
    Exponential Moving Average (causal).
    alpha = 2 / (window + 1)
    Uses first value as seed.
    """
    n = arr.shape[0]
    out = np.empty(n, dtype=np.float64)
    if window <= 0:
        out[:] = np.nan
        return out
    alpha = 2.0 / (window + 1.0)
    out[0] = arr[0]
    for i in range(1, n):
        out[i] = alpha * arr[i] + (1.0 - alpha) * out[i - 1]
    return out


@njit(cache=True)
def wma(arr: np.ndarray, window: int) -> np.ndarray:
    """
    Weighted Moving Average (causal) with linear weights.
    Weights: window, window-1, ..., 1.
    Returns NaN for i < window-1.
    """
    n = arr.shape[0]
    out = np.empty(n, dtype=np.float64)
    if window <= 0:
        out[:] = np.nan
        return out
    # compute weight sum
    weight_sum = window * (window + 1) / 2.0
    for i in range(n):
        if i < window - 1:
            out[i] = np.nan
            continue
        s = 0.0
        w = 1.0
        for j in range(i - window + 1, i + 1):
            s += arr[j] * w
            w += 1.0
        out[i] = s / weight_sum
    return out


@njit(cache=True)
def rolling_stdev(arr: np.ndarray, window: int) -> np.ndarray:
    """
    Rolling sample standard deviation (causal, ddof=1).
    Returns NaN for i < window-1.
    Uses Welford's online algorithm for variance.
    """
    n = arr.shape[0]
    out = np.empty(n, dtype=np.float64)
    if window <= 1:
        out[:] = 0.0
        return out
    for i in range(n):
        if i < window - 1:
            out[i] = np.nan
            continue
        # compute mean
        mean = 0.0
        for j in range(i - window + 1, i + 1):
            mean += arr[j]
        mean /= window
        # compute variance
        var = 0.0
        for j in range(i - window + 1, i + 1):
            diff = arr[j] - mean
            var += diff * diff
        var /= (window - 1)  # sample variance
        out[i] = np.sqrt(var)
    return out


@njit(cache=True)
def zscore(arr: np.ndarray, window: int) -> np.ndarray:
    """
    Z‑score: (arr[i] - SMA(arr, window)) / STDEV(arr, window).
    Returns NaN where stdev = 0.
    """
    n = arr.shape[0]
    out = np.empty(n, dtype=np.float64)
    if window <= 1:
        out[:] = np.nan
        return out
    # compute SMA and STDEV
    sma_vals = sma(arr, window)
    stdev_vals = rolling_stdev(arr, window)
    for i in range(n):
        if i < window - 1:
            out[i] = np.nan
            continue
        if stdev_vals[i] == 0.0:
            out[i] = np.nan
        else:
            out[i] = (arr[i] - sma_vals[i]) / stdev_vals[i]
    return out


@njit(cache=True)
def momentum(arr: np.ndarray, window: int) -> np.ndarray:
    """
    Momentum: arr[i] - arr[i - window].
    Returns NaN for i < window.
    """
    n = arr.shape[0]
    out = np.empty(n, dtype=np.float64)
    if window <= 0:
        out[:] = np.nan
        return out
    for i in range(n):
        if i < window:
            out[i] = np.nan
        else:
            out[i] = arr[i] - arr[i - window]
    return out


@njit(cache=True)
def roc(arr: np.ndarray, window: int) -> np.ndarray:
    """
    Rate of Change: (arr[i] - arr[i - window]) / arr[i - window] * 100.
    Returns NaN where divisor is zero.
    """
    n = arr.shape[0]
    out = np.empty(n, dtype=np.float64)
    if window <= 0:
        out[:] = np.nan
        return out
    for i in range(n):
        if i < window:
            out[i] = np.nan
            continue
        divisor = arr[i - window]
        if divisor == 0.0:
            out[i] = np.nan
        else:
            out[i] = ((arr[i] - divisor) / divisor) * 100.0
    return out


@njit(cache=True)
def bbands_pb(arr: np.ndarray, window: int) -> np.ndarray:
    """
    Bollinger Bands %b: (close - lower) / (upper - lower).
    
    Where:
        sma = simple moving average of arr over window
        std = standard deviation of arr over window
        upper = sma + 2.0 * std
        lower = sma - 2.0 * std
    
    Uses fixed multiplier k=2.0.
    Returns NaN for indices < window-1 (warmup) and when denominator == 0.
    """
    n = arr.shape[0]
    out = np.empty(n, dtype=np.float64)
    if window <= 1:
        out[:] = np.nan
        return out
    
    sma_vals = sma(arr, window)
    stdev_vals = rolling_stdev(arr, window)
    
    for i in range(n):
        if i < window - 1:
            out[i] = np.nan
            continue
        upper = sma_vals[i] + 2.0 * stdev_vals[i]
        lower = sma_vals[i] - 2.0 * stdev_vals[i]
        out[i] = safe_div(arr[i] - lower, upper - lower)
    
    return out


@njit(cache=True)
def bbands_width(arr: np.ndarray, window: int) -> np.ndarray:
    """
    Bollinger Bands width: (upper - lower) / sma.
    
    Where:
        sma = simple moving average of arr over window
        std = standard deviation of arr over window
        upper = sma + 2.0 * std
        lower = sma - 2.0 * std
    
    Uses fixed multiplier k=2.0.
    Returns NaN for indices < window-1 (warmup) and when sma == 0.
    """
    n = arr.shape[0]
    out = np.empty(n, dtype=np.float64)
    if window <= 1:
        out[:] = np.nan
        return out
    
    sma_vals = sma(arr, window)
    stdev_vals = rolling_stdev(arr, window)
    
    for i in range(n):
        if i < window - 1:
            out[i] = np.nan
            continue
        upper = sma_vals[i] + 2.0 * stdev_vals[i]
        lower = sma_vals[i] - 2.0 * stdev_vals[i]
        out[i] = safe_div(upper - lower, sma_vals[i])
    
    return out


@njit(cache=True)
def atr_channel_upper(high: np.ndarray, low: np.ndarray, close: np.ndarray, window: int) -> np.ndarray:
    """
    ATR Channel upper band: SMA(close, window) + ATR(high, low, close, window).
    
    Returns NaN for indices < window-1 (warmup).
    """
    n = close.shape[0]
    out = np.empty(n, dtype=np.float64)
    if window <= 0:
        out[:] = np.nan
        return out
    
    sma_vals = sma(close, window)
    atr_vals = atr_wilder(high, low, close, window)
    
    for i in range(n):
        if i < window - 1:
            out[i] = np.nan
        else:
            out[i] = sma_vals[i] + atr_vals[i]
    
    return out


@njit(cache=True)
def atr_channel_lower(high: np.ndarray, low: np.ndarray, close: np.ndarray, window: int) -> np.ndarray:
    """
    ATR Channel lower band: SMA(close, window) - ATR(high, low, close, window).
    
    Returns NaN for indices < window-1 (warmup).
    """
    n = close.shape[0]
    out = np.empty(n, dtype=np.float64)
    if window <= 0:
        out[:] = np.nan
        return out
    
    sma_vals = sma(close, window)
    atr_vals = atr_wilder(high, low, close, window)
    
    for i in range(n):
        if i < window - 1:
            out[i] = np.nan
        else:
            out[i] = sma_vals[i] - atr_vals[i]
    
    return out


@njit(cache=True)
def atr_channel_pos(high: np.ndarray, low: np.ndarray, close: np.ndarray, window: int) -> np.ndarray:
    """
    ATR Channel position: (close - lower) / (upper - lower).
    
    Where:
        upper = SMA(close, window) + ATR(high, low, close, window)
        lower = SMA(close, window) - ATR(high, low, close, window)
    
    Returns NaN for indices < window-1 (warmup) and when denominator == 0.
    """
    n = close.shape[0]
    out = np.empty(n, dtype=np.float64)
    if window <= 0:
        out[:] = np.nan
        return out
    
    sma_vals = sma(close, window)
    atr_vals = atr_wilder(high, low, close, window)
    
    for i in range(n):
        if i < window - 1:
            out[i] = np.nan
            continue
        upper = sma_vals[i] + atr_vals[i]
        lower = sma_vals[i] - atr_vals[i]
        out[i] = safe_div(close[i] - lower, upper - lower)
    
    return out


@njit(cache=True)
def donchian_width(high: np.ndarray, low: np.ndarray, close: np.ndarray, window: int) -> np.ndarray:
    """
    Donchian Channel width: (HH - LL) / close.
    
    Where:
        HH = rolling maximum of high over window
        LL = rolling minimum of low over window
    
    Returns NaN for indices < window-1 (warmup) and when close == 0.
    """
    n = close.shape[0]
    out = np.empty(n, dtype=np.float64)
    if window <= 0:
        out[:] = np.nan
        return out
    
    hh_vals = hh(high, window)
    ll_vals = ll(low, window)
    
    for i in range(n):
        if i < window - 1:
            out[i] = np.nan
            continue
        out[i] = safe_div(hh_vals[i] - ll_vals[i], close[i])
    
    return out


@njit(cache=True)
def dist_to_hh(high: np.ndarray, close: np.ndarray, window: int) -> np.ndarray:
    """
    Distance to Highest High: (close / HH) - 1.
    
    Where:
        HH = rolling maximum of high over window
    
    Returns NaN for indices < window-1 (warmup) and when HH == 0.
    """
    n = close.shape[0]
    out = np.empty(n, dtype=np.float64)
    if window <= 0:
        out[:] = np.nan
        return out
    
    hh_vals = hh(high, window)
    
    for i in range(n):
        if i < window - 1:
            out[i] = np.nan
            continue
        ratio = safe_div(close[i], hh_vals[i])
        out[i] = ratio - 1.0
    
    return out


@njit(cache=True)
def dist_to_ll(low: np.ndarray, close: np.ndarray, window: int) -> np.ndarray:
    """
    Distance to Lowest Low: (close / LL) - 1.
    
    Where:
        LL = rolling minimum of low over window
    
    Returns NaN for indices < window-1 (warmup) and when LL == 0.
    """
    n = close.shape[0]
    out = np.empty(n, dtype=np.float64)
    if window <= 0:
        out[:] = np.nan
        return out
    
    ll_vals = ll(low, window)
    
    for i in range(n):
        if i < window - 1:
            out[i] = np.nan
            continue
        ratio = safe_div(close[i], ll_vals[i])
        out[i] = ratio - 1.0
    
    return out


@njit(cache=True)
def percentile_rank(arr: np.ndarray, window: int) -> np.ndarray:
    """
    Rolling percentile rank of current value within trailing window (causal).
    Returns in [0,1].
    NOTE: O(n*window) but OK for offline feature build.
    
    This is the source-agnostic canonical name for the percentile rank indicator.
    The legacy alias `vx_percentile` is deprecated but kept for backward compatibility.
    """
    n = arr.shape[0]
    out = np.empty(n, dtype=np.float64)
    
    if window <= 0:
        out[:] = np.nan
        return out

    for i in range(n):
        start = i - window + 1
        if start < 0:
            start = 0
        cur = arr[i]
        cnt = 0
        denom = i - start + 1
        for j in range(start, i + 1):
            if arr[j] <= cur:
                cnt += 1
        out[i] = cnt / float(denom)

    return out


