"""Test that the default strategy registry contains S1."""

from __future__ import annotations

import pytest
from strategy.registry import load_builtin_strategies


def test_default_strategy_registry_contains_s1():
    """Ensure S1 is registered in the default strategy registry."""
    # Load builtin strategies (idempotent)
    load_builtin_strategies()
    
    # Get the default registry (global module-level registry)
    # The registry is accessed via the module-level functions
    from strategy.registry import get, list_strategies
    
    # Verify S1 exists
    spec = get("S1")
    assert spec.strategy_id == "S1"
    assert spec.version == "v1"
    
    # Verify via list
    strategies = list_strategies()
    strategy_ids = [s.strategy_id for s in strategies]
    assert "S1" in strategy_ids


def test_s1_feature_requirements():
    """Ensure S1 provides feature requirements (Config Constitution v1: YAML only)."""
    from strategy.registry import get, load_builtin_strategies
    load_builtin_strategies()
    
    spec = get("S1")
    
    # Check if spec has feature_requirements method
    if hasattr(spec, "feature_requirements") and callable(spec.feature_requirements):
        req = spec.feature_requirements()
        from contracts.strategy_features import StrategyFeatureRequirements
        assert isinstance(req, StrategyFeatureRequirements)
        assert req.strategy_id == "S1"
        # Should have at least the 16 registry features + baseline
        assert len(req.required) >= 18
    else:
        # Config Constitution v1: Check for YAML file
        import yaml
        from pathlib import Path
        yaml_path = Path("configs/strategies/s1_v1.yaml")
        assert yaml_path.exists(), f"S1 feature requirements YAML not found at {yaml_path}"
        with open(yaml_path, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        assert data["strategy_id"] == "s1_v1"
        assert len(data.get("features", [])) >= 18


def test_s1_registry_deterministic():
    """Ensure registry loading is deterministic (same order each time)."""
    from strategy.registry import clear, load_builtin_strategies, list_strategies
    
    # Clear and load twice
    clear()
    load_builtin_strategies()
    first = [s.strategy_id for s in list_strategies()]
    
    clear()
    load_builtin_strategies()
    second = [s.strategy_id for s in list_strategies()]
    
    assert first == second, "Registry loading is not deterministic"
    assert "S1" in first


def test_run_research_resolves_s1():
    """Ensure run_research can resolve S1 without allow_build."""
    from pathlib import Path
    import tempfile
    import numpy as np
    
    # Create a minimal features cache to satisfy feature resolver
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        outputs_root = tmp_path / "outputs"
        season = "TEST2026Q1"
        dataset_id = "TEST.MNQ"
        
        # Create features directory
        features_dir = outputs_root / "shared" / season / dataset_id / "features"
        features_dir.mkdir(parents=True, exist_ok=True)
        
        # Write dummy features NPZ (just ts and a few features)
        n = 10
        ts = np.arange(n).astype("datetime64[s]")
        features_data = {
            "ts": ts,
            "sma_5": np.random.randn(n),
            "sma_20": np.random.randn(n),
            "ret_z_200": np.random.randn(n),
            "session_vwap": np.random.randn(n),
        }
        # Add all required features
        for name in ["sma_5", "sma_10", "sma_20", "sma_40",
                     "hh_5", "hh_10", "hh_20", "hh_40",
                     "ll_5", "ll_10", "ll_20", "ll_40",
                     "atr_10", "atr_14",
                     "vx_percentile_126", "vx_percentile_252"]:
            if name not in features_data:
                features_data[name] = np.random.randn(n)
        
        import numpy as np
        np.savez(features_dir / "features_60m.npz", **features_data)
        
        # Create features manifest
        from control.features_manifest import (
            build_features_manifest_data,
            write_features_manifest,
        )
        from contracts.features import FeatureSpec, FeatureRegistry
        
        registry = FeatureRegistry(specs=[
            FeatureSpec(name=name, timeframe_min=60, lookback_bars=14)
            for name in features_data.keys() if name != "ts"
        ])
        
        manifest_data = build_features_manifest_data(
            season=season,
            dataset_id=dataset_id,
            mode="FULL",
            ts_dtype="datetime64[s]",
            breaks_policy="drop",
            features_specs=[spec.model_dump() for spec in registry.specs],
            append_only=False,
            append_range=None,
            lookback_rewind_by_tf={},
            files_sha256={"features_60m.npz": "dummy"},
        )
        write_features_manifest(manifest_data, features_dir / "features_manifest.json")
        
        # Create strategy requirements JSON (outputs artifact, allowed)
        strategy_dir = outputs_root / "strategies" / "S1"
        strategy_dir.mkdir(parents=True, exist_ok=True)
        import json
        req_data = {
            "strategy_id": "S1",
            "required": [{"name": name, "timeframe_min": 60} for name in features_data.keys() if name != "ts"],
            "optional": [],
            "min_schema_version": "v1",
            "notes": "test"
        }
        (strategy_dir / "features.json").write_text(json.dumps(req_data))
        
        # Now test that run_research can resolve S1
        from control.research_runner import run_research
        from strategy.registry import load_builtin_strategies
        
        load_builtin_strategies()
        
        # This should not raise "Strategy 'S1' not found in registry"
        report = run_research(
            season=season,
            dataset_id=dataset_id,
            strategy_id="S1",
            outputs_root=outputs_root,
            allow_build=False,
            wfs_config=None,
        )
        
        assert report["strategy_id"] == "S1"
        assert report["dataset_id"] == dataset_id
        assert report["season"] == season
        assert not report["build_performed"]  # No build needed


if __name__ == "__main__":
    pytest.main([__file__, "-v"])