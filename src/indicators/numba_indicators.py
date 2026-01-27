"""
Numba-accelerated technical indicators.
"""
import numpy as np
from numba import njit

@njit(cache=True)
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

@njit(cache=True)
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

@njit(cache=True)
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

@njit(cache=True)
def ema(arr: np.ndarray, window: int) -> np.ndarray:
    n = arr.shape[0]
    out = np.full(n, np.nan, dtype=np.float64)
    if window <= 0 or n == 0:
        return out
    if window == 1:
        for i in range(n):
            out[i] = arr[i]
        return out
    # Seed with SMA of first window
    if n < window:
        return out
    s = 0.0
    for i in range(window):
        s += arr[i]
    out[window - 1] = s / window
    alpha = 2.0 / (window + 1.0)
    for i in range(window, n):
        out[i] = (arr[i] * alpha) + (out[i - 1] * (1.0 - alpha))
    return out

@njit(cache=True)
def hh(arr: np.ndarray, window: int) -> np.ndarray:
    return rolling_max(arr, window)

@njit(cache=True)
def ll(arr: np.ndarray, window: int) -> np.ndarray:
    return rolling_min(arr, window)

@njit(cache=True)
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

@njit(cache=True)
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

@njit(cache=True)
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

@njit(cache=True)
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

@njit(cache=True)
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

@njit(cache=True)
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

@njit(cache=True)
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

@njit(cache=True)
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

@njit(cache=True)
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

@njit(cache=True)
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

@njit(cache=True)
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

@njit(cache=True)
def rsi_wilder(arr: np.ndarray, window: int) -> np.ndarray:
    n = arr.shape[0]
    out = np.full(n, np.nan, dtype=np.float64)
    if window <= 0 or n <= window:
        return out
    
    diff = np.zeros(n, dtype=np.float64)
    for i in range(1, n):
        diff[i] = arr[i] - arr[i - 1]
    
    gain = np.zeros(n, dtype=np.float64)
    loss = np.zeros(n, dtype=np.float64)
    for i in range(1, n):
        if diff[i] > 0:
            gain[i] = diff[i]
        else:
            loss[i] = -diff[i]
            
    # Initial seed: SMA
    avg_gain = 0.0
    avg_loss = 0.0
    for i in range(1, window + 1):
        avg_gain += gain[i]
        avg_loss += loss[i]
    avg_gain /= window
    avg_loss /= window
    
    if avg_loss == 0:
        out[window] = 100.0 if avg_gain > 0 else 50.0
    else:
        rs = avg_gain / avg_loss
        out[window] = 100.0 - (100.0 / (1.0 + rs))
        
    # Wilder smoothing (RMA)
    for i in range(window + 1, n):
        avg_gain = (avg_gain * (window - 1) + gain[i]) / window
        avg_loss = (avg_loss * (window - 1) + loss[i]) / window
        
        if avg_loss == 0:
            out[i] = 100.0 if avg_gain > 0 else 50.0
        else:
            rs = avg_gain / avg_loss
            out[i] = 100.0 - (100.0 / (1.0 + rs))
    return out

