"""
Baseline Experiments Tests

Comprehensive tests for baseline experiments in scripts/run_baseline.py.

Test Categories:
1. Baseline YAML files exist and parse correctly
2. Canonical feature names (no vx_/dx_/zn_ prefixes)
3. Baseline runs succeed with allow_build=False (CI-safe)
4. Failure mode is loud when missing features
5. Parameter validation against strategy parameter schemas
6. CLI argument validation

All tests are CI-safe: no long compute, use temporary NPZ cache with dummy data.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import yaml
from pathlib import Path
from typing import Dict, Any, List
import numpy as np
import pytest

# Skip entire module if baseline YAML files are missing (deleted per spec)
baseline_paths = [
    Path("configs/strategies/S1/baseline.yaml"),
    Path("configs/strategies/S2/baseline.yaml"),
    Path("configs/strategies/S3/baseline.yaml"),
]
if not any(p.exists() for p in baseline_paths):
    pytest.skip("Baseline YAML files deleted per spec", allow_module_level=True)

from scripts.run_baseline import (
    load_baseline_config,
    resolve_feature_names,
    verify_feature_cache,
    run_baseline_experiment,
    parse_args,
    main,
)
from control.research_runner import run_research, ResearchRunError
from control.features_store import load_features_npz, write_features_npz_atomic
from contracts.strategy_features import (
    StrategyFeatureRequirements,
    FeatureRef,
    save_requirements_to_json,
)


# ------------------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------------------

@pytest.fixture
def baseline_configs_root() -> Path:
    """Return the baseline configs directory."""
    return Path("configs/strategies")


@pytest.fixture
def baseline_yaml_paths(baseline_configs_root: Path) -> Dict[str, Path]:
    """Return mapping of strategy IDs to their baseline YAML paths."""
    return {
        "S1": baseline_configs_root / "S1" / "baseline.yaml",
        "S2": baseline_configs_root / "S2" / "baseline.yaml",
        "S3": baseline_configs_root / "S3" / "baseline.yaml",
    }


@pytest.fixture
def dummy_features_cache(tmp_path: Path) -> Path:
    """
    Create a temporary NPZ cache with dummy feature data.
    
    Returns path to the NPZ file.
    """
    # Create directory structure matching outputs/shared/season/dataset/features
    season = "2026Q1"
    dataset_id = "CME.MNQ"
    tf = 60
    features_dir = tmp_path / "outputs" / "shared" / season / dataset_id / "features"
    features_dir.mkdir(parents=True, exist_ok=True)
    
    # Create dummy data (small arrays for CI safety)
    n = 10  # small size
    ts = np.arange(n) * 3600
    ts = ts.astype("datetime64[s]")
    
    # Include all canonical feature names from baseline configs
    # S1 features
    s1_features = [
        "sma_5", "sma_10", "sma_20", "sma_40",
        "hh_5", "hh_10", "hh_20", "hh_40",
        "ll_5", "ll_10", "ll_20", "ll_40",
        "atr_10", "atr_14",
        "percentile_126", "percentile_252",
        "ret_z_200",
        "session_vwap",
    ]
    # S2/S3 features (from params)
    s2_s3_features = ["ema_40", "bb_pb_20"]
    
    features_data = {"ts": ts}
    for feat in s1_features + s2_s3_features:
        features_data[feat] = np.random.randn(n).astype(np.float64)
    
    # Write NPZ
    feat_path = features_dir / f"features_{tf}m.npz"
    write_features_npz_atomic(feat_path, features_data)
    
    return feat_path


@pytest.fixture
def mock_research_runner(monkeypatch):
    """
    Mock research_runner.run_research to return success without actual computation.
    """
    def mock_run_research(
        season: str,
        dataset_id: str,
        strategy_id: str,
        outputs_root: Path,
        allow_build: bool,
        build_ctx=None,
        wfs_config=None,
        enable_slippage_stress=False,
        slippage_policy=None,
        commission_config=None,
        tick_size_map=None,
    ) -> Dict[str, Any]:
        # Return a minimal success report
        return {
            "strategy_id": strategy_id,
            "dataset_id": dataset_id,
            "season": season,
            "used_features": [],
            "build_performed": False,
            "wfs_summary": {"artifact_path": "/fake/path"},
        }
    
    monkeypatch.setattr("control.research_runner.run_research", mock_run_research)
    monkeypatch.setattr("scripts.run_baseline.run_research", mock_run_research)


@pytest.fixture
def mock_load_features_npz(monkeypatch, dummy_features_cache: Path):
    """
    Mock features_store.load_features_npz to return dummy data.
    """
    def mock_load(path: Path) -> Dict[str, np.ndarray]:
        # Load the actual dummy cache we created
        if path == dummy_features_cache:
            return np.load(str(path), allow_pickle=False)
        # For any other path, return empty dict
        return {}
    
    monkeypatch.setattr("control.features_store.load_features_npz", mock_load)
    monkeypatch.setattr("scripts.run_baseline.load_features_npz", mock_load)


# ------------------------------------------------------------------------------
# Test 1: Baseline YAML Files Exist and Parse
# ------------------------------------------------------------------------------

def test_baseline_yaml_files_exist(baseline_yaml_paths: Dict[str, Path]):
    """Verify all 3 baseline YAML files exist at correct paths."""
    for strategy_id, path in baseline_yaml_paths.items():
        assert path.exists(), f"Baseline YAML for {strategy_id} not found at {path}"


def test_baseline_yaml_parse_correctly(baseline_yaml_paths: Dict[str, Path]):
    """Parse YAML files and validate required fields."""
    for strategy_id, path in baseline_yaml_paths.items():
        with open(path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        
        # Required fields
        required_fields = ["version", "strategy_id", "dataset_id", "timeframe", "features", "params"]
        for field in required_fields:
            assert field in config, f"Missing required field '{field}' in {strategy_id} config"
        
        # Strategy ID matches file location
        assert config["strategy_id"] == strategy_id, \
            f"Config strategy_id mismatch: expected '{strategy_id}', got '{config['strategy_id']}'"
        
        # Features structure
        assert "required" in config["features"], \
            f"Missing 'features.required' list in {strategy_id} config"
        
        # Params is a dict
        assert isinstance(config["params"], dict), \
            f"Params should be a dict in {strategy_id} config"


def test_load_baseline_config_function():
    """Test the load_baseline_config function works correctly."""
    # Test S1
    config = load_baseline_config("S1")
    assert config["strategy_id"] == "S1"
    assert config["dataset_id"] == "CME.MNQ"
    assert config["timeframe"] == 60
    assert "features" in config
    assert "params" in config
    
    # Test S2
    config = load_baseline_config("S2")
    assert config["strategy_id"] == "S2"
    
    # Test S3
    config = load_baseline_config("S3")
    assert config["strategy_id"] == "S3"
    
    # Test invalid strategy raises FileNotFoundError
    with pytest.raises(FileNotFoundError):
        load_baseline_config("INVALID")


# ------------------------------------------------------------------------------
# Test 2: Canonical Feature Names
# ------------------------------------------------------------------------------

def test_canonical_feature_names_no_prefixes():
    """Assert no feature names start with vx_, dx_, zn_ prefixes."""
    strategies = ["S1", "S2", "S3"]
    for strategy in strategies:
        config = load_baseline_config(strategy)
        
        # Get all feature names (including resolved placeholders)
        resolved = resolve_feature_names(config)
        feature_names = [feat["name"] for feat in resolved]
        
        # Check for forbidden prefixes
        forbidden_prefixes = ["vx_", "dx_", "zn_"]
        for name in feature_names:
            for prefix in forbidden_prefixes:
                assert not name.startswith(prefix), \
                    f"Feature '{name}' in {strategy} starts with forbidden prefix '{prefix}'"


def test_canonical_feature_names_only_canonical():
    """Verify only canonical feature names are used (no placeholder names)."""
    strategies = ["S1", "S2", "S3"]
    for strategy in strategies:
        config = load_baseline_config(strategy)
        resolved = resolve_feature_names(config)
        
        # Placeholder names that should have been resolved
        placeholder_names = ["context_feature", "value_feature", "filter_feature"]
        for feat in resolved:
            assert feat["name"] not in placeholder_names, \
                f"Unresolved placeholder '{feat['name']}' in {strategy} features"
        
        # For S2/S3, check that concrete names are from known canonical set
        if strategy in ["S2", "S3"]:
            canonical_features = {"ema_40", "bb_pb_20", "atr_14"}
            for feat in resolved:
                if feat["name"]:  # skip empty filter feature
                    assert feat["name"] in canonical_features, \
                        f"Non-canonical feature '{feat['name']}' in {strategy}"


# ------------------------------------------------------------------------------
# Test 3: Baseline Runs Succeed with allow_build=False (CI-safe)
# ------------------------------------------------------------------------------

def test_baseline_run_s1_success(
    tmp_path: Path,
    dummy_features_cache: Path,
    mock_research_runner,
    mock_load_features_npz,
):
    """Test S1 baseline runs successfully with allow_build=False."""
    # Monkeypatch the features cache path
    import scripts.run_baseline as rb_module
    original_verify = rb_module.verify_feature_cache
    
    def patched_verify(*args, **kwargs):
        # Skip actual verification since we have dummy cache
        pass
    
    import sys
    sys.modules["scripts.run_baseline"].verify_feature_cache = patched_verify
    
    try:
        # Run baseline experiment
        report = run_baseline_experiment(
            season="2026Q1",
            dataset_id="CME.MNQ",
            tf=60,
            strategy="S1",
            allow_build=False,
        )
        
        # Verify success
        assert report["strategy_id"] == "S1"
        assert report["dataset_id"] == "CME.MNQ"
        assert report["season"] == "2026Q1"
    finally:
        # Restore original
        sys.modules["scripts.run_baseline"].verify_feature_cache = original_verify


def test_baseline_run_s2_s3_success(
    tmp_path: Path,
    dummy_features_cache: Path,
    mock_research_runner,
    mock_load_features_npz,
):
    """Test S2 and S3 baseline runs successfully with allow_build=False."""
    strategies = ["S2", "S3"]
    
    for strategy in strategies:
        # Monkeypatch verify_feature_cache
        import scripts.run_baseline as rb_module
        original_verify = rb_module.verify_feature_cache
        
        def patched_verify(*args, **kwargs):
            pass
        
        import sys
        sys.modules["scripts.run_baseline"].verify_feature_cache = patched_verify
        
        try:
            report = run_baseline_experiment(
                season="2026Q1",
                dataset_id="CME.MNQ",
                tf=60,
                strategy=strategy,
                allow_build=False,
            )
            
            assert report["strategy_id"] == strategy
            assert report["dataset_id"] == "CME.MNQ"
        finally:
            sys.modules["scripts.run_baseline"].verify_feature_cache = original_verify


def test_verify_feature_cache_with_dummy_data(dummy_features_cache: Path):
    """Test verify_feature_cache works with dummy cache."""
    # Get required features for S1
    config = load_baseline_config("S1")
    resolved = resolve_feature_names(config)
    
    # Verify should pass
    verify_feature_cache(
        season="2026Q1",
        dataset_id="CME.MNQ",
        tf=60,
        required_features=resolved,
    )
    # No exception means success


# ------------------------------------------------------------------------------
# Test 4: Failure Mode on Missing Features
# ------------------------------------------------------------------------------

def test_missing_features_failure(tmp_path: Path, monkeypatch):
    """Test that missing required features raises RuntimeError."""
    # Create a cache missing one required feature
    season = "2026Q1"
    dataset_id = "CME.MNQ"
    tf = 60
    features_dir = tmp_path / "outputs" / "shared" / season / dataset_id / "features"
    features_dir.mkdir(parents=True, exist_ok=True)
    
    # Create cache with all S1 features except "sma_5"
    n = 10
    ts = np.arange(n) * 3600
    ts = ts.astype("datetime64[s]")
    
    # All S1 feature names from baseline config
    s1_features = [
        "sma_5", "sma_10", "sma_20", "sma_40",
        "hh_5", "hh_10", "hh_20", "hh_40",
        "ll_5", "ll_10", "ll_20", "ll_40",
        "atr_10", "atr_14",
        "percentile_126", "percentile_252",
        "ret_z_200",
        "session_vwap",
    ]
    
    features_data = {"ts": ts}
    # Include all features except sma_5
    for feat in s1_features:
        if feat != "sma_5":
            features_data[feat] = np.random.randn(n).astype(np.float64)
    
    feat_path = features_dir / f"features_{tf}m.npz"
    # Use np.savez directly to avoid validation
    np.savez(str(feat_path), **features_data)
    
    # Monkeypatch load_features_npz to load from our temporary file
    def mock_load(path: Path) -> Dict[str, np.ndarray]:
        # If path matches the expected pattern, load our cache
        # Otherwise fallback
        if str(path).endswith(f"features_{tf}m.npz"):
            return np.load(str(feat_path), allow_pickle=False)
        raise FileNotFoundError(f"File not found: {path}")
    
    monkeypatch.setattr("scripts.run_baseline.load_features_npz", mock_load)
    monkeypatch.setattr("control.features_store.load_features_npz", mock_load)
    
    # Get S1 required features
    config = load_baseline_config("S1")
    resolved = resolve_feature_names(config)
    
    # Verify should raise RuntimeError
    with pytest.raises(RuntimeError) as exc_info:
        verify_feature_cache(
            season=season,
            dataset_id=dataset_id,
            tf=tf,
            required_features=resolved,
        )
    
    # Error message should include missing feature name
    error_msg = str(exc_info.value).lower()
    assert "missing" in error_msg or "sma_5" in error_msg


def test_missing_cache_file_failure():
    """Test that missing cache file raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        verify_feature_cache(
            season="NONEXISTENT",
            dataset_id="NONEXISTENT",
            tf=60,
            required_features=[],
        )


