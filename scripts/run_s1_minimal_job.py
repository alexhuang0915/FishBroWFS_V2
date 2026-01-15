#!/usr/bin/env python3
"""
Run S1 minimal job with config load instrumentation.
Generates config reachability report.
"""
import sys
import tempfile
from pathlib import Path
import json

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from config import reset_config_load_records, get_config_load_records, write_config_load_report, clear_config_caches
from control.research_runner import run_research
from strategy.registry import load_builtin_strategies

def main():
    # Clear config caches and reset config load records before run
    clear_config_caches()
    reset_config_load_records()
    
    # Create temporary outputs directory
    with tempfile.TemporaryDirectory() as tmpdir:
        outputs_root = Path(tmpdir) / "outputs"
        outputs_root.mkdir(parents=True, exist_ok=True)
        
        # Create dummy features cache (just enough to satisfy S1)
        # We'll reuse the same dummy cache we used earlier
        season = "TEST2026Q1"
        dataset_id = "CME.MNQ"
        features_dir = outputs_root / "shared" / season / dataset_id / "features"
        features_dir.mkdir(parents=True, exist_ok=True)
        
        import numpy as np
        n = 100
        ts = np.arange(n).astype("datetime64[s]")
        features_data = {
            "ts": ts,
            "sma_5": np.random.randn(n),
            "sma_10": np.random.randn(n),
            "sma_20": np.random.randn(n),
            "sma_40": np.random.randn(n),
            "hh_5": np.random.randn(n),
            "hh_10": np.random.randn(n),
            "hh_20": np.random.randn(n),
            "hh_40": np.random.randn(n),
            "ll_5": np.random.randn(n),
            "ll_10": np.random.randn(n),
            "ll_20": np.random.randn(n),
            "ll_40": np.random.randn(n),
            "atr_10": np.random.randn(n),
            "atr_14": np.random.randn(n),
            "percentile_126": np.random.randn(n),
            "percentile_252": np.random.randn(n),
            "zscore_200": np.random.randn(n),
            "ret_z_200": np.random.randn(n),  # baseline feature
            "session_vwap": np.random.randn(n),
        }
        np.savez(features_dir / "features_60m.npz", **features_data)
        
        # Create features manifest (simplified)
        from control.features_manifest import build_features_manifest_data, write_features_manifest
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
        
        # Load builtin strategies
        load_builtin_strategies()
        
        # Run S1 minimal job
        try:
            report = run_research(
                season=season,
                dataset_id=dataset_id,
                strategy_id="S1",
                outputs_root=outputs_root,
                allow_build=False,
                wfs_config=None,
            )
            print(f"S1 minimal job completed: {report}")
        except Exception as e:
            print(f"S1 minimal job failed: {e}")
            sys.exit(1)
        
        # Get config load records
        records = get_config_load_records()  # returns dict {path: load_count}
        
        # Write report
        report_dir = Path("outputs/_dp_evidence/config_runtime_report")
        report_dir.mkdir(parents=True, exist_ok=True)
        report_path = report_dir / "s1_config_loads.json"
        with open(report_path, "w") as f:
            json.dump(records, f, indent=2)
        print(f"Config reachability report written to {report_path}")
        
        # Also write summary
        summary = {
            "strategy": "S1",
            "total_configs_loaded": len(records),
            "configs": list(records.keys())
        }
        summary_path = report_dir / "s1_summary.json"
        with open(summary_path, "w") as f:
            json.dump(summary, f, indent=2)
        print(f"Summary written to {summary_path}")

if __name__ == "__main__":
    main()