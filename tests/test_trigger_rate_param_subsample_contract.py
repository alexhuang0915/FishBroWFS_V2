"""
Stage P2-3: Contract Tests for Param-subsample Trigger Rate

Verifies that trigger_rate controls param subsampling:
- selected_params_count scales with trigger_rate
- intents_total scales approximately linearly with trigger_rate
- Workload reduction is effective
"""
from __future__ import annotations

import numpy as np
import os

from FishBroWFS_V2.pipeline.runner_grid import run_grid


def test_selected_params_count_reasonable() -> None:
    """
    Test that selected_params_count is reasonable for given trigger_rate.
    
    With n_params=1000 and trigger_rate=0.05, we expect selected_params_count
    to be approximately 50 (allowing rounding error).
    """
    # Ensure clean environment
    old_param_subsample_rate = os.environ.pop("FISHBRO_PERF_PARAM_SUBSAMPLE_RATE", None)
    old_param_subsample_seed = os.environ.pop("FISHBRO_PERF_PARAM_SUBSAMPLE_SEED", None)
    
    try:
        n_bars = 500
        n_params = 1000
        
        # Generate simple OHLC data
        rng = np.random.default_rng(42)
        close = 100.0 + np.cumsum(rng.standard_normal(n_bars))
        high = close + np.abs(rng.standard_normal(n_bars)) * 2.0
        low = close - np.abs(rng.standard_normal(n_bars)) * 2.0
        open_ = (high + low) / 2
        
        high = np.maximum(high, np.maximum(open_, close))
        low = np.minimum(low, np.minimum(open_, close))
        
        # Generate params matrix
        params_list = []
        for i in range(n_params):
            ch_len = 20 + (i % 10)
            atr_len = 10 + (i % 5)
            stop_mult = 1.0 + (i % 3) * 0.5
            params_list.append([ch_len, atr_len, stop_mult])
        
        params_matrix = np.array(params_list, dtype=np.float64)
        
        # Set param_subsample_rate=0.05
        os.environ["FISHBRO_PERF_PARAM_SUBSAMPLE_RATE"] = "0.05"
        os.environ["FISHBRO_PERF_PARAM_SUBSAMPLE_SEED"] = "42"
        
        result = run_grid(
            open_=open_,
            high=high,
            low=low,
            close=close,
            params_matrix=params_matrix,
            commission=0.0,
            slip=0.0,
            order_qty=1,
            sort_params=True,
        )
        
        # Verify perf dict contains trigger rate info
        assert "perf" in result, "perf must exist in run_grid result"
        perf = result["perf"]
        assert isinstance(perf, dict), "perf must be a dict"
        
        selected_params_count = perf.get("selected_params_count")
        param_subsample_rate_configured = perf.get("param_subsample_rate_configured")
        selected_params_ratio = perf.get("selected_params_ratio")
        
        assert selected_params_count is not None, "selected_params_count must exist"
        assert param_subsample_rate_configured is not None, "param_subsample_rate_configured must exist"
        assert selected_params_ratio is not None, "selected_params_ratio must exist"
        
        assert param_subsample_rate_configured == 0.05, f"param_subsample_rate_configured should be 0.05, got {param_subsample_rate_configured}"
        
        # Contract: selected_params_count should be approximately 5% of n_params
        # Allow rounding error: [45, 55] for n_params=1000, rate=0.05
        assert 45 <= selected_params_count <= 55, (
            f"selected_params_count ({selected_params_count}) should be approximately 50 "
            f"(5% of {n_params}), got {selected_params_count}"
        )
        
        # Contract: selected_params_ratio should match trigger_rate approximately
        expected_ratio = 0.05
        assert 0.04 <= selected_params_ratio <= 0.06, (
            f"selected_params_ratio ({selected_params_ratio}) should be approximately "
            f"{expected_ratio}, got {selected_params_ratio}"
        )
        
        # Contract: metrics_rows_computed should equal selected_params_count
        metrics_rows_computed = perf.get("metrics_rows_computed")
        assert metrics_rows_computed == selected_params_count, (
            f"metrics_rows_computed ({metrics_rows_computed}) should equal "
            f"selected_params_count ({selected_params_count})"
        )
        
    finally:
        # Restore environment
        if old_param_subsample_rate is None:
            os.environ.pop("FISHBRO_PERF_PARAM_SUBSAMPLE_RATE", None)
        else:
            os.environ["FISHBRO_PERF_PARAM_SUBSAMPLE_RATE"] = old_param_subsample_rate
        
        if old_param_subsample_seed is None:
            os.environ.pop("FISHBRO_PERF_PARAM_SUBSAMPLE_SEED", None)
        else:
            os.environ["FISHBRO_PERF_PARAM_SUBSAMPLE_SEED"] = old_param_subsample_seed


