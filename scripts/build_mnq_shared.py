#!/usr/bin/env python3
"""
Build shared cache for MNQ dataset.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from control.build_context import BuildContext
from control.shared_build import build_shared

def main() -> None:
    txt_path = Path("FishBroData/raw/CME.MNQ HOT-Minute-Trade.txt")
    if not txt_path.exists():
        print(f"Error: TXT file not found at {txt_path}")
        sys.exit(1)
    
    season = "2026Q1"
    dataset_id = "CME.MNQ"
    outputs_root = Path("outputs")
    
    # Create build context
    ctx = BuildContext(
        txt_path=txt_path,
        mode="FULL",
        outputs_root=outputs_root,
        build_bars_if_missing=True,
        season=season,
        dataset_id=dataset_id,
    )
    
    # Build shared cache (bars only, no features)
    print(f"Building shared cache for {dataset_id} season {season}...")
    report = build_shared(
        season=season,
        dataset_id=dataset_id,
        txt_path=txt_path,
        outputs_root=outputs_root,
        mode="FULL",
        save_fingerprint=True,
        generated_at_utc=None,
        build_bars=True,
        build_features=False,
        feature_registry=None,
        tfs=[15, 30, 60, 120, 240],
    )
    
    if report.get("success"):
        print("Shared cache built successfully.")
        print(f"Report: {report}")
    else:
        print(f"Build failed: {report.get('error')}")
        sys.exit(1)

if __name__ == "__main__":
    main()