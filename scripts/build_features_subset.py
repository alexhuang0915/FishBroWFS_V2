from __future__ import annotations

import argparse
from pathlib import Path
import sys

# Ensure src importable even when run as a script
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from control.shared_build import build_shared


def main() -> None:
    ap = argparse.ArgumentParser(description="Build shared features cache for a dataset/timeframe subset.")
    ap.add_argument("--dataset", required=True, help="Dataset ID, e.g. CME.MNQ or CFE.VX")
    ap.add_argument("--timeframe", type=int, required=True, help="Timeframe in minutes, e.g. 60")
    ap.add_argument("--features", required=True, help="Comma-separated feature names")
    ap.add_argument("--season", default="2026Q1", help="Season, default=2026Q1")
    ap.add_argument("--build-features", action="store_true", help="Build features cache (requires bars already exist or build_bars enabled elsewhere)")
    args = ap.parse_args()

    dataset_id = args.dataset
    season = args.season
    tf = args.timeframe

    txt_path = Path(f"FishBroData/raw/{dataset_id}_SUBSET.txt")
    if not txt_path.exists():
        print(f"Error: TXT file not found at {txt_path}")
        raise SystemExit(2)

    features = [x.strip() for x in args.features.split(",") if x.strip()]
    if not features:
        print("Error: empty --features")
        raise SystemExit(2)

    print(f"Building features cache for {dataset_id} season {season}...")

    # build_shared will compute bars/features; feature_registry is resolved inside build_shared
report = build_shared(
    season=season,
    dataset_id=dataset_id,
    txt_path=txt_path,
    outputs_root=Path("outputs"),
    mode="FULL",
    save_fingerprint=True,
    generated_at_utc=None,
    build_bars=True,
    build_features=bool(args.build_features),
    feature_registry=None,  # use features.registry.get_default_registry() inside shared_build
    tfs=[tf],
)



    print("Features cache built successfully.")
    print("Report keys:", list(report.keys()))


if __name__ == "__main__":
    main()
