"""Generate research artifacts.

Phase 9: Generate canonical_results.json and research_index.json.
"""

from __future__ import annotations

import sys
import argparse
from pathlib import Path


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
        "--dry-run",
        action="store_true",
        help="Dry run mode (don't write files, just show what would be done)",
    )
    
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Verbose output",
    )
    
    return parser.parse_args()


def main() -> int:
    """Main entry point."""
    args = parse_args()
    
    # Add src to path (must be done before imports)
    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
    
    try:
        from FishBroWFS_V2.research.registry import build_research_index
        from FishBroWFS_V2.research.__main__ import generate_canonical_results
    except ImportError as e:
        print(f"Import error: {e}", file=sys.stderr)
        return 1
    
    outputs_root = args.outputs_root
    research_dir = outputs_root / "research"
    
    if args.verbose:
        print(f"Outputs root: {outputs_root}")
        print(f"Research dir: {research_dir}")
    
    if args.dry_run:
        print("Dry run mode - would generate:")
        print(f"  - {research_dir / 'canonical_results.json'}")
        print(f"  - {research_dir / 'research_index.json'}")
        return 0
    
    try:
        # Generate canonical results
        print("Generating canonical_results.json...")
        generate_canonical_results(outputs_root, research_dir)
        
        # Build research index
        print("Building research_index.json...")
        build_research_index(outputs_root, research_dir)
        
        print("Research governance layer completed successfully.")
        print(f"Output directory: {research_dir}")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
