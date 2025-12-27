#!/usr/bin/env python3
"""
Verify season integrity against freeze snapshot.

Phase 5: Artifact Diff Guard - Detect unauthorized modifications to frozen seasons.
"""

import sys
import json
from pathlib import Path

# Add src to path
src_dir = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_dir))

from core.season_state import load_season_state
from core.snapshot import verify_snapshot_integrity
from core.season_context import current_season


def main():
    """CLI entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Verify season integrity against freeze snapshot"
    )
    parser.add_argument(
        "--season",
        help="Season identifier (default: current season)",
        default=None
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON"
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with non-zero code if integrity check fails"
    )
    
    args = parser.parse_args()
    
    # Determine season
    season = args.season or current_season()
    
    # Check if season is frozen
    try:
        state = load_season_state(season)
        is_frozen = state.is_frozen()
    except Exception as e:
        print(f"Error loading season state: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Verify integrity
    try:
        result = verify_snapshot_integrity(season)
    except Exception as e:
        print(f"Error verifying integrity: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Output results
    if args.json:
        output = {
            "season": season,
            "is_frozen": is_frozen,
            "integrity_check": result
        }
        print(json.dumps(output, indent=2))
    else:
        print(f"Season: {season}")
        print(f"State: {'FROZEN' if is_frozen else 'OPEN'}")
        print(f"Integrity Check: {'PASS' if result['ok'] else 'FAIL'}")
        print(f"Artifacts Checked: {result['total_checked']}")
        
        if not result["ok"]:
            print("\n--- Integrity Issues ---")
            if result["missing_files"]:
                print(f"Missing files ({len(result['missing_files'])}):")
                for f in result["missing_files"][:10]:  # Show first 10
                    print(f"  - {f}")
                if len(result["missing_files"]) > 10:
                    print(f"  ... and {len(result['missing_files']) - 10} more")
            
            if result["changed_files"]:
                print(f"\nChanged files ({len(result['changed_files'])}):")
                for f in result["changed_files"][:10]:  # Show first 10
                    print(f"  - {f}")
                if len(result["changed_files"]) > 10:
                    print(f"  ... and {len(result['changed_files']) - 10} more")
            
            if result["new_files"]:
                print(f"\nNew files ({len(result['new_files'])}):")
                for f in result["new_files"][:10]:  # Show first 10
                    print(f"  - {f}")
                if len(result["new_files"]) > 10:
                    print(f"  ... and {len(result['new_files']) - 10} more")
        
        if result["errors"]:
            print(f"\nErrors:")
            for error in result["errors"]:
                print(f"  - {error}")
    
    # Exit code
    if args.strict and not result["ok"]:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()