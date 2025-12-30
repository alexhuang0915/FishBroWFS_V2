import numpy as np

from indicators.numba_indicators import (
    rolling_max,
    rolling_min,
    atr_wilder,
    bbands_pb,
    bbands_width,
    atr_channel_upper,
    atr_channel_lower,
    atr_channel_pos,
    donchian_width,
    dist_to_hh,
    dist_to_ll,
    percentile_rank,
    vx_percentile,
)


def _py_rolling_max(arr: np.ndarray, window: int) -> np.ndarray:
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


def _py_rolling_min(arr: np.ndarray, window: int) -> np.ndarray:
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


def _py_atr_wilder(high, low, close, window):
    n = len(high)
    out = np.full(n, np.nan, dtype=np.float64)
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
    end = window
    out[end - 1] = np.mean(tr[:end])
    for i in range(window, n):
        out[i] = (out[i - 1] * (window - 1) + tr[i]) / window
    return out


def _py_sma(arr: np.ndarray, window: int) -> np.ndarray:
    """Simple moving average."""
    n = arr.shape[0]
    out = np.full(n, np.nan, dtype=np.float64)
    if window <= 0:
        return out
    for i in range(n):
        if i < window - 1:
            out[i] = np.mean(arr[:i + 1])
        else:
            out[i] = np.mean(arr[i - window + 1:i + 1])
    return out


def _py_rolling_stdev(arr: np.ndarray, window: int) -> np.ndarray:
    """Rolling sample standard deviation (ddof=1)."""
    n = arr.shape[0]
    out = np.full(n, np.nan, dtype=np.float64)
    if window <= 1:
        out[:] = 0.0
        return out
    for i in range(n):
        if i < window - 1:
            continue
        slice_arr = arr[i - window + 1:i + 1]
        out[i] = np.std(slice_arr, ddof=1)
    return out


def _py_hh(arr: np.ndarray, window: int) -> np.ndarray:
    return _py_rolling_max(arr, window)


def _py_ll(arr: np.ndarray, window: int) -> np.ndarray:
    return _py_rolling_min(arr, window)


def _py_bbands_pb(arr: np.ndarray, window: int) -> np.ndarray:
    n = arr.shape[0]
    out = np.full(n, np.nan, dtype=np.float64)
    if window <= 1:
        return out
    sma_vals = _py_sma(arr, window)
    stdev_vals = _py_rolling_stdev(arr, window)
    for i in range(n):
        if i < window - 1:
            continue
        upper = sma_vals[i] + 2.0 * stdev_vals[i]
        lower = sma_vals[i] - 2.0 * stdev_vals[i]
        denom = upper - lower
        if denom == 0.0 or np.isinf(denom):
            out[i] = np.nan
        else:
            out[i] = (arr[i] - lower) / denom
    return out


def _py_bbands_width(arr: np.ndarray, window: int) -> np.ndarray:
    n = arr.shape[0]
    out = np.full(n, np.nan, dtype=np.float64)
    if window <= 1:
        return out
    sma_vals = _py_sma(arr, window)
    stdev_vals = _py_rolling_stdev(arr, window)
    for i in range(n):
        if i < window - 1:
            continue
        upper = sma_vals[i] + 2.0 * stdev_vals[i]
        lower = sma_vals[i] - 2.0 * stdev_vals[i]
        denom = sma_vals[i]
        if denom == 0.0 or np.isinf(denom):
            out[i] = np.nan
        else:
            out[i] = (upper - lower) / denom
    return out


def _py_atr_channel_upper(high: np.ndarray, low: np.ndarray, close: np.ndarray, window: int) -> np.ndarray:
    n = close.shape[0]
    out = np.full(n, np.nan, dtype=np.float64)
    if window <= 0:
        return out
    sma_vals = _py_sma(close, window)
    atr_vals = _py_atr_wilder(high, low, close, window)
    for i in range(n):
        if i < window - 1:
            continue
        out[i] = sma_vals[i] + atr_vals[i]
    return out


def _py_atr_channel_lower(high: np.ndarray, low: np.ndarray, close: np.ndarray, window: int) -> np.ndarray:
    n = close.shape[0]
    out = np.full(n, np.nan, dtype=np.float64)
    if window <= 0:
        return out
    sma_vals = _py_sma(close, window)
    atr_vals = _py_atr_wilder(high, low, close, window)
    for i in range(n):
        if i < window - 1:
            continue
        out[i] = sma_vals[i] - atr_vals[i]
    return out


