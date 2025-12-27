
"""CLI to generate and explain portfolio plan views."""
import argparse
import json
import sys
from pathlib import Path

from contracts.portfolio.plan_models import PortfolioPlan


# Helper function to get outputs root
def _get_outputs_root() -> Path:
    """Get outputs root from environment or default."""
    import os
    return Path(os.environ.get("FISHBRO_OUTPUTS_ROOT", "outputs"))


def load_portfolio_plan(plan_dir: Path) -> PortfolioPlan:
    """Load portfolio plan from directory."""
    plan_path = plan_dir / "portfolio_plan.json"
    if not plan_path.exists():
        raise FileNotFoundError(f"portfolio_plan.json not found in {plan_dir}")
    
    data = json.loads(plan_path.read_text(encoding="utf-8"))
    return PortfolioPlan.model_validate(data)


def main():
    parser = argparse.ArgumentParser(
        description="Generate human-readable view of a portfolio plan."
    )
    parser.add_argument(
        "--plan-id",
        required=True,
        help="Plan ID (directory name under outputs/portfolio/plans/)",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=50,
        help="Number of top candidates to include in view (default: 50)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Render view but don't write files",
    )
    
    args = parser.parse_args()
    
    # Locate plan directory
    outputs_root = _get_outputs_root()
    plan_dir = outputs_root / "portfolio" / "plans" / args.plan_id
    
    if not plan_dir.exists():
        print(f"Error: Plan directory not found: {plan_dir}", file=sys.stderr)
        sys.exit(1)
    
    # Load portfolio plan
    try:
        plan = load_portfolio_plan(plan_dir)
    except Exception as e:
        print(f"Error loading portfolio plan: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Import renderer here to avoid circular imports
    try:
        from portfolio.plan_view_renderer import render_plan_view, write_plan_view_files
    except ImportError as e:
        print(f"Error importing plan view renderer: {e}", file=sys.stderr)
        sys.exit(1)
    
    # Render view
    try:
        view = render_plan_view(plan, top_n=args.top_n)
    except Exception as e:
        print(f"Error rendering plan view: {e}", file=sys.stderr)
        sys.exit(1)
    
    if args.dry_run:
        # Print summary
        print(f"Plan ID: {view.plan_id}")
        print(f"Generated at: {view.generated_at_utc}")
        print(f"Source season: {view.source.get('season', 'N/A')}")
        print(f"Total candidates: {view.universe_stats.get('total_candidates', 0)}")
        print(f"Selected candidates: {view.universe_stats.get('num_selected', 0)}")
        print(f"Top {len(view.top_candidates)} candidates rendered")
        print("\nDry run complete - no files written.")
    else:
        # Write view files
        try:
            write_plan_view_files(plan_dir, view)
            print(f"Successfully wrote plan view files to {plan_dir}")
            print(f"  - plan_view.json")
            print(f"  - plan_view.md")
            print(f"  - plan_view_checksums.json")
            print(f"  - plan_view_manifest.json")
            
            # Print markdown path for convenience
            md_path = plan_dir / "plan_view.md"
            if md_path.exists():
                print(f"\nView markdown: {md_path}")
        except Exception as e:
            print(f"Error writing plan view files: {e}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()


