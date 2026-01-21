import pytest
import numpy as np
from unittest.mock import patch, MagicMock
from src.pipeline.runner_adapter import _run_stage1_job, _run_stage2_job

@patch("src.pipeline.runner_adapter.run_grid")
def test_runner_adapter_stage1_exports_candidates(mock_run_grid):
    """Verify Stage 1 job returns plateau_candidates."""
    # Mock run_grid result
    # metrics_array: [net_profit, trades, max_dd]
    mock_metrics_array = np.array([
        [100.0, 10, -50.0], # param_id 0: score 100
        [200.0, 5, -20.0],  # param_id 1: score 200
    ], dtype=np.float64)
    
    mock_run_grid.return_value = {
        "metrics": mock_metrics_array,
        "perf": {"t_total_s": 0.5}
    }
    
    # Mock data
    params_matrix = np.array([
        [10, 20, 2.0],  # param_id 0
        [15, 25, 3.0],  # param_id 1
    ], dtype=np.float64)
    
    # OHLC arrays
    data = np.ones(100, dtype=np.float64)
    
    cfg = {
        "params_matrix": params_matrix,
        "metrics_array": mock_metrics_array,
        "topk": 1,
        "open_": data,
        "high": data,
        "low": data,
        "close": data,
        "commission": 0.0,
        "slip": 0.0,
    }
    
    # Run
    out = _run_stage1_job(cfg)
    
    # Assertions
    assert "plateau_candidates" in out
    candidates = out["plateau_candidates"]
    assert len(candidates) == 2
    
    # Check sorting (descending by score)
    assert candidates[0]["param_id"] == 1
    assert candidates[0]["score"] == 200.0
    assert candidates[0]["params"] == {"channel_len": 15, "atr_len": 25, "stop_mult": 3.0}
    
    assert candidates[1]["param_id"] == 0
    assert candidates[1]["score"] == 100.0
    assert candidates[1]["params"] == {"channel_len": 10, "atr_len": 20, "stop_mult": 2.0}

@patch("src.pipeline.runner_adapter.run_stage2")
def test_runner_adapter_stage2_exports_candidates(mock_run_stage2):
    """Verify Stage 2 job returns plateau_candidates."""
    from src.pipeline.stage2_runner import Stage2Result
    
    # Mock data
    params_matrix = np.array([
        [10, 20, 2.0],
    ], dtype=np.float64)
    
    stage2_results = [
        Stage2Result(param_id=0, net_profit=150.0, trades=12, max_dd=-30.0)
    ]
    
    mock_run_stage2.return_value = stage2_results
    
    # OHLC arrays
    data = np.ones(100, dtype=np.float64)
    
    cfg = {
        "params_matrix": params_matrix,
        "stage2_results": stage2_results,
        "metrics": {"total_profit": 150.0},
        "open_": data,
        "high": data,
        "low": data,
        "close": data,
        "commission": 0.0,
        "slip": 0.0,
    }
    
    # Run
    out = _run_stage2_job(cfg)
    
    # Assertions
    assert "plateau_candidates" in out
    candidates = out["plateau_candidates"]
    assert len(candidates) == 1
    assert candidates[0]["param_id"] == 0
    assert candidates[0]["score"] == 150.0
    assert candidates[0]["params"] == {"channel_len": 10, "atr_len": 20, "stop_mult": 2.0}
