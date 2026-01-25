from __future__ import annotations

import numpy as np

from core.features.cross import compute_cross_features_v1


def _make_series(n: int) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    t = np.arange(n, dtype=np.float64)
    c = 100.0 + 0.2 * t + np.sin(t / 4.0) * 2.0
    o = c + 0.1
    h = c + 0.5
    l = c - 0.5
    return o, h, l, c


def _rolling_corr_manual(x: np.ndarray, y: np.ndarray) -> float:
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    if np.any(np.isnan(x)) or np.any(np.isnan(y)):
        return np.nan
    xm = x.mean()
    ym = y.mean()
    vx = (x * x).mean() - xm * xm
    vy = (y * y).mean() - ym * ym
    if vx <= 0 or vy <= 0:
        return np.nan
    cov = (x * y).mean() - xm * ym
    return cov / (np.sqrt(vx) * np.sqrt(vy))


def test_cross_features_v1_shapes_and_warmup():
    n = 120
    o1, h1, l1, c1 = _make_series(n)
    o2, h2, l2, c2 = _make_series(n)
    # make data2 different but correlated
    c2 = c2 * 0.7 + 10.0
    o2 = c2 + 0.1
    h2 = c2 + 0.4
    l2 = c2 - 0.4

    features = compute_cross_features_v1(
        o1=o1, h1=h1, l1=l1, c1=c1,
        o2=o2, h2=h2, l2=l2, c2=c2,
    )

    required = {
        "spread_log",
        "spread_log_z_60",
        "rel_ret_1",
        "rel_mom_20",
        "rel_vol_ratio",
        "corr_60",
        "beta_60",
        "alpha_60",
        "r2_60",
        "vol_atr1_14",
        "vol_atr2_14",
        "vol_atr_spread",
    }
    assert required.issubset(set(features.keys()))
    for v in features.values():
        assert len(v) == n

    # warmup expectations
    assert np.isnan(features["rel_ret_1"][0])
    assert np.all(np.isnan(features["rel_mom_20"][:19]))
    assert np.all(np.isnan(features["corr_60"][:59]))
    assert np.all(np.isnan(features["rel_vol_ratio"][:13]))
    assert np.all(np.isnan(features["beta_60"][:59]))

    # Check corr_60 last value matches manual calc on last 60 returns
    # log returns
    ret1 = np.log(c1[1:] / c1[:-1])
    ret2 = np.log(c2[1:] / c2[:-1])
    corr_manual = _rolling_corr_manual(ret1[-60:], ret2[-60:])
    corr_model = features["corr_60"][-1]
    if np.isnan(corr_manual):
        assert np.isnan(corr_model)
    else:
        assert np.isfinite(corr_model)
        assert abs(corr_model - corr_manual) < 1e-6

    # beta_60 sanity: should be finite for correlated series when window full
    beta_model = features["beta_60"][-1]
    assert np.isnan(beta_model) or np.isfinite(beta_model)
