#!/usr/bin/env python3
"""
Check allow_build=False contract by monitoring file writes.
"""
import sys
import os
import tempfile
import shutil
from pathlib import Path
import numpy as np

sys.path.insert(0, '.')
sys.path.insert(0, './src')

def check_allow_build_contract():
    """Run research with allow_build=False and verify no new files are written."""
    from pathlib import Path
    import tempfile
    import numpy as np
    
    print("=== Checking allow_build=False Contract ===")
    
    # Create a temporary outputs directory
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        outputs_root = tmp_path / "outputs"
        season = "TEST2026Q1"
        dataset_id = "TEST.MNQ"
        
        # Create features directory
        features_dir = outputs_root / "shared" / season / dataset_id / "features"
        features_dir.mkdir(parents=True, exist_ok=True)
        
        # Write dummy features NPZ (just ts and all required features)
        n = 100
        ts = np.arange(n).astype("datetime64[s]")
        features_data = {"ts": ts}
        
        # All S1 required features
        required_features = [
            "sma_5", "sma_10", "sma_20", "sma_40",
            "hh_5", "hh_10", "hh_20", "hh_40",
            "ll_5", "ll_10", "ll_20", "ll_40",
            "atr_10", "atr_14",
            "vx_percentile_126", "vx_percentile_252",
            "ret_z_200", "session_vwap"
        ]
        
        for name in required_features:
            features_data[name] = np.random.randn(n)
        
        np.savez(features_dir / "features_60m.npz", **features_data)
        
        # Create features manifest
        from control.features_manifest import (
            build_features_manifest_data,
            write_features_manifest,
        )
        from contracts.features import FeatureSpec, FeatureRegistry
        
        registry = FeatureRegistry(specs=[
            FeatureSpec(name=name, timeframe_min=60, lookback_bars=14)
            for name in required_features
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
        
        # Create strategy requirements JSON (optional, S1 has Python method)
        strategy_dir = outputs_root / "strategies" / "S1"
        strategy_dir.mkdir(parents=True, exist_ok=True)
        import json
        req_data = {
            "strategy_id": "S1",
            "required": [{"name": name, "timeframe_min": 60} for name in required_features],
            "optional": [],
            "min_schema_version": "v1",
            "notes": "test"
        }
        (strategy_dir / "features.json").write_text(json.dumps(req_data))
        
        # Record all files before research run
        before_files = set()
        for root, dirs, files in os.walk(outputs_root):
            for file in files:
                path = Path(root) / file
                rel_path = path.relative_to(outputs_root)
                before_files.add(str(rel_path))
        
        print(f"Files present before research run: {len(before_files)}")
        for f in sorted(before_files):
            print(f"  - {f}")
        
        # Now run research
        from control.research_runner import run_research
        from strategy.registry import load_builtin_strategies
        
        load_builtin_strategies()
        
        try:
            report = run_research(
                season=season,
                dataset_id=dataset_id,
                strategy_id="S1",
                outputs_root=outputs_root,
                allow_build=False,
                wfs_config=None,
            )
            
            # Record all files after research run
            after_files = set()
            for root, dirs, files in os.walk(outputs_root):
                for file in files:
                    path = Path(root) / file
                    rel_path = path.relative_to(outputs_root)
                    after_files.add(str(rel_path))
            
            new_files = after_files - before_files
            deleted_files = before_files - after_files
            
            print(f"\nFiles after research run: {len(after_files)}")
            print(f"New files created: {len(new_files)}")
            print(f"Files deleted: {len(deleted_files)}")
            
            if new_files:
                print("\nWARNING: New files created despite allow_build=False:")
                for f in sorted(new_files):
                    print(f"  - {f}")
                # Check if any are logs (allowed)
                log_files = [f for f in new_files if f.endswith('.log')]
                if log_files:
                    print(f"  (Note: {len(log_files)} log files are allowed)")
                non_log_files = [f for f in new_files if not f.endswith('.log')]
                if non_log_files:
                    print("  VIOLATION: Non-log files written!")
                    return False, report, list(non_log_files)
                else:
                    print("  OK: Only log files written (allowed)")
                    return True, report, []
            else:
                print("\nOK: No new files created (contract respected)")
                return True, report, []
                
        except Exception as e:
            print(f"\nERROR: Research run failed: {e}")
            import traceback
            traceback.print_exc()
            return False, None, [str(e)]

if __name__ == "__main__":
    success, report, violations = check_allow_build_contract()
    if success:
        if violations:
            print(f"\nContract violated with files: {violations}")
        else:
            print("\n✓ allow_build=False contract fully respected")
    else:
        print("\n✗ Research run failed or contract violated")