
"""Research Index CLI - generate research artifacts.

Phase 9: Generate canonical_results.json and research_index.json.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from research.registry import build_research_index


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Generate research index")
    parser.add_argument(
        "--outputs-root",
        type=Path,
        default=Path("outputs"),
        help="Root outputs directory (default: outputs)",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("outputs/research"),
        help="Research output directory (default: outputs/research)",
    )
    
    args = parser.parse_args()
    
    try:
        index_path = build_research_index(args.outputs_root, args.out_dir)
        print(f"Research index generated successfully.")
        print(f"  Index: {index_path}")
        print(f"  Canonical results: {args.out_dir / 'canonical_results.json'}")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())



