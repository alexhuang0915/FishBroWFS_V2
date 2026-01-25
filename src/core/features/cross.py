from __future__ import annotations

import numpy as np

from .compute import compute_atr_14


def _log_returns(c: np.ndarray) -> np.ndarray:
    n = len(c)
    if n <= 1:
        return np.full(n, np.nan, dtype=np.float64)
    ret = np.full(n, np.nan, dtype=np.float64)
    valid = c > 0
    log_c = np.full(n, np.nan, dtype=np.float64)
    log_c[valid] = np.log(c[valid])
    ret[1:] = log_c[1:] - log_c[:-1]
    return ret


def _rolling_mean_strict(x: np.ndarray, window: int) -> np.ndarray:
    n = len(x)
    out = np.full(n, np.nan, dtype=np.float64)
    if window <= 0 or n == 0:
        return out
    valid = ~np.isnan(x)
    x0 = np.where(valid, x, 0.0)
    csum = np.cumsum(x0, dtype=np.float64)
    ccount = np.cumsum(valid.astype(np.int64))
    for i in range(window - 1, n):
        if i == window - 1:
            count = ccount[i]
            total = csum[i]
        else:
            count = ccount[i] - ccount[i - window]
            total = csum[i] - csum[i - window]
        if count == window:
            out[i] = total / window
    return out


def _rolling_sum_strict(x: np.ndarray, window: int) -> np.ndarray:
    n = len(x)
    out = np.full(n, np.nan, dtype=np.float64)
    if window <= 0 or n == 0:
        return out
    valid = ~np.isnan(x)
    x0 = np.where(valid, x, 0.0)
    csum = np.cumsum(x0, dtype=np.float64)
    ccount = np.cumsum(valid.astype(np.int64))
    for i in range(window - 1, n):
        if i == window - 1:
            count = ccount[i]
            total = csum[i]
        else:
            count = ccount[i] - ccount[i - window]
            total = csum[i] - csum[i - window]
        if count == window:
            out[i] = total
    return out


def _rolling_z_strict(x: np.ndarray, window: int) -> np.ndarray:
    n = len(x)
    out = np.full(n, np.nan, dtype=np.float64)
    if window <= 1 or n == 0:
        return out
    valid = ~np.isnan(x)
    x0 = np.where(valid, x, 0.0)
    csum = np.cumsum(x0, dtype=np.float64)
    csum2 = np.cumsum(x0 * x0, dtype=np.float64)
    ccount = np.cumsum(valid.astype(np.int64))
    for i in range(window - 1, n):
        if i == window - 1:
            count = ccount[i]
            sum_x = csum[i]
            sum_x2 = csum2[i]
        else:
            count = ccount[i] - ccount[i - window]
            sum_x = csum[i] - csum[i - window]
            sum_x2 = csum2[i] - csum2[i - window]
        if count != window:
            continue
        mean = sum_x / window
        var = (sum_x2 / window) - (mean * mean)
        if var <= 0:
            continue
        std = np.sqrt(var)
        out[i] = (x[i] - mean) / std
    return out


def _rolling_corr_strict(x: np.ndarray, y: np.ndarray, window: int) -> np.ndarray:
    n = len(x)
    out = np.full(n, np.nan, dtype=np.float64)
    if window <= 1 or n == 0:
        return out
    valid = (~np.isnan(x)) & (~np.isnan(y))
    x0 = np.where(valid, x, 0.0)
    y0 = np.where(valid, y, 0.0)
    csum_x = np.cumsum(x0, dtype=np.float64)
    csum_y = np.cumsum(y0, dtype=np.float64)
    csum_x2 = np.cumsum(x0 * x0, dtype=np.float64)
    csum_y2 = np.cumsum(y0 * y0, dtype=np.float64)
    csum_xy = np.cumsum(x0 * y0, dtype=np.float64)
    ccount = np.cumsum(valid.astype(np.int64))
    for i in range(window - 1, n):
        if i == window - 1:
            count = ccount[i]
            sum_x = csum_x[i]
            sum_y = csum_y[i]
            sum_x2 = csum_x2[i]
            sum_y2 = csum_y2[i]
            sum_xy = csum_xy[i]
        else:
            count = ccount[i] - ccount[i - window]
            sum_x = csum_x[i] - csum_x[i - window]
            sum_y = csum_y[i] - csum_y[i - window]
            sum_x2 = csum_x2[i] - csum_x2[i - window]
            sum_y2 = csum_y2[i] - csum_y2[i - window]
            sum_xy = csum_xy[i] - csum_xy[i - window]
        if count != window:
            continue
        mean_x = sum_x / window
        mean_y = sum_y / window
        var_x = (sum_x2 / window) - (mean_x * mean_x)
        var_y = (sum_y2 / window) - (mean_y * mean_y)
        if var_x <= 0 or var_y <= 0:
            continue
        cov = (sum_xy / window) - (mean_x * mean_y)
        out[i] = cov / (np.sqrt(var_x) * np.sqrt(var_y))
    return out