def _py_atr_channel_pos(high: np.ndarray, low: np.ndarray, close: np.ndarray, window: int) -> np.ndarray:
    n = close.shape[0]
    out = np.full(n, np.nan, dtype=np.float64)
    if window <= 0:
        return out
    sma_vals = _py_sma(close, window)
    atr_vals = _py_atr_wilder(high, low, close, window)
    for i in range(n):
        if i < window - 1:
            continue
        upper = sma_vals[i] + atr_vals[i]
        lower = sma_vals[i] - atr_vals[i]
        denom = upper - lower
        if denom == 0.0 or np.isinf(denom):
            out[i] = np.nan
        else:
            out[i] = (close[i] - lower) / denom
    return out


def _py_donchian_width(high: np.ndarray, low: np.ndarray, close: np.ndarray, window: int) -> np.ndarray:
    n = close.shape[0]
    out = np.full(n, np.nan, dtype=np.float64)
    if window <= 0:
        return out
    hh_vals = _py_hh(high, window)
    ll_vals = _py_ll(low, window)
    for i in range(n):
        if i < window - 1:
            continue
        denom = close[i]
        if denom == 0.0 or np.isinf(denom):
            out[i] = np.nan
        else:
            out[i] = (hh_vals[i] - ll_vals[i]) / denom
    return out


def _py_dist_to_hh(high: np.ndarray, close: np.ndarray, window: int) -> np.ndarray:
    n = close.shape[0]
    out = np.full(n, np.nan, dtype=np.float64)
    if window <= 0:
        return out
    hh_vals = _py_hh(high, window)
    for i in range(n):
        if i < window - 1:
            continue
        denom = hh_vals[i]
        if denom == 0.0 or np.isinf(denom):
            out[i] = np.nan
        else:
            out[i] = (close[i] / denom) - 1.0
    return out


def _py_dist_to_ll(low: np.ndarray, close: np.ndarray, window: int) -> np.ndarray:
    n = close.shape[0]
    out = np.full(n, np.nan, dtype=np.float64)
    if window <= 0:
        return out
    ll_vals = _py_ll(low, window)
    for i in range(n):
        if i < window - 1:
            continue
        denom = ll_vals[i]
        if denom == 0.0 or np.isinf(denom):
            out[i] = np.nan
        else:
            out[i] = (close[i] / denom) - 1.0
    return out


def _py_percentile_rank(arr: np.ndarray, window: int) -> np.ndarray:
    n = arr.shape[0]
    out = np.full(n, np.nan, dtype=np.float64)
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


def test_rolling_max_min_consistency():
    arr = np.array([1.0, 3.0, 2.0, 5.0, 4.0], dtype=np.float64)
    w = 3

    mx_py = _py_rolling_max(arr, w)
    mn_py = _py_rolling_min(arr, w)

    mx = rolling_max(arr, w)
    mn = rolling_min(arr, w)

    np.testing.assert_allclose(mx, mx_py, rtol=0.0, atol=0.0)
    np.testing.assert_allclose(mn, mn_py, rtol=0.0, atol=0.0)


def test_atr_wilder_consistency():
    high = np.array([10, 11, 12, 11, 13, 14], dtype=np.float64)
    low = np.array([9, 9, 10, 9, 11, 12], dtype=np.float64)
    close = np.array([9.5, 10.5, 11.0, 10.0, 12.0, 13.0], dtype=np.float64)
    w = 3

    atr_py = _py_atr_wilder(high, low, close, w)
    atr = atr_wilder(high, low, close, w)

    np.testing.assert_allclose(atr, atr_py, rtol=0.0, atol=1e-12)


def test_atr_wilder_window_gt_n_returns_all_nan():
    high = np.array([10, 11], dtype=np.float64)
    low = np.array([9, 10], dtype=np.float64)
    close = np.array([9.5, 10.5], dtype=np.float64)
    atr = atr_wilder(high, low, close, 999)
    assert atr.shape == (2,)
    assert np.all(np.isnan(atr))


def test_bbands_pb_consistency():
    arr = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 4.0, 3.0, 2.0, 1.0], dtype=np.float64)
    w = 5
    py = _py_bbands_pb(arr, w)
    nb = bbands_pb(arr, w)
    np.testing.assert_allclose(nb, py, rtol=1e-12, atol=1e-12)


def test_bbands_width_consistency():
    arr = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 4.0, 3.0, 2.0, 1.0], dtype=np.float64)
    w = 5
    py = _py_bbands_width(arr, w)
    nb = bbands_width(arr, w)
    np.testing.assert_allclose(nb, py, rtol=1e-12, atol=1e-12)


def test_atr_channel_upper_consistency():
    high = np.array([10, 11, 12, 11, 13, 14], dtype=np.float64)
    low = np.array([9, 9, 10, 9, 11, 12], dtype=np.float64)
    close = np.array([9.5, 10.5, 11.0, 10.0, 12.0, 13.0], dtype=np.float64)
    w = 3
    py = _py_atr_channel_upper(high, low, close, w)
    nb = atr_channel_upper(high, low, close, w)
    np.testing.assert_allclose(nb, py, rtol=1e-12, atol=1e-12)


