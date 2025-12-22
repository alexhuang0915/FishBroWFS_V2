
from __future__ import annotations

import os

import numpy as np
import pytest

from FishBroWFS_V2.pipeline.metrics_schema import (
    METRICS_COL_MAX_DD,
    METRICS_COL_NET_PROFIT,
    METRICS_COL_TRADES,
    METRICS_COLUMN_NAMES,
)
from FishBroWFS_V2.pipeline.runner_grid import run_grid
from FishBroWFS_V2.stage0.proxies import activity_proxy, trend_proxy, vol_proxy

try:
    import numba as nb
except Exception:
    nb = None  # type: ignore


def _rankdata(x: np.ndarray) -> np.ndarray:
    """
    Compute ranks for Spearman correlation (handles ties with average rank).

    Args:
        x: 1D array

    Returns:
        ranks: 1D array of ranks (1-indexed, ties get average rank)
    """
    n = x.shape[0]
    if n == 0:
        return np.empty(0, dtype=np.float64)

    # Get sorted indices
    sorted_indices = np.argsort(x, kind="stable")

    # Compute ranks
    ranks = np.empty(n, dtype=np.float64)
    i = 0
    while i < n:
        # Find all values equal to current value
        j = i
        while j < n - 1 and x[sorted_indices[j]] == x[sorted_indices[j + 1]]:
            j += 1

        # Average rank for this group
        avg_rank = (i + j + 2) / 2.0  # +2 because ranks are 1-indexed

        # Assign ranks
        for k in range(i, j + 1):
            ranks[sorted_indices[k]] = avg_rank

        i = j + 1

    return ranks


def _pearson_corr(x: np.ndarray, y: np.ndarray) -> float:
    """
    Compute Pearson correlation coefficient.

    Args:
        x, y: 1D arrays of same length

    Returns:
        correlation coefficient
    """
    n = x.shape[0]
    if n == 0 or n != y.shape[0]:
        raise ValueError("x and y must have same non-zero length")

    # Compute means
    mx = np.mean(x)
    my = np.mean(y)

    # Compute covariance and variances
    cov = np.sum((x - mx) * (y - my))
    var_x = np.sum((x - mx) ** 2)
    var_y = np.sum((y - my) ** 2)

    # Handle degenerate cases
    if var_x == 0.0 or var_y == 0.0:
        return 0.0

    return cov / np.sqrt(var_x * var_y)


def spearman_corr(x: np.ndarray, y: np.ndarray) -> float:
    """
    Compute Spearman rank correlation coefficient.

    Args:
        x, y: 1D arrays of same length

    Returns:
        Spearman correlation coefficient (rho)
    """
    rx = _rankdata(x)
    ry = _rankdata(y)
    return _pearson_corr(rx, ry)


def _generate_ohlc_for_corr(n: int, seed: int = 42) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """
    Generate OHLC data with regime-switch + jumps for reliable breakout opportunities.
    
    Design:
    - Regime switches every ~250 bars: trending-up, trending-down, mean-reverting/chop
    - Gaussian noise with increased variance
    - Occasional jumps (p=0.01, ±(2~4)*sigma shock)
    - Ensures high/low have clear intrabar range
    """
    rng = np.random.default_rng(seed)
    base_price = 100.0
    regime_period = 250
    
    # Generate regime sequence (0=trend-up, 1=trend-down, 2=chop)
    n_regimes = (n + regime_period - 1) // regime_period
    regime_seed = seed + 10000
    regime_rng = np.random.default_rng(regime_seed)
    regimes = regime_rng.integers(0, 3, size=n_regimes)
    
    # Generate close series
    close = np.empty(n, dtype=np.float64)
    close[0] = base_price
    
    sigma_base = 3.0  # Base noise sigma
    jump_prob = 0.01
    
    for t in range(1, n):
        regime_idx = t // regime_period
        regime = regimes[regime_idx] if regime_idx < len(regimes) else regimes[-1]
        
        # Trend component based on regime
        if regime == 0:  # Trending up
            trend_component = 0.05
        elif regime == 1:  # Trending down
            trend_component = -0.05
        else:  # Chop/mean-reverting
            trend_component = -0.01 * (close[t-1] - base_price) / 10.0
        
        # Gaussian noise
        noise = rng.standard_normal() * sigma_base
        
        # Occasional jump
        if rng.random() < jump_prob:
            jump_magnitude = rng.uniform(2.0, 4.0) * sigma_base
            jump_sign = 1.0 if rng.random() < 0.5 else -1.0
            noise += jump_sign * jump_magnitude
        
        close[t] = close[t-1] + trend_component + noise
    
    # Generate open (prev close with small gap)
    open_ = np.empty(n, dtype=np.float64)
    open_[0] = base_price
    for t in range(1, n):
        gap = rng.standard_normal() * 0.5
        open_[t] = close[t-1] + gap
    
    # Generate high/low with intrabar range
    high = np.empty(n, dtype=np.float64)
    low = np.empty(n, dtype=np.float64)
    base_range = 1.0
    
    for t in range(n):
        # Intrabar range based on noise magnitude
        noise_mag = abs(rng.standard_normal())
        intrabar_range = noise_mag * 2.0 + base_range
        
        # Ensure high >= max(open, close) and low <= min(open, close)
        max_oc = max(open_[t], close[t])
        min_oc = min(open_[t], close[t])
        
        high[t] = max_oc + intrabar_range * 0.5
        low[t] = min_oc - intrabar_range * 0.5
    
    return open_, high, low, close


