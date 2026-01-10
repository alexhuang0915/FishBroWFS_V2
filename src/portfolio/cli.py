"""Portfolio CLI."""

import argparse
import json
import sys
import yaml
from pathlib import Path
from typing import Optional

from core.schemas.portfolio_v1 import (
    PortfolioPolicyV1,
    PortfolioSpecV1,
)
from portfolio.runner_v1 import (
    run_portfolio_admission,
    validate_portfolio_spec,
)
from portfolio.artifacts_writer_v1 import (
    write_portfolio_artifacts,
    compute_spec_sha256,
    compute_policy_sha256,
)


def load_yaml_or_json(filepath: Path) -> dict:
    """Load YAML or JSON file."""
    content = filepath.read_text(encoding="utf-8")
    if filepath.suffix.lower() in (".yaml", ".yml"):
        return yaml.safe_load(content)
    else:
        return json.loads(content)


def save_yaml_or_json(filepath: Path, data: dict):
    """Save data as YAML or JSON based on file extension."""
    if filepath.suffix.lower() in (".yaml", ".yml"):
        filepath.write_text(yaml.dump(data, default_flow_style=False), encoding="utf-8")
    else:
        filepath.write_text(json.dumps(data, indent=2), encoding="utf-8")


def validate_command(args):
    """Validate portfolio specification."""
    try:
        # Load spec
        spec_data = load_yaml_or_json(args.spec)
        
        # Load policy if provided separately
        policy_data = {}
        if args.policy:
            policy_data = load_yaml_or_json(args.policy)
            spec_data["policy"] = policy_data
        
        # Create spec object (without sha256 for now)
        if "spec_sha256" in spec_data:
            spec_data.pop("spec_sha256")
        
        spec = PortfolioSpecV1(**spec_data)
        
        # Compute spec SHA256
        spec_sha256 = compute_spec_sha256(spec)
        print(f"✓ Spec SHA256: {spec_sha256}")
        
        # Validate against outputs
        outputs_root = Path(args.outputs_root) if args.outputs_root else Path("outputs")
        errors = validate_portfolio_spec(spec, outputs_root)
        
        if errors:
            print("✗ Validation errors:")
            for error in errors:
                print(f"  - {error}")
            sys.exit(1)
        
        # Resource estimate
        total_estimate = len(spec.seasons) * len(spec.strategy_ids) * len(spec.instrument_ids) * 1000
        print(f"✓ Resource estimate: ~{total_estimate} candidates")
        
        print("✓ Spec validation passed")
        
        # If --save flag, update spec with SHA256
        if args.save:
            spec_dict = spec.model_dump()
            spec_dict["spec_sha256"] = spec_sha256
            save_yaml_or_json(args.spec, spec_dict)
            print(f"✓ Updated {args.spec} with spec_sha256")
        
    except Exception as e:
        print(f"✗ Validation failed: {e}")
        sys.exit(1)


