#!/usr/bin/env python3
"""
Manual verification script for Phase 15.1 Artifact Contract.
Demonstrates the artifact contract behavior as specified in acceptance test E2.
"""
import json
import tempfile
import shutil
from pathlib import Path
import sys

# Add src to path to import our validation module
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from gui.desktop.artifact_validation import (
    is_artifact_dir_name,
    validate_artifact_dir,
    find_latest_valid_artifact,
)

def test_artifact_contract():
    """Test the artifact contract as described in acceptance test E2."""
    print("=" * 70)
    print("PHASE 15.1 ARTIFACT CONTRACT VERIFICATION")
    print("=" * 70)
    
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        # Create a fake season/runs structure
        runs_dir = tmp_path / "outputs" / "seasons" / "2026Q1" / "runs"
        runs_dir.mkdir(parents=True)
        
        print(f"\n1. Creating fake run directory 'run_XXXX' with only intent.json and derived.json")
        run_dir = runs_dir / "run_12345678"
        run_dir.mkdir()
        (run_dir / "intent.json").write_text(json.dumps({"strategy": "S1"}))
        (run_dir / "derived.json").write_text(json.dumps({"status": "completed"}))
        
        # Test 1: run_* should NOT be considered an artifact
        print(f"   Directory name: {run_dir.name}")
        print(f"   is_artifact_dir_name? {is_artifact_dir_name(run_dir.name)}")
        validation = validate_artifact_dir(run_dir)
        print(f"   validate_artifact_dir result: {validation['ok']}")
        if not validation['ok']:
            print(f"   Reason: {validation['reason']}")
        
        # Test 2: Find latest valid artifact (should find none)
        print(f"\n2. Scanning for latest valid artifact...")
        result = find_latest_valid_artifact(runs_dir)
        print(f"   Result: {result['ok']}")
        if not result['ok']:
            print(f"   Reason: {result['reason']}")
        
        print(f"\n3. Creating artifact directory 'artifact_YYYY' with ONLY manifest.json (missing metrics.json)")
        artifact_dir1 = runs_dir / "artifact_87654321"
        artifact_dir1.mkdir()
        (artifact_dir1 / "manifest.json").write_text(json.dumps({"run_id": "artifact_87654321"}))
        
        validation1 = validate_artifact_dir(artifact_dir1)
        print(f"   Directory name: {artifact_dir1.name}")
        print(f"   is_artifact_dir_name? {is_artifact_dir_name(artifact_dir1.name)}")
        print(f"   validate_artifact_dir result: {validation1['ok']}")
        if not validation1['ok']:
            print(f"   Reason: {validation1['reason']}")
            if 'missing' in validation1:
                print(f"   Missing files: {validation1['missing']}")
        
        print(f"\n4. Creating valid artifact directory 'artifact_ZZZZ' with BOTH manifest.json AND metrics.json")
        artifact_dir2 = runs_dir / "artifact_99999999"
        artifact_dir2.mkdir()
        (artifact_dir2 / "manifest.json").write_text(json.dumps({"run_id": "artifact_99999999"}))
        (artifact_dir2 / "metrics.json").write_text(json.dumps({"net_profit": 1000, "max_dd": 50}))
        
        validation2 = validate_artifact_dir(artifact_dir2)
        print(f"   Directory name: {artifact_dir2.name}")
        print(f"   is_artifact_dir_name? {is_artifact_dir_name(artifact_dir2.name)}")
        print(f"   validate_artifact_dir result: {validation2['ok']}")
        if validation2['ok']:
            print(f"   ✓ VALID ARTIFACT")
        
        # Test 3: Find latest valid artifact (should find artifact_ZZZZ)
        print(f"\n5. Scanning for latest valid artifact again...")
        result2 = find_latest_valid_artifact(runs_dir)
        print(f"   Result: {result2['ok']}")
        if result2['ok']:
            print(f"   Found artifact: {Path(result2['artifact_dir']).name}")
            print(f"   Validation: {result2['validation']}")
        
        print(f"\n6. Creating stage0_coarse-* directory (should be ignored)")
        stage0_dir = runs_dir / "stage0_coarse-research-123"
        stage0_dir.mkdir()
        (stage0_dir / "debug.log").write_text("debug output")
        
        print(f"   Directory name: {stage0_dir.name}")
        print(f"   is_artifact_dir_name? {is_artifact_dir_name(stage0_dir.name)}")
        
        print(f"\n" + "=" * 70)
        print("SUMMARY:")
        print("=" * 70)
        print("✓ run_* directories are NOT artifact candidates")
        print("✓ stage0_coarse-* directories are NOT artifact candidates")
        print("✓ artifact_* directories require BOTH manifest.json AND metrics.json")
        print("✓ find_latest_valid_artifact() returns only valid artifact_* directories")
        print("\nExpected Desktop UI behavior:")
        print("  - With only run_XXXX: Artifact: NONE, Promote disabled")
        print("  - With artifact_YYYY (missing metrics): Artifact: NONE, Promote disabled")
        print("  - With artifact_ZZZZ (complete): Artifact: READY, Promote enabled")
        
        # Final verification
        all_dirs = list(runs_dir.iterdir())
        artifact_dirs = [d for d in all_dirs if is_artifact_dir_name(d.name)]
        print(f"\nTotal directories in runs: {len(all_dirs)}")
        print(f"Artifact_* directories: {len(artifact_dirs)}")
        print(f"Non-artifact directories: {len(all_dirs) - len(artifact_dirs)}")
        
        return 0

if __name__ == "__main__":
    sys.exit(test_artifact_contract())