
"""CLI for generating portfolio plan quality reports."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from portfolio.plan_quality import compute_quality_from_plan_dir
from portfolio.plan_quality_writer import write_plan_quality_files


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate quality report for a portfolio plan.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--outputs-root",
        type=Path,
        default=Path("outputs"),
        help="Root outputs directory",
    )
    parser.add_argument(
        "--plan-id",
        required=True,
        help="Plan ID (directory name under outputs/portfolio/plans/)",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write quality files to plan directory (otherwise just print)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print detailed quality report",
    )
    
    args = parser.parse_args()
    
    # Build plan directory path
    plan_dir = args.outputs_root / "portfolio" / "plans" / args.plan_id
    
    if not plan_dir.exists():
        print(f"Error: Plan directory does not exist: {plan_dir}", file=sys.stderr)
        sys.exit(1)
    
    try:
        # Compute quality (read-only)
        quality, inputs = compute_quality_from_plan_dir(plan_dir)
        
        # Print grade and reasons
        print(f"Plan: {quality.plan_id}")
        print(f"Grade: {quality.grade}")
        print(f"Reasons: {', '.join(quality.reasons) if quality.reasons else 'None'}")
        
        if args.verbose:
            print("\n--- Quality Report ---")
            print(json.dumps(quality.model_dump(), indent=2))
        
        # Write files if requested
        if args.write:
            # Note: write_plan_quality_files now only takes plan_dir and quality
            # It computes inputs_sha256 internally via _compute_inputs_sha256
            write_plan_quality_files(plan_dir, quality)
            print(f"\nQuality files written to: {plan_dir}")
            print("  - plan_quality.json")
            print("  - plan_quality_checksums.json")
            print("  - plan_quality_manifest.json")
        
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()