def test_atr_channel_lower_consistency():
    high = np.array([10, 11, 12, 11, 13, 14], dtype=np.float64)
    low = np.array([9, 9, 10, 9, 11, 12], dtype=np.float64)
    close = np.array([9.5, 10.5, 11.0, 10.0, 12.0, 13.0], dtype=np.float64)
    w = 3
    py = _py_atr_channel_lower(high, low, close, w)
    nb = atr_channel_lower(high, low, close, w)
    np.testing.assert_allclose(nb, py, rtol=1e-12, atol=1e-12)


def test_atr_channel_pos_consistency():
    high = np.array([10, 11, 12, 11, 13, 14], dtype=np.float64)
    low = np.array([9, 9, 10, 9, 11, 12], dtype=np.float64)
    close = np.array([9.5, 10.5, 11.0, 10.0, 12.0, 13.0], dtype=np.float64)
    w = 3
    py = _py_atr_channel_pos(high, low, close, w)
    nb = atr_channel_pos(high, low, close, w)
    np.testing.assert_allclose(nb, py, rtol=1e-12, atol=1e-12)


def test_donchian_width_consistency():
    high = np.array([10, 11, 12, 11, 13, 14], dtype=np.float64)
    low = np.array([9, 9, 10, 9, 11, 12], dtype=np.float64)
    close = np.array([9.5, 10.5, 11.0, 10.0, 12.0, 13.0], dtype=np.float64)
    w = 3
    py = _py_donchian_width(high, low, close, w)
    nb = donchian_width(high, low, close, w)
    np.testing.assert_allclose(nb, py, rtol=1e-12, atol=1e-12)


def test_dist_to_hh_consistency():
    high = np.array([10, 11, 12, 11, 13, 14], dtype=np.float64)
    close = np.array([9.5, 10.5, 11.0, 10.0, 12.0, 13.0], dtype=np.float64)
    w = 3
    py = _py_dist_to_hh(high, close, w)
    nb = dist_to_hh(high, close, w)
    np.testing.assert_allclose(nb, py, rtol=1e-12, atol=1e-12)


def test_dist_to_ll_consistency():
    low = np.array([9, 9, 10, 9, 11, 12], dtype=np.float64)
    close = np.array([9.5, 10.5, 11.0, 10.0, 12.0, 13.0], dtype=np.float64)
    w = 3
    py = _py_dist_to_ll(low, close, w)
    nb = dist_to_ll(low, close, w)
    np.testing.assert_allclose(nb, py, rtol=1e-12, atol=1e-12)


def test_percentile_rank_consistency():
    arr = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 4.0, 3.0, 2.0, 1.0], dtype=np.float64)
    w = 5
    py = _py_percentile_rank(arr, w)
    nb = percentile_rank(arr, w)
    np.testing.assert_allclose(nb, py, rtol=1e-12, atol=1e-12)


def test_vx_percentile_equals_percentile_rank():
    arr = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 4.0, 3.0, 2.0, 1.0], dtype=np.float64)
    w = 5
    vx = vx_percentile(arr, w)
    pr = percentile_rank(arr, w)
    np.testing.assert_allclose(vx, pr, rtol=0.0, atol=0.0)


def test_edge_cases():
    # Test window=0
    arr = np.array([1.0, 2.0, 3.0], dtype=np.float64)
    high = np.array([1.5, 2.5, 3.5], dtype=np.float64)
    low = np.array([0.5, 1.5, 2.5], dtype=np.float64)
    close = np.array([1.0, 2.0, 3.0], dtype=np.float64)
    
    # Single-array functions
    for func in [bbands_pb, bbands_width, percentile_rank, vx_percentile]:
        result = func(arr, 0)
        assert np.all(np.isnan(result))
    
    # Three-array functions (high, low, close, window)
    for func in [atr_channel_upper, atr_channel_lower, atr_channel_pos, donchian_width]:
        result = func(high, low, close, 0)
        assert np.all(np.isnan(result))
    
    # Two-array functions
    result = dist_to_hh(high, close, 0)
    assert np.all(np.isnan(result))
    result = dist_to_ll(low, close, 0)
    assert np.all(np.isnan(result))
    
    # Test window larger than array length
    result = atr_wilder(high, low, close, 10)
    assert np.all(np.isnan(result))
    
    # Test division by zero
    zero_arr = np.array([0.0, 0.0, 0.0], dtype=np.float64)
    result = bbands_width(zero_arr, 2)
    assert np.all(np.isnan(result[1:]))
    
    # Test single element
    single = np.array([5.0], dtype=np.float64)
    result = rolling_max(single, 1)
    # rolling max with window=1 returns the element itself
    assert result[0] == 5.0
