"""Contract tests for funnel pipeline.

Tests verify:
1. Funnel plan has three stages
2. Stage2 subsample is 1.0
3. Each stage creates artifacts
4. param_subsample_rate visibility
5. params_effective calculation consistency
6. Funnel result index structure
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pytest

from FishBroWFS_V2.core.audit_schema import compute_params_effective
from FishBroWFS_V2.pipeline.funnel_plan import build_default_funnel_plan
from FishBroWFS_V2.pipeline.funnel_runner import run_funnel
from FishBroWFS_V2.pipeline.funnel_schema import StageName


def test_funnel_build_default_plan_has_three_stages():
    """Test that default funnel plan has exactly three stages."""
    cfg = {
        "param_subsample_rate": 0.1,
        "topk_stage0": 50,
        "topk_stage1": 20,
    }
    
    plan = build_default_funnel_plan(cfg)
    
    assert len(plan.stages) == 3
    
    # Verify stage names
    assert plan.stages[0].name == StageName.STAGE0_COARSE
    assert plan.stages[1].name == StageName.STAGE1_TOPK
    assert plan.stages[2].name == StageName.STAGE2_CONFIRM


def test_stage2_subsample_is_one():
    """Test that Stage2 subsample rate is always 1.0."""
    test_cases = [
        {"param_subsample_rate": 0.1},
        {"param_subsample_rate": 0.5},
        {"param_subsample_rate": 0.9},
    ]
    
    for cfg in test_cases:
        plan = build_default_funnel_plan(cfg)
        stage2 = plan.stages[2]
        
        assert stage2.name == StageName.STAGE2_CONFIRM
        assert stage2.param_subsample_rate == 1.0, (
            f"Stage2 subsample must be 1.0, got {stage2.param_subsample_rate}"
        )


def test_subsample_rate_progression():
    """Test that subsample rates progress correctly."""
    cfg = {"param_subsample_rate": 0.1}
    plan = build_default_funnel_plan(cfg)
    
    s0_rate = plan.stages[0].param_subsample_rate
    s1_rate = plan.stages[1].param_subsample_rate
    s2_rate = plan.stages[2].param_subsample_rate
    
    # Stage0: config rate
    assert s0_rate == 0.1
    
    # Stage1: min(1.0, s0 * 2)
    assert s1_rate == min(1.0, 0.1 * 2.0) == 0.2
    
    # Stage2: must be 1.0
    assert s2_rate == 1.0
    
    # Verify progression: s0 <= s1 <= s2
    assert s0_rate <= s1_rate <= s2_rate


def test_each_stage_creates_run_dir_with_artifacts():
    """Test that each stage creates run directory with required artifacts."""
    with tempfile.TemporaryDirectory() as tmpdir:
        outputs_root = Path(tmpdir) / "outputs"
        
        # Create minimal config
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
        }
        
        # Run funnel
        result_index = run_funnel(cfg, outputs_root)
        
        # Verify all stages have run directories
        assert len(result_index.stages) == 3
        
        artifacts = [
            "manifest.json",
            "config_snapshot.json",
            "metrics.json",
            "winners.json",
            "README.md",
            "logs.txt",
        ]
        
        for stage_idx in result_index.stages:
            run_dir = outputs_root / stage_idx.run_dir
            
            # Verify directory exists
            assert run_dir.exists(), f"Run directory missing for {stage_idx.stage.value}"
            assert run_dir.is_dir()
            
            # Verify all artifacts exist
            for artifact_name in artifacts:
                artifact_path = run_dir / artifact_name
                assert artifact_path.exists(), (
                    f"Missing artifact {artifact_name} for {stage_idx.stage.value}"
                )


def test_param_subsample_rate_visible_in_artifacts():
    """Test that param_subsample_rate is visible in manifest/metrics/README."""
    with tempfile.TemporaryDirectory() as tmpdir:
        outputs_root = Path(tmpdir) / "outputs"
        
        cfg = {
            "season": "test_season",
            "dataset_id": "test_dataset",
            "bars": 1000,
            "params_total": 100,
            "param_subsample_rate": 0.25,
            "open_": np.random.randn(1000).astype(np.float64),
            "high": np.random.randn(1000).astype(np.float64),
            "low": np.random.randn(1000).astype(np.float64),
            "close": np.random.randn(1000).astype(np.float64),
            "params_matrix": np.random.randn(100, 3).astype(np.float64),
            "commission": 0.0,
            "slip": 0.0,
            "order_qty": 1,
        }
        
        result_index = run_funnel(cfg, outputs_root)
        
        import json
        
        for stage_idx in result_index.stages:
            run_dir = outputs_root / stage_idx.run_dir
            
            # Check manifest.json
            manifest_path = run_dir / "manifest.json"
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            assert "param_subsample_rate" in manifest
            
            # Check metrics.json
            metrics_path = run_dir / "metrics.json"
            with open(metrics_path, "r", encoding="utf-8") as f:
                metrics = json.load(f)
            assert "param_subsample_rate" in metrics
            
            # Check README.md
            readme_path = run_dir / "README.md"
            with open(readme_path, "r", encoding="utf-8") as f:
                readme_content = f.read()
            assert "param_subsample_rate" in readme_content


def test_params_effective_floor_rule_consistent():
    """Test that params_effective uses consistent floor rule across stages."""
    with tempfile.TemporaryDirectory() as tmpdir:
        outputs_root = Path(tmpdir) / "outputs"
        
        params_total = 1000
        param_subsample_rate = 0.33
        
        cfg = {
            "season": "test_season",
            "dataset_id": "test_dataset",
            "bars": 1000,
            "params_total": params_total,
            "param_subsample_rate": param_subsample_rate,
            "open_": np.random.randn(1000).astype(np.float64),
            "high": np.random.randn(1000).astype(np.float64),
            "low": np.random.randn(1000).astype(np.float64),
            "close": np.random.randn(1000).astype(np.float64),
            "params_matrix": np.random.randn(params_total, 3).astype(np.float64),
            "commission": 0.0,
            "slip": 0.0,
            "order_qty": 1,
        }
        
        result_index = run_funnel(cfg, outputs_root)
        
        import json
        
        plan = result_index.plan
        for i, (spec, stage_idx) in enumerate(zip(plan.stages, result_index.stages)):
            run_dir = outputs_root / stage_idx.run_dir
            
            # Read manifest
            manifest_path = run_dir / "manifest.json"
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
            
            # Verify params_effective matches computed value
            expected_effective = compute_params_effective(
                params_total, spec.param_subsample_rate
            )
            assert manifest["params_effective"] == expected_effective, (
                f"Stage {i} params_effective mismatch: "
                f"expected={expected_effective}, got={manifest['params_effective']}"
            )


def test_funnel_result_index_contains_all_stages():
    """Test that funnel result index contains all stages."""
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
        }
        
        result_index = run_funnel(cfg, outputs_root)
        
        # Verify index structure
        assert result_index.plan is not None
        assert len(result_index.stages) == 3
        
        # Verify stage order matches plan
        for spec, stage_idx in zip(result_index.plan.stages, result_index.stages):
            assert spec.name == stage_idx.stage
            assert stage_idx.run_id is not None
            assert stage_idx.run_dir is not None


def test_config_snapshot_is_json_serializable_and_small():
    """Test that config_snapshot.json excludes ndarrays and is JSON-serializable."""
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
        }
        
        result_index = run_funnel(cfg, outputs_root)
        
        import json
        
        # Keys that should NOT exist in snapshot (raw ndarrays)
        forbidden_keys = {"open_", "open", "high", "low", "close", "volume", "params_matrix"}
        
        # Required keys that MUST exist
        required_keys = {
            "season",
            "dataset_id",
            "bars",
            "params_total",
            "param_subsample_rate",
            "stage_name",
        }
        
        for stage_idx in result_index.stages:
            run_dir = outputs_root / stage_idx.run_dir
            config_snapshot_path = run_dir / "config_snapshot.json"
            
            assert config_snapshot_path.exists()
            
            # Verify JSON is valid and loadable
            with open(config_snapshot_path, "r", encoding="utf-8") as f:
                snapshot_content = f.read()
                snapshot_data = json.loads(snapshot_content)  # Should not crash
            
            # Verify no raw ndarray keys exist
            for forbidden_key in forbidden_keys:
                assert forbidden_key not in snapshot_data, (
                    f"config_snapshot.json should not contain '{forbidden_key}' "
                    f"(raw ndarray) for {stage_idx.stage.value}"
                )
            
            # Verify required keys exist
            for required_key in required_keys:
                assert required_key in snapshot_data, (
                    f"config_snapshot.json missing required key '{required_key}' "
                    f"for {stage_idx.stage.value}"
                )
            
            # Verify param_subsample_rate is present and correct
            assert "param_subsample_rate" in snapshot_data
            assert isinstance(snapshot_data["param_subsample_rate"], (int, float))
            
            # Verify stage_name is present
            assert "stage_name" in snapshot_data
            assert isinstance(snapshot_data["stage_name"], str)
            
            # Optional: verify metadata keys exist if needed
            # (e.g., "open__meta", "params_matrix_meta")
            # This is optional - metadata may or may not be included
