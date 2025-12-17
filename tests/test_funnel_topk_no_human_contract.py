"""Funnel Top-K no-human contract tests - Phase 4 Stage D.

These tests ensure that Top-K selection is purely automatic based on proxy_value,
with no possibility of human intervention or manual filtering.
"""

import numpy as np

from FishBroWFS_V2.pipeline.funnel import run_funnel
from FishBroWFS_V2.pipeline.stage0_runner import Stage0Result, run_stage0
from FishBroWFS_V2.pipeline.topk import select_topk


def test_topk_only_uses_proxy_value():
    """Test that Top-K selection uses ONLY proxy_value, not any other field."""
    # Create Stage0 results with varying proxy_value and other fields
    results = [
        Stage0Result(param_id=0, proxy_value=5.0, warmup_ok=True, meta={"custom": "data"}),
        Stage0Result(param_id=1, proxy_value=10.0, warmup_ok=False, meta=None),
        Stage0Result(param_id=2, proxy_value=15.0, warmup_ok=True, meta={"other": 123}),
        Stage0Result(param_id=3, proxy_value=8.0, warmup_ok=True, meta=None),
        Stage0Result(param_id=4, proxy_value=12.0, warmup_ok=False, meta={"test": True}),
    ]
    
    # Select top 3
    topk = select_topk(results, k=3)
    
    # Expected: param_id=2 (value=15.0), param_id=4 (value=12.0), param_id=1 (value=10.0)
    # Should ignore warmup_ok and meta fields
    assert topk == [2, 4, 1], (
        f"Top-K should only consider proxy_value, got {topk}, expected [2, 4, 1]"
    )


def test_topk_tie_break_param_id():
    """Test that tie-breaking uses param_id (ascending) when proxy_value is identical."""
    # Create results with identical proxy_value
    results = [
        Stage0Result(param_id=5, proxy_value=10.0),
        Stage0Result(param_id=2, proxy_value=10.0),
        Stage0Result(param_id=8, proxy_value=10.0),
        Stage0Result(param_id=1, proxy_value=10.0),
        Stage0Result(param_id=3, proxy_value=15.0),  # Higher value
        Stage0Result(param_id=4, proxy_value=12.0),   # Medium value
    ]
    
    # Select top 3
    topk = select_topk(results, k=3)
    
    # Expected: param_id=3 (value=15.0), param_id=4 (value=12.0), param_id=1 (value=10.0, lowest param_id)
    assert topk == [3, 4, 1], (
        f"Tie-break should use param_id ascending, got {topk}, expected [3, 4, 1]"
    )


def test_topk_deterministic_same_input():
    """Test that Top-K selection is deterministic: same input produces same output."""
    np.random.seed(42)
    n_bars = 500
    n_params = 50
    
    close = 10000 + np.cumsum(np.random.randn(n_bars)) * 10
    
    params_matrix = np.column_stack([
        np.random.randint(10, 50, size=n_params),
        np.random.randint(5, 30, size=n_params),
        np.random.uniform(1.0, 3.0, size=n_params),
    ]).astype(np.float64)
    
    # Run Stage0 twice
    stage0_results_1 = run_stage0(close, params_matrix)
    stage0_results_2 = run_stage0(close, params_matrix)
    
    # Select Top-K twice
    topk_1 = select_topk(stage0_results_1, k=10)
    topk_2 = select_topk(stage0_results_2, k=10)
    
    # Should be identical
    assert topk_1 == topk_2, (
        f"Top-K selection not deterministic:\n"
        f"  First run:  {topk_1}\n"
        f"  Second run: {topk_2}"
    )


def test_funnel_topk_no_manual_filtering():
    """Test that funnel Top-K selection cannot be manually filtered."""
    np.random.seed(42)
    n_bars = 300
    n_params = 20
    
    close = 10000 + np.cumsum(np.random.randn(n_bars)) * 10
    open_ = close + np.random.randn(n_bars) * 2
    high = np.maximum(open_, close) + np.abs(np.random.randn(n_bars)) * 3
    low = np.minimum(open_, close) - np.abs(np.random.randn(n_bars)) * 3
    
    params_matrix = np.column_stack([
        np.random.randint(10, 40, size=n_params),
        np.random.randint(5, 25, size=n_params),
        np.random.uniform(1.0, 2.5, size=n_params),
    ]).astype(np.float64)
    
    # Run funnel
    result = run_funnel(
        open_,
        high,
        low,
        close,
        params_matrix,
        k=5,
    )
    
    # Verify Top-K is based solely on proxy_value
    stage0_by_id = {r.param_id: r for r in result.stage0_results}
    
    # Get proxy_values for Top-K
    topk_values = [stage0_by_id[pid].proxy_value for pid in result.topk_param_ids]
    
    # Get proxy_values for all params
    all_values = [r.proxy_value for r in result.stage0_results]
    all_values_sorted = sorted(all_values, reverse=True)
    
    # Top-K values should match top K values from all params
    assert topk_values == all_values_sorted[:5], (
        f"Top-K should contain top 5 proxy_values:\n"
        f"  Top-K values: {topk_values}\n"
        f"  Top 5 values:  {all_values_sorted[:5]}"
    )


def test_funnel_stage2_only_runs_topk():
    """Test that Stage2 only runs on Top-K parameters, not all parameters."""
    np.random.seed(42)
    n_bars = 200
    n_params = 15
    
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
    
    # Verify Top-K selected
    assert len(result.topk_param_ids) == 3
    
    # Verify Stage2 ran ONLY on Top-K (not all params)
    assert len(result.stage2_results) == 3, (
        f"Stage2 should run only on Top-K (3 params), not all params ({n_params})"
    )
    
    # Verify Stage2 param_ids match Top-K
    stage2_param_ids = set(r.param_id for r in result.stage2_results)
    topk_param_ids_set = set(result.topk_param_ids)
    assert stage2_param_ids == topk_param_ids_set, (
        f"Stage2 param_ids should match Top-K:\n"
        f"  Stage2: {stage2_param_ids}\n"
        f"  Top-K:  {topk_param_ids_set}"
    )


def test_funnel_stage0_no_pnl_fields():
    """Test that Stage0 results contain NO PnL-related fields."""
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
        k=5,
    )
    
    # Check all Stage0 results
    forbidden_fields = {"net", "profit", "mdd", "dd", "drawdown", "sqn", "sharpe", 
                       "winrate", "equity", "pnl", "trades", "score"}
    
    for stage0_result in result.stage0_results:
        # Get field names
        if hasattr(stage0_result, "__dataclass_fields__"):
            field_names = set(stage0_result.__dataclass_fields__.keys())
        else:
            field_names = set(getattr(stage0_result, "__dict__", {}).keys())
        
        # Check no forbidden fields
        for field_name in field_names:
            field_lower = field_name.lower()
            for forbidden in forbidden_fields:
                assert forbidden not in field_lower, (
                    f"Stage0Result contains forbidden PnL field: {field_name} "
                    f"(contains '{forbidden}')"
                )