# ------------------------------------------------------------------------------
# Test 5: Parameter Validation
# ------------------------------------------------------------------------------

def test_baseline_params_validate_against_schemas():
    """Verify baseline params validate against strategy parameter schemas."""
    # This test would require importing strategy registry and checking param schemas
    # For now, we can test that params dicts have expected keys
    strategies = ["S1", "S2", "S3"]
    
    for strategy in strategies:
        config = load_baseline_config(strategy)
        params = config["params"]
        
        # S1 has empty params
        if strategy == "S1":
            assert params == {}
        
        # S2/S3 have specific param keys
        if strategy == "S2":
            expected_keys = {
                "filter_mode", "trigger_mode", "entry_mode",
                "context_threshold", "value_threshold", "filter_threshold",
                "context_feature_name", "value_feature_name", "filter_feature_name",
                "order_qty",
            }
            assert set(params.keys()) == expected_keys
        
        if strategy == "S3":
            expected_keys = {
                "filter_mode", "trigger_mode", "entry_mode",
                "context_threshold", "value_threshold", "filter_threshold",
                "context_feature_name", "value_feature_name", "filter_feature_name",
                "order_qty",
            }
            assert set(params.keys()) == expected_keys


def test_invalid_param_combinations():
    """Test invalid parameter combinations raise appropriate errors."""
    # This would require mocking the strategy validation
    # For now, we can test that resolve_feature_names handles empty filter_feature_name
    config = load_baseline_config("S2")
    resolved = resolve_feature_names(config)
    
    # filter_feature_name is empty string, so filter_feature should be omitted
    filter_features = [f for f in resolved if f.get("name") == ""]
    assert len(filter_features) == 0, "Empty filter feature should be omitted"


