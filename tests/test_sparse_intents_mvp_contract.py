
"""Contract tests for sparse intents MVP (Stage P2-1).

These tests ensure:
1. created_bar is sorted (deterministic ordering)
2. intents_total drops significantly with sparse masking
3. Vectorization parity remains bit-exact
"""

import numpy as np
import pytest

from config.dtypes import INDEX_DTYPE
from engine.types import BarArrays
from strategy.kernel import (
    DonchianAtrParams,
    _build_entry_intents_from_trigger,
    run_kernel_arrays,
)


def _expected_entry_count(donch_prev: np.ndarray, warmup: int) -> int:
    """
    Calculate expected entry count using the same mask rules as production.
    
    Production mask (from _build_entry_intents_from_trigger):
    - i = np.arange(1, n)  # bar indices t (from 1 to n-1)
    - valid_mask = (~np.isnan(donch_prev[1:])) & (donch_prev[1:] > 0) & (i >= warmup)
    
    This helper replicates that exact logic.
    """
    n = donch_prev.size
    # Create index array for bars 1..n-1 (bar indices t, where created_bar = t-1)
    i = np.arange(1, n, dtype=INDEX_DTYPE)
    # Sparse mask: valid entries must be finite, positive, and past warmup
    valid_mask = (~np.isnan(donch_prev[1:])) & (donch_prev[1:] > 0) & (i >= warmup)
    return int(np.count_nonzero(valid_mask))


def _make_donch_hi_with_trigger_rate(
    n_bars: int,
    warmup: int,
    trigger_rate: float,
    seed: int = 42,
) -> np.ndarray:
    """
    Generate donch_hi array with controlled trigger rate.
    
    Args:
        n_bars: number of bars
        warmup: warmup period (bars before warmup are NaN)
        trigger_rate: fraction of bars after warmup that should be valid (0.0-1.0)
        seed: random seed
    
    Returns:
        donch_hi array (float64, n_bars):
        - Bars 0..warmup-1: NaN
        - Bars warmup..n_bars-1: trigger_rate fraction are positive values, rest are NaN
    """
    rng = np.random.default_rng(seed)
    
    donch_hi = np.full(n_bars, np.nan, dtype=np.float64)
    
    # After warmup, set trigger_rate fraction to positive values
    post_warmup_bars = n_bars - warmup
    if post_warmup_bars > 0:
        n_valid = int(post_warmup_bars * trigger_rate)
        if n_valid > 0:
            # Select random indices after warmup
            valid_indices = rng.choice(
                np.arange(warmup, n_bars),
                size=n_valid,
                replace=False,
            )
            # Set valid indices to positive values (e.g., 100.0 + small random)
            donch_hi[valid_indices] = 100.0 + rng.random(n_valid) * 10.0
    
    return donch_hi


class TestSparseIntentsMVP:
    """Test sparse intents MVP contract."""

    def test_sparse_intents_created_bar_is_sorted(self):
        """
        Contract: created_bar must be sorted (non-decreasing).
        
        This ensures deterministic ordering and that sparse masking preserves
        the original bar sequence.
        """
        n_bars = 1000
        warmup = 20
        trigger_rate = 0.1
        
        # Generate donch_hi with controlled trigger rate
        donch_hi = _make_donch_hi_with_trigger_rate(n_bars, warmup, trigger_rate, seed=42)
        
        # Create donch_prev (shifted for next-bar active)
        donch_prev = np.empty_like(donch_hi)
        donch_prev[0] = np.nan
        donch_prev[1:] = donch_hi[:-1]
        
        # Build entry intents
        result = _build_entry_intents_from_trigger(
            donch_prev=donch_prev,
            channel_len=warmup,
            order_qty=1,
        )
        
        created_bar = result["created_bar"]
        n_entry = result["n_entry"]
        
        # Verify n_entry matches expected count (exact match using production mask rules)
        expected = _expected_entry_count(donch_prev, warmup)
        assert n_entry == expected, (
            f"n_entry ({n_entry}) should equal expected ({expected}) "
            f"calculated using production mask rules"
        )
        
        # Verify created_bar is sorted (non-decreasing)
        if n_entry > 1:
            assert np.all(created_bar[1:] >= created_bar[:-1]), (
                f"created_bar must be sorted (non-decreasing). "
                f"Got: {created_bar[:10]} ... (showing first 10)"
            )
        
        # Hard consistency check: created_bar must match flatnonzero result exactly
        # This locks in the ordering contract
        i = np.arange(1, donch_prev.size, dtype=INDEX_DTYPE)
        valid_mask = (~np.isnan(donch_prev[1:])) & (donch_prev[1:] > 0) & (i >= warmup)
        idx = np.flatnonzero(valid_mask).astype(created_bar.dtype)
        assert np.array_equal(created_bar[:n_entry], idx), (
            f"created_bar must exactly match flatnonzero result. "
            f"Got: {created_bar[:min(10, n_entry)]}, "
            f"Expected: {idx[:min(10, len(idx))]}"
        )

    def test_sparse_intents_total_drops_order_of_magnitude(self):
        """
        Contract: intents_total should drop significantly with sparse masking.
        
        With controlled trigger rate (e.g., 5%), intents_total should be << n_bars.
        This test directly controls donch_hi to ensure precise trigger rate.
        """
        n_bars = 1000
        warmup = 20
        trigger_rate = 0.05  # 5% trigger rate
        
        # Generate donch_hi with controlled trigger rate
        donch_hi = _make_donch_hi_with_trigger_rate(n_bars, warmup, trigger_rate, seed=42)
        
        # Create donch_prev (shifted for next-bar active)
        donch_prev = np.empty_like(donch_hi)
        donch_prev[0] = np.nan
        donch_prev[1:] = donch_hi[:-1]
        
        # Build entry intents
        result = _build_entry_intents_from_trigger(
            donch_prev=donch_prev,
            channel_len=warmup,
            order_qty=1,
        )
        
        n_entry = result["n_entry"]
        obs = result["obs"]
        
        # Verify diagnostic observations
        assert obs["n_bars"] == n_bars
        assert obs["warmup"] == warmup
        assert obs["valid_mask_sum"] == n_entry
        
        # Verify n_entry matches expected count (exact match using production mask rules)
        expected = _expected_entry_count(donch_prev, warmup)
        assert n_entry == expected, (
            f"n_entry ({n_entry}) should equal expected ({expected}) "
            f"calculated using production mask rules"
        )
        
        # Order-of-magnitude contract: n_entry should be significantly less than n_bars
        # This is the core contract of this test
        # Conservative threshold: 6% of (n_bars - warmup) as upper bound
        max_expected_ratio = 0.06  # 6% conservative upper bound
        max_expected = int((n_bars - warmup) * max_expected_ratio)
        
        assert n_entry <= max_expected, (
            f"n_entry ({n_entry}) should be <= {max_expected} "
            f"({max_expected_ratio*100}% of post-warmup bars) "
            f"with trigger_rate={trigger_rate}, n_bars={n_bars}, warmup={warmup}. "
            f"Sparse masking should significantly reduce intent count (order-of-magnitude reduction)."
        )
        
        # Also verify it's not zero (unless trigger_rate is too low)
        if trigger_rate > 0:
            # With 5% trigger rate, we should have some intents
            assert n_entry > 0, (
                f"Expected some intents with trigger_rate={trigger_rate}, "
                f"but got n_entry={n_entry}"
            )

    def test_vectorization_parity_still_bit_exact(self):
        """
        Contract: Vectorization parity tests should still pass after sparse masking.
        
        This test ensures that sparse masking doesn't break existing parity contracts.
        We rely on the existing test_vectorization_parity.py to verify this.
        
        This test is a placeholder to document the requirement.
        """
        # This test doesn't need to re-implement parity checks.
        # It's sufficient to ensure that make check passes all existing tests.
        # The actual parity verification is in tests/test_vectorization_parity.py
        
        # Basic sanity check: sparse masking should produce valid results
        n_bars = 100
        bars = BarArrays(
            open=np.arange(100, 200, dtype=np.float64),
            high=np.arange(101, 201, dtype=np.float64),
            low=np.arange(99, 199, dtype=np.float64),
            close=np.arange(100, 200, dtype=np.float64),
        )
        
        params = DonchianAtrParams(
            channel_len=10,
            atr_len=5,
            stop_mult=1.5,
        )
        
        result = run_kernel_arrays(
            bars,
            params,
            commission=0.0,
            slip=0.0,
            order_qty=1,
        )
        
        # Verify result structure is intact
        assert "fills" in result
        assert "metrics" in result
        assert "_obs" in result
        assert "intents_total" in result["_obs"]
        
        # Verify diagnostic observations are present
        assert "n_bars" in result["_obs"]
        assert "warmup" in result["_obs"]
        assert "valid_mask_sum" in result["_obs"]
        
        # Verify intents_total is reasonable
        intents_total = result["_obs"]["intents_total"]
        assert intents_total >= 0
        assert intents_total <= n_bars  # Should be <= n_bars due to sparse masking
        
        # Note: Full parity verification is done by test_vectorization_parity.py
        # This test just ensures the basic contract is met


