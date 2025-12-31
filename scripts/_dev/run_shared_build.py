#!/usr/bin/env python3
"""
Run shared build for MNQ with new feature families.
"""
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from control.shared_build import build_shared

def main():
    # Use the subset file for faster testing
    txt_path = Path("FishBroData/raw/CME.MNQ_SUBSET.txt")
    
    if not txt_path.exists():
        print(f"Error: TXT file not found at {txt_path}")
        sys.exit(1)
    
    print(f"Running shared build for MNQ using {txt_path}")
    
    try:
        report = build_shared(
            season="2026Q1",
            dataset_id="CME.MNQ",
            txt_path=txt_path,
            outputs_root=Path("outputs"),
            mode="FULL",
            save_fingerprint=False,  # Don't save fingerprint for testing
            build_bars=False,  # Bars already exist
            build_features=True,  # Recompute features with new registry
            tfs=[60],  # Only compute for 60-minute timeframe for testing
        )
        
        print("Build successful!")
        print(f"Report: {report}")
        
        # Check features were built
        if report.get("build_features"):
            print("Features were built successfully")
            if "features_files_sha256" in report:
                print(f"Features SHA256: {report['features_files_sha256']}")
        
    except Exception as e:
        print(f"Build failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()