#!/usr/bin/env python3
"""CLI for building portfolio from research decisions."""

import argparse
import sys
from pathlib import Path

# Add src to path
src_dir = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_dir))

from FishBroWFS_V2.portfolio.research_bridge import build_portfolio_from_research
from FishBroWFS_V2.portfolio.writer import write_portfolio_artifacts


def main():
    parser = argparse.ArgumentParser(
        description="Build portfolio from research decisions"
    )
    parser.add_argument(
        "--season",
        required=True,
        help="Season identifier (e.g., 2026Q1)"
    )
    parser.add_argument(
        "--outputs-root",
        default="outputs",
        help="Root outputs directory (default: outputs)"
    )
    parser.add_argument(
        "--allowlist",
        default="CME.MNQ,TWF.MXF",
        help="Comma-separated list of allowed symbols (default: CME.MNQ,TWF.MXF)"
    )
    
    args = parser.parse_args()
    
    # Parse allowlist
    symbols_allowlist = set(args.allowlist.split(','))
    
    # Build paths
    outputs_root = Path(args.outputs_root)
    
    try:
        print(f"Building portfolio for season: {args.season}")
        print(f"Outputs root: {outputs_root}")
        print(f"Symbols allowlist: {symbols_allowlist}")
        print()
        
        # Build portfolio
        portfolio_id, spec, manifest = build_portfolio_from_research(
            season=args.season,
            outputs_root=outputs_root,
            symbols_allowlist=symbols_allowlist
        )
        
        print(f"Generated portfolio ID: {portfolio_id}")
        print(f"Total decisions: {manifest['counts']['total_decisions']}")
        print(f"KEEP decisions: {manifest['counts']['keep_decisions']}")
        print(f"Final legs: {manifest['counts']['num_legs_final']}")
        
        # Write artifacts
        portfolio_dir = write_portfolio_artifacts(
            outputs_root=outputs_root,
            season=args.season,
            spec=spec,
            manifest=manifest
        )
        
        print(f"\nPortfolio artifacts written to: {portfolio_dir}")
        print(f"  - {portfolio_dir / 'portfolio_spec.json'}")
        print(f"  - {portfolio_dir / 'portfolio_manifest.json'}")
        print(f"  - {portfolio_dir / 'README.md'}")
        
        # Print warnings if any
        if manifest.get('warnings', {}).get('missing_run_ids'):
            print(f"\nWarnings: {len(manifest['warnings']['missing_run_ids'])} run IDs missing metadata")
        
        return 0
        
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        print("\nMake sure the research directory exists:", file=sys.stderr)
        print(f"  {outputs_root / 'seasons' / args.season / 'research'}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())