
"""Test Top-K determinism - same input must produce same Top-K selection."""

import numpy as np

from pipeline.funnel import run_funnel
from pipeline.stage0_runner import Stage0Result, run_stage0
from pipeline.topk import select_topk


def test_topk_determinism_same_input():
    """Test that Top-K selection is deterministic: same input produces same output."""
    # Generate deterministic test data
    np.random.seed(42)
    n_bars = 1000
    n_params = 100
    
    close = 10000 + np.cumsum(np.random.randn(n_bars)) * 10
    open_ = close + np.random.randn(n_bars) * 2
    high = np.maximum(open_, close) + np.abs(np.random.randn(n_bars)) * 3
    low = np.minimum(open_, close) - np.abs(np.random.randn(n_bars)) * 3
    
    # Generate parameter grid
    params_matrix = np.column_stack([
        np.random.randint(10, 100, size=n_params),  # fast_len / channel_len
        np.random.randint(5, 50, size=n_params),      # slow_len / atr_len
        np.random.uniform(1.0, 5.0, size=n_params),   # stop_mult
    ]).astype(np.float64)
    
    # Run Stage0 twice with same input
    stage0_results_1 = run_stage0(close, params_matrix)
    stage0_results_2 = run_stage0(close, params_matrix)
    
    # Verify Stage0 results are identical
    assert len(stage0_results_1) == len(stage0_results_2)
    for r1, r2 in zip(stage0_results_1, stage0_results_2):
        assert r1.param_id == r2.param_id
        assert r1.proxy_value == r2.proxy_value
    
    # Run Top-K selection twice
    k = 20
    topk_1 = select_topk(stage0_results_1, k=k)
    topk_2 = select_topk(stage0_results_2, k=k)
    
    # Verify Top-K selection is identical
    assert topk_1 == topk_2, (
        f"Top-K selection not deterministic:\n"
        f"  First run:  {topk_1}\n"
        f"  Second run: {topk_2}"
    )
    assert len(topk_1) == k
    assert len(topk_2) == k


def test_topk_determinism_tie_break():
    """Test that tie-breaking by param_id is deterministic."""
    # Create Stage0 results with identical proxy_value
    # Tie-break should use param_id (ascending)
    results = [
        Stage0Result(param_id=5, proxy_value=10.0),
        Stage0Result(param_id=2, proxy_value=10.0),  # Same value, lower param_id
        Stage0Result(param_id=8, proxy_value=10.0),
        Stage0Result(param_id=1, proxy_value=10.0),  # Same value, lowest param_id
        Stage0Result(param_id=3, proxy_value=15.0),  # Higher value
        Stage0Result(param_id=4, proxy_value=12.0),  # Medium value
    ]
    
    # Select top 3
    topk = select_topk(results, k=3)
    
    # Expected: param_id=3 (value=15.0), param_id=4 (value=12.0), param_id=1 (value=10.0, lowest param_id)
    assert topk == [3, 4, 1], f"Tie-break failed: got {topk}, expected [3, 4, 1]"
    
    # Run again - should be identical
    topk_2 = select_topk(results, k=3)
    assert topk_2 == topk


def test_funnel_determinism():
    """Test that complete funnel pipeline is deterministic."""
    # Generate deterministic test data
    np.random.seed(123)
    n_bars = 500
    n_params = 50
    
    close = 10000 + np.cumsum(np.random.randn(n_bars)) * 10
    open_ = close + np.random.randn(n_bars) * 2
    high = np.maximum(open_, close) + np.abs(np.random.randn(n_bars)) * 3
    low = np.minimum(open_, close) - np.abs(np.random.randn(n_bars)) * 3
    
    # Generate parameter grid
    params_matrix = np.column_stack([
        np.random.randint(10, 50, size=n_params),
        np.random.randint(5, 30, size=n_params),
        np.random.uniform(1.0, 3.0, size=n_params),
    ]).astype(np.float64)
    
    # Run funnel twice
    result_1 = run_funnel(
        open_,
        high,
        low,
        close,
        params_matrix,
        k=10,
        commission=0.0,
        slip=0.0,
    )
    
    result_2 = run_funnel(
        open_,
        high,
        low,
        close,
        params_matrix,
        k=10,
        commission=0.0,
        slip=0.0,
    )
    
    # Verify Top-K selection is identical
    assert result_1.topk_param_ids == result_2.topk_param_ids, (
        f"Funnel Top-K not deterministic:\n"
        f"  First run:  {result_1.topk_param_ids}\n"
        f"  Second run: {result_2.topk_param_ids}"
    )
    
    # Verify Stage2 results are for same parameters
    assert len(result_1.stage2_results) == len(result_2.stage2_results)
    for r1, r2 in zip(result_1.stage2_results, result_2.stage2_results):
        assert r1.param_id == r2.param_id