def _rolling_ols_strict(x: np.ndarray, y: np.ndarray, window: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Rolling OLS: y = a + b*x, strict NaN propagation.

    Returns (alpha, beta, r2).
    """
    n = len(x)
    alpha = np.full(n, np.nan, dtype=np.float64)
    beta = np.full(n, np.nan, dtype=np.float64)
    r2 = np.full(n, np.nan, dtype=np.float64)
    if window <= 1 or n == 0:
        return alpha, beta, r2

    valid = (~np.isnan(x)) & (~np.isnan(y))
    x0 = np.where(valid, x, 0.0)
    y0 = np.where(valid, y, 0.0)
    ccount = np.cumsum(valid.astype(np.int64))

    csum_x = np.cumsum(x0, dtype=np.float64)
    csum_y = np.cumsum(y0, dtype=np.float64)
    csum_x2 = np.cumsum(x0 * x0, dtype=np.float64)
    csum_y2 = np.cumsum(y0 * y0, dtype=np.float64)
    csum_xy = np.cumsum(x0 * y0, dtype=np.float64)

    for i in range(window - 1, n):
        if i == window - 1:
            count = ccount[i]
            sum_x = csum_x[i]
            sum_y = csum_y[i]
            sum_x2 = csum_x2[i]
            sum_y2 = csum_y2[i]
            sum_xy = csum_xy[i]
        else:
            count = ccount[i] - ccount[i - window]
            sum_x = csum_x[i] - csum_x[i - window]
            sum_y = csum_y[i] - csum_y[i - window]
            sum_x2 = csum_x2[i] - csum_x2[i - window]
            sum_y2 = csum_y2[i] - csum_y2[i - window]
            sum_xy = csum_xy[i] - csum_xy[i - window]
        if count != window:
            continue
        mean_x = sum_x / window
        mean_y = sum_y / window
        var_x = (sum_x2 / window) - (mean_x * mean_x)
        var_y = (sum_y2 / window) - (mean_y * mean_y)
        if var_x <= 0 or var_y <= 0:
            continue
        cov_xy = (sum_xy / window) - (mean_x * mean_y)
        b = cov_xy / var_x
        a = mean_y - b * mean_x
        alpha[i] = a
        beta[i] = b
        r2[i] = (cov_xy * cov_xy) / (var_x * var_y)
    return alpha, beta, r2


def _rolling_resid_std_strict(x: np.ndarray, y: np.ndarray, window: int, alpha: np.ndarray, beta: np.ndarray) -> np.ndarray:
    """
    Residual std (population) for y = alpha + beta*x.
    Strict NaN propagation: if any NaN in window -> NaN.
    """
    n = len(x)
    out = np.full(n, np.nan, dtype=np.float64)
    if window <= 1 or n == 0:
        return out

    valid = (~np.isnan(x)) & (~np.isnan(y))
    x0 = np.where(valid, x, 0.0)
    y0 = np.where(valid, y, 0.0)
    ccount = np.cumsum(valid.astype(np.int64))

    csum_x = np.cumsum(x0, dtype=np.float64)
    csum_y = np.cumsum(y0, dtype=np.float64)
    csum_x2 = np.cumsum(x0 * x0, dtype=np.float64)
    csum_y2 = np.cumsum(y0 * y0, dtype=np.float64)
    csum_xy = np.cumsum(x0 * y0, dtype=np.float64)

    for i in range(window - 1, n):
        a = alpha[i]
        b = beta[i]
        if np.isnan(a) or np.isnan(b):
            continue
        if i == window - 1:
            count = ccount[i]
            sum_x = csum_x[i]
            sum_y = csum_y[i]
            sum_x2 = csum_x2[i]
            sum_y2 = csum_y2[i]
            sum_xy = csum_xy[i]
        else:
            count = ccount[i] - ccount[i - window]
            sum_x = csum_x[i] - csum_x[i - window]
            sum_y = csum_y[i] - csum_y[i - window]
            sum_x2 = csum_x2[i] - csum_x2[i - window]
            sum_y2 = csum_y2[i] - csum_y2[i - window]
            sum_xy = csum_xy[i] - csum_xy[i - window]
        if count != window:
            continue

        # RSS = Σ(y - (a + b x))^2 expanded (population, window points)
        rss = (
            sum_y2
            + (a * a) * window
            + (b * b) * sum_x2
            + 2.0 * a * b * sum_x
            - 2.0 * a * sum_y
            - 2.0 * b * sum_xy
        )
        if rss < 0:
            rss = 0.0
        out[i] = np.sqrt(rss / window)
    return out


def compute_cross_features_v1(
    *,
    o1: np.ndarray,
    h1: np.ndarray,
    l1: np.ndarray,
    c1: np.ndarray,
    o2: np.ndarray,
    h2: np.ndarray,
    l2: np.ndarray,
    c2: np.ndarray,
) -> dict[str, np.ndarray]:
    """
    Compute V1 cross features (B/Core) for aligned data1 vs data2.

    Required: inputs are aligned and same length.
    """
    n = len(c1)
    for arr, name in [
        (o1, "o1"),
        (h1, "h1"),
        (l1, "l1"),
        (c1, "c1"),
        (o2, "o2"),
        (h2, "h2"),
        (l2, "l2"),
        (c2, "c2"),
    ]:
        if len(arr) != n:
            raise ValueError(f"length mismatch for {name}: {len(arr)} != {n}")

    ret1 = _log_returns(c1)
    ret2 = _log_returns(c2)

    spread_log = np.full(n, np.nan, dtype=np.float64)
    valid_spread = (c1 > 0) & (c2 > 0)
    spread_log[valid_spread] = np.log(c1[valid_spread] / c2[valid_spread])

    spread_log_z_20 = _rolling_z_strict(spread_log, window=20)
    spread_log_z_60 = _rolling_z_strict(spread_log, window=60)
    spread_log_z_120 = _rolling_z_strict(spread_log, window=120)

    rel_ret_1 = ret1 - ret2
    rel_mom_5 = _rolling_sum_strict(rel_ret_1, window=5)
    rel_mom_20 = _rolling_sum_strict(rel_ret_1, window=20)
    rel_mom_60 = _rolling_sum_strict(rel_ret_1, window=60)
    rel_mom_120 = _rolling_sum_strict(rel_ret_1, window=120)

    atr1_14 = compute_atr_14(o1, h1, l1, c1)
    atr2_14 = compute_atr_14(o2, h2, l2, c2)
    rel_vol_ratio = np.full(n, np.nan, dtype=np.float64)
    valid_vol = (~np.isnan(atr1_14)) & (~np.isnan(atr2_14)) & (atr2_14 != 0)
    rel_vol_ratio[valid_vol] = atr1_14[valid_vol] / atr2_14[valid_vol]

    rel_vol_z_20 = _rolling_z_strict(rel_vol_ratio, window=20)
    rel_vol_z_60 = _rolling_z_strict(rel_vol_ratio, window=60)
    rel_vol_z_120 = _rolling_z_strict(rel_vol_ratio, window=120)

    corr_20 = _rolling_corr_strict(ret1, ret2, window=20)
    corr_60 = _rolling_corr_strict(ret1, ret2, window=60)
    corr_120 = _rolling_corr_strict(ret1, ret2, window=120)
    corr_abs_20 = np.abs(corr_20)
    corr_abs_60 = np.abs(corr_60)
    corr_abs_120 = np.abs(corr_120)

    alpha_20, beta_20, r2_20 = _rolling_ols_strict(ret2, ret1, window=20)
    alpha_60, beta_60, r2_60 = _rolling_ols_strict(ret2, ret1, window=60)
    alpha_120, beta_120, r2_120 = _rolling_ols_strict(ret2, ret1, window=120)
    resid_std_60 = _rolling_resid_std_strict(ret2, ret1, window=60, alpha=alpha_60, beta=beta_60)
    resid_std_120 = _rolling_resid_std_strict(ret2, ret1, window=120, alpha=alpha_120, beta=beta_120)

    vol_atr1_14 = atr1_14
    vol_atr2_14 = atr2_14
    vol_atr_spread = atr1_14 - atr2_14
    vol_atr_spread_z_20 = _rolling_z_strict(vol_atr_spread, window=20)
    vol_atr_spread_z_60 = _rolling_z_strict(vol_atr_spread, window=60)
    vol_atr_spread_z_120 = _rolling_z_strict(vol_atr_spread, window=120)

    return {
        "spread_log": spread_log,
        "spread_log_z_20": spread_log_z_20,
        "spread_log_z_60": spread_log_z_60,
        "spread_log_z_120": spread_log_z_120,
        "rel_ret_1": rel_ret_1,
        "rel_mom_5": rel_mom_5,
        "rel_mom_20": rel_mom_20,
        "rel_mom_60": rel_mom_60,
        "rel_mom_120": rel_mom_120,
        "rel_vol_ratio": rel_vol_ratio,
        "rel_vol_z_20": rel_vol_z_20,
        "rel_vol_z_60": rel_vol_z_60,
        "rel_vol_z_120": rel_vol_z_120,
        "corr_20": corr_20,
        "corr_60": corr_60,
        "corr_120": corr_120,
        "corr_abs_20": corr_abs_20,
        "corr_abs_60": corr_abs_60,
        "corr_abs_120": corr_abs_120,
        "beta_20": beta_20,
        "beta_60": beta_60,
        "beta_120": beta_120,
        "alpha_60": alpha_60,
        "alpha_120": alpha_120,
        "r2_60": r2_60,
        "r2_120": r2_120,
        "resid_std_60": resid_std_60,
        "resid_std_120": resid_std_120,
        "vol_atr1_14": vol_atr1_14,
        "vol_atr2_14": vol_atr2_14,
        "vol_atr_spread": vol_atr_spread,
        "vol_atr_spread_z_20": vol_atr_spread_z_20,
        "vol_atr_spread_z_60": vol_atr_spread_z_60,
        "vol_atr_spread_z_120": vol_atr_spread_z_120,
    }
