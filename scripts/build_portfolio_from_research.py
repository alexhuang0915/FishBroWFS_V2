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
import json
import pandas as pd
from pathlib import Path


def create_season_level_portfolio_files(
    outputs_root: Path,
    season: str,
    portfolio_id: str,
    manifest: dict
) -> None:
    """Create season-level portfolio files as required by Phase 3 contract."""
    
    season_portfolio_dir = outputs_root / "seasons" / season / "portfolio"
    season_portfolio_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. portfolio_summary.json
    summary = {
        "portfolio_id": portfolio_id,
        "season": season,
        "generated_at": manifest.get("generated_at", ""),
        "total_decisions": manifest["counts"]["total_decisions"],
        "keep_decisions": manifest["counts"]["keep_decisions"],
        "num_legs_final": manifest["counts"]["num_legs_final"],
        "symbols_breakdown": manifest["counts"]["symbols_breakdown"],
        "warnings": manifest.get("warnings", {})
    }
    
    summary_path = season_portfolio_dir / "portfolio_summary.json"
    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(summary, f, ensure_ascii=False, indent=2, sort_keys=True)
    
    # 2. portfolio_admission.parquet (empty DataFrame with required schema)
    admission_df = pd.DataFrame({
        "run_id": [],
        "symbol": [],
        "strategy_id": [],
        "decision": [],
        "score_final": [],
        "timestamp": []
    })
    admission_path = season_portfolio_dir / "portfolio_admission.parquet"
    admission_df.to_parquet(admission_path, index=False)
    
    # 3. portfolio_state_timeseries.parquet (empty DataFrame with required schema)
    states_df = pd.DataFrame({
        "timestamp": [],
        "portfolio_value": [],
        "open_positions_count": [],
        "margin_ratio": []
    })
    states_path = season_portfolio_dir / "portfolio_state_timeseries.parquet"
    states_df.to_parquet(states_path, index=False)
    
    # 4. portfolio_manifest.json (copy from run_id directory with deterministic sorting)
    run_dir = outputs_root / "seasons" / season / "portfolio" / portfolio_id
    run_manifest_path = run_dir / "portfolio_manifest.json"
    
    if run_manifest_path.exists():
        with open(run_manifest_path, 'r', encoding='utf-8') as f:
            run_manifest = json.load(f)
        
        # Ensure deterministic sorting
        def sort_dict_recursively(obj):
            if isinstance(obj, dict):
                return {k: sort_dict_recursively(v) for k, v in sorted(obj.items())}
            elif isinstance(obj, list):
                # For lists, sort if all elements are strings or numbers
                if all(isinstance(item, (str, int, float)) for item in obj):
                    return sorted(obj)
                else:
                    return [sort_dict_recursively(item) for item in obj]
            else:
                return obj
        
        sorted_manifest = sort_dict_recursively(run_manifest)
        manifest_path = season_portfolio_dir / "portfolio_manifest.json"
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(sorted_manifest, f, ensure_ascii=False, indent=2, sort_keys=True)
    else:
        # Create minimal manifest if run directory doesn't exist
        minimal_manifest = {
            "portfolio_id": portfolio_id,
            "season": season,
            "generated_at": manifest.get("generated_at", ""),
            "artifacts": [
                {"path": "portfolio_summary.json", "type": "json"},
                {"path": "portfolio_admission.parquet", "type": "parquet"},
                {"path": "portfolio_state_timeseries.parquet", "type": "parquet"},
                {"path": "portfolio_manifest.json", "type": "json"}
            ]
        }
        manifest_path = season_portfolio_dir / "portfolio_manifest.json"
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(minimal_manifest, f, ensure_ascii=False, indent=2, sort_keys=True)
    
    print(f"Season-level portfolio files created in: {season_portfolio_dir}")
    print(f"  - {summary_path}")
    print(f"  - {admission_path}")
    print(f"  - {states_path}")
    print(f"  - {season_portfolio_dir / 'portfolio_manifest.json'}")


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
    
    # Phase 5: Check season freeze state before any action
    try:
        # Add src to path
        src_dir = Path(__file__).parent.parent / "src"
        sys.path.insert(0, str(src_dir))
        from FishBroWFS_V2.core.season_state import check_season_not_frozen
        check_season_not_frozen(args.season, action="build_portfolio_from_research")
    except ImportError:
        # If season_state module is not available, skip check (backward compatibility)
        pass
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    
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
        
        # Write artifacts to run_id directory
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
        
        # Create season-level portfolio files (Phase 3 contract)
        create_season_level_portfolio_files(
            outputs_root=outputs_root,
            season=args.season,
            portfolio_id=portfolio_id,
            manifest=manifest
        )
        
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