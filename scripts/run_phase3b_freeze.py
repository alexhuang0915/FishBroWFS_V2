#!/usr/bin/env python3
"""
Phase 3B Season Freeze – Execution Script.

Calls freeze_season_with_manifest.py with default season (2026Q1).
If season already frozen, will raise error unless --force.

Usage:
    python scripts/run_phase3b_freeze.py [--season SEASON] [--force]
"""

import sys
from pathlib import Path

# Ensure the package root is in sys.path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from scripts.freeze_season_with_manifest import main as freeze_main


def main() -> None:
    # Simulate command line arguments
    # For simplicity, we'll just call the freeze script with default season
    # In a real UI, the season should be passed as argument.
    import argparse
    parser = argparse.ArgumentParser(description="Freeze a season")
    parser.add_argument("--season", default="2026Q1", help="Season identifier")
    parser.add_argument("--force", action="store_true", help="Overwrite existing frozen season")
    args = parser.parse_args()

    # Build sys.argv for the freeze script
    sys.argv = [sys.argv[0], "--season", args.season]
    if args.force:
        sys.argv.append("--force")

    freeze_main()


if __name__ == "__main__":
    main()