
"""Contract tests for OOM gate.

Tests verify:
1. Gate PASS when under limit
2. Gate BLOCK when over limit and no auto-downsample
3. Gate AUTO_DOWNSAMPLE when allowed
"""

from __future__ import annotations

import numpy as np
import pytest

from FishBroWFS_V2.core.oom_gate import decide_oom_action
from FishBroWFS_V2.core.oom_cost_model import estimate_memory_bytes, summarize_estimates


def test_oom_gate_pass_when_under_limit():
    """Test that gate PASSes when memory estimate is under limit."""
    cfg = {
        "bars": 1000,
        "params_total": 100,
        "param_subsample_rate": 0.1,
        "open_": np.random.randn(1000).astype(np.float64),
        "high": np.random.randn(1000).astype(np.float64),
        "low": np.random.randn(1000).astype(np.float64),
        "close": np.random.randn(1000).astype(np.float64),
        "params_matrix": np.random.randn(100, 3).astype(np.float64),
    }
    
    # Use a very high limit to ensure PASS
    mem_limit_mb = 10000.0
    
    result = decide_oom_action(cfg, mem_limit_mb=mem_limit_mb)
    
    assert result["action"] == "PASS"
    assert result["original_subsample"] == 0.1
    assert result["final_subsample"] == 0.1
    assert "estimates" in result
    assert result["estimates"]["mem_est_mb"] <= mem_limit_mb


def test_oom_gate_block_when_over_limit_and_no_auto():
    """Test that gate BLOCKs when over limit and auto-downsample is disabled."""
    cfg = {
        "bars": 100000,
        "params_total": 10000,
        "param_subsample_rate": 1.0,
        "open_": np.random.randn(100000).astype(np.float64),
        "high": np.random.randn(100000).astype(np.float64),
        "low": np.random.randn(100000).astype(np.float64),
        "close": np.random.randn(100000).astype(np.float64),
        "params_matrix": np.random.randn(10000, 3).astype(np.float64),
    }
    
    # Use a very low limit to ensure BLOCK
    mem_limit_mb = 1.0
    
    result = decide_oom_action(
        cfg,
        mem_limit_mb=mem_limit_mb,
        allow_auto_downsample=False,
    )
    
    assert result["action"] == "BLOCK"
    assert result["original_subsample"] == 1.0
    assert result["final_subsample"] == 1.0  # Not changed
    assert "reason" in result
    assert "mem_est_mb" in result["reason"] or "limit" in result["reason"]


