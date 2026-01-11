"""Generate research artifacts.

Phase 9: Generate canonical_results.json and research_index.json.
"""

from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import argparse
import json
import os
import shutil

from research.registry import build_research_index
from research.__main__ import generate_canonical_results
from core.season_state import check_season_not_frozen


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate research artifacts (canonical_results.json and research_index.json)",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    
    parser.add_argument(
        "--outputs-root",
        type=Path,
        default=Path("outputs"),
        help="Root outputs directory",
    )
    
    parser.add_argument(
        "--season",
        type=str,
        default=None,
        help="Season identifier (e.g., 2026Q1). If provided, outputs go to outputs/seasons/<season>/",
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run mode (don't write files, just show what would be done)",
    )
    
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Verbose output",
    )
    
    parser.add_argument(
        "--legacy-copy",
        action="store_true",
        help="Copy research artifacts to outputs/research/ for backward compatibility",
    )
    
    return parser.parse_args()


def generate_for_season(outputs_root: Path, season: str, verbose: bool) -> Path:
    """
    Write canonical_results.json + research_index.json into outputs/seasons/<season>/research/ and return research_dir.
    """
    research_dir = outputs_root / "seasons" / season / "research"
    if verbose:
        print(f"Research directory: {research_dir}")
    
    # Generate canonical results
    canonical_path = generate_canonical_results(outputs_root, research_dir)
    
    # Build research index
    build_research_index(outputs_root, research_dir)
    
    return research_dir


def main() -> int:
    """Main entry point."""
    args = parse_args()
    
    # Phase 5: Check season freeze state before any action
    if args.season:
        try:
            check_season_not_frozen(args.season, action="generate_research")
        except ImportError:
            # If season_state module is not available, skip check (backward compatibility)
            pass
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1
    
    # Determine output directory
    if args.season:
        research_dir = args.outputs_root / "seasons" / args.season / "research"
    else:
        research_dir = args.outputs_root / "research"
    
    if args.verbose:
        print(f"Outputs root: {args.outputs_root}")
        print(f"Research dir: {research_dir}")
        if args.season:
            print(f"Season: {args.season}")
    
    if args.dry_run:
        print("Dry run mode - would generate:")
        print(f"  - {research_dir / 'canonical_results.json'}")
        print(f"  - {research_dir / 'research_index.json'}")
        return 0
    
    try:
        # Generate canonical results
        print(f"Generating canonical_results.json...")
        generate_canonical_results(args.outputs_root, research_dir)
        
        # Build research index
        print(f"Building research_index.json...")
        build_research_index(args.outputs_root, research_dir)
        
        # Check if legacy copy should be performed
        should_do_legacy_copy = args.legacy_copy or (os.getenv("FISHBRO_LEGACY_COPY") == "1")
        
        # If season is specified and legacy copy is enabled, copy to outputs/research/ for backward compatibility
        if args.season and should_do_legacy_copy:
            legacy_dir = args.outputs_root / "research"
            legacy_dir.mkdir(parents=True, exist_ok=True)
            
            # Copy canonical_results.json
            src_canonical = research_dir / "canonical_results.json"
            dst_canonical = legacy_dir / "canonical_results.json"
            if src_canonical.exists():
                shutil.copy2(src_canonical, dst_canonical)
                if args.verbose:
                    print(f"Legacy copy: canonical_results.json to {dst_canonical}")
            
            # Copy research_index.json
            src_index = research_dir / "research_index.json"
            dst_index = legacy_dir / "research_index.json"
            if src_index.exists():
                shutil.copy2(src_index, dst_index)
                if args.verbose:
                    print(f"Legacy copy: research_index.json to {dst_index}")
            
            # Write a metadata file indicating which season this legacy copy represents
            metadata = {
                "season": args.season,
                "copied_from": str(research_dir),
                "note": "Legacy copy for backward compatibility (enabled via --legacy-copy or FISHBRO_LEGACY_COPY=1)"
            }
            metadata_path = legacy_dir / ".season_metadata.json"
            with open(metadata_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False, sort_keys=True)
            
            print(f"Legacy copy completed: {legacy_dir}")
        elif args.season and not should_do_legacy_copy:
            if args.verbose:
                print("Legacy copy skipped (default behavior). Use --legacy-copy or set FISHBRO_LEGACY_COPY=1 to enable.")
        
        print("Research governance layer completed successfully.")
        print(f"Output directory: {research_dir}")
        if args.season and should_do_legacy_copy:
            print(f"Legacy copy: {args.outputs_root / 'research'}")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
