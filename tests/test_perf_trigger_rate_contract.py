"""
Stage P2-1.6: Contract Tests for Trigger Rate Masking

Tests that verify trigger_rate control works correctly:
- entry_intents_total scales linearly with trigger_rate
- entry_valid_mask_sum == entry_intents_total
- Deterministic behavior (same seed → same result)
"""
from __future__ import annotations

import numpy as np
import os

from FishBroWFS_V2.perf.scenario_control import apply_trigger_rate_mask


def test_trigger_rate_mask_rate_1_0_no_change() -> None:
    """
    Test that trigger_rate=1.0 preserves all valid triggers unchanged.
    """
    n_bars = 2000
    warmup = 100
    
    # Create trigger array: warmup period NaN, rest are valid positive values
    trigger = np.full(n_bars, np.nan, dtype=np.float64)
    trigger[warmup:] = np.arange(1, n_bars - warmup + 1, dtype=np.float64)
    
    # Apply mask with rate=1.0
    masked = apply_trigger_rate_mask(
        trigger=trigger,
        trigger_rate=1.0,
        warmup=warmup,
        seed=42,
    )
    
    # Should be unchanged
    assert np.array_equal(trigger, masked, equal_nan=True), (
        "trigger_rate=1.0 should not change trigger array"
    )


def test_trigger_rate_mask_rate_0_05_approximately_5_percent() -> None:
    """
    Test that trigger_rate=0.05 results in approximately 5% of valid triggers.
    Allows ±20% relative error to account for random fluctuations.
    """
    n_bars = 2000
    warmup = 100
    n_valid_expected = n_bars - warmup  # Valid positions after warmup
    
    # Create trigger array: warmup period NaN, rest are valid positive values
    trigger = np.full(n_bars, np.nan, dtype=np.float64)
    trigger[warmup:] = np.arange(1, n_bars - warmup + 1, dtype=np.float64)
    
    # Apply mask with rate=0.05
    masked = apply_trigger_rate_mask(
        trigger=trigger,
        trigger_rate=0.05,
        warmup=warmup,
        seed=42,
    )
    
    # Count valid (finite) positions after warmup
    valid_after_warmup = np.isfinite(masked[warmup:])
    n_valid_actual = int(np.sum(valid_after_warmup))
    
    # Expected: approximately 5% of valid positions
    expected_min = int(n_valid_expected * 0.05 * 0.8)  # 80% of 5% (lower bound)
    expected_max = int(n_valid_expected * 0.05 * 1.2)  # 120% of 5% (upper bound)
    
    assert expected_min <= n_valid_actual <= expected_max, (
        f"Expected ~5% valid triggers ({expected_min}-{expected_max}), "
        f"got {n_valid_actual} ({n_valid_actual/n_valid_expected*100:.2f}%)"
    )


def test_trigger_rate_mask_deterministic() -> None:
    """
    Test that same seed and same input produce identical mask results.
    """
    n_bars = 2000
    warmup = 100
    
    # Create trigger array
    trigger = np.full(n_bars, np.nan, dtype=np.float64)
    trigger[warmup:] = np.arange(1, n_bars - warmup + 1, dtype=np.float64)
    
    # Apply mask twice with same parameters
    masked1 = apply_trigger_rate_mask(
        trigger=trigger,
        trigger_rate=0.05,
        warmup=warmup,
        seed=42,
    )
    
    masked2 = apply_trigger_rate_mask(
        trigger=trigger,
        trigger_rate=0.05,
        warmup=warmup,
        seed=42,
    )
    
    # Should be identical
    assert np.array_equal(masked1, masked2, equal_nan=True), (
        "Same seed and input should produce identical mask results"
    )


def test_trigger_rate_mask_different_seeds_different_results() -> None:
    """
    Test that different seeds produce different mask results (when rate < 1.0).
    """
    n_bars = 2000
    warmup = 100
    
    # Create trigger array
    trigger = np.full(n_bars, np.nan, dtype=np.float64)
    trigger[warmup:] = np.arange(1, n_bars - warmup + 1, dtype=np.float64)
    
    # Apply mask with different seeds
    masked1 = apply_trigger_rate_mask(
        trigger=trigger,
        trigger_rate=0.05,
        warmup=warmup,
        seed=42,
    )
    
    masked2 = apply_trigger_rate_mask(
        trigger=trigger,
        trigger_rate=0.05,
        warmup=warmup,
        seed=999,
    )
    
    # Should be different (very unlikely to be identical with different seeds)
    assert not np.array_equal(masked1, masked2, equal_nan=True), (
        "Different seeds should produce different mask results"
    )


def test_trigger_rate_mask_preserves_warmup_nan() -> None:
    """
    Test that warmup period NaN positions are preserved (not masked).
    """
    n_bars = 2000
    warmup = 100
    
    # Create trigger array: warmup period NaN, rest are valid
    trigger = np.full(n_bars, np.nan, dtype=np.float64)
    trigger[warmup:] = np.arange(1, n_bars - warmup + 1, dtype=np.float64)
    
    # Apply mask
    masked = apply_trigger_rate_mask(
        trigger=trigger,
        trigger_rate=0.05,
        warmup=warmup,
        seed=42,
    )
    
    # Warmup period should remain NaN
    assert np.all(np.isnan(masked[:warmup])), (
        "Warmup period should remain NaN after masking"
    )