@njit(cache=True)
def adx_wilder(high: np.ndarray, low: np.ndarray, close: np.ndarray, window: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    n = close.shape[0]
    adx = np.full(n, np.nan, dtype=np.float64)
    di_plus = np.full(n, np.nan, dtype=np.float64)
    di_minus = np.full(n, np.nan, dtype=np.float64)
    
    if window <= 1 or n < window * 2:
        return adx, di_plus, di_minus
        
    up_move = np.zeros(n, dtype=np.float64)
    down_move = np.zeros(n, dtype=np.float64)
    for i in range(1, n):
        up_move[i] = high[i] - high[i - 1]
        down_move[i] = low[i - 1] - low[i]
        
    plus_dm = np.zeros(n, dtype=np.float64)
    minus_dm = np.zeros(n, dtype=np.float64)
    for i in range(1, n):
        if up_move[i] > down_move[i] and up_move[i] > 0:
            plus_dm[i] = up_move[i]
        if down_move[i] > up_move[i] and down_move[i] > 0:
            minus_dm[i] = down_move[i]
            
    tr = np.zeros(n, dtype=np.float64)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
        
    # Initial SMA of DM and TR
    smooth_plus = 0.0
    smooth_minus = 0.0
    smooth_tr = 0.0
    for i in range(1, window + 1):
        smooth_plus += plus_dm[i]
        smooth_minus += minus_dm[i]
        smooth_tr += tr[i]
        
    if smooth_tr > 0:
        di_plus[window] = 100.0 * smooth_plus / smooth_tr
        di_minus[window] = 100.0 * smooth_minus / smooth_tr
    else:
        di_plus[window] = 0.0
        di_minus[window] = 0.0
        
    dx = np.zeros(n, dtype=np.float64)
    diff = abs(di_plus[window] - di_minus[window])
    summ = di_plus[window] + di_minus[window]
    dx[window] = 100.0 * diff / summ if summ != 0 else 0.0
    
    # Smooth DM/TR and calc ADX
    for i in range(window + 1, n):
        smooth_plus = (smooth_plus * (window - 1) + plus_dm[i]) / window
        smooth_minus = (smooth_minus * (window - 1) + minus_dm[i]) / window
        smooth_tr = (smooth_tr * (window - 1) + tr[i]) / window
        
        if smooth_tr > 0:
            di_plus[i] = 100.0 * smooth_plus / smooth_tr
            di_minus[i] = 100.0 * smooth_minus / smooth_tr
        else:
            di_plus[i] = 0.0
            di_minus[i] = 0.0
            
        diff = abs(di_plus[i] - di_minus[i])
        summ = di_plus[i] + di_minus[i]
        dx[i] = 100.0 * diff / summ if summ != 0 else 0.0
        
        if i == window * 2 - 1:
            # First ADX is SMA of DX
            dx_sum = 0.0
            for j in range(i - window + 1, i + 1):
                dx_sum += dx[j]
            adx[i] = dx_sum / window
        elif i >= window * 2:
            adx[i] = (adx[i - 1] * (window - 1) + dx[i]) / window
            
    return adx, di_plus, di_minus

@njit(cache=True)
def macd_hist(arr: np.ndarray, fast: int, slow: int, signal: int) -> np.ndarray:
    n = arr.shape[0]
    out = np.full(n, np.nan, dtype=np.float64)
    if n < slow + signal:
        return out
    
    ema_fast = ema(arr, fast)
    ema_slow = ema(arr, slow)
    macd_line = ema_fast - ema_slow
    
    # Signal line is EMA of macd_line
    # Custom EMA for macd_line as it has NaNs at start
    signal_line = np.full(n, np.nan, dtype=np.float64)
    start_idx = slow - 1
    if n < start_idx + signal:
        return out
        
    # Seed Signal SMA
    s = 0.0
    for i in range(start_idx, start_idx + signal):
        s += macd_line[i]
    signal_line[start_idx + signal - 1] = s / signal
    
    alpha = 2.0 / (signal + 1.0)
    for i in range(start_idx + signal, n):
        signal_line[i] = (macd_line[i] * alpha) + (signal_line[i - 1] * (1.0 - alpha))
        
    for i in range(n):
        if not np.isnan(macd_line[i]) and not np.isnan(signal_line[i]):
            out[i] = macd_line[i] - signal_line[i]
    return out

@njit(cache=True)
def roc(arr: np.ndarray, window: int) -> np.ndarray:
    n = arr.shape[0]
    out = np.full(n, np.nan, dtype=np.float64)
    if window <= 0 or n <= window:
        return out
    for i in range(window, n):
        prev = arr[i - window]
        curr = arr[i]
        if prev != 0 and np.isfinite(prev) and np.isfinite(curr):
            out[i] = (curr / prev) - 1.0
    return out

@njit(cache=True)
def rolling_z_strict(arr: np.ndarray, window: int) -> np.ndarray:
    n = arr.shape[0]
    out = np.full(n, np.nan, dtype=np.float64)
    if window <= 1 or n < window:
        return out
    for i in range(window - 1, n):
        # Strict window check
        is_valid = True
        sum_x = 0.0
        sum_x2 = 0.0
        for j in range(i - window + 1, i + 1):
            val = arr[j]
            if not np.isfinite(val):
                is_valid = False
                break
            sum_x += val
            sum_x2 += val * val
        if not is_valid:
            continue
            
        mean = sum_x / window
        var = (sum_x2 / window) - (mean * mean)
        if var <= 0:
            continue
        std = np.sqrt(var)
        out[i] = (arr[i] - mean) / std
    return out