def test_oom_gate_auto_downsample_when_allowed(monkeypatch):
    """Test that gate AUTO_DOWNSAMPLEs when allowed and over limit."""
    # Monkeypatch estimate_memory_bytes to make it subsample-sensitive for testing
    def mock_estimate_memory_bytes(cfg, work_factor=2.0):
        """Mock that makes memory estimate sensitive to subsample."""
        bars = int(cfg.get("bars", 0))
        params_total = int(cfg.get("params_total", 0))
        subsample_rate = float(cfg.get("param_subsample_rate", 1.0))
        params_effective = int(params_total * subsample_rate)
        
        # Simplified: mem scales with bars and effective params
        base_mem = bars * 8 * 4  # 4 price arrays
        params_mem = params_effective * 3 * 8  # params_matrix
        total_mem = (base_mem + params_mem) * work_factor
        return int(total_mem)
    
    monkeypatch.setattr(
        "FishBroWFS_V2.core.oom_cost_model.estimate_memory_bytes",
        mock_estimate_memory_bytes,
    )
    
    cfg = {
        "bars": 10000,
        "params_total": 1000,
        "param_subsample_rate": 0.5,  # Start at 50%
        "open_": np.random.randn(10000).astype(np.float64),
        "high": np.random.randn(10000).astype(np.float64),
        "low": np.random.randn(10000).astype(np.float64),
        "close": np.random.randn(10000).astype(np.float64),
        "params_matrix": np.random.randn(1000, 3).astype(np.float64),
    }
    
    # Dynamic calculation: compute mem_mb for two subsample rates, use midpoint
    def _mem_mb(cfg_dict):
        b = mock_estimate_memory_bytes(cfg_dict, work_factor=2.0)
        return b / (1024.0 * 1024.0)
    
    cfg_half = dict(cfg)
    cfg_half["param_subsample_rate"] = 0.5
    cfg_quarter = dict(cfg)
    cfg_quarter["param_subsample_rate"] = 0.25
    
    mb_half = _mem_mb(cfg_half)  # ~0.633
    mb_quarter = _mem_mb(cfg_quarter)  # ~0.622
    
    # Set limit between these two values → guaranteed to trigger AUTO_DOWNSAMPLE
    mem_limit_mb = (mb_half + mb_quarter) / 2.0
    
    result = decide_oom_action(
        cfg,
        mem_limit_mb=mem_limit_mb,
        allow_auto_downsample=True,
        auto_downsample_step=0.5,
        auto_downsample_min=0.02,
    )
    
    assert result["action"] == "AUTO_DOWNSAMPLE"
    assert result["original_subsample"] == 0.5
    assert result["final_subsample"] < result["original_subsample"]
    assert result["final_subsample"] >= 0.02  # Above minimum
    assert "reason" in result
    assert "auto-downsample" in result["reason"].lower()
    assert result["estimates"]["mem_est_mb"] <= mem_limit_mb


def test_oom_gate_block_when_min_still_over_limit(monkeypatch):
    """Test that gate BLOCKs when even at minimum subsample still over limit."""
    def mock_estimate_memory_bytes(cfg, work_factor=2.0):
        """Mock that always returns high memory."""
        return 100 * 1024 * 1024  # Always 100MB
    
    monkeypatch.setattr(
        "FishBroWFS_V2.core.oom_cost_model.estimate_memory_bytes",
        mock_estimate_memory_bytes,
    )
    
    cfg = {
        "bars": 1000,
        "params_total": 100,
        "param_subsample_rate": 0.5,
        "open_": np.random.randn(1000).astype(np.float64),
        "high": np.random.randn(1000).astype(np.float64),
        "low": np.random.randn(1000).astype(np.float64),
        "close": np.random.randn(1000).astype(np.float64),
        "params_matrix": np.random.randn(100, 3).astype(np.float64),
    }
    
    mem_limit_mb = 50.0  # Lower than mock estimate
    
    result = decide_oom_action(
        cfg,
        mem_limit_mb=mem_limit_mb,
        allow_auto_downsample=True,
        auto_downsample_min=0.02,
    )
    
    assert result["action"] == "BLOCK"
    assert "min_subsample" in result["reason"].lower() or "still too large" in result["reason"].lower()


def test_oom_gate_result_schema():
    """Test that gate result has correct schema."""
    cfg = {
        "bars": 1000,
        "params_total": 100,
        "param_subsample_rate": 0.1,
        "open_": np.random.randn(1000).astype(np.float64),
        "high": np.random.randn(1000).astype(np.float64),
        "low": np.random.randn(1000).astype(np.float64),
        "close": np.random.randn(1000).astype(np.float64),
        "params_matrix": np.random.randn(100, 3).astype(np.float64),
    }
    
    result = decide_oom_action(cfg, mem_limit_mb=10000.0)
    
    # Verify schema
    assert "action" in result
    assert result["action"] in ("PASS", "BLOCK", "AUTO_DOWNSAMPLE")
    assert "reason" in result
    assert isinstance(result["reason"], str)
    assert "original_subsample" in result
    assert "final_subsample" in result
    assert "estimates" in result
    
    # Verify estimates structure
    estimates = result["estimates"]
    assert "mem_est_bytes" in estimates
    assert "mem_est_mb" in estimates
    assert "ops_est" in estimates
    assert "time_est_s" in estimates