@pytest.mark.slow
def test_stage0_proxy_spearman_correlation() -> None:
    """
    Test that Stage0 proxy scores have median Spearman ρ ≥ 0.4 with actual PnL.

    This test:
    1. Runs all seeds and computes rho for each non-degenerate seed
    2. Collects all rho values into a list
    3. Uses median rho as the contract (more stable than mean)
    4. Degenerate seeds are skipped but recorded for diagnostics
    5. If all seeds are degenerate, test fails with diagnostic info
    """
    # JIT requirement check: avoid degenerate samples in CI-safe / no-jit environments
    numba_disable_jit_env = os.environ.get("NUMBA_DISABLE_JIT", "").strip() == "1"
    numba_disable_jit_config = False
    if nb is not None:
        numba_disable_jit_config = getattr(nb.config, "DISABLE_JIT", 0) == 1

    if numba_disable_jit_env or numba_disable_jit_config:
        pytest.skip(
            "Spearman correlation test requires JIT-enabled Stage2; run without NUMBA_DISABLE_JIT=1\n"
            "Suggested command: PYTHONDONTWRITEBYTECODE=1 pytest -q -m slow -k spearman -vv"
        )

    SEEDS = [0, 1, 2, 3, 4, 5, 6, 7]
    MAX_TRIES = len(SEEDS)
    MIN_VALID = 4  # Hard gate: require at least 4 valid seeds
    n_bars = 1500
    n_params = 250

    # Track evidence for all seeds (including degenerate)
    seeds_tried = []
    pnl_unique_counts = []
    pnl_mins = []
    pnl_maxs = []
    trades_totals = []
    trades_unique_counts = []
    intent_modes = []
    intents_totals = []
    fills_totals = []
    # Collect rho values for non-degenerate seeds
    rho_values = []
    degenerate_seeds = []
    valid_seeds = []

    for seed in SEEDS:
        seeds_tried.append(seed)

        # Generate OHLC data with current seed
        open_, high, low, close = _generate_ohlc_for_corr(n_bars, seed=seed)

        # Generate random params with deterministic seed (seed + 1000 to avoid collision)
        rng = np.random.default_rng(seed + 1000)

        # Params for kernel: [channel_len, atr_len, stop_mult]
        params_kernel = np.empty((n_params, 3), dtype=np.float64)
        params_kernel[:, 0] = rng.integers(5, 40, size=n_params)  # channel_len (reduced range)
        params_kernel[:, 1] = rng.integers(5, 50, size=n_params)  # atr_len
        params_kernel[:, 2] = rng.uniform(0.2, 1.5, size=n_params)  # stop_mult (reduced range)

        # Params for proxies (aligned with Stage2 kernel params)
        # Trend: [fast, slow] where fast = max(2, floor(channel_len/3)), slow = channel_len
        params_trend = np.empty((n_params, 2), dtype=np.float64)
        params_trend[:, 0] = np.maximum(2, params_kernel[:, 0] // 3)  # fast
        params_trend[:, 1] = params_kernel[:, 0]  # slow = channel_len
        # Activity: [channel_len, atr_len] (atr_len kept for compatibility but not used)
        params_activity = params_kernel[:, :2].copy()
        # Vol: [atr_len, stop_mult]
        params_vol = params_kernel[:, 1:3].copy()

        # Compute proxy scores
        trend_scores = trend_proxy(open_, high, low, close, params_trend)
        vol_scores = vol_proxy(open_, high, low, close, params_vol)
        activity_scores = activity_proxy(open_, high, low, close, params_activity)

        # Filter out -inf scores (invalid params)
        valid_mask = np.isfinite(trend_scores) & np.isfinite(vol_scores) & np.isfinite(activity_scores)

        # Combined proxy score (weights: w1=1.0, w2=0.5, w3=1.0)
        # Adjusted weights: emphasize activity (often strongest for breakout strategies)
        proxy_scores = 1.0 * trend_scores + 0.5 * vol_scores + 1.0 * activity_scores

        # Run minimal backtest to get PnL
        from FishBroWFS_V2.pipeline.runner_grid import run_grid

        result = run_grid(
            open_=open_,
            high=high,
            low=low,
            close=close,
            params_matrix=params_kernel,
            commission=0.0,
            slip=0.0,
            order_qty=1,
            sort_params=False,
            force_close_last=True,
        )

        metrics = result["metrics"]
        pnl = metrics[:, METRICS_COL_NET_PROFIT]  # net_profit column
        trades = metrics[:, METRICS_COL_TRADES]  # trades column

        # Extract perf diagnostic info
        perf = result.get("perf", {})
        intent_mode = perf.get("intent_mode")
        intents_total = perf.get("intents_total")
        fills_total = perf.get("fills_total")

        # Strict diagnostics when trades_sum == 0 (fills exist but trades/pnl = 0)
        trades_sum = float(np.sum(trades))
        if trades_sum == 0.0:
            # Dump metrics diagnostics
            diag_parts = [f"\n[DIAG] seed={seed}: trades_sum=0 but fills_total={fills_total}"]
            diag_parts.append(f"metrics.shape={metrics.shape}")
            diag_parts.append(f"metrics_column_names={METRICS_COLUMN_NAMES}")
            diag_parts.append(f"result.keys()={list(result.keys())}")
            if "metrics_columns" in result:
                diag_parts.append(f"result['metrics_columns']={result.get('metrics_columns')}")

            # First row of metrics
            if metrics.shape[0] > 0:
                n_cols_to_show = min(10, metrics.shape[1])
                diag_parts.append(f"metrics[0, :{n_cols_to_show}]={metrics[0, :n_cols_to_show].tolist()}")

            # Min/max of first few columns (with column names)
            n_cols_to_check = min(5, metrics.shape[1])
            for col_idx in range(n_cols_to_check):
                col_data = metrics[:, col_idx]
                col_name = METRICS_COLUMN_NAMES[col_idx] if col_idx < len(METRICS_COLUMN_NAMES) else f"col{col_idx}"
                diag_parts.append(
                    f"metrics[:, {col_idx}] ({col_name}): min={np.min(col_data):.6f}, max={np.max(col_data):.6f}"
                )

            # Inspect fills payload
            if "fills" in result:
                fills_list = result["fills"]
                if isinstance(fills_list, list):
                    diag_parts.append(f"fills (list): len={len(fills_list)}")
                    if len(fills_list) > 0:
                        diag_parts.append(f"fills[0]={repr(fills_list[0])} (type={type(fills_list[0])})")
                    if len(fills_list) > 1:
                        diag_parts.append(f"fills[1]={repr(fills_list[1])}")
                    if len(fills_list) > 2:
                        diag_parts.append(f"fills[2]={repr(fills_list[2])}")
            elif "fills_arr" in result:
                fills_arr = result["fills_arr"]
                diag_parts.append(f"fills_arr: shape={fills_arr.shape}, dtype={fills_arr.dtype}")
                if fills_arr.shape[0] > 0:
                    n_rows = min(5, fills_arr.shape[0])
                    diag_parts.append(f"fills_arr[:{n_rows}]=\n{fills_arr[:n_rows]}")
            elif "fills_array" in result:
                fills_array = result["fills_array"]
                diag_parts.append(f"fills_array: shape={fills_array.shape}, dtype={fills_array.dtype}")
                if fills_array.shape[0] > 0:
                    n_rows = min(5, fills_array.shape[0])
                    diag_parts.append(f"fills_array[:{n_rows}]=\n{fills_array[:n_rows]}")
            else:
                diag_parts.append("No 'fills', 'fills_arr', or 'fills_array' in result (perf only)")

            # Print diagnostics to stderr for visibility
            import sys

            print("\n".join(diag_parts), file=sys.stderr)

        # Check for degenerate cases
        pnl_unique = np.unique(pnl)
        pnl_unique_count = pnl_unique.size
        pnl_std = np.std(pnl)
        proxy_std = np.std(proxy_scores)

        # Record evidence (including perf diagnostics)
        pnl_unique_counts.append(pnl_unique_count)
        pnl_mins.append(float(np.min(pnl)))
        pnl_maxs.append(float(np.max(pnl)))
        trades_totals.append(float(np.sum(trades)))
        trades_unique_counts.append(np.unique(trades).size)
        intent_modes.append(intent_mode)
        intents_totals.append(intents_total)
        fills_totals.append(fills_total)

        # Check if this sample is degenerate and compute rho if non-degenerate
        is_degenerate = False
        if proxy_std == 0.0:
            is_degenerate = True
        elif pnl_unique_count < 2 or pnl_std == 0.0:
            is_degenerate = True
        else:
            # Filter out invalid proxy scores (-inf)
            # Combine proxy valid_mask with pnl finite check
            valid_mask_combined = valid_mask & np.isfinite(pnl)
            if np.sum(valid_mask_combined) < 10:
                is_degenerate = True
            else:
                proxy_valid = proxy_scores[valid_mask_combined]
                pnl_valid = pnl[valid_mask_combined]

                # Check again after filtering
                if np.std(pnl_valid) == 0.0 or np.unique(pnl_valid).size < 2:
                    is_degenerate = True
                else:
                    # Non-degenerate sample - compute Spearman correlation
                    rho = spearman_corr(proxy_valid, pnl_valid)
                    rho_values.append(rho)
                    valid_seeds.append(seed)
                    # Continue to next seed (collect all rho values)

        if is_degenerate:
            degenerate_seeds.append(seed)
            # Continue to next seed (skip degenerate, but diagnostics already recorded)

    # Check minimum valid seeds requirement
    if len(rho_values) < MIN_VALID:
        # Build detailed diagnostic message with per-seed info
        diag_lines = [
            f"Insufficient valid seeds: {len(rho_values)}/{MAX_TRIES} < MIN_VALID={MIN_VALID}",
            f"Valid seeds: {valid_seeds}",
            f"Degenerate seeds: {degenerate_seeds}",
            "",
            "Per-seed summary:",
        ]
        for i, seed in enumerate(seeds_tried):
            is_valid = seed in valid_seeds
            diag_lines.append(
                f"seed={seed} ({'VALID' if is_valid else 'DEGENERATE'}): "
                f"intent_mode={intent_modes[i]}, "
                f"intents_total={intents_totals[i]}, "
                f"fills_total={fills_totals[i]}, "
                f"trades_sum={trades_totals[i]}, "
                f"pnl_unique={pnl_unique_counts[i]}, "
                f"pnl_range=[{pnl_mins[i]:.4f}, {pnl_maxs[i]:.4f}], "
                f"trades_unique={trades_unique_counts[i]}"
            )
        if len(rho_values) > 0:
            diag_lines.append(f"rho_values (partial): {rho_values}")
        pytest.fail("\n".join(diag_lines))

    # Compute median and mean rho
    median_rho = float(np.median(rho_values))
    mean_rho = float(np.mean(rho_values))

    # Assert correlation contract using median (more stable than mean)
    # Only assert if we have enough valid seeds (already checked above)
    assert median_rho >= 0.4, (
        f"Median Spearman correlation {median_rho:.4f} < 0.4 threshold. "
        f"Mean rho={mean_rho:.4f}, "
        f"rho_values={rho_values}, "
        f"valid_seeds={valid_seeds} ({len(rho_values)}/{MAX_TRIES}), "
        f"degenerate_seeds={degenerate_seeds}"
    )


def test_spearman_corr_basic() -> None:
    """Basic test for Spearman correlation function."""
    # Perfect positive correlation
    x = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    y = np.array([2.0, 4.0, 6.0, 8.0, 10.0])
    rho = spearman_corr(x, y)
    assert abs(rho - 1.0) < 1e-10

    # Perfect negative correlation
    y_neg = np.array([10.0, 8.0, 6.0, 4.0, 2.0])
    rho_neg = spearman_corr(x, y_neg)
    assert abs(rho_neg - (-1.0)) < 1e-10

    # No correlation (random)
    rng = np.random.default_rng(42)
    y_rand = rng.standard_normal(100)
    x_rand = rng.standard_normal(100)
    rho_rand = spearman_corr(x_rand, y_rand)
    assert abs(rho_rand) < 0.5  # Should be close to 0 for independent data


def test_spearman_corr_with_ties() -> None:
    """Test Spearman correlation with tied values."""
    # Test with ties
    x = np.array([1.0, 2.0, 2.0, 3.0, 4.0])
    y = np.array([2.0, 3.0, 4.0, 5.0, 6.0])
    rho = spearman_corr(x, y)
    # Should still be positive
    assert rho > 0.0

    # All same values (degenerate)
    x_same = np.array([1.0, 1.0, 1.0])
    y_same = np.array([2.0, 2.0, 2.0])
    rho_same = spearman_corr(x_same, y_same)
    # Should handle gracefully (0 or NaN)
    assert np.isfinite(rho_same) or np.isnan(rho_same)