def run_command(args):
    """Run portfolio admission."""
    try:
        # Load spec
        spec_data = load_yaml_or_json(args.spec)
        spec = PortfolioSpecV1(**spec_data)
        
        # Load policy (could be embedded in spec or separate)
        if "policy" in spec_data:
            policy_data = spec_data["policy"]
        elif args.policy:
            policy_data = load_yaml_or_json(args.policy)
        else:
            raise ValueError("Policy not found in spec and --policy not provided")
        
        policy = PortfolioPolicyV1(**policy_data)
        
        # Compute SHA256 for audit
        policy_sha256 = compute_policy_sha256(policy)
        spec_sha256 = spec.spec_sha256 if hasattr(spec, "spec_sha256") else compute_spec_sha256(spec)
        
        print(f"Policy SHA256: {policy_sha256}")
        print(f"Spec SHA256: {spec_sha256}")
        
        # Set equity
        equity_base = args.equity if args.equity else 1_000_000.0  # Default 1M TWD
        
        # Output directory
        if args.output_dir:
            output_dir = Path(args.output_dir)
        else:
            # Create auto-generated directory
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_dir = Path("outputs") / "jobs" / f"portfolio_{timestamp}"
        
        outputs_root = Path(args.outputs_root) if args.outputs_root else Path("outputs")
        
        # Run portfolio admission
        candidates, final_positions, results = run_portfolio_admission(
            policy=policy,
            spec=spec,
            equity_base=equity_base,
            outputs_root=outputs_root,
            replay_mode=False,
        )
        
        # Update summary with SHA256
        summary = results["summary"]
        summary.policy_sha256 = policy_sha256
        summary.spec_sha256 = spec_sha256
        
        # Write artifacts
        hashes = write_portfolio_artifacts(
            output_dir=output_dir,
            decisions=results["decisions"],
            bar_states=results["bar_states"],
            summary=summary,
            policy=policy,
            spec=spec,
            replay_mode=False,
        )
        
        print(f"\n✓ Portfolio admission completed")
        print(f"  Output directory: {output_dir}")
        print(f"  Candidates: {summary.total_candidates}")
        print(f"  Accepted: {summary.accepted_count}")
        print(f"  Rejected: {summary.rejected_count}")
        print(f"  Final slots used: {summary.final_slots_used}/{policy.max_slots_total}")
        print(f"  Final margin ratio: {summary.final_margin_ratio:.2%}")
        
        # Save run info
        run_info = {
            "run_id": output_dir.name,
            "timestamp": datetime.now().isoformat(),
            "spec_sha256": spec_sha256,
            "policy_sha256": policy_sha256,
            "output_dir": str(output_dir),
            "summary": summary.model_dump(),
        }
        run_info_path = output_dir / "run_info.json"
        run_info_path.write_text(json.dumps(run_info, indent=2), encoding="utf-8")
        
    except Exception as e:
        print(f"✗ Run failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def replay_command(args):
    """Replay portfolio admission (read-only)."""
    try:
        # Find run directory
        run_id = args.run_id
        runs_dir = Path("outputs") / "portfolio"
        
        run_dir = None
        for dir_path in runs_dir.glob(f"*{run_id}*"):
            if dir_path.is_dir():
                run_dir = dir_path
                break
        
        if not run_dir or not run_dir.exists():
            print(f"✗ Run directory not found for run_id: {run_id}")
            sys.exit(1)
        
        # Load spec and policy from run directory
        spec_path = run_dir / "portfolio_spec.json"
        policy_path = run_dir / "portfolio_policy.json"
        
        if not spec_path.exists() or not policy_path.exists():
            print(f"✗ Spec or policy not found in run directory")
            sys.exit(1)
        
        spec_data = json.loads(spec_path.read_text(encoding="utf-8"))
        policy_data = json.loads(policy_path.read_text(encoding="utf-8"))
        
        spec = PortfolioSpecV1(**spec_data)
        policy = PortfolioPolicyV1(**policy_data)
        
        print(f"Replaying run: {run_dir.name}")
        print(f"Spec SHA256: {spec.spec_sha256 if hasattr(spec, 'spec_sha256') else 'N/A'}")
        print(f"Policy SHA256: {compute_policy_sha256(policy)}")
        
        # Run in replay mode (no writes)
        equity_base = args.equity if args.equity else 1_000_000.0
        outputs_root = Path(args.outputs_root) if args.outputs_root else Path("outputs")
        
        candidates, final_positions, results = run_portfolio_admission(
            policy=policy,
            spec=spec,
            equity_base=equity_base,
            outputs_root=outputs_root,
            replay_mode=True,
        )
        
        summary = results["summary"]
        print(f"\n✓ Replay completed (read-only)")
        print(f"  Candidates: {summary.total_candidates}")
        print(f"  Accepted: {summary.accepted_count}")
        print(f"  Rejected: {summary.rejected_count}")
        print(f"  Final slots used: {summary.final_slots_used}/{policy.max_slots_total}")
        
        # Compare with original results if available
        original_summary_path = run_dir / "portfolio_summary.json"
        if original_summary_path.exists():
            original_summary = json.loads(original_summary_path.read_text(encoding="utf-8"))
            if (summary.accepted_count == original_summary["accepted_count"] and
                summary.rejected_count == original_summary["rejected_count"]):
                print("✓ Replay matches original results")
            else:
                print("✗ Replay differs from original results!")
                print(f"  Original: {original_summary['accepted_count']} accepted, {original_summary['rejected_count']} rejected")
                print(f"  Replay: {summary.accepted_count} accepted, {summary.rejected_count} rejected")
        
    except Exception as e:
        print(f"✗ Replay failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Portfolio Engine CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # Validate command
    validate_parser = subparsers.add_parser("validate", help="Validate portfolio specification")
    validate_parser.add_argument("--spec", type=Path, required=True, help="Spec file (YAML/JSON)")
    validate_parser.add_argument("--policy", type=Path, help="Policy file (YAML/JSON, optional if embedded in spec)")
    validate_parser.add_argument("--outputs-root", type=Path, help="Outputs root directory (default: outputs)")
    validate_parser.add_argument("--save", action="store_true", help="Save spec with computed SHA256")
    validate_parser.set_defaults(func=validate_command)
    
    # Run command
    run_parser = subparsers.add_parser("run", help="Run portfolio admission")
    run_parser.add_argument("--spec", type=Path, required=True, help="Spec file (YAML/JSON)")
    run_parser.add_argument("--policy", type=Path, help="Policy file (YAML/JSON, optional if embedded in spec)")
    run_parser.add_argument("--equity", type=float, help="Equity in base currency (default: 1,000,000 TWD)")
    run_parser.add_argument("--outputs-root", type=Path, help="Outputs root directory (default: outputs)")
    run_parser.add_argument("--output-dir", type=Path, help="Output directory (default: auto-generated)")
    run_parser.set_defaults(func=run_command)
    
    # Replay command
    replay_parser = subparsers.add_parser("replay", help="Replay portfolio admission (read-only)")
    replay_parser.add_argument("--run-id", type=str, required=True, help="Run ID or directory name")
    replay_parser.add_argument("--equity", type=float, help="Equity in base currency (default: 1,000,000 TWD)")
    replay_parser.add_argument("--outputs-root", type=Path, help="Outputs root directory (default: outputs)")
    replay_parser.set_defaults(func=replay_command)
    
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()