# ------------------------------------------------------------------------------
# Test 6: CLI Argument Validation
# ------------------------------------------------------------------------------

def test_cli_parse_args_valid():
    """Test CLI argument parsing with valid inputs."""
    test_args = [
        "--strategy", "S1",
        "--season", "2026Q1",
        "--dataset", "CME.MNQ",
        "--tf", "60",
    ]
    
    # Temporarily replace sys.argv
    original_argv = sys.argv
    sys.argv = ["run_baseline.py"] + test_args
    
    try:
        args = parse_args()
        assert args.strategy == "S1"
        assert args.season == "2026Q1"
        assert args.dataset == "CME.MNQ"
        assert args.tf == 60
        assert args.allow_build is False
    finally:
        sys.argv = original_argv


def test_cli_parse_args_missing_required():
    """Test missing required strategy argument raises SystemExit."""
    test_args = [
        "--season", "2026Q1",
    ]
    
    original_argv = sys.argv
    sys.argv = ["run_baseline.py"] + test_args
    
    try:
        with pytest.raises(SystemExit):
            parse_args()
    finally:
        sys.argv = original_argv


def test_cli_parse_args_invalid_strategy():
    """Test invalid strategy argument raises SystemExit."""
    test_args = [
        "--strategy", "INVALID",
    ]
    
    original_argv = sys.argv
    sys.argv = ["run_baseline.py"] + test_args
    
    try:
        with pytest.raises(SystemExit):
            parse_args()
    finally:
        sys.argv = original_argv


