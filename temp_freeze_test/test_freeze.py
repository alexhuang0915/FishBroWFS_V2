#!/usr/bin/env python3
"""Test the freezer module with dummy artifacts."""

import sys
from pathlib import Path

# Add src to path
src_dir = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_dir))

from governance.freezer import freeze_season
from governance.models import FreezeContext


def main():
    base = Path(__file__).parent
    ctx = FreezeContext(
        universe_path=base / "universe.yaml",
        dataset_registry_path=base / "dataset_registry.json",
        strategy_spec_path=base / "strategy_spec.json",
        plateau_report_path=base / "plateau" / "plateau_report.json",
        chosen_params_path=base / "plateau" / "chosen_params.json",
        engine_version="test_engine_v1",
        notes="Test freeze",
        season_id="test_season_2025",
    )
    
    outputs_root = base / "outputs"
    print(f"Outputs root: {outputs_root}")
    
    try:
        manifest = freeze_season(ctx, outputs_root=outputs_root, force=True)
        print("SUCCESS: Season frozen")
        print(f"  season_id: {manifest.season_id}")
        print(f"  timestamp: {manifest.timestamp}")
        print(f"  universe_ref: {manifest.universe_ref[:16]}...")
        print(f"  dataset_ref: {manifest.dataset_ref[:16]}...")
        print(f"  strategy_spec_hash: {manifest.strategy_spec_hash[:16]}...")
        print(f"  plateau_ref: {manifest.plateau_ref[:16]}...")
        
        # Verify manifest file exists
        manifest_path = outputs_root / "seasons" / manifest.season_id / "season_manifest.json"
        if manifest_path.exists():
            print(f"Manifest saved at: {manifest_path}")
        else:
            print("ERROR: Manifest file not found")
            return 1
            
        # Load back and compare
        from governance.freezer import load_season_manifest
        loaded = load_season_manifest(manifest.season_id, outputs_root)
        assert loaded.season_id == manifest.season_id
        assert loaded.universe_ref == manifest.universe_ref
        print("Manifest can be loaded correctly.")
        
        return 0
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())