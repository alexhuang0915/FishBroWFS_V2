import numpy as np

from FishBroWFS_V2.indicators.numba_indicators import (
    rolling_max,
    rolling_min,
    atr_wilder,
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

