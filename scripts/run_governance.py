
#!/usr/bin/env python3
"""CLI entry point for governance evaluation.

Reads artifacts from three stage run directories and produces governance decisions.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from FishBroWFS_V2.core.governance_writer import write_governance_artifacts
from FishBroWFS_V2.core.paths import get_run_dir
from FishBroWFS_V2.core.run_id import make_run_id
from FishBroWFS_V2.pipeline.governance_eval import evaluate_governance


def main() -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Evaluate governance rules on funnel stage artifacts",
    )
    parser.add_argument(
        "--stage0-dir",
        type=Path,
        required=True,
        help="Path to Stage0 run directory",
    )
    parser.add_argument(
        "--stage1-dir",
        type=Path,
        required=True,
        help="Path to Stage1 run directory",
    )
    parser.add_argument(
        "--stage2-dir",
        type=Path,
        required=True,
        help="Path to Stage2 run directory",
    )
    parser.add_argument(
        "--outputs-root",
        type=Path,
        required=True,
        help="Root outputs directory (e.g., outputs/)",
    )
    parser.add_argument(
        "--season",
        type=str,
        required=True,
        help="Season identifier",
    )
    
    args = parser.parse_args()
    
    # Validate stage directories exist
    if not args.stage0_dir.exists():
        print(f"Error: Stage0 directory does not exist: {args.stage0_dir}", file=sys.stderr)
        return 1
    if not args.stage1_dir.exists():
        print(f"Error: Stage1 directory does not exist: {args.stage1_dir}", file=sys.stderr)
        return 1
    if not args.stage2_dir.exists():
        print(f"Error: Stage2 directory does not exist: {args.stage2_dir}", file=sys.stderr)
        return 1
    
    # Evaluate governance
    try:
        report = evaluate_governance(
            stage0_dir=args.stage0_dir,
            stage1_dir=args.stage1_dir,
            stage2_dir=args.stage2_dir,
        )
    except Exception as e:
        print(f"Error evaluating governance: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1
    
    # Generate governance_id
    governance_id = make_run_id(prefix="gov")
    
    # Determine governance directory path
    # Format: outputs/seasons/{season}/governance/{governance_id}/
    governance_dir = args.outputs_root / "seasons" / args.season / "governance" / governance_id
    
    # Write artifacts
    try:
        write_governance_artifacts(governance_dir, report)
    except Exception as e:
        print(f"Error writing governance artifacts: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1
    
    # Output governance_dir path (stdout)
    print(str(governance_dir))
    
    return 0


if __name__ == "__main__":
    sys.exit(main())