def test_intents_total_linear_scaling() -> None:
    """
    Test that intents_total scales approximately linearly with trigger_rate.
    
    This verifies workload reduction: when we run 5% of params, intents_total
    should be approximately 5% of baseline.
    """
    # Ensure clean environment
    old_param_subsample_rate = os.environ.pop("FISHBRO_PERF_PARAM_SUBSAMPLE_RATE", None)
    old_param_subsample_seed = os.environ.pop("FISHBRO_PERF_PARAM_SUBSAMPLE_SEED", None)
    
    try:
        n_bars = 500
        n_params = 200
        
        # Generate simple OHLC data
        rng = np.random.default_rng(42)
        close = 100.0 + np.cumsum(rng.standard_normal(n_bars))
        high = close + np.abs(rng.standard_normal(n_bars)) * 2.0
        low = close - np.abs(rng.standard_normal(n_bars)) * 2.0
        open_ = (high + low) / 2
        
        high = np.maximum(high, np.maximum(open_, close))
        low = np.minimum(low, np.minimum(open_, close))
        
        # Generate params matrix
        params_list = []
        for i in range(n_params):
            ch_len = 20 + (i % 10)
            atr_len = 10 + (i % 5)
            stop_mult = 1.0 + (i % 3) * 0.5
            params_list.append([ch_len, atr_len, stop_mult])
        
        params_matrix = np.array(params_list, dtype=np.float64)
        
        # Run A: param_subsample_rate=1.0 (baseline, all params)
        os.environ["FISHBRO_PERF_PARAM_SUBSAMPLE_RATE"] = "1.0"
        os.environ["FISHBRO_PERF_PARAM_SUBSAMPLE_SEED"] = "42"
        
        result_a = run_grid(
            open_=open_,
            high=high,
            low=low,
            close=close,
            params_matrix=params_matrix,
            commission=0.0,
            slip=0.0,
            order_qty=1,
            sort_params=True,
        )
        
        # Run B: param_subsample_rate=0.05 (5% of params)
        os.environ["FISHBRO_PERF_PARAM_SUBSAMPLE_RATE"] = "0.05"
        os.environ["FISHBRO_PERF_PARAM_SUBSAMPLE_SEED"] = "42"  # Same seed for deterministic selection
        
        result_b = run_grid(
            open_=open_,
            high=high,
            low=low,
            close=close,
            params_matrix=params_matrix,
            commission=0.0,
            slip=0.0,
            order_qty=1,
            sort_params=True,
        )
        
        # Verify perf dicts
        perf_a = result_a.get("perf", {})
        perf_b = result_b.get("perf", {})
        
        assert isinstance(perf_a, dict), "perf_a must be a dict"
        assert isinstance(perf_b, dict), "perf_b must be a dict"
        
        intents_total_a = perf_a.get("intents_total")
        intents_total_b = perf_b.get("intents_total")
        
        assert intents_total_a is not None, "intents_total_a must exist"
        assert intents_total_b is not None, "intents_total_b must exist"
        
        # Contract: intents_total_B should be <= intents_total_A * 0.07 (allowing overhead)
        # With 5% params, we expect approximately 5% workload, but allow up to 7% for overhead
        if intents_total_a > 0:
            ratio = intents_total_b / intents_total_a
            assert ratio <= 0.07, (
                f"intents_total_B ({intents_total_b}) should be <= intents_total_A * 0.07 "
                f"({intents_total_a * 0.07}), got ratio {ratio:.4f}"
            )
        
        # Verify selected_params_count scaling
        selected_count_a = perf_a.get("selected_params_count", n_params)
        selected_count_b = perf_b.get("selected_params_count")
        
        assert selected_count_b is not None, "selected_params_count_B must exist"
        assert selected_count_b < selected_count_a, (
            f"selected_params_count_B ({selected_count_b}) should be < "
            f"selected_params_count_A ({selected_count_a})"
        )
        
    finally:
        # Restore environment
        if old_param_subsample_rate is None:
            os.environ.pop("FISHBRO_PERF_PARAM_SUBSAMPLE_RATE", None)
        else:
            os.environ["FISHBRO_PERF_PARAM_SUBSAMPLE_RATE"] = old_param_subsample_rate
        
        if old_param_subsample_seed is None:
            os.environ.pop("FISHBRO_PERF_PARAM_SUBSAMPLE_SEED", None)
        else:
            os.environ["FISHBRO_PERF_PARAM_SUBSAMPLE_SEED"] = old_param_subsample_seed


def test_metrics_shape_preserved() -> None:
    """
    Test that metrics shape is preserved (n_params, METRICS_N_COLUMNS) even with subsampling.
    
    Only selected rows should be computed; unselected rows remain zeros.
    Uses metrics_computed_mask to verify which rows were computed.
    """
    # Ensure clean environment
    old_trigger_rate = os.environ.pop("FISHBRO_PERF_TRIGGER_RATE", None)
    old_param_subsample_rate = os.environ.pop("FISHBRO_PERF_PARAM_SUBSAMPLE_RATE", None)
    old_param_subsample_seed = os.environ.pop("FISHBRO_PERF_PARAM_SUBSAMPLE_SEED", None)
    
    try:
        n_bars = 300
        n_params = 100
        
        # Generate simple OHLC data
        rng = np.random.default_rng(42)
        close = 100.0 + np.cumsum(rng.standard_normal(n_bars))
        high = close + np.abs(rng.standard_normal(n_bars)) * 2.0
        low = close - np.abs(rng.standard_normal(n_bars)) * 2.0
        open_ = (high + low) / 2
        
        high = np.maximum(high, np.maximum(open_, close))
        low = np.minimum(low, np.minimum(open_, close))
        
        # Generate params matrix
        params_list = []
        for i in range(n_params):
            ch_len = 20 + (i % 10)
            atr_len = 10 + (i % 5)
            stop_mult = 1.0
            params_list.append([ch_len, atr_len, stop_mult])
        
        params_matrix = np.array(params_list, dtype=np.float64)
        
        # Fix trigger_rate=1.0 (no intent-level sparsity) to test param subsample only
        os.environ["FISHBRO_PERF_TRIGGER_RATE"] = "1.0"
        # Set param_subsample_rate=0.1 (10% of params)
        os.environ["FISHBRO_PERF_PARAM_SUBSAMPLE_RATE"] = "0.1"
        os.environ["FISHBRO_PERF_PARAM_SUBSAMPLE_SEED"] = "42"
        
        result = run_grid(
            open_=open_,
            high=high,
            low=low,
            close=close,
            params_matrix=params_matrix,
            commission=0.0,
            slip=0.0,
            order_qty=1,
            sort_params=True,
        )
        
        # Verify metrics shape is preserved
        metrics = result.get("metrics")
        assert metrics is not None, "metrics must exist"
        assert isinstance(metrics, np.ndarray), "metrics must be np.ndarray"
        assert metrics.shape == (n_params, 3), (
            f"metrics shape should be ({n_params}, 3), got {metrics.shape}"
        )
        
        # Verify perf dict
        perf = result.get("perf", {})
        metrics_rows_computed = perf.get("metrics_rows_computed")
        selected_params_count = perf.get("selected_params_count")
        metrics_computed_mask = perf.get("metrics_computed_mask")
        
        assert metrics_rows_computed == selected_params_count, (
            f"metrics_rows_computed ({metrics_rows_computed}) should equal "
            f"selected_params_count ({selected_params_count})"
        )
        
        # Verify metrics_computed_mask exists and has correct shape
        assert metrics_computed_mask is not None, "metrics_computed_mask must exist in perf"
        assert isinstance(metrics_computed_mask, list), "metrics_computed_mask must be a list"
        assert len(metrics_computed_mask) == n_params, (
            f"metrics_computed_mask length ({len(metrics_computed_mask)}) should equal n_params ({n_params})"
        )
        
        # Convert to numpy array for easier manipulation
        mask_array = np.array(metrics_computed_mask, dtype=bool)
        
        # Verify that mask sum equals selected_params_count
        assert np.sum(mask_array) == selected_params_count, (
            f"metrics_computed_mask sum ({np.sum(mask_array)}) should equal "
            f"selected_params_count ({selected_params_count})"
        )
        
        # Verify that uncomputed rows remain all zeros
        uncomputed_non_zero = np.sum(np.any(np.abs(metrics[~mask_array]) > 1e-10, axis=1))
        assert uncomputed_non_zero == 0, (
            f"Uncomputed rows with non-zero metrics ({uncomputed_non_zero}) should be 0"
        )
        
        # NOTE: Do NOT require computed rows to be non-zero.
        # It's valid to have entry fills but no exits (trades=0), producing all-zero metrics.
        # Evidence of computation is provided by metrics_rows_computed == selected_params_count
        # and the metrics_computed_mask bookkeeping above.
        
    finally:
        # Restore environment
        if old_trigger_rate is None:
            os.environ.pop("FISHBRO_PERF_TRIGGER_RATE", None)
        else:
            os.environ["FISHBRO_PERF_TRIGGER_RATE"] = old_trigger_rate
        
        if old_param_subsample_rate is None:
            os.environ.pop("FISHBRO_PERF_PARAM_SUBSAMPLE_RATE", None)
        else:
            os.environ["FISHBRO_PERF_PARAM_SUBSAMPLE_RATE"] = old_param_subsample_rate
        
        if old_param_subsample_seed is None:
            os.environ.pop("FISHBRO_PERF_PARAM_SUBSAMPLE_SEED", None)
        else:
            os.environ["FISHBRO_PERF_PARAM_SUBSAMPLE_SEED"] = old_param_subsample_seed
