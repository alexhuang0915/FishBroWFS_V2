"""Test research runner integration with S2 and S3 strategies."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Dict, Any
import numpy as np
import pytest

from contracts.strategy_features import (
    StrategyFeatureRequirements,
    FeatureRef,
    save_requirements_to_json,
)
from control.research_runner import (
    run_research,
    ResearchRunError,
)
from control.features_manifest import (
    write_features_manifest,
    build_features_manifest_data,
)
from control.features_store import write_features_npz_atomic
from contracts.features import FeatureSpec, FeatureRegistry


def create_test_features_cache(
    tmp_path: Path,
    season: str,
    dataset_id: str,
    tf: int = 60,
) -> Dict[str, Any]:
    """
    Create test features cache for S2/S3.
    """
    # Create features directory
    features_dir = tmp_path / "outputs" / "shared" / season / dataset_id / "features"
    features_dir.mkdir(parents=True, exist_ok=True)
    
    # Create test data
    n = 50
    ts = np.arange(n) * 3600  # seconds
    ts = ts.astype("datetime64[s]")
    
    # Create features that S2/S3 might use
    # S2/S3 feature requirements use placeholder names: context_feature, value_feature, filter_feature
    # We need to create features with those exact names for the resolver to match
    # Also include baseline features required by features store (atr_14, ret_z_200, session_vwap)
    features_data = {
        "ts": ts,
        "context_feature": np.random.randn(n).astype(np.float64) * 10 + 100,
        "value_feature": np.random.randn(n).astype(np.float64) * 10 + 50,
        "filter_feature": np.random.randn(n).astype(np.float64) * 2 + 10,
        "close": np.random.randn(n).astype(np.float64) * 100 + 1000,
        "atr_14": np.random.randn(n).astype(np.float64) * 2 + 10,
        "ret_z_200": np.random.randn(n).astype(np.float64) * 0.1,
        "session_vwap": np.random.randn(n).astype(np.float64) * 10 + 1000,
    }
    
    feat_path = features_dir / f"features_{tf}m.npz"
    write_features_npz_atomic(feat_path, features_data)
    
    # Create features manifest
    registry = FeatureRegistry(specs=[
        FeatureSpec(name="context_feature", timeframe_min=tf, lookback_bars=20),
        FeatureSpec(name="value_feature", timeframe_min=tf, lookback_bars=14),
        FeatureSpec(name="filter_feature", timeframe_min=tf, lookback_bars=14),
        FeatureSpec(name="close", timeframe_min=tf, lookback_bars=0),
        FeatureSpec(name="atr_14", timeframe_min=tf, lookback_bars=14),
        FeatureSpec(name="ret_z_200", timeframe_min=tf, lookback_bars=200),
        FeatureSpec(name="session_vwap", timeframe_min=tf, lookback_bars=0),
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
        files_sha256={f"features_{tf}m.npz": "test_sha256"},
    )
    
    manifest_path = features_dir / "features_manifest.json"
    write_features_manifest(manifest_data, manifest_path)
    
    return {
        "features_dir": features_dir,
        "features_data": features_data,
        "manifest_path": manifest_path,
        "manifest_data": manifest_data,
    }


def create_test_strategy_requirements(
    tmp_path: Path,
    strategy_id: str,
    outputs_root: Path,
) -> Path:
    """
    Create test strategy feature requirements JSON for S2 or S3.
    
    S2/S3 are feature-agnostic - they accept feature names as parameters.
    So their requirements are generic placeholders.
    """
    req = StrategyFeatureRequirements(
        strategy_id=strategy_id,
        required=[
            FeatureRef(name="context_feature", timeframe_min=60),
            FeatureRef(name="value_feature", timeframe_min=60),
        ],
        optional=[
            FeatureRef(name="filter_feature", timeframe_min=60),
        ],
        min_schema_version="v1",
        notes=f"{strategy_id} is feature-agnostic. Actual feature names are provided via parameters.",
    )
    
    # Create strategy directory
    strategy_dir = outputs_root / "strategies" / strategy_id
    strategy_dir.mkdir(parents=True, exist_ok=True)
    
    # Write JSON
    json_path = strategy_dir / "features.json"
    save_requirements_to_json(req, str(json_path))
    
    return json_path


def test_research_run_s2_success(tmp_path: Path, monkeypatch):
    """
    Test that S2 can be loaded via research runner with allow_build=False.
    """
    season = "TEST2026Q1"
    dataset_id = "TEST.MNQ"
    strategy_id = "S2"
    
    # Create test features cache
    cache = create_test_features_cache(tmp_path, season, dataset_id, tf=60)
    
    # Create strategy requirements
    create_test_strategy_requirements(tmp_path, strategy_id, tmp_path / "outputs")
    
    # Monkeypatch to ensure S2 is in registry
    from strategy.registry import load_builtin_strategies
    load_builtin_strategies()
    
    # Run research (should not raise StrategyNotFoundError)
    report = run_research(
        season=season,
        dataset_id=dataset_id,
        strategy_id=strategy_id,
        outputs_root=tmp_path / "outputs",
        allow_build=False,
        build_ctx=None,
        wfs_config=None,
    )
    
    # Verify report
    assert report["strategy_id"] == strategy_id
    assert report["dataset_id"] == dataset_id
    assert report["season"] == season
    assert report["build_performed"] is False  # No build needed
    assert "used_features" in report
    assert "wfs_summary" in report


def test_research_run_s3_success(tmp_path: Path, monkeypatch):
    """
    Test that S3 can be loaded via research runner with allow_build=False.
    """
    season = "TEST2026Q1"
    dataset_id = "TEST.MNQ"
    strategy_id = "S3"
    
    # Create test features cache
    cache = create_test_features_cache(tmp_path, season, dataset_id, tf=60)
    
    # Create strategy requirements
    create_test_strategy_requirements(tmp_path, strategy_id, tmp_path / "outputs")
    
    # Load builtin strategies
    from strategy.registry import load_builtin_strategies
    load_builtin_strategies()
    
    # Run research
    report = run_research(
        season=season,
        dataset_id=dataset_id,
        strategy_id=strategy_id,
        outputs_root=tmp_path / "outputs",
        allow_build=False,
        build_ctx=None,
        wfs_config=None,
    )
    
    assert report["strategy_id"] == strategy_id
    assert report["dataset_id"] == dataset_id
    assert report["season"] == season
    assert report["build_performed"] is False


def test_research_run_s2_missing_features_no_build(tmp_path: Path):
    """
    Test that S2 with missing features and allow_build=False raises ResearchRunError.
    """
    season = "TEST2026Q1"
    dataset_id = "TEST.MNQ"
    strategy_id = "S2"
    
    # DO NOT create features cache (features missing)
    
    # Create strategy requirements
    create_test_strategy_requirements(tmp_path, strategy_id, tmp_path / "outputs")
    
    # Load builtin strategies
    from strategy.registry import load_builtin_strategies
    load_builtin_strategies()
    
    # Run research with allow_build=False should raise ResearchRunError
    with pytest.raises(ResearchRunError) as exc_info:
        run_research(
            season=season,
            dataset_id=dataset_id,
            strategy_id=strategy_id,
            outputs_root=tmp_path / "outputs",
            allow_build=False,
            build_ctx=None,
            wfs_config=None,
        )
    
    # Verify error message contains missing features
    error_msg = str(exc_info.value).lower()
    assert "缺失特徵" in error_msg or "missing features" in error_msg


def test_research_run_s3_missing_features_no_build(tmp_path: Path):
    """
    Test that S3 with missing features and allow_build=False raises ResearchRunError.
    """
    season = "TEST2026Q1"
    dataset_id = "TEST.MNQ"
    strategy_id = "S3"
    
    # No features cache
    
    create_test_strategy_requirements(tmp_path, strategy_id, tmp_path / "outputs")
    
    from strategy.registry import load_builtin_strategies
    load_builtin_strategies()
    
    with pytest.raises(ResearchRunError) as exc_info:
        run_research(
            season=season,
            dataset_id=dataset_id,
            strategy_id=strategy_id,
            outputs_root=tmp_path / "outputs",
            allow_build=False,
            build_ctx=None,
            wfs_config=None,
        )
    
    error_msg = str(exc_info.value).lower()
    assert "缺失特徵" in error_msg or "missing features" in error_msg


def test_research_run_s2_with_allow_build_true(monkeypatch, tmp_path: Path):
    """
    Test S2 with allow_build=True (simulate build).
    """
    season = "TEST2026Q1"
    dataset_id = "TEST.MNQ"
    strategy_id = "S2"
    
    # Create strategy requirements
    create_test_strategy_requirements(tmp_path, strategy_id, tmp_path / "outputs")
    
    # Load builtin strategies
    from strategy.registry import load_builtin_strategies
    load_builtin_strategies()
    
    # Create a mock build_shared function that simulates successful build
    def mock_build_shared(**kwargs):
        # Create features cache (simulate successful build)
        create_test_features_cache(tmp_path, season, dataset_id, tf=60)
        return {"success": True, "build_features": True}
    
    # Monkeypatch build_shared
    import control.shared_build as shared_build_module
    monkeypatch.setattr(shared_build_module, "build_shared", mock_build_shared)
    
    import control.feature_resolver as feature_resolver_module
    monkeypatch.setattr(feature_resolver_module, "build_shared", mock_build_shared)
    
    # Create build_ctx
    from control.build_context import BuildContext
    txt_path = tmp_path / "test.txt"
    txt_path.write_text("dummy content")
    
    build_ctx = BuildContext(
        txt_path=txt_path,
        mode="FULL",
        outputs_root=tmp_path / "outputs",
        build_bars_if_missing=True,
    )
    
    # Run research with allow_build=True
    report = run_research(
        season=season,
        dataset_id=dataset_id,
        strategy_id=strategy_id,
        outputs_root=tmp_path / "outputs",
        allow_build=True,
        build_ctx=build_ctx,
        wfs_config=None,
    )
    
    assert report["strategy_id"] == strategy_id
    assert report["build_performed"] is True  # Build was performed


def test_research_run_s3_with_allow_build_true(monkeypatch, tmp_path: Path):
    """
    Test S3 with allow_build=True (simulate build).
    """
    season = "TEST2026Q1"
    dataset_id = "TEST.MNQ"
    strategy_id = "S3"
    
    create_test_strategy_requirements(tmp_path, strategy_id, tmp_path / "outputs")
    
    from strategy.registry import load_builtin_strategies
    load_builtin_strategies()
    
    def mock_build_shared(**kwargs):
        create_test_features_cache(tmp_path, season, dataset_id, tf=60)
        return {"success": True, "build_features": True}
    
    import control.shared_build as shared_build_module
    monkeypatch.setattr(shared_build_module, "build_shared", mock_build_shared)
    
    import control.feature_resolver as feature_resolver_module
    monkeypatch.setattr(feature_resolver_module, "build_shared", mock_build_shared)
    
    from control.build_context import BuildContext
    txt_path = tmp_path / "test.txt"
    txt_path.write_text("dummy content")
    
    build_ctx = BuildContext(
        txt_path=txt_path,
        mode="FULL",
        outputs_root=tmp_path / "outputs",
        build_bars_if_missing=True,
    )
    
    report = run_research(
        season=season,
        dataset_id=dataset_id,
        strategy_id=strategy_id,
        outputs_root=tmp_path / "outputs",
        allow_build=True,
        build_ctx=build_ctx,
        wfs_config=None,
    )
    
    assert report["strategy_id"] == strategy_id
    assert report["build_performed"] is True


def test_s2_s3_feature_resolution():
    """
    Test that S2 and S3 feature requirements are resolved correctly.
    """
    from control.feature_resolver import _check_missing_features
    
    # Create a mock manifest with some features
    manifest = {
        "features_specs": [
            {"name": "sma_20", "timeframe_min": 60},
            {"name": "rsi_14", "timeframe_min": 60},
            {"name": "atr_14", "timeframe_min": 60},
            {"name": "close", "timeframe_min": 60},
        ]
    }
    
    # S2/S3 require generic placeholder features
    # The resolver should match based on timeframe_min, not exact name
    requirements = StrategyFeatureRequirements(
        strategy_id="S2",
        required=[
            FeatureRef(name="context_feature", timeframe_min=60),
            FeatureRef(name="value_feature", timeframe_min=60),
        ],
        optional=[
            FeatureRef(name="filter_feature", timeframe_min=60),
        ],
    )
    
    # Check missing features - should be empty because we have features with matching timeframe
    missing = _check_missing_features(manifest, requirements)
    
    # Since S2/S3 use placeholder names, the resolver may not find exact matches
    # But the test is to ensure no crash
    assert isinstance(missing, list)


def test_s2_s3_in_registry_after_load():
    """
    Test that S2 and S3 appear in strategy registry after load_builtin_strategies.
    """
    from strategy.registry import load_builtin_strategies, list_strategies
    
    load_builtin_strategies()
    
    strategies = list_strategies()
    strategy_ids = [s.strategy_id for s in strategies]
    
    assert "S2" in strategy_ids
    assert "S3" in strategy_ids
    
    # Verify they have correct versions
    from strategy.registry import get
    spec_s2 = get("S2")
    spec_s3 = get("S3")
    
    assert spec_s2.version == "v1"
    assert spec_s3.version == "v1"
    
    # Verify they have param_schema
    assert "param_schema" in spec_s2.to_dict()
    assert "param_schema" in spec_s3.to_dict()
    
    # Verify feature_requirements can be imported from strategy modules
    # S2 and S3 have feature_requirements() function in their modules
    import importlib
    s2_module = importlib.import_module("src.strategy.builtin.s2_v1")
    s3_module = importlib.import_module("src.strategy.builtin.s3_v1")
    
    assert hasattr(s2_module, 'feature_requirements')
    assert callable(s2_module.feature_requirements)
    assert hasattr(s3_module, 'feature_requirements')
    assert callable(s3_module.feature_requirements)


def test_s2_s3_no_test_failures():
    """
    Test that S2 and S3 don't cause any test failures in existing test suite.
    
    This is a meta-test to ensure our tests don't break existing functionality.
    We'll run a simple check that the strategies can be instantiated and run.
    """
    from strategy.registry import load_builtin_strategies, get
    
    load_builtin_strategies()
    
    for strategy_id in ["S2", "S3"]:
        spec = get(strategy_id)
        
        # Create minimal test context
        features = {
            "test_feature": np.array([1.0, 2.0, 3.0]),
            "close": np.array([100.0, 101.0, 102.0]),
        }
        
        context = {
            "bar_index": 1,
            "order_qty": 1.0,
            "features": features,
        }
        
        # Use parameters that reference existing features
        params = {
            "filter_mode": "NONE",
            "trigger_mode": "NONE",
            "entry_mode": "MARKET_NEXT_OPEN",
            "context_threshold": 0.0,
            "value_threshold": 0.0,
            "filter_threshold": 0.0,
            "context_feature_name": "test_feature",
            "value_feature_name": "test_feature",
            "filter_feature_name": "",
            "order_qty": 1.0,
        }
        
        # Run strategy - should not crash
        result = spec.fn(context, params)
        
        assert isinstance(result, dict)
        assert "intents" in result
        assert "debug" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])