def test_trigger_rate_mask_linear_scaling() -> None:
    """
    Test that valid trigger count scales approximately linearly with trigger_rate.
    """
    n_bars = 2000
    warmup = 100
    n_valid_expected = n_bars - warmup
    
    # Create trigger array
    trigger = np.full(n_bars, np.nan, dtype=np.float64)
    trigger[warmup:] = np.arange(1, n_bars - warmup + 1, dtype=np.float64)
    
    rates = [0.1, 0.3, 0.5, 0.7, 0.9]
    valid_counts = []
    
    for rate in rates:
        masked = apply_trigger_rate_mask(
            trigger=trigger,
            trigger_rate=rate,
            warmup=warmup,
            seed=42,
        )
        n_valid = int(np.sum(np.isfinite(masked[warmup:])))
        valid_counts.append(n_valid)
    
    # Check approximate linearity: valid_counts[i] / valid_counts[j] ≈ rates[i] / rates[j]
    # Use first and last as reference
    ratio_expected = rates[-1] / rates[0]  # 0.9 / 0.1 = 9.0
    ratio_actual = valid_counts[-1] / valid_counts[0] if valid_counts[0] > 0 else 0
    
    # Allow ±30% error for random fluctuations
    assert 0.7 * ratio_expected <= ratio_actual <= 1.3 * ratio_expected, (
        f"Valid counts should scale linearly with rate. "
        f"Expected ratio ~{ratio_expected:.2f}, got {ratio_actual:.2f}. "
        f"Counts: {valid_counts}"
    )


def test_trigger_rate_mask_preserves_dtype() -> None:
    """
    Test that masking preserves the input dtype.
    """
    n_bars = 200
    warmup = 20
    
    # Test with float64
    trigger_f64 = np.full(n_bars, np.nan, dtype=np.float64)
    trigger_f64[warmup:] = np.arange(1, n_bars - warmup + 1, dtype=np.float64)
    
    masked_f64 = apply_trigger_rate_mask(
        trigger=trigger_f64,
        trigger_rate=0.5,
        warmup=warmup,
        seed=42,
    )
    
    assert masked_f64.dtype == np.float64, (
        f"Expected float64, got {masked_f64.dtype}"
    )
    
    # Test with float32
    trigger_f32 = np.full(n_bars, np.nan, dtype=np.float32)
    trigger_f32[warmup:] = np.arange(1, n_bars - warmup + 1, dtype=np.float32)
    
    masked_f32 = apply_trigger_rate_mask(
        trigger=trigger_f32,
        trigger_rate=0.5,
        warmup=warmup,
        seed=42,
    )
    
    assert masked_f32.dtype == np.float32, (
        f"Expected float32, got {masked_f32.dtype}"
    )


def test_trigger_rate_mask_integration_with_kernel() -> None:
    """
    Integration test: verify that trigger_rate affects entry_intents_total in run_kernel_arrays.
    This test uses run_kernel_arrays directly (no subprocess) to verify the integration.
    """
    from FishBroWFS_V2.strategy.kernel import run_kernel_arrays, DonchianAtrParams
    from FishBroWFS_V2.engine.types import BarArrays
    
    n_bars = 200
    warmup = 20
    
    # Generate simple OHLC data
    rng = np.random.default_rng(42)
    close = 100.0 + np.cumsum(rng.standard_normal(n_bars))
    high = close + np.abs(rng.standard_normal(n_bars)) * 2.0
    low = close - np.abs(rng.standard_normal(n_bars)) * 2.0
    open_ = (high + low) / 2
    
    high = np.maximum(high, np.maximum(open_, close))
    low = np.minimum(low, np.minimum(open_, close))
    
    bars = BarArrays(
        open=open_.astype(np.float64),
        high=high.astype(np.float64),
        low=low.astype(np.float64),
        close=close.astype(np.float64),
    )
    
    params = DonchianAtrParams(channel_len=warmup, atr_len=10, stop_mult=1.0)
    
    # Test with trigger_rate=1.0 (baseline) - explicitly set to avoid env interference
    os.environ["FISHBRO_PERF_TRIGGER_RATE"] = "1.0"
    result_1_0 = run_kernel_arrays(
        bars=bars,
        params=params,
        commission=0.0,
        slip=0.0,
        order_qty=1,
    )
    
    # Contract test: fail fast if keys missing (no .get() with defaults)
    entry_intents_1_0 = result_1_0["_obs"]["entry_intents_total"]
    valid_mask_sum_1_0 = result_1_0["_obs"]["entry_valid_mask_sum"]
    assert entry_intents_1_0 == valid_mask_sum_1_0
    
    # Test with trigger_rate=0.5
    os.environ["FISHBRO_PERF_TRIGGER_RATE"] = "0.5"
    result_0_5 = run_kernel_arrays(
        bars=bars,
        params=params,
        commission=0.0,
        slip=0.0,
        order_qty=1,
    )
    
    # Contract test: fail fast if keys missing (no .get() with defaults)
    entry_intents_0_5 = result_0_5["_obs"]["entry_intents_total"]
    valid_mask_sum_0_5 = result_0_5["_obs"]["entry_valid_mask_sum"]
    assert entry_intents_0_5 == valid_mask_sum_0_5
    
    # Cleanup
    os.environ.pop("FISHBRO_PERF_TRIGGER_RATE", None)
    
    # Verify that entry_intents_0_5 is approximately 50% of entry_intents_1_0
    # Allow ±30% error for random fluctuations and warmup/NaN deterministic effects
    if entry_intents_1_0 > 0:
        ratio = entry_intents_0_5 / entry_intents_1_0
        assert 0.35 <= ratio <= 0.65, (
            f"With trigger_rate=0.5, expected entry_intents ~50% of baseline, "
            f"got {ratio*100:.1f}% (baseline={entry_intents_1_0}, actual={entry_intents_0_5})"
        )
