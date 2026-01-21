#!/usr/bin/env python3
"""
Unified CLI for Replay/Compare UX v1 (Read-only Audit Diff for Deployment Bundles).

Provides a simple interface for comparing deployment bundles with:
- Bundle resolution and validation
- Deterministic diff generation
- Metric leakage prevention (Hybrid BC v1.1 compliant)
- Evidence generation in outputs/_dp_evidence/

Usage examples:
  # List deployment bundles for a job
  python scripts/compare_deployment_bundles.py list --job-id <job_id>
  
  # Resolve a single deployment bundle
  python scripts/compare_deployment_bundles.py resolve --deployment-dir <path>
  
  # Compare two deployment bundles
  python scripts/compare_deployment_bundles.py compare <bundle_a> <bundle_b>
  
  # Generate detailed diff report
  python scripts/compare_deployment_bundles.py diff <bundle_a> <bundle_b>
"""

import sys
import argparse
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.deployment.bundle_resolver import BundleResolver, main_cli as resolver_cli
from src.core.deployment.diff_engine import DiffEngine, main_cli as diff_cli


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Replay/Compare UX v1: Read-only audit diff for deployment bundles",
        epilog="See individual command help for more details: python scripts/compare_deployment_bundles.py <command> --help"
    )
    
    subparsers = parser.add_subparsers(
        dest="command",
        help="Command to execute",
        required=True,
    )
    
    # ----------------------------------------------------------------------
    # list command
    # ----------------------------------------------------------------------
    list_parser = subparsers.add_parser(
        "list",
        help="List deployment bundles for a job"
    )
    list_parser.add_argument(
        "--job-id",
        type=str,
        required=True,
        help="Job identifier"
    )
    list_parser.add_argument(
        "--outputs-root",
        type=Path,
        default=Path("outputs"),
        help="Root outputs directory (default: outputs/)"
    )
    
    # ----------------------------------------------------------------------
    # resolve command
    # ----------------------------------------------------------------------
    resolve_parser = subparsers.add_parser(
        "resolve",
        help="Resolve and validate a deployment bundle"
    )
    resolve_parser.add_argument(
        "--deployment-dir",
        type=Path,
        required=True,
        help="Path to deployment directory"
    )
    resolve_parser.add_argument(
        "--outputs-root",
        type=Path,
        default=Path("outputs"),
        help="Root outputs directory (default: outputs/)"
    )
    
    # ----------------------------------------------------------------------
    # compare command (simple comparison)
    # ----------------------------------------------------------------------
    compare_parser = subparsers.add_parser(
        "compare",
        help="Simple comparison of two deployment bundles"
    )
    compare_parser.add_argument(
        "bundle_a",
        type=Path,
        help="Path to first deployment directory"
    )
    compare_parser.add_argument(
        "bundle_b",
        type=Path,
        help="Path to second deployment directory"
    )
    compare_parser.add_argument(
        "--outputs-root",
        type=Path,
        default=Path("outputs"),
        help="Root outputs directory (default: outputs/)"
    )
    
    # ----------------------------------------------------------------------
    # diff command (detailed diff report)
    # ----------------------------------------------------------------------
    diff_parser = subparsers.add_parser(
        "diff",
        help="Generate detailed diff report for two deployment bundles"
    )
    diff_parser.add_argument(
        "bundle_a",
        type=Path,
        help="Path to first deployment directory"
    )
    diff_parser.add_argument(
        "bundle_b",
        type=Path,
        help="Path to second deployment directory"
    )
    diff_parser.add_argument(
        "--output-dir",
        type=Path,
        help="Output directory for diff report (default: outputs/_dp_evidence/replay_compare_v1/)"
    )
    diff_parser.add_argument(
        "--no-redact",
        action="store_true",
        help="Disable metric redaction (not recommended for Hybrid BC v1.1)"
    )
    diff_parser.add_argument(
        "--outputs-root",
        type=Path,
        default=Path("outputs"),
        help="Root outputs directory (default: outputs/)"
    )
    
    # ----------------------------------------------------------------------
    # version command
    # ----------------------------------------------------------------------
    subparsers.add_parser(
        "version",
        help="Show version information"
    )
    
    args = parser.parse_args()
    
    # Configure logging
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    
    # Execute command
    if args.command == "list":
        return run_list_command(args)
    elif args.command == "resolve":
        return run_resolve_command(args)
    elif args.command == "compare":
        return run_compare_command(args)
    elif args.command == "diff":
        return run_diff_command(args)
    elif args.command == "version":
        return run_version_command()
    else:
        parser.print_help()
        return 1


def run_list_command(args):
    """Run list command."""
    print(f"Listing deployment bundles for job: {args.job_id}")
    print(f"Outputs root: {args.outputs_root}")
    print()
    
    resolver = BundleResolver(outputs_root=args.outputs_root)
    deployment_dirs = resolver.find_deployment_bundles(args.job_id)
    
    if not deployment_dirs:
        print(f"No deployment bundles found for job: {args.job_id}")
        return 0
    
    print(f"Found {len(deployment_dirs)} deployment bundle(s):")
    for i, deployment_dir in enumerate(deployment_dirs):
        manifest_data = resolver.load_manifest(deployment_dir)
        if manifest_data:
            deployment_id = manifest_data.get("deployment_id", "unknown")
            created_at = manifest_data.get("created_at", "unknown")
            artifact_count = manifest_data.get("artifact_count", 0)
            print(f"  {i+1}. {deployment_dir.name}")
            print(f"     Deployment ID: {deployment_id}")
            print(f"     Created: {created_at}")
            print(f"     Artifacts: {artifact_count}")
            print(f"     Path: {deployment_dir}")
        else:
            print(f"  {i+1}. {deployment_dir.name} (invalid manifest)")
        print()
    
    return 0


def run_resolve_command(args):
    """Run resolve command."""
    if not args.deployment_dir.exists():
        print(f"Error: Deployment directory not found: {args.deployment_dir}")
        return 1
    
    print(f"Resolving deployment bundle: {args.deployment_dir}")
    print(f"Outputs root: {args.outputs_root}")
    print()
    
    resolver = BundleResolver(outputs_root=args.outputs_root)
    resolution = resolver.resolve_bundle(args.deployment_dir)
    
    print(f"Bundle resolution for {args.deployment_dir}:")
    print(f"  Is valid: {resolution.is_valid}")
    print(f"  Resolution time: {resolution.resolution_time}")
    
    if resolution.manifest:
        manifest = resolution.manifest
        print(f"  Deployment ID: {manifest.deployment_id}")
        print(f"  Job ID: {manifest.job_id}")
        print(f"  Artifact count: {manifest.artifact_count}")
        print(f"  Created at: {manifest.created_at}")
        print(f"  Created by: {manifest.created_by}")
        print(f"  Deployment target: {manifest.deployment_target}")
        
        # Show key artifacts
        print(f"  Key artifacts loaded:")
        if manifest.gate_summary:
            print(f"    - Gate Summary: {manifest.gate_summary.overall_status.value}")
        if manifest.strategy_report:
            print(f"    - Strategy Report: Yes")
        if manifest.portfolio_config:
            print(f"    - Portfolio Config: Yes")
        if manifest.admission_report:
            print(f"    - Admission Report: Yes")
        if manifest.config_snapshot:
            print(f"    - Config Snapshot: Yes")
        if manifest.input_manifest:
            print(f"    - Input Manifest: Yes")
    
    if resolution.validation_errors:
        print(f"  Validation errors ({len(resolution.validation_errors)}):")
        for error in resolution.validation_errors:
            print(f"    - {error}")
    
    return 0 if resolution.is_valid else 1


def run_compare_command(args):
    """Run simple compare command."""
    if not args.bundle_a.exists():
        print(f"Error: Bundle A not found: {args.bundle_a}")
        return 1
    
    if not args.bundle_b.exists():
        print(f"Error: Bundle B not found: {args.bundle_b}")
        return 1
    
    print(f"Comparing deployment bundles:")
    print(f"  Bundle A: {args.bundle_a}")
    print(f"  Bundle B: {args.bundle_b}")
    print(f"  Outputs root: {args.outputs_root}")
    print()
    
    resolver = BundleResolver(outputs_root=args.outputs_root)
    diff = resolver.compare_bundles(args.bundle_a, args.bundle_b)
    
    print(f"Comparison results:")
    print(f"  Compared at: {diff['compared_at']}")
    print(f"  Bundle A: {diff['bundle_a']['path']}")
    print(f"    Deployment ID: {diff['bundle_a']['deployment_id']}")
    print(f"    Job ID: {diff['bundle_a']['job_id']}")
    print(f"    Is valid: {diff['bundle_a']['is_valid']}")
    print(f"  Bundle B: {diff['bundle_b']['path']}")
    print(f"    Deployment ID: {diff['bundle_b']['deployment_id']}")
    print(f"    Job ID: {diff['bundle_b']['job_id']}")
    print(f"    Is valid: {diff['bundle_b']['is_valid']}")
    
    comparison = diff['comparison']
    print(f"  Comparison:")
    print(f"    Same job: {comparison['same_job']}")
    print(f"    Same deployment: {comparison['same_deployment']}")
    print(f"    Artifact count difference: {comparison['artifact_count_diff']}")
    
    if comparison['gate_summary_diff']:
        gate_diff = comparison['gate_summary_diff']
        print(f"    Gate summary changes:")
        print(f"      Overall status changed: {gate_diff['overall_status_changed']}")
        print(f"      Overall status A: {gate_diff['overall_status_a']}")
        print(f"      Overall status B: {gate_diff['overall_status_b']}")
        print(f"      Gate count difference: {gate_diff['gate_count_diff']}")
        
        if gate_diff['gate_status_changes']:
            print(f"      Gate status changes ({len(gate_diff['gate_status_changes'])}):")
            for change in gate_diff['gate_status_changes'][:5]:  # Show first 5
                print(f"        - {change['gate_id']}: {change['status_a']} → {change['status_b']}")
            if len(gate_diff['gate_status_changes']) > 5:
                print(f"        ... and {len(gate_diff['gate_status_changes']) - 5} more")
    
    # Check if both bundles are valid
    if not diff['bundle_a']['is_valid'] or not diff['bundle_b']['is_valid']:
        print(f"\n⚠️  Warning: One or both bundles are invalid")
        return 1
    
    return 0


def run_diff_command(args):
    """Run detailed diff command."""
    # Use the diff engine CLI directly
    sys.argv = [
        "diff_engine.py",
        str(args.bundle_a),
        str(args.bundle_b),
    ]
    
    if args.output_dir:
        sys.argv.extend(["--output-dir", str(args.output_dir)])
    
    if args.no_redact:
        sys.argv.append("--no-redact")
    
    if args.outputs_root:
        sys.argv.extend(["--outputs-root", str(args.outputs_root)])
    
    return diff_cli()


def run_version_command():
    """Show version information."""
    print("Replay/Compare UX v1 - Read-only Audit Diff for Deployment Bundles")
    print("Version: 1.0.0")
    print("Hybrid BC v1.1 compliant: Yes")
    print("Metric leakage prevention: Enabled")
    print("Deterministic diff: Yes")
    print("Read-only operation: Yes")
    return 0


if __name__ == "__main__":
    sys.exit(main())