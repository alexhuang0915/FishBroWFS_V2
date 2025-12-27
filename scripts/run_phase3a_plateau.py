#!/usr/bin/env python3
"""
Phase 3A Plateau Identification – Execution Script.

Loads winners.json from a research run, runs plateau identification,
and saves plateau_report.json + chosen_params.json.

Usage:
    python scripts/run_phase3a_plateau.py <path/to/winners.json>
    python scripts/run_phase3a_plateau.py   (default: use test fixture)
"""

import sys
from pathlib import Path

# Ensure the package root is in sys.path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from research.plateau import (
    identify_plateau_from_winners,
    save_plateau_report,
)


def main() -> None:
    if len(sys.argv) > 1:
        winners_path = Path(sys.argv[1])
    else:
        # Fallback to test fixture (for development)
        winners_path = Path("tests/fixtures/artifacts/winners_v2_valid.json")
        print(f"No path provided, using test fixture: {winners_path}")

    if not winners_path.exists():
        print(f"ERROR: File not found: {winners_path}")
        print("Please provide a valid winners.json path.")
        sys.exit(1)

    print(f"Loading candidates from {winners_path}")
    try:
        report = identify_plateau_from_winners(
            winners_path,
            k_neighbors=5,
            score_threshold_rel=0.1,
        )
    except Exception as e:
        print(f"Plateau identification failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    # Save reports next to winners.json (in same directory)
    output_dir = winners_path.parent / "plateau"
    save_plateau_report(report, output_dir)

    # Print summary
    print("\n--- Plateau Identification Summary ---")
    print(f"Candidates analyzed: {report.candidates_seen}")
    print(f"Parameters considered: {report.param_names}")
    print(f"Selected main candidate: {report.selected_main.candidate_id}")
    print(f"  score = {report.selected_main.score}")
    print(f"  params = {report.selected_main.params}")
    print(f"Backup candidates: {[c.candidate_id for c in report.selected_backup]}")
    print(f"Plateau region size: {len(report.plateau_region.members)}")
    print(f"Plateau stability score: {report.plateau_region.stability_score:.3f}")
    print(f"Reports saved to: {output_dir}")
    print("--- End of report ---")


if __name__ == "__main__":
    main()