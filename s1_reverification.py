#!/usr/bin/env python3
"""
S1 Re-verification script.
Performs registry dump, research run with allow_build=False, and feature verification.
"""
import sys
import os
import tempfile
import shutil
import json
from pathlib import Path
import numpy as np

sys.path.insert(0, '.')
sys.path.insert(0, './src')

def dump_strategy_registry():
    """Dump strategy registry and verify S1 presence."""
    from strategy.registry import load_builtin_strategies, get, list_strategies
    
    print("=== Strategy Registry Dump ===")
    load_builtin_strategies()
    reg = list_strategies()
    print(f"Total strategies: {len(reg)}")
    for s in reg:
        print(f"  - {s.strategy_id} (content_id: {s.content_id})")
    
    # Verify S1 exists
    s1_spec = get("S1")
    print(f"\nS1 verification:")
    print(f"  Strategy ID: {s1_spec.strategy_id}")
    print(f"  Version: {s1_spec.version}")
    print(f"  Content ID: {s1_spec.content_id}")
    print(f"  Parameter schema: {s1_spec.param_schema}")
    print(f"  Defaults: {s1_spec.defaults}")
    
    # Check feature requirements
    if hasattr(s1_spec, 'feature_requirements') and callable(s1_spec.feature_requirements):
        reqs = s1_spec.feature_requirements()
        print(f"\nS1 feature requirements:")
        print(f"  Required: {len(reqs.required)} features")
        for f in reqs.required:
            print(f"    - {f.name} (tf={f.timeframe_min}m)")
        print(f"  Optional: {len(reqs.optional)} features")
    else:
        print("\nS1 does not have feature_requirements() method")
    
    return s1_spec

def verify_feature_registry():
    """Verify S1 feature requirements against expanded registry."""
    from features.registry import get_default_registry
    
    print("\n=== Feature Registry Verification ===")
    reg = get_default_registry()
    specs_60 = reg.specs_for_tf(60)
    print(f"Features available for TF=60: {len(specs_60)}")
    
    # S1 required features from the spec
    s1_features = [
        "sma_5", "sma_10", "sma_20", "sma_40",
        "hh_5", "hh_10", "hh_20", "hh_40",
        "ll_5", "ll_10", "ll_20", "ll_40",
        "atr_10", "atr_14",
        "vx_percentile_126", "vx_percentile_252",
        "ret_z_200", "session_vwap"
    ]
    
    print(f"\nS1 required features check:")
    available = []
    missing = []
    for feat in s1_features:
        found = any(s.name == feat for s in specs_60)
        if found:
            available.append(feat)
        else:
            missing.append(feat)
    
    print(f"  Available: {len(available)}/{len(s1_features)}")
    print(f"  Missing: {len(missing)}/{len(s1_features)}")
    if missing:
        print(f"  Missing features: {missing}")
    
    # Check for deprecated feature names
    deprecated = []
    for feat in s1_features:
        if feat.startswith('vx_percentile_'):
            # Check if there's a 'percentile_' alternative
            alt = feat.replace('vx_percentile_', 'percentile_')
            if any(s.name == alt for s in specs_60):
                deprecated.append((feat, alt))
    
    if deprecated:
        print(f"\nDeprecated feature names (should be updated):")
        for old, new in deprecated:
            print(f"  {old} -> {new}")
    
    return available, missing, deprecated

def run_research_with_allow_build_false():
    """Run minimal research run with allow_build=False using test pattern."""
    from pathlib import Path
    import tempfile
    import numpy as np
    
    print("\n=== Minimal Research Run with allow_build=False ===")
    
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
        req_data = {
            "strategy_id": "S1",
            "required": [{"name": name, "timeframe_min": 60} for name in required_features],
            "optional": [],
            "min_schema_version": "v1",
            "notes": "test"
        }
        (strategy_dir / "features.json").write_text(json.dumps(req_data))
        
        # Now test that run_research can resolve S1
        from control.research_runner import run_research
        from strategy.registry import load_builtin_strategies
        
        load_builtin_strategies()
        
        try:
            print(f"Outputs root: {outputs_root}")
            print("Running research with allow_build=False...")
            report = run_research(
                season=season,
                dataset_id=dataset_id,
                strategy_id="S1",
                outputs_root=outputs_root,
                allow_build=False,
                wfs_config=None,
            )
            
            print(f"Research run successful!")
            print(f"Report keys: {list(report.keys())}")
            print(f"Build performed: {report.get('build_performed')}")
            
            # Verify no files were written (except maybe logs)
            files_written = []
            for root, dirs, files in os.walk(outputs_root):
                for file in files:
                    if not file.endswith('.log'):
                        files_written.append(os.path.join(root, file))
            
            if files_written:
                print(f"\nWARNING: Files written despite allow_build=False:")
                for f in files_written:
                    print(f"  - {f}")
            else:
                print(f"\nOK: No files written (allow_build=False contract respected)")
            
            return True, report, None
        except Exception as e:
            print(f"\nERROR: Research run failed: {e}")
            import traceback
            traceback.print_exc()
            return False, None, str(e)

def main():
    """Main verification routine."""
    evidence_lines = []
    
    # Capture stdout
    import io
    import sys
    old_stdout = sys.stdout
    sys.stdout = io.StringIO()
    
    try:
        # 1. Dump strategy registry
        s1_spec = dump_strategy_registry()
        
        # 2. Verify feature registry
        available, missing, deprecated = verify_feature_registry()
        
        # 3. Run research with allow_build=False
        success, report, error = run_research_with_allow_build_false()
        
    finally:
        output = sys.stdout.getvalue()
        sys.stdout = old_stdout
    
    # Print to console
    print(output)
    
    # Save to evidence file
    evidence_dir = Path("outputs/_dp_evidence/20251230_201916")
    evidence_file = evidence_dir / "S1_REVERIFY_FULL.txt"
    
    with open(evidence_file, 'w') as f:
        f.write("=== S1 RE-VERIFICATION EVIDENCE (FULL) ===\n")
        f.write(f"Timestamp: {np.datetime64('now')}\n")
        f.write(f"Working directory: {os.getcwd()}\n\n")
        f.write(output)
    
    print(f"\nEvidence saved to: {evidence_file}")
    
    # Summary
    print("\n=== SUMMARY ===")
    if success:
        print("✓ S1 is present in registry")
        print("✓ Research run with allow_build=False succeeded")
        print(f"✓ Feature availability: {len(available)}/{len(available)+len(missing)}")
        if missing:
            print(f"  Missing features: {missing}")
        if deprecated:
            print(f"  Deprecated feature names detected: {[d[0] for d in deprecated]}")
    else:
        print("✗ Research run failed")
        print(f"  Error: {error}")

if __name__ == "__main__":
    main()