from __future__ import annotations

import numpy as np
import pytest

from FishBroWFS_V2.stage0.proxies import (
    activity_proxy,
    activity_proxy_nb,
    activity_proxy_py,
    trend_proxy,
    trend_proxy_nb,
    trend_proxy_py,
    vol_proxy,
    vol_proxy_nb,
    vol_proxy_py,
)

try:
    import numba as nb

    NUMBA_AVAILABLE = nb is not None
except Exception:
    NUMBA_AVAILABLE = False


def _generate_ohlc_trend(n: int, seed: int = 42) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Generate upward trend OHLC data."""
    rng = np.random.default_rng(seed)
    close = np.linspace(100.0, 200.0, n, dtype=np.float64)
    noise = rng.standard_normal(n) * 2.0
    close = close + noise
    high = close + np.abs(rng.standard_normal(n)) * 1.0
    low = close - np.abs(rng.standard_normal(n)) * 1.0
    open_ = (high + low) / 2 + rng.standard_normal(n) * 0.5
    high = np.maximum(high, np.maximum(open_, close))
    low = np.minimum(low, np.minimum(open_, close))
    return open_, high, low, close


def _generate_ohlc_sine(n: int, seed: int = 999) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Generate oscillating (sine wave) OHLC data."""
    rng = np.random.default_rng(seed)
    t = np.linspace(0, 4 * np.pi, n)
    close = 100.0 + 20.0 * np.sin(t) + rng.standard_normal(n) * 1.0
    high = close + np.abs(rng.standard_normal(n)) * 1.0
    low = close - np.abs(rng.standard_normal(n)) * 1.0
    open_ = (high + low) / 2 + rng.standard_normal(n) * 0.5
    high = np.maximum(high, np.maximum(open_, close))
    low = np.minimum(low, np.minimum(open_, close))
    return open_, high, low, close


# ============================================================================
# Parity Tests (nb vs py)
# ============================================================================


def test_trend_proxy_parity() -> None:
    """Test parity between Numba and Python versions of trend_proxy."""
    if not NUMBA_AVAILABLE:
        pytest.skip("Numba not available")

    open_, high, low, close = _generate_ohlc_trend(500, seed=42)

    # Generate random params
    rng = np.random.default_rng(123)
    n_params = 200
    params = np.empty((n_params, 2), dtype=np.float64)
    params[:, 0] = rng.integers(5, 50, size=n_params)  # fast
    params[:, 1] = rng.integers(20, 100, size=n_params)  # slow

    scores_nb = trend_proxy_nb(open_, high, low, close, params)
    scores_py = trend_proxy_py(open_, high, low, close, params)

    assert scores_nb.shape == scores_py.shape == (n_params,)

    # Check finite scores match
    finite_mask = np.isfinite(scores_py)
    assert np.all(np.isfinite(scores_py[finite_mask]))
    assert np.allclose(scores_nb[finite_mask], scores_py[finite_mask], rtol=0, atol=1e-12)

    # Check -inf matches
    inf_mask = ~finite_mask
    assert np.all(np.isinf(scores_nb[inf_mask]))
    assert np.all(np.isinf(scores_py[inf_mask]))


def test_vol_proxy_parity() -> None:
    """Test parity between Numba and Python versions of vol_proxy."""
    if not NUMBA_AVAILABLE:
        pytest.skip("Numba not available")

    open_, high, low, close = _generate_ohlc_trend(500, seed=42)

    # Generate random params
    rng = np.random.default_rng(456)
    n_params = 200
    params = np.empty((n_params, 2), dtype=np.float64)
    params[:, 0] = rng.integers(5, 50, size=n_params)  # atr_len
    params[:, 1] = rng.uniform(0.2, 1.5, size=n_params)  # stop_mult

    scores_nb = vol_proxy_nb(open_, high, low, close, params)
    scores_py = vol_proxy_py(open_, high, low, close, params)

    assert scores_nb.shape == scores_py.shape == (n_params,)

    finite_mask = np.isfinite(scores_py)
    assert np.all(np.isfinite(scores_py[finite_mask]))
    assert np.allclose(scores_nb[finite_mask], scores_py[finite_mask], rtol=0, atol=1e-12)

    inf_mask = ~finite_mask
    assert np.all(np.isinf(scores_nb[inf_mask]))
    assert np.all(np.isinf(scores_py[inf_mask]))


def test_activity_proxy_parity() -> None:
    """Test parity between Numba and Python versions of activity_proxy."""
    if not NUMBA_AVAILABLE:
        pytest.skip("Numba not available")

    open_, high, low, close = _generate_ohlc_trend(500, seed=42)

    # Generate random params
    rng = np.random.default_rng(789)
    n_params = 200
    params = np.empty((n_params, 1), dtype=np.float64)
    params[:, 0] = rng.integers(5, 50, size=n_params)  # channel_len

    scores_nb = activity_proxy_nb(open_, high, low, close, params)
    scores_py = activity_proxy_py(open_, high, low, close, params)

    assert scores_nb.shape == scores_py.shape == (n_params,)

    finite_mask = np.isfinite(scores_py)
    assert np.all(np.isfinite(scores_py[finite_mask]))
    # Activity proxy uses log1p, so allow slightly larger tolerance
    assert np.allclose(scores_nb[finite_mask], scores_py[finite_mask], rtol=0, atol=1e-10)

    inf_mask = ~finite_mask
    assert np.all(np.isinf(scores_nb[inf_mask]))
    assert np.all(np.isinf(scores_py[inf_mask]))


# ============================================================================
# Semantic Tests
# ============================================================================


def test_trend_proxy_sanity_upward_trend() -> None:
    """Test that upward trend produces positive trend_score."""
    open_, high, low, close = _generate_ohlc_trend(500, seed=42)

    # Good params: fast < slow, reasonable values
    params_good = np.array([[10.0, 30.0], [15.0, 50.0]], dtype=np.float64)
    scores_good = trend_proxy(open_, high, low, close, params_good)

    # Bad params: inverted (fast >= slow)
    params_bad = np.array([[30.0, 10.0], [50.0, 15.0]], dtype=np.float64)
    scores_bad = trend_proxy(open_, high, low, close, params_bad)

    assert np.all(np.isfinite(scores_good))
    assert np.all(np.isfinite(scores_bad))

    # Good params should score better (or at least not worse) than inverted
    # In upward trend, fast < slow should give positive score
    assert scores_good[0] > 0.0 or scores_good[1] > 0.0


def test_activity_proxy_sanity_oscillation_vs_trend() -> None:
    """Test that oscillating sequence has higher activity than trend."""
    # Generate oscillating data
    open_sine, high_sine, low_sine, close_sine = _generate_ohlc_sine(500, seed=999)
    # Generate trend data
    open_trend, high_trend, low_trend, close_trend = _generate_ohlc_trend(500, seed=42)

    # Same params for both (channel_len only)
    params = np.array([[10.0], [15.0]], dtype=np.float64)

    scores_sine = activity_proxy(open_sine, high_sine, low_sine, close_sine, params)
    scores_trend = activity_proxy(open_trend, high_trend, low_trend, close_trend, params)

    assert np.all(np.isfinite(scores_sine))
    assert np.all(np.isfinite(scores_trend))

    # Oscillating sequence should have higher activity (more breakout triggers)
    assert np.mean(scores_sine) > np.mean(scores_trend)


def test_vol_proxy_sanity_positive_scores() -> None:
    """Test that vol_proxy returns finite scores for valid params."""
    open_, high, low, close = _generate_ohlc_trend(500, seed=42)

    params = np.array([[10.0, 0.5], [20.0, 1.0], [30.0, 1.5]], dtype=np.float64)  # [atr_len, stop_mult]
    scores = vol_proxy(open_, high, low, close, params)

    assert np.all(np.isfinite(scores))
    # Vol proxy scores are negative (-log1p(stop_mean)), but finite
    assert np.all(scores <= 0.0)  # Scores are negative (closer to 0 is better)


def test_proxies_reject_invalid_params() -> None:
    """Test that all proxies return -inf for invalid params."""
    open_, high, low, close = _generate_ohlc_trend(100, seed=42)

    # Invalid: too large
    params_invalid = np.array([[1000.0, 2000.0]], dtype=np.float64)

    scores_trend = trend_proxy(open_, high, low, close, params_invalid)
    params_activity_invalid = np.array([[1000.0]], dtype=np.float64)
    scores_activity = activity_proxy(open_, high, low, close, params_activity_invalid)

    assert np.all(np.isinf(scores_trend))
    assert np.all(np.isinf(scores_activity))
    assert np.all(scores_trend < 0)
    assert np.all(scores_activity < 0)

    # Invalid: zero or negative
    params_invalid2 = np.array([[0.0, 10.0], [-5.0, 10.0]], dtype=np.float64)

    scores_trend2 = trend_proxy(open_, high, low, close, params_invalid2)
    params_activity_invalid2 = np.array([[0.0], [-5.0]], dtype=np.float64)
    scores_activity2 = activity_proxy(open_, high, low, close, params_activity_invalid2)

    assert np.all(np.isinf(scores_trend2))
    assert np.all(np.isinf(scores_activity2))

    # Vol proxy: invalid
    params_vol_invalid = np.array([[1000.0, 0.5], [500.0, -1.0]], dtype=np.float64)  # [atr_len, stop_mult]
    scores_vol = vol_proxy(open_, high, low, close, params_vol_invalid)
    assert np.all(np.isinf(scores_vol))
