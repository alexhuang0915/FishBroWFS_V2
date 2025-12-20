"""Funnel smoke contract tests - Phase 4 Stage D.

Basic smoke tests to ensure the complete funnel pipeline works end-to-end.
"""

import numpy as np

from FishBroWFS_V2.pipeline.funnel import FunnelResult, run_funnel


def test_funnel_smoke_basic():
    """Basic smoke test: run funnel with small parameter grid."""
    # Generate deterministic test data
    np.random.seed(42)
    n_bars = 500
    n_params = 20
    
    close = 10000 + np.cumsum(np.random.randn(n_bars)) * 10
    open_ = close + np.random.randn(n_bars) * 2
    high = np.maximum(open_, close) + np.abs(np.random.randn(n_bars)) * 3
    low = np.minimum(open_, close) - np.abs(np.random.randn(n_bars)) * 3
    
    # Generate parameter grid
    params_matrix = np.column_stack([
        np.random.randint(10, 50, size=n_params),  # channel_len / fast_len
        np.random.randint(5, 30, size=n_params),   # atr_len / slow_len
        np.random.uniform(1.0, 3.0, size=n_params), # stop_mult
    ]).astype(np.float64)
    
    # Run funnel
    result = run_funnel(
        open_,
        high,
        low,
        close,
        params_matrix,
        k=5,
        commission=0.0,
        slip=0.0,
    )
    
    # Verify result structure
    assert isinstance(result, FunnelResult)
    assert len(result.stage0_results) == n_params
    assert len(result.topk_param_ids) == 5
    assert len(result.stage2_results) == 5
    
    # Verify Stage0 results
    for stage0_result in result.stage0_results:
        assert hasattr(stage0_result, "param_id")
        assert hasattr(stage0_result, "proxy_value")
        assert hasattr(stage0_result, "warmup_ok")
        assert isinstance(stage0_result.param_id, int)
        assert isinstance(stage0_result.proxy_value, (int, float))
    
    # Verify Top-K param_ids are valid
    for param_id in result.topk_param_ids:
        assert 0 <= param_id < n_params
    
    # Verify Stage2 results match Top-K
    assert len(result.stage2_results) == len(result.topk_param_ids)
    for i, stage2_result in enumerate(result.stage2_results):
        assert stage2_result.param_id == result.topk_param_ids[i]
        assert isinstance(stage2_result.net_profit, (int, float))
        assert isinstance(stage2_result.trades, int)
        assert isinstance(stage2_result.max_dd, (int, float))


def test_funnel_smoke_empty_params():
    """Test funnel with empty parameter grid."""
    np.random.seed(42)
    n_bars = 100
    
    close = 10000 + np.cumsum(np.random.randn(n_bars)) * 10
    open_ = close + np.random.randn(n_bars) * 2
    high = np.maximum(open_, close) + np.abs(np.random.randn(n_bars)) * 3
    low = np.minimum(open_, close) - np.abs(np.random.randn(n_bars)) * 3
    
    # Empty parameter grid
    params_matrix = np.empty((0, 3), dtype=np.float64)
    
    result = run_funnel(
        open_,
        high,
        low,
        close,
        params_matrix,
        k=5,
    )
    
    assert len(result.stage0_results) == 0
    assert len(result.topk_param_ids) == 0
    assert len(result.stage2_results) == 0


def test_funnel_smoke_k_larger_than_params():
    """Test funnel when k is larger than number of parameters."""
    np.random.seed(42)
    n_bars = 100
    n_params = 5
    
    close = 10000 + np.cumsum(np.random.randn(n_bars)) * 10
    open_ = close + np.random.randn(n_bars) * 2
    high = np.maximum(open_, close) + np.abs(np.random.randn(n_bars)) * 3
    low = np.minimum(open_, close) - np.abs(np.random.randn(n_bars)) * 3
    
    params_matrix = np.column_stack([
        np.random.randint(10, 50, size=n_params),
        np.random.randint(5, 30, size=n_params),
        np.random.uniform(1.0, 3.0, size=n_params),
    ]).astype(np.float64)
    
    # k=10 but only 5 params
    result = run_funnel(
        open_,
        high,
        low,
        close,
        params_matrix,
        k=10,
    )
    
    # Should return all 5 params
    assert len(result.topk_param_ids) == 5
    assert len(result.stage2_results) == 5


def test_funnel_smoke_pipeline_order():
    """Test that pipeline executes in correct order: Stage0 → Top-K → Stage2."""
    np.random.seed(42)
    n_bars = 200
    n_params = 10
    
    close = 10000 + np.cumsum(np.random.randn(n_bars)) * 10
    open_ = close + np.random.randn(n_bars) * 2
    high = np.maximum(open_, close) + np.abs(np.random.randn(n_bars)) * 3
    low = np.minimum(open_, close) - np.abs(np.random.randn(n_bars)) * 3
    
    params_matrix = np.column_stack([
        np.random.randint(10, 30, size=n_params),
        np.random.randint(5, 20, size=n_params),
        np.random.uniform(1.0, 2.0, size=n_params),
    ]).astype(np.float64)
    
    result = run_funnel(
        open_,
        high,
        low,
        close,
        params_matrix,
        k=3,
    )
    
    # Verify Stage0 ran on all params
    assert len(result.stage0_results) == n_params
    
    # Verify Top-K selected from Stage0 results
    assert len(result.topk_param_ids) == 3
    # Top-K should be sorted by proxy_value (descending)
    stage0_by_id = {r.param_id: r for r in result.stage0_results}
    topk_values = [stage0_by_id[pid].proxy_value for pid in result.topk_param_ids]
    assert topk_values == sorted(topk_values, reverse=True)
    
    # Verify Stage2 ran only on Top-K
    assert len(result.stage2_results) == 3
    stage2_param_ids = [r.param_id for r in result.stage2_results]
    assert set(stage2_param_ids) == set(result.topk_param_ids)
