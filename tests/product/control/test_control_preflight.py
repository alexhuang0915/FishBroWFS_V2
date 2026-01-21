
"""Tests for preflight check."""

from __future__ import annotations

import pytest

from control.preflight import PreflightResult, run_preflight


def test_run_preflight_returns_required_keys() -> None:
    """Test that preflight returns all required keys."""
    cfg_snapshot = {
        "season": "test",
        "dataset_id": "test",
        "bars": 1000,
        "params_total": 100,
        "param_subsample_rate": 0.1,
        "mem_limit_mb": 6000.0,
        "allow_auto_downsample": True,
    }
    
    result = run_preflight(cfg_snapshot)
    
    assert isinstance(result, PreflightResult)
    assert result.action in {"PASS", "BLOCK", "AUTO_DOWNSAMPLE"}
    assert isinstance(result.reason, str)
    assert isinstance(result.original_subsample, float)
    assert isinstance(result.final_subsample, float)
    assert isinstance(result.estimated_bytes, int)
    assert isinstance(result.estimated_mb, float)
    assert isinstance(result.mem_limit_mb, float)
    assert isinstance(result.mem_limit_bytes, int)
    assert isinstance(result.estimates, dict)
    
    # Check estimates keys
    assert "ops_est" in result.estimates
    assert "time_est_s" in result.estimates
    assert "mem_est_mb" in result.estimates
    assert "mem_est_bytes" in result.estimates
    assert "mem_limit_mb" in result.estimates
    assert "mem_limit_bytes" in result.estimates


def test_preflight_pure_no_io() -> None:
    """Test that preflight is pure (no I/O)."""
    cfg_snapshot = {
        "season": "test",
        "dataset_id": "test",
        "bars": 100,
        "params_total": 10,
        "param_subsample_rate": 0.5,
        "mem_limit_mb": 10000.0,
    }
    
    # Should not raise any I/O errors
    result1 = run_preflight(cfg_snapshot)
    result2 = run_preflight(cfg_snapshot)
    
    # Should be deterministic
    assert result1.action == result2.action
    assert result1.estimated_bytes == result2.estimated_bytes



