#!/usr/bin/env python3
"""
Test S1 research runner with dummy features cache.
"""
import sys
sys.path.insert(0, 'src')

import numpy as np
from pathlib import Path
import tempfile
import shutil

from config import reset_config_load_records, enable_config_recording
from control.research_runner import run_research
from strategy.registry import load_builtin_strategies
from control.features_store import write_features_npz_atomic
from control.features_manifest import (
    write_features_manifest,
    build_features_manifest_data,
)
from contracts.features import FeatureSpec, FeatureRegistry

# Clear caches
from config.registry.instruments import load_instruments
from config.registry.timeframes import load_timeframes
from config.registry.datasets import load_datasets
from config.registry.strategy_catalog import load_strategy_catalog
from config.profiles import load_profile
from config.strategies import load_strategy
from config.portfolio import load_portfolio_config

def clear_all_config_caches():
    load_instruments.cache_clear()
    load_timeframes.cache_clear()
    load_datasets.cache_clear()
    load_strategy_catalog.cache_clear()
    load_profile.cache_clear()
    load_strategy.cache_clear()
    load_portfolio_config.cache_clear()

clear_all_config_caches()
reset_config_load_records()
enable_config_recording(True)

load_builtin_strategies()

season = "TEST2026Q1"
dataset_id = "TEST.MNQ"
tf = 60

# Create a temporary directory for this run
with tempfile.TemporaryDirectory() as tmpdir:
    tmp_path = Path(tmpdir)
    
    # Create features directory
    features_dir = tmp_path / "outputs" / "shared" / season / dataset_id / "features"
    features_dir.mkdir(parents=True, exist_ok=True)
    
    # Create test data
    n = 100
    ts = np.arange(n) * 3600  # seconds
    ts = ts.astype("datetime64[s]")
    
    # Create features that S1 requires
    features_data = {
        "ts": ts,
        "sma_5": np.random.randn(n).astype(np.float64) * 10 + 100,
        "sma_10": np.random.randn(n).astype(np.float64) * 10 + 100,
        "sma_20": np.random.randn(n).astype(np.float64) * 10 + 100,
        "sma_40": np.random.randn(n).astype(np.float64) * 10 + 100,
        "hh_5": np.random.randn(n).astype(np.float64) * 10 + 100,
        "hh_10": np.random.randn(n).astype(np.float64) * 10 + 100,
        "hh_20": np.random.randn(n).astype(np.float64) * 10 + 100,
        "hh_40": np.random.randn(n).astype(np.float64) * 10 + 100,
        "ll_5": np.random.randn(n).astype(np.float64) * 10 + 100,
        "ll_10": np.random.randn(n).astype(np.float64) * 10 + 100,
        "ll_20": np.random.randn(n).astype(np.float64) * 10 + 100,
        "ll_40": np.random.randn(n).astype(np.float64) * 10 + 100,
        "atr_10": np.random.randn(n).astype(np.float64) * 2 + 10,
        "atr_14": np.random.randn(n).astype(np.float64) * 2 + 10,
        "percentile_126": np.random.randn(n).astype(np.float64) * 0.5,
        "percentile_252": np.random.randn(n).astype(np.float64) * 0.5,
        "zscore_200": np.random.randn(n).astype(np.float64) * 0.1,
        "ret_z_200": np.random.randn(n).astype(np.float64) * 0.1,  # baseline feature
        "session_vwap": np.random.randn(n).astype(np.float64) * 10 + 1000,
    }
    
    feat_path = features_dir / f"features_{tf}m.npz"
    write_features_npz_atomic(feat_path, features_data)
    
    # Create features manifest
    registry = FeatureRegistry(specs=[
        FeatureSpec(name=name, timeframe_min=tf, lookback_bars=0)
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
        files_sha256={f"features_{tf}m.npz": "test_sha256"},
    )
    
    manifest_path = features_dir / "features_manifest.json"
    write_features_manifest(manifest_data, manifest_path)
    
    # Run research
    try:
        report = run_research(
            season=season,
            dataset_id=dataset_id,
            strategy_id="S1",
            outputs_root=tmp_path / "outputs",
            allow_build=False,
            build_ctx=None,
            wfs_config=None,
        )
        print("SUCCESS: Research run completed")
        print("Status:", report.get('wfs_summary', {}).get('status', 'unknown'))
        # Write config load report
        from config import get_config_load_records
        records = get_config_load_records()
        print(f"Total config files loaded: {len(records)}")
        for rel_path, info in sorted(records.items()):
            print(f"  {rel_path}: count={info['count']}")
    except Exception as e:
        print("FAILED:", e)
        import traceback
        traceback.print_exc()