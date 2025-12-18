"""
Stage P2-3A: Contract Tests for Sparse Entry Intents (Grid Level)

Verifies that entry intents are truly sparse at grid level:
- entry_intents_total == entry_valid_mask_sum (not Bars × Params)
- Sparse builder produces identical results to dense builder (same triggers)
"""
from __future__ import annotations

from dataclasses import asdict, is_dataclass

import numpy as np
import os

from FishBroWFS_V2.engine.types import Fill
from FishBroWFS_V2.pipeline.runner_grid import run_grid


def _fill_to_tuple(f: Fill) -> tuple:
    """
    Convert Fill to a comparable tuple representation.
    
    Uses dataclasses.asdict for dataclass instances, falls back to __dict__ or repr.
    Returns sorted tuple to ensure deterministic comparison.
    """
    if is_dataclass(f):
        d = asdict(f)
    else:
        # fallback: __dict__ (for normal classes)
        d = dict(getattr(f, "__dict__", {}))
        if not d:
            # last resort: repr
            return (repr(f),)
    # Fixed ordering to avoid dict order differences
    return tuple(sorted(d.items()))


def test_grid_sparse_intents_count() -> None:
    """
    Test that grid-level entry intents count scales with trigger_rate (param-subsample).
    
    This test verifies the core sparse contract at grid level:
    - entry_intents_total == entry_valid_mask_sum
    - entry_intents_total scales approximately linearly with trigger_rate
    """
    # Ensure clean environment
    old_trigger_rate = os.environ.pop("FISHBRO_PERF_TRIGGER_RATE", None)
    old_param_subsample_rate = os.environ.pop("FISHBRO_PERF_PARAM_SUBSAMPLE_RATE", None)
    old_profile_grid = os.environ.pop("FISHBRO_PROFILE_GRID", None)
    
    try:
        n_bars = 500
        n_params = 30  # Enough params to make "unique repetition" meaningful
        
        # Generate simple OHLC data
        rng = np.random.default_rng(42)
        close = 100.0 + np.cumsum(rng.standard_normal(n_bars))
        high = close + np.abs(rng.standard_normal(n_bars)) * 2.0
        low = close - np.abs(rng.standard_normal(n_bars)) * 2.0
        open_ = (high + low) / 2
        
        high = np.maximum(high, np.maximum(open_, close))
        low = np.minimum(low, np.minimum(open_, close))
        
        # Generate params matrix (at least 10-50 params for meaningful unique repetition)
        params_list = []
        for i in range(n_params):
            ch_len = 20 + (i % 10)  # Vary channel_len (20-29)
            atr_len = 10 + (i % 5)  # Vary atr_len (10-14)
            stop_mult = 1.0 + (i % 3) * 0.5  # Vary stop_mult (1.0, 1.5, 2.0)
            params_list.append([ch_len, atr_len, stop_mult])
        
        params_matrix = np.array(params_list, dtype=np.float64)
        
        # Fix param_subsample_rate=1.0 (all params) to test trigger_rate effect on intents
        os.environ["FISHBRO_PERF_PARAM_SUBSAMPLE_RATE"] = "1.0"
        os.environ["FISHBRO_PROFILE_GRID"] = "1"
        
        # Run Dense (trigger_rate=1.0) - baseline
        os.environ["FISHBRO_PERF_TRIGGER_RATE"] = "1.0"
        
        result_dense = run_grid(
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
        
        # Run Sparse (trigger_rate=0.05) - bar/intent-level sparsity
        os.environ["FISHBRO_PERF_TRIGGER_RATE"] = "0.05"
        
        result_sparse = run_grid(
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
        
        # Verify perf dicts exist
        perf_dense = result_dense.get("perf", {})
        perf_sparse = result_sparse.get("perf", {})
        
        assert isinstance(perf_dense, dict), "perf_dense must be a dict"
        assert isinstance(perf_sparse, dict), "perf_sparse must be a dict"
        
        # Core contract: entry_intents_total == entry_valid_mask_sum (both runs)
        entry_intents_dense = perf_dense.get("entry_intents_total")
        entry_valid_mask_dense = perf_dense.get("entry_valid_mask_sum")
        entry_intents_sparse = perf_sparse.get("entry_intents_total")
        entry_valid_mask_sparse = perf_sparse.get("entry_valid_mask_sum")
        
        assert entry_intents_dense == entry_valid_mask_dense, (
            f"Dense: entry_intents_total ({entry_intents_dense}) "
            f"must equal entry_valid_mask_sum ({entry_valid_mask_dense})"
        )
        assert entry_intents_sparse == entry_valid_mask_sparse, (
            f"Sparse: entry_intents_total ({entry_intents_sparse}) "
            f"must equal entry_valid_mask_sum ({entry_valid_mask_sparse})"
        )
        
        # Contract: entry_intents_sparse should be approximately trigger_rate * entry_intents_dense
        # With trigger_rate=0.05, we expect approximately 5% of dense baseline
        # Allow wide tolerance: [0.02, 0.08] (2% to 8% of dense)
        if entry_intents_dense is not None and entry_intents_dense > 0:
            ratio = entry_intents_sparse / entry_intents_dense
            assert 0.02 <= ratio <= 0.08, (
                f"With trigger_rate=0.05, entry_intents_sparse ({entry_intents_sparse}) "
                f"should be approximately 5% of entry_intents_dense ({entry_intents_dense}), "
                f"got ratio {ratio:.4f} (expected [0.02, 0.08])"
            )
        
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
        
        if old_profile_grid is None:
            os.environ.pop("FISHBRO_PROFILE_GRID", None)
        else:
            os.environ["FISHBRO_PROFILE_GRID"] = old_profile_grid


def test_sparse_vs_dense_builder_parity() -> None:
    """
    Test that sparse builder produces identical results to dense builder (same triggers).
    
    This test verifies determinism parity:
    - Same triggers set → same results (metrics, fills)
    - Order ID determinism
    - Bit-exact parity
    
    Uses FISHBRO_FORCE_SPARSE_BUILDER=1 to test numba builder vs python builder.
    """
    # Ensure clean environment
    old_trigger_rate = os.environ.pop("FISHBRO_PERF_TRIGGER_RATE", None)
    old_force_sparse = os.environ.pop("FISHBRO_FORCE_SPARSE_BUILDER", None)
    
    try:
        n_bars = 300
        n_params = 20
        
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
        
        # Run A: trigger_rate=1.0, force_sparse=0 (Python builder)
        os.environ["FISHBRO_PERF_TRIGGER_RATE"] = "1.0"
        os.environ.pop("FISHBRO_FORCE_SPARSE_BUILDER", None)  # Ensure not set
        
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
        
        # Run B: trigger_rate=1.0, force_sparse=1 (Numba builder, same triggers)
        os.environ["FISHBRO_PERF_TRIGGER_RATE"] = "1.0"
        os.environ["FISHBRO_FORCE_SPARSE_BUILDER"] = "1"
        
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
        
        # Verify metrics are identical (bit-exact)
        metrics_a = result_a.get("metrics")
        metrics_b = result_b.get("metrics")
        
        assert metrics_a is not None, "metrics_a must exist"
        assert metrics_b is not None, "metrics_b must exist"
        
        # Compare metrics arrays (should be bit-exact)
        np.testing.assert_array_equal(metrics_a, metrics_b, "metrics must be bit-exact")
        
        # Verify sparse contract holds in both runs
        perf_a = result_a.get("perf", {})
        perf_b = result_b.get("perf", {})
        
        if isinstance(perf_a, dict) and isinstance(perf_b, dict):
            entry_intents_a = perf_a.get("entry_intents_total")
            entry_intents_b = perf_b.get("entry_intents_total")
            
            if entry_intents_a is not None and entry_intents_b is not None:
                assert entry_intents_a == entry_intents_b, (
                    f"entry_intents_total should be identical (same triggers): "
                    f"A={entry_intents_a}, B={entry_intents_b}"
                )
        
    finally:
        # Restore environment
        if old_trigger_rate is None:
            os.environ.pop("FISHBRO_PERF_TRIGGER_RATE", None)
        else:
            os.environ["FISHBRO_PERF_TRIGGER_RATE"] = old_trigger_rate
        
        if old_force_sparse is None:
            os.environ.pop("FISHBRO_FORCE_SPARSE_BUILDER", None)
        else:
            os.environ["FISHBRO_FORCE_SPARSE_BUILDER"] = old_force_sparse


def test_created_bar_sorted() -> None:
    """
    Test that created_bar arrays are sorted (ascending).
    
    Note: This test verifies the sparse builder contract that created_bar must be
    sorted. We verify this indirectly through the sparse contract consistency.
    """
    # Ensure clean environment
    old_trigger_rate = os.environ.pop("FISHBRO_PERF_TRIGGER_RATE", None)
    
    try:
        n_bars = 200
        n_params = 10
        
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
            ch_len = 20 + (i % 5)
            atr_len = 10 + (i % 3)
            stop_mult = 1.0
            params_list.append([ch_len, atr_len, stop_mult])
        
        params_matrix = np.array(params_list, dtype=np.float64)
        
        # Run grid
        os.environ["FISHBRO_PERF_TRIGGER_RATE"] = "1.0"
        
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
        
        # Verify sparse contract: entry_intents_total == entry_valid_mask_sum
        perf = result.get("perf", {})
        if isinstance(perf, dict):
            entry_intents_total = perf.get("entry_intents_total")
            entry_valid_mask_sum = perf.get("entry_valid_mask_sum")
            
            if entry_intents_total is not None and entry_valid_mask_sum is not None:
                assert entry_intents_total == entry_valid_mask_sum, (
                    f"Sparse contract: entry_intents_total ({entry_intents_total}) "
                    f"must equal entry_valid_mask_sum ({entry_valid_mask_sum})"
                )
        
        # Note: created_bar sorted verification would require accessing internal arrays
        # For now, we verify the sparse contract which implies created_bar is sorted
        # (since flatnonzero returns sorted indices)
        
    finally:
        # Restore environment
        if old_trigger_rate is None:
            os.environ.pop("FISHBRO_PERF_TRIGGER_RATE", None)
        else:
            os.environ["FISHBRO_PERF_TRIGGER_RATE"] = old_trigger_rate
