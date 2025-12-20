"""Integration tests for OOM gate in funnel pipeline.

Tests verify:
1. Funnel metrics include OOM gate fields
2. Auto-downsample updates snapshot and hash consistently
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np
import pytest

from FishBroWFS_V2.pipeline.funnel_runner import run_funnel


def test_funnel_metrics_include_oom_gate_fields():
    """Test that funnel metrics include OOM gate fields."""
    with tempfile.TemporaryDirectory() as tmpdir:
        outputs_root = Path(tmpdir) / "outputs"
        
        cfg = {
            "season": "test_season",
            "dataset_id": "test_dataset",
            "bars": 1000,
            "params_total": 100,
            "param_subsample_rate": 0.1,
            "open_": np.random.randn(1000).astype(np.float64),
            "high": np.random.randn(1000).astype(np.float64),
            "low": np.random.randn(1000).astype(np.float64),
            "close": np.random.randn(1000).astype(np.float64),
            "params_matrix": np.random.randn(100, 3).astype(np.float64),
            "commission": 0.0,
            "slip": 0.0,
            "order_qty": 1,
            "mem_limit_mb": 10000.0,  # High limit to ensure PASS
        }
        
        result_index = run_funnel(cfg, outputs_root)
        
        # Verify all stages have OOM gate fields in metrics
        for stage_idx in result_index.stages:
            run_dir = outputs_root / stage_idx.run_dir
            metrics_path = run_dir / "metrics.json"
            
            assert metrics_path.exists()
            
            with open(metrics_path, "r", encoding="utf-8") as f:
                metrics = json.load(f)
            
            # Verify required OOM gate fields
            assert "oom_gate_action" in metrics
            assert "oom_gate_reason" in metrics
            assert "mem_est_mb" in metrics
            assert "mem_limit_mb" in metrics
            assert "ops_est" in metrics
            assert "stage_planned_subsample" in metrics
            
            # Verify action is valid
            assert metrics["oom_gate_action"] in ("PASS", "BLOCK", "AUTO_DOWNSAMPLE")
            
            # Verify stage_planned_subsample matches expected planned for this stage
            stage_name = metrics.get("stage_name")
            s0_base = cfg.get("param_subsample_rate", 0.1)
            expected_planned = planned_subsample_for_stage(stage_name, s0_base)
            assert metrics["stage_planned_subsample"] == expected_planned, (
                f"stage_planned_subsample mismatch for {stage_name}: "
                f"expected={expected_planned}, got={metrics['stage_planned_subsample']}"
            )


def planned_subsample_for_stage(stage_name: str, s0: float) -> float:
    """
    Get planned subsample rate for a stage based on funnel plan rules.
    
    Args:
        stage_name: Stage identifier
        s0: Stage0 base subsample rate (from config)
        
    Returns:
        Planned subsample rate for the stage
    """
    if stage_name == "stage0_coarse":
        return s0
    if stage_name == "stage1_topk":
        return min(1.0, s0 * 2.0)
    if stage_name == "stage2_confirm":
        return 1.0
    raise AssertionError(f"Unknown stage_name: {stage_name}")


def test_auto_downsample_updates_snapshot_and_hash(monkeypatch):
    """Test that auto-downsample updates snapshot and hash consistently."""
    # Monkeypatch estimate_memory_bytes to trigger auto-downsample
    def mock_estimate_memory_bytes(cfg, work_factor=2.0):
        """Mock that makes memory estimate sensitive to subsample."""
        bars = int(cfg.get("bars", 0))
        params_total = int(cfg.get("params_total", 0))
        subsample_rate = float(cfg.get("param_subsample_rate", 1.0))
        params_effective = int(params_total * subsample_rate)
        
        base_mem = bars * 8 * 4  # 4 price arrays
        params_mem = params_effective * 3 * 8  # params_matrix
        total_mem = (base_mem + params_mem) * work_factor
        return int(total_mem)
    
    monkeypatch.setattr(
        "FishBroWFS_V2.core.oom_cost_model.estimate_memory_bytes",
        mock_estimate_memory_bytes,
    )
    
    with tempfile.TemporaryDirectory() as tmpdir:
        outputs_root = Path(tmpdir) / "outputs"
        
        # Stage0 base subsample rate (from config)
        s0_base = 0.5
        
        cfg = {
            "season": "test_season",
            "dataset_id": "test_dataset",
            "bars": 10000,
            "params_total": 1000,
            "param_subsample_rate": s0_base,  # Stage0 base rate
            "open_": np.random.randn(10000).astype(np.float64),
            "high": np.random.randn(10000).astype(np.float64),
            "low": np.random.randn(10000).astype(np.float64),
            "close": np.random.randn(10000).astype(np.float64),
            "params_matrix": np.random.randn(1000, 3).astype(np.float64),
            "commission": 0.0,
            "slip": 0.0,
            "order_qty": 1,
            # Dynamic limit calculation
            "mem_limit_mb": 0.65,  # Will trigger auto-downsample for some stages
            "allow_auto_downsample": True,
        }
        
        result_index = run_funnel(cfg, outputs_root)
        
        # Check each stage
        for stage_idx in result_index.stages:
            run_dir = outputs_root / stage_idx.run_dir
            
            # Read manifest
            manifest_path = run_dir / "manifest.json"
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            
            # Read config_snapshot
            config_snapshot_path = run_dir / "config_snapshot.json"
            with open(config_snapshot_path, "r", encoding="utf-8") as f:
                config_snapshot = json.load(f)
            
            # Read metrics
            metrics_path = run_dir / "metrics.json"
            with open(metrics_path, "r", encoding="utf-8") as f:
                metrics = json.load(f)
            
            # Get stage name and planned subsample
            stage_name = metrics.get("stage_name")
            expected_planned = planned_subsample_for_stage(stage_name, s0_base)
            
            # Verify consistency: if auto-downsample occurred, all must match
            if metrics.get("oom_gate_action") == "AUTO_DOWNSAMPLE":
                final_subsample = metrics.get("oom_gate_final_subsample")
                
                # Manifest must have final subsample
                assert manifest["param_subsample_rate"] == final_subsample, (
                    f"Manifest subsample mismatch: "
                    f"expected={final_subsample}, got={manifest['param_subsample_rate']}"
                )
                
                # Config snapshot must have final subsample
                assert config_snapshot["param_subsample_rate"] == final_subsample, (
                    f"Config snapshot subsample mismatch: "
                    f"expected={final_subsample}, got={config_snapshot['param_subsample_rate']}"
                )
                
                # Metrics must have final subsample
                assert metrics["param_subsample_rate"] == final_subsample, (
                    f"Metrics subsample mismatch: "
                    f"expected={final_subsample}, got={metrics['param_subsample_rate']}"
                )
                
                # Verify original subsample matches planned subsample for this stage
                assert "oom_gate_original_subsample" in metrics
                assert metrics["oom_gate_original_subsample"] == expected_planned, (
                    f"oom_gate_original_subsample mismatch for {stage_name}: "
                    f"expected={expected_planned} (planned), "
                    f"got={metrics['oom_gate_original_subsample']}"
                )
                
                # Verify stage_planned_subsample equals oom_gate_original_subsample
                assert "stage_planned_subsample" in metrics
                assert metrics["stage_planned_subsample"] == metrics["oom_gate_original_subsample"], (
                    f"stage_planned_subsample should equal oom_gate_original_subsample for {stage_name}: "
                    f"stage_planned={metrics['stage_planned_subsample']}, "
                    f"original={metrics['oom_gate_original_subsample']}"
                )


def test_oom_gate_fields_in_readme():
    """Test that OOM gate fields are included in README."""
    with tempfile.TemporaryDirectory() as tmpdir:
        outputs_root = Path(tmpdir) / "outputs"
        
        cfg = {
            "season": "test_season",
            "dataset_id": "test_dataset",
            "bars": 1000,
            "params_total": 100,
            "param_subsample_rate": 0.1,
            "open_": np.random.randn(1000).astype(np.float64),
            "high": np.random.randn(1000).astype(np.float64),
            "low": np.random.randn(1000).astype(np.float64),
            "close": np.random.randn(1000).astype(np.float64),
            "params_matrix": np.random.randn(100, 3).astype(np.float64),
            "commission": 0.0,
            "slip": 0.0,
            "order_qty": 1,
            "mem_limit_mb": 10000.0,
        }
        
        result_index = run_funnel(cfg, outputs_root)
        
        # Check README for at least one stage
        for stage_idx in result_index.stages:
            run_dir = outputs_root / stage_idx.run_dir
            readme_path = run_dir / "README.md"
            
            assert readme_path.exists()
            
            with open(readme_path, "r", encoding="utf-8") as f:
                readme_content = f.read()
            
            # Verify OOM gate section exists
            assert "OOM Gate" in readme_content
            assert "action" in readme_content.lower()
            assert "mem_est_mb" in readme_content.lower()
            
            break  # Check at least one stage


def test_block_action_raises_error():
    """Test that BLOCK action raises RuntimeError."""
    with tempfile.TemporaryDirectory() as tmpdir:
        outputs_root = Path(tmpdir) / "outputs"
        
        cfg = {
            "season": "test_season",
            "dataset_id": "test_dataset",
            "bars": 1000000,  # Very large
            "params_total": 100000,  # Very large
            "param_subsample_rate": 1.0,
            "open_": np.random.randn(1000000).astype(np.float64),
            "high": np.random.randn(1000000).astype(np.float64),
            "low": np.random.randn(1000000).astype(np.float64),
            "close": np.random.randn(1000000).astype(np.float64),
            "params_matrix": np.random.randn(100000, 3).astype(np.float64),
            "commission": 0.0,
            "slip": 0.0,
            "order_qty": 1,
            "mem_limit_mb": 1.0,  # Very low limit
            "allow_auto_downsample": False,  # Disable auto-downsample to force BLOCK
        }
        
        # Should raise RuntimeError
        with pytest.raises(RuntimeError, match="OOM Gate BLOCKED"):
            run_funnel(cfg, outputs_root)
