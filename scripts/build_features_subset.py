#!/usr/bin/env python3
"""
Build features cache with subset data.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from control.shared_build import build_shared
from contracts.features import default_feature_registry

def main() -> None:
    txt_path = Path("FishBroData/raw/CME.MNQ_SUBSET.txt")
    if not txt_path.exists():
        print(f"Error: TXT file not found at {txt_path}")
        sys.exit(1)
    
    season = "2026Q1"
    dataset_id = "CME.MNQ"
    outputs_root = Path("outputs")
    
    print(f"Building features cache for {dataset_id} season {season}...")
    try:
        report = build_shared(
            season=season,
            dataset_id=dataset_id,
            txt_path=txt_path,
            outputs_root=outputs_root,
            mode="FULL",
            save_fingerprint=True,
            generated_at_utc=None,
            build_bars=True,
            build_features=True,
            feature_registry=default_feature_registry(),
            tfs=[60],
        )
        
        if report.get("success"):
            print("Features cache built successfully.")
            print(f"Report keys: {list(report.keys())}")
        else:
            print(f"Build failed: {report.get('error')}")
            sys.exit(1)
    except Exception as e:
        print(f"Exception during build: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()