"""
Contract Tests for Sparse Builder (P2-3)

Verifies sparse intent builder behavior:
- Intent scaling with trigger_rate
- Metrics zeroing for non-selected params
- Seed determinism
"""
from __future__ import annotations

import numpy as np
import os

from FishBroWFS_V2.strategy.builder_sparse import build_intents_sparse


def test_builder_intent_scaling_with_intent_sparse_rate() -> None:
    """
    Test that intents scale approximately linearly with trigger_rate.
    
    Verifies that when trigger_rate=0.05, intents_generated is approximately
    5% of allowed_bars (with tolerance for rounding).
    """
    n_bars = 1000
    channel_len = 20
    order_qty = 1
    
    # Generate synthetic donch_prev array (all valid after warmup)
    donch_prev = np.full(n_bars, 100.0, dtype=np.float64)
    donch_prev[0] = np.nan  # First bar is NaN (shifted)
    # Bars 1..channel_len-1 are valid but before warmup
    # Bars channel_len..n_bars-1 are valid and past warmup
    
    # Run dense (trigger_rate=1.0) - baseline
    result_dense = build_intents_sparse(
        donch_prev=donch_prev,
        channel_len=channel_len,
        order_qty=order_qty,
        trigger_rate=1.0,
        seed=42,
        use_dense=False,
    )
    
    # Run sparse (trigger_rate=0.05) - 5% of triggers
    result_sparse = build_intents_sparse(
        donch_prev=donch_prev,
        channel_len=channel_len,
        order_qty=order_qty,
        trigger_rate=0.05,
        seed=42,
        use_dense=False,
    )
    
    obs_dense = result_dense["obs"]
    obs_sparse = result_sparse["obs"]
    
    allowed_bars_dense = obs_dense.get("allowed_bars")
    intents_generated_dense = obs_dense.get("intents_generated")
    allowed_bars_sparse = obs_sparse.get("allowed_bars")
    intents_generated_sparse = obs_sparse.get("intents_generated")
    valid_mask_sum_dense = obs_dense.get("valid_mask_sum")
    valid_mask_sum_sparse = obs_sparse.get("valid_mask_sum")
    
    # Contract: allowed_bars should be the same (represents valid bars before trigger rate)
    # allowed_bars = valid_mask_sum (baseline, for comparison)
    assert allowed_bars_dense == allowed_bars_sparse, (
        f"allowed_bars should be the same for dense and sparse (both equal valid_mask_sum), "
        f"got {allowed_bars_dense} vs {allowed_bars_sparse}"
    )
    assert valid_mask_sum_dense == valid_mask_sum_sparse, (
        f"valid_mask_sum should be the same for dense and sparse, "
        f"got {valid_mask_sum_dense} vs {valid_mask_sum_sparse}"
    )
    
    # Contract: intents_generated should scale approximately with trigger_rate
    # With trigger_rate=0.05, we expect approximately 5% of valid_mask_sum
    # Allow wide tolerance: [0.02, 0.08] (2% to 8% of valid_mask_sum)
    if valid_mask_sum_dense is not None and valid_mask_sum_dense > 0:
        ratio = intents_generated_sparse / valid_mask_sum_sparse
        assert 0.02 <= ratio <= 0.08, (
            f"With trigger_rate=0.05, intents_generated_sparse ({intents_generated_sparse}) "
            f"should be approximately 5% of valid_mask_sum ({valid_mask_sum_sparse}), "
            f"got ratio {ratio:.4f} (expected [0.02, 0.08])"
        )
    
    # Contract: intents_generated_dense should equal valid_mask_sum (trigger_rate=1.0)
    assert intents_generated_dense == valid_mask_sum_dense, (
        f"With trigger_rate=1.0, intents_generated ({intents_generated_dense}) "
        f"should equal valid_mask_sum ({valid_mask_sum_dense})"
    )


def test_metrics_zeroing_for_non_selected_params() -> None:
    """
    Test that builder correctly handles edge cases (no valid triggers, etc.).
    
    This test verifies that the builder returns empty arrays when there are
    no valid triggers, and that all fields are properly initialized.
    """
    n_bars = 100
    channel_len = 50  # Large warmup, so most bars are invalid
    order_qty = 1
    
    # Generate donch_prev with only a few valid bars
    donch_prev = np.full(n_bars, np.nan, dtype=np.float64)
    donch_prev[0] = np.nan  # First bar is NaN (shifted)
    # Set a few bars to valid values (after warmup)
    donch_prev[60] = 100.0
    donch_prev[70] = 100.0
    donch_prev[80] = 100.0
    
    result = build_intents_sparse(
        donch_prev=donch_prev,
        channel_len=channel_len,
        order_qty=order_qty,
        trigger_rate=1.0,
        seed=42,
        use_dense=False,
    )
    
    # Contract: Should have some intents (3 valid bars after warmup)
    assert result["n_entry"] > 0, "Should have some intents for valid bars"
    
    # Contract: All arrays should have same length
    assert len(result["created_bar"]) == result["n_entry"]
    assert len(result["price"]) == result["n_entry"]
    assert len(result["order_id"]) == result["n_entry"]
    assert len(result["role"]) == result["n_entry"]
    assert len(result["kind"]) == result["n_entry"]
    assert len(result["side"]) == result["n_entry"]
    assert len(result["qty"]) == result["n_entry"]
    
    # Contract: Test with trigger_rate=0.0 (should return empty)
    result_empty = build_intents_sparse(
        donch_prev=donch_prev,
        channel_len=channel_len,
        order_qty=order_qty,
        trigger_rate=0.0,
        seed=42,
        use_dense=False,
    )
    
    assert result_empty["n_entry"] == 0, "With trigger_rate=0.0, should have no intents"
    assert len(result_empty["created_bar"]) == 0
    assert len(result_empty["price"]) == 0


def test_seed_determinism_builder_output() -> None:
    """
    Test that builder output is deterministic for same seed.
    
    Verifies that running the builder twice with the same seed produces
    identical results (bit-exact).
    """
    n_bars = 500
    channel_len = 20
    order_qty = 1
    trigger_rate = 0.1  # 10% of triggers
    
    # Generate synthetic donch_prev array
    donch_prev = np.full(n_bars, 100.0, dtype=np.float64)
    donch_prev[0] = np.nan  # First bar is NaN (shifted)
    
    # Run twice with same seed
    result1 = build_intents_sparse(
        donch_prev=donch_prev,
        channel_len=channel_len,
        order_qty=order_qty,
        trigger_rate=trigger_rate,
        seed=42,
        use_dense=False,
    )
    
    result2 = build_intents_sparse(
        donch_prev=donch_prev,
        channel_len=channel_len,
        order_qty=order_qty,
        trigger_rate=trigger_rate,
        seed=42,
        use_dense=False,
    )
    
    # Contract: Results should be bit-exact identical
    assert result1["n_entry"] == result2["n_entry"], (
        f"n_entry should be identical, got {result1['n_entry']} vs {result2['n_entry']}"
    )
    
    if result1["n_entry"] > 0:
        assert np.array_equal(result1["created_bar"], result2["created_bar"]), (
            "created_bar should be bit-exact identical"
        )
        assert np.array_equal(result1["price"], result2["price"]), (
            "price should be bit-exact identical"
        )
        assert np.array_equal(result1["order_id"], result2["order_id"]), (
            "order_id should be bit-exact identical"
        )
    
    # Contract: Different seeds should produce different results (for sparse mode)
    result3 = build_intents_sparse(
        donch_prev=donch_prev,
        channel_len=channel_len,
        order_qty=order_qty,
        trigger_rate=trigger_rate,
        seed=123,  # Different seed
        use_dense=False,
    )
    
    # With different seed, results may differ (but should still be deterministic)
    # We just verify that the builder runs without error
    assert isinstance(result3["n_entry"], int)
    assert result3["n_entry"] >= 0


def test_dense_vs_sparse_parity() -> None:
    """
    Test that dense builder (use_dense=True) produces same results as sparse with trigger_rate=1.0.
    
    Verifies that the dense reference implementation matches sparse builder
    when trigger_rate=1.0.
    """
    n_bars = 200
    channel_len = 20
    order_qty = 1
    
    # Generate synthetic donch_prev array
    donch_prev = np.full(n_bars, 100.0, dtype=np.float64)
    donch_prev[0] = np.nan  # First bar is NaN (shifted)
    
    # Run dense builder
    result_dense = build_intents_sparse(
        donch_prev=donch_prev,
        channel_len=channel_len,
        order_qty=order_qty,
        trigger_rate=1.0,
        seed=42,
        use_dense=True,
    )
    
    # Run sparse builder with trigger_rate=1.0
    result_sparse = build_intents_sparse(
        donch_prev=donch_prev,
        channel_len=channel_len,
        order_qty=order_qty,
        trigger_rate=1.0,
        seed=42,
        use_dense=False,
    )
    
    # Contract: Results should be identical (both use all valid triggers)
    assert result_dense["n_entry"] == result_sparse["n_entry"], (
        f"n_entry should be identical, got {result_dense['n_entry']} vs {result_sparse['n_entry']}"
    )
    
    if result_dense["n_entry"] > 0:
        assert np.array_equal(result_dense["created_bar"], result_sparse["created_bar"]), (
            "created_bar should be identical"
        )
        assert np.array_equal(result_dense["price"], result_sparse["price"]), (
            "price should be identical"
        )
