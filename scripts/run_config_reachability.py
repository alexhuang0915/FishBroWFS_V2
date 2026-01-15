#!/usr/bin/env python3
"""
Run minimal jobs for S1, S2, S3 and emit config reachability report.

This script executes research runs for each strategy, recording every YAML
configuration file loaded during the job. After each run, a report is written
to outputs/_dp_evidence/config_runtime_report/{strategy_id}/.

Step 4 of the HARD DELETE + FORCED REPAIR spec.
"""

import json
import tempfile
import shutil
from pathlib import Path
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from config import (
    reset_config_load_records,
    get_config_load_records,
    write_config_load_report,
    enable_config_recording,
)
from control.research_runner import run_research
from strategy.registry import load_builtin_strategies


def create_test_features_cache(tmp_path: Path, season: str, dataset_id: str, tf: int = 60):
    """
    Create a minimal features cache for testing.
    Adapted from tests/control/test_research_runner_s2_s3.py.
    """
    import numpy as np
    from control.features_store import write_features_npz_atomic
    from control.features_manifest import (
        write_features_manifest,
        build_features_manifest_data,
    )
    from contracts.features import FeatureSpec, FeatureRegistry
    
    # Create features directory
    features_dir = tmp_path / "outputs" / "shared" / season / dataset_id / "features"
    features_dir.mkdir(parents=True, exist_ok=True)
    
    # Create test data
    n = 50
    ts = np.arange(n) * 3600  # seconds
    ts = ts.astype("datetime64[s]")
    
    # Create features that S1/S2/S3 might use
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
    
    return features_dir


def run_strategy_with_report(strategy_id: str, outputs_root: Path):
    """
    Run a single strategy research job and write config load report.
    """
    season = "TEST2026Q1"
    dataset_id = "TEST.MNQ"
    
    # Create a temporary directory for this run
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        # Create test features cache
        create_test_features_cache(tmp_path, season, dataset_id, tf=60)
        
        # Reset config load records before run
        reset_config_load_records()
        enable_config_recording(True)
        
        # Load builtin strategies (required for registry)
        load_builtin_strategies()
        
        # Run research
        try:
            report = run_research(
                season=season,
                dataset_id=dataset_id,
                strategy_id=strategy_id,
                outputs_root=tmp_path / "outputs",
                allow_build=False,
                build_ctx=None,
                wfs_config=None,
            )
            print(f"  Research run completed for {strategy_id}: {report.get('wfs_summary', {}).get('status', 'unknown')}")
        except Exception as e:
            print(f"  Research run failed for {strategy_id}: {e}")
            # Still write config loads that were recorded before failure
            pass
        
        # Write config load report
        report_dir = outputs_root / strategy_id
        write_config_load_report(report_dir)
        print(f"  Config load report written to {report_dir}")
        
        # Also print a summary
        records = get_config_load_records()
        print(f"  Total config files loaded: {len(records)}")
        for rel_path, info in sorted(records.items()):
            print(f"    {rel_path}: count={info['count']}")


def main():
    """Main entry point."""
    # Ensure output directory exists
    output_base = Path("outputs") / "_dp_evidence" / "config_runtime_report"
    output_base.mkdir(parents=True, exist_ok=True)
    
    print("Starting config reachability report generation...")
    print(f"Reports will be saved to {output_base}")
    
    strategies = ["S1", "S2", "S3"]
    
    for strategy_id in strategies:
        print(f"\n--- Running {strategy_id} ---")
        run_strategy_with_report(strategy_id, output_base)
    
    print("\n--- All reports generated ---")
    print("Check the following directories:")
    for strategy_id in strategies:
        print(f"  {output_base / strategy_id}/loaded_configs_report.json")


if __name__ == "__main__":
    main()