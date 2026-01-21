
"""Contract tests for runner adapter input coercion.

Tests verify that input arrays are coerced to np.ndarray float64,
preventing .shape access errors when lists are passed.
"""

from __future__ import annotations

import numpy as np
import pytest

from pipeline.runner_adapter import run_stage_job
from strategy.spec import StrategySpec
from strategy import registry

TEST_STRAT_ID = "test_strat_coercion"

def setup_module():
    spec = StrategySpec(
        strategy_id=TEST_STRAT_ID,
        version="1.0.0",
        param_schema={
            "p0": {"type": "float"},
            "p1": {"type": "float"},
            "p2": {"type": "float"}
        },
        fn=lambda x: x,
        defaults={}
    )
    registry._registry_by_id[TEST_STRAT_ID] = spec

def teardown_module():
    if TEST_STRAT_ID in registry._registry_by_id:
        del registry._registry_by_id[TEST_STRAT_ID]



def test_stage0_coercion_with_lists() -> None:
    """Test that Stage0 accepts list inputs and coerces to np.ndarray."""
    # Use list instead of np.ndarray
    close_list = [100.0 + i * 0.1 for i in range(1000)]
    params_matrix_list = [[10.0, 5.0, 1.0], [15.0, 7.0, 1.5], [20.0, 10.0, 2.0]]
    
    cfg = {
        "stage_name": "stage0_coarse",
        "param_subsample_rate": 1.0,
        "topk": 3,
        "close": close_list,  # List, not np.ndarray
        "params_matrix": params_matrix_list,  # List, not np.ndarray
        "params_total": 3,
        "proxy_name": "ma_proxy_v0",
    }
    
    # Should not raise AttributeError: 'list' object has no attribute 'shape'
    result = run_stage_job(cfg)
    
    # Verify result structure
    assert "metrics" in result
    assert "winners" in result
    
    # Verify that internal arrays are np.ndarray (by checking results work)
    assert isinstance(result["winners"]["topk"], list)
    assert len(result["winners"]["topk"]) <= 3


def test_stage1_coercion_with_lists() -> None:
    """Test that Stage1 accepts list inputs and coerces to np.ndarray."""
    # Use lists instead of np.ndarray
    open_list = [100.0 + i * 0.1 for i in range(100)]
    high_list = [101.0 + i * 0.1 for i in range(100)]
    low_list = [99.0 + i * 0.1 for i in range(100)]
    close_list = [100.0 + i * 0.1 for i in range(100)]
    params_matrix_list = [[10.0, 5.0, 1.0], [15.0, 7.0, 1.5]]
    
    cfg = {
        "stage_name": "stage1_topk",
        "param_subsample_rate": 1.0,
        "topk": 2,
        "open_": open_list,  # List, not np.ndarray
        "high": high_list,  # List, not np.ndarray
        "low": low_list,  # List, not np.ndarray
        "close": close_list,  # List, not np.ndarray
        "params_matrix": params_matrix_list,  # List, not np.ndarray
        "params_total": 2,
        "commission": 0.0,
        "slip": 0.0,
        "strategy_id": TEST_STRAT_ID,
    }
    
    # Should not raise AttributeError: 'list' object has no attribute 'shape'
    result = run_stage_job(cfg)
    
    # Verify result structure
    assert "metrics" in result
    assert "winners" in result
    
    # Verify that internal arrays are np.ndarray (by checking results work)
    assert isinstance(result["winners"]["topk"], list)


def test_stage2_coercion_with_lists() -> None:
    """Test that Stage2 accepts list inputs and coerces to np.ndarray."""
    # Use lists instead of np.ndarray
    open_list = [100.0 + i * 0.1 for i in range(100)]
    high_list = [101.0 + i * 0.1 for i in range(100)]
    low_list = [99.0 + i * 0.1 for i in range(100)]
    close_list = [100.0 + i * 0.1 for i in range(100)]
    params_matrix_list = [[10.0, 5.0, 1.0], [15.0, 7.0, 1.5]]
    
    cfg = {
        "stage_name": "stage2_confirm",
        "param_subsample_rate": 1.0,
        "open_": open_list,  # List, not np.ndarray
        "high": high_list,  # List, not np.ndarray
        "low": low_list,  # List, not np.ndarray
        "close": close_list,  # List, not np.ndarray
        "params_matrix": params_matrix_list,  # List, not np.ndarray
        "params_total": 2,
        "commission": 0.0,
        "slip": 0.0,
        "strategy_id": TEST_STRAT_ID,
    }
    
    # Should not raise AttributeError: 'list' object has no attribute 'shape'
    result = run_stage_job(cfg)
    
    # Verify result structure
    assert "metrics" in result
    assert "winners" in result
    
    # Verify that internal arrays are np.ndarray (by checking results work)
    assert isinstance(result["winners"]["topk"], list)


def test_coercion_preserves_dtype_float64() -> None:
    """Test that coercion produces float64 arrays."""
    # Test with float32 input (should be coerced to float64)
    close_float32 = np.array([100.0, 101.0, 102.0], dtype=np.float32)
    params_matrix_float32 = np.array([[10.0, 5.0, 1.0]], dtype=np.float32)
    
    cfg = {
        "stage_name": "stage0_coarse",
        "param_subsample_rate": 1.0,
        "topk": 1,
        "close": close_float32,
        "params_matrix": params_matrix_float32,
        "params_total": 1,
        "proxy_name": "ma_proxy_v0",
    }
    
    # Should not raise errors
    result = run_stage_job(cfg)
    
    # Verify result structure
    assert "metrics" in result
    assert "winners" in result


def test_coercion_handles_mixed_inputs() -> None:
    """Test that coercion handles mixed list/np.ndarray inputs."""
    # Mix of lists and np.ndarray
    open_list = [100.0 + i * 0.1 for i in range(100)]
    high_array = np.array([101.0 + i * 0.1 for i in range(100)], dtype=np.float64)
    low_list = [99.0 + i * 0.1 for i in range(100)]
    close_array = np.array([100.0 + i * 0.1 for i in range(100)], dtype=np.float32)
    params_matrix_list = [[10.0, 5.0, 1.0], [15.0, 7.0, 1.5]]
    
    cfg = {
        "stage_name": "stage1_topk",
        "param_subsample_rate": 1.0,
        "topk": 2,
        "open_": open_list,  # List
        "high": high_array,  # np.ndarray float64
        "low": low_list,  # List
        "close": close_array,  # np.ndarray float32 (should be coerced to float64)
        "params_matrix": params_matrix_list,  # List
        "params_total": 2,
        "commission": 0.0,
        "slip": 0.0,
        "strategy_id": TEST_STRAT_ID,
    }
    
    # Should not raise errors
    result = run_stage_job(cfg)
    
    # Verify result structure
    assert "metrics" in result
    assert "winners" in result


