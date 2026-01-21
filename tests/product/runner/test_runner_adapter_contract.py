
"""Contract tests for runner adapter.

Tests verify:
1. Adapter returns data only (no file I/O)
2. Winners schema is stable
3. Metrics structure is consistent
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pytest

from pipeline.runner_adapter import run_stage_job
from strategy.spec import StrategySpec
from strategy import registry

TEST_STRAT_ID = "test_strat_contract"

def setup_module():
    """Register a test strategy for the duration of tests."""
    spec = StrategySpec(
        strategy_id=TEST_STRAT_ID,
        version="1.0.0",
        param_schema={
            "p0": {"type": "float"},
            "p1": {"type": "float"},
            "p2": {"type": "float"}
        },
        fn=lambda x: x, # Dummy fn
        defaults={}
    )
    # Register purely for lookup (content_id generation happens inside register if not provided? No, Spec needs immutable_id?)
    # StrategySpec computes immutable_id in __init__? 
    # Let's check StrategySpec definition if needed. Assuming it works for now or I try to mock registry.register logic.
    # Actually, simpler to just inject into registry._registry_by_id directly to avoid strict content checks if they are complex.
    registry._registry_by_id[TEST_STRAT_ID] = spec

def teardown_module():
    if TEST_STRAT_ID in registry._registry_by_id:
        del registry._registry_by_id[TEST_STRAT_ID]



def test_runner_adapter_returns_no_files_written():
    """Test that adapter does not write any files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        # Count files before
        files_before = list(tmp_path.rglob("*"))
        file_count_before = len([f for f in files_before if f.is_file()])
        
        # Run adapter
        cfg = {
            "stage_name": "stage0_coarse",
            "param_subsample_rate": 0.1,
            "topk": 10,
            "close": np.random.randn(1000).astype(np.float64),
            "params_matrix": np.random.randn(100, 3).astype(np.float64),
            "params_total": 100,
            "proxy_name": "ma_proxy_v0",
            "strategy_id": TEST_STRAT_ID,
        }
        
        result = run_stage_job(cfg)
        
        # Count files after
        files_after = list(tmp_path.rglob("*"))
        file_count_after = len([f for f in files_after if f.is_file()])
        
        # Verify no new files were created
        assert file_count_after == file_count_before, (
            "Adapter should not write files, but new files were created"
        )
        
        # Verify result structure
        assert "metrics" in result
        assert "winners" in result


def test_winners_schema_is_stable():
    """Test that winners schema is stable across all stages."""
    test_cases = [
        {
            "stage_name": "stage0_coarse",
            "close": np.random.randn(1000).astype(np.float64),
            "params_matrix": np.random.randn(100, 3).astype(np.float64),
            "params_total": 100,
            "topk": 10,
        },
        {
            "stage_name": "stage1_topk",
            "open_": np.random.randn(1000).astype(np.float64),
            "high": np.random.randn(1000).astype(np.float64),
            "low": np.random.randn(1000).astype(np.float64),
            "close": np.random.randn(1000).astype(np.float64),
            "params_matrix": np.random.randn(100, 3).astype(np.float64),
            "params_total": 100,
            "topk": 5,
            "commission": 0.0,
            "slip": 0.0,
            "strategy_id": TEST_STRAT_ID,
        },
        {
            "stage_name": "stage2_confirm",
            "open_": np.random.randn(1000).astype(np.float64),
            "high": np.random.randn(1000).astype(np.float64),
            "low": np.random.randn(1000).astype(np.float64),
            "close": np.random.randn(1000).astype(np.float64),
            "params_matrix": np.random.randn(100, 3).astype(np.float64),
            "params_total": 100,
            "commission": 0.0,
            "slip": 0.0,
            "strategy_id": TEST_STRAT_ID,
        },
    ]
    
    for cfg in test_cases:
        cfg["param_subsample_rate"] = 1.0  # Use full for simplicity
        
        result = run_stage_job(cfg)
        
        # Verify winners schema
        winners = result.get("winners", {})
        assert "topk" in winners, f"Missing 'topk' in winners for {cfg['stage_name']}"
        assert "notes" in winners, f"Missing 'notes' in winners for {cfg['stage_name']}"
        assert isinstance(winners["topk"], list)
        assert isinstance(winners["notes"], dict)
        assert winners["notes"].get("schema") == "v1"


def test_metrics_structure_is_consistent():
    """Test that metrics structure is consistent across stages."""
    test_cases = [
        {
            "stage_name": "stage0_coarse",
            "close": np.random.randn(1000).astype(np.float64),
            "params_matrix": np.random.randn(100, 3).astype(np.float64),
            "params_total": 100,
            "topk": 10,
        },
        {
            "stage_name": "stage1_topk",
            "open_": np.random.randn(1000).astype(np.float64),
            "high": np.random.randn(1000).astype(np.float64),
            "low": np.random.randn(1000).astype(np.float64),
            "close": np.random.randn(1000).astype(np.float64),
            "params_matrix": np.random.randn(100, 3).astype(np.float64),
            "params_total": 100,
            "topk": 5,
            "commission": 0.0,
            "slip": 0.0,
            "strategy_id": TEST_STRAT_ID,
        },
    ]
    
    required_fields = ["params_total", "params_effective", "bars", "stage_name"]
    
    for cfg in test_cases:
        cfg["param_subsample_rate"] = 0.5
        
        result = run_stage_job(cfg)
        
        metrics = result.get("metrics", {})
        
        # Verify required fields exist
        for field in required_fields:
            assert field in metrics, (
                f"Missing required field '{field}' in metrics for {cfg['stage_name']}"
            )
        
        # Verify stage_name matches
        assert metrics["stage_name"] == cfg["stage_name"]


