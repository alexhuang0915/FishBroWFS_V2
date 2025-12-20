"""Generate research artifacts.

Phase 9: Generate canonical_results.json and research_index.json.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from FishBroWFS_V2.research.registry import build_research_index
from FishBroWFS_V2.research.__main__ import generate_canonical_results


def main() -> int:
    """Main entry point."""
    outputs_root = Path("outputs")
    research_dir = outputs_root / "research"
    
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
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