def test_cli_parse_args_default_values():
    """Test CLI argument default values."""
    test_args = [
        "--strategy", "S1",
    ]
    
    original_argv = sys.argv
    sys.argv = ["run_baseline.py"] + test_args
    
    try:
        args = parse_args()
        assert args.strategy == "S1"
        assert args.season == "2026Q1"  # default
        assert args.dataset == "CME.MNQ"  # default
        assert args.tf == 60  # default
        assert args.allow_build is False  # default
    finally:
        sys.argv = original_argv


def test_cli_parse_args_allow_build_true():
    """Test allow_build flag can be set to True."""
    test_args = [
        "--strategy", "S1",
        "--allow-build",
    ]
    
    original_argv = sys.argv
    sys.argv = ["run_baseline.py"] + test_args
    
    try:
        args = parse_args()
        assert args.strategy == "S1"
        assert args.allow_build is True
    finally:
        sys.argv = original_argv


def test_main_success(
    tmp_path: Path,
    dummy_features_cache: Path,
    mock_research_runner,
    mock_load_features_npz,
    monkeypatch,
):
    """Test main function runs successfully (CI-safe)."""
    # Monkeypatch verify_feature_cache
    import scripts.run_baseline as rb_module
    original_verify = rb_module.verify_feature_cache
    
    def patched_verify(*args, **kwargs):
        pass
    
    monkeypatch.setattr(rb_module, "verify_feature_cache", patched_verify)
    
    # Mock sys.argv
    test_args = [
        "--strategy", "S1",
        "--season", "2026Q1",
        "--dataset", "CME.MNQ",
        "--tf", "60",
    ]
    
    original_argv = sys.argv
    sys.argv = ["run_baseline.py"] + test_args
    
    try:
        # main() should return 0 on success
        exit_code = main()
        assert exit_code == 0
    finally:
        sys.argv = original_argv
        monkeypatch.setattr(rb_module, "verify_feature_cache", original_verify)


def test_main_failure_missing_features(
    tmp_path: Path,
    monkeypatch,
):
    """Test main function fails when features missing."""
    # Create a cache missing features
    season = "2026Q1"
    dataset_id = "CME.MNQ"
    tf = 60
    features_dir = tmp_path / "outputs" / "shared" / season / dataset_id / "features"
    features_dir.mkdir(parents=True, exist_ok=True)
    
    # Empty cache
    feat_path = features_dir / f"features_{tf}m.npz"
    np.savez(str(feat_path), ts=np.array([]))
    
    # Mock load_features_npz to return empty
    def mock_load(path: Path) -> Dict[str, np.ndarray]:
        return {}
    
    monkeypatch.setattr("scripts.run_baseline.load_features_npz", mock_load)
    
    # Mock sys.argv
    test_args = [
        "--strategy", "S1",
        "--season", season,
        "--dataset", dataset_id,
        "--tf", str(tf),
    ]
    
    original_argv = sys.argv
    sys.argv = ["run_baseline.py"] + test_args
    
    try:
        # main() should return 3 (feature cache verification error)
        exit_code = main()
        assert exit_code == 3
    finally:
        sys.argv = original_argv