#!/usr/bin/env python3
"""
Deploy Job Bundle CLI.

Command-line interface for building and verifying job deployment bundles.
Part of Deployment Automation v1 (Deterministic Deployment Bundle).

Usage:
  python scripts/deploy_job_bundle.py build --job-id JOB_ID [--target staging] [--notes "deployment notes"]
  python scripts/deploy_job_bundle.py verify --job-id JOB_ID [--deployment-dir PATH]
"""

import sys
import argparse
import logging
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from core.deployment.job_deployment_builder import JobDeploymentBuilder, get_outputs_root


def setup_logging(verbose: bool = False):
    """Setup logging configuration."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def build_command(args):
    """Handle build command."""
    print(f"Building deployment bundle for job: {args.job_id}")
    print(f"Target: {args.target}")
    if args.notes:
        print(f"Notes: {args.notes}")
    
    try:
        builder = JobDeploymentBuilder(outputs_root=args.outputs_root)
        bundle = builder.build(
            job_id=args.job_id,
            deployment_target=args.target,
            deployment_notes=args.notes,
        )
        
        print("\n" + "="*60)
        print("✓ DEPLOYMENT BUNDLE CREATED SUCCESSFULLY")
        print("="*60)
        print(f"Deployment ID: {bundle.deployment_id}")
        print(f"Job ID: {bundle.manifest.job_id}")
        print(f"Bundle path: {bundle.bundle_path}")
        print(f"Bundle size: {bundle.bundle_size_bytes:,} bytes")
        print(f"Artifacts included: {bundle.manifest.artifact_count}")
        print(f"Bundle hash: {bundle.manifest.bundle_hash[:16]}...")
        print(f"Manifest hash: {bundle.manifest.manifest_hash[:16]}...")
        
        # Show artifact breakdown
        artifact_types = {}
        for artifact in bundle.manifest.artifacts:
            artifact_types[artifact.artifact_type] = artifact_types.get(artifact.artifact_type, 0) + 1
        
        print(f"\nArtifact breakdown:")
        for artifact_type, count in sorted(artifact_types.items()):
            print(f"  - {artifact_type}: {count}")
        
        print(f"\nNext steps:")
        print(f"  1. Bundle location: {bundle.bundle_path}")
        print(f"  2. Verify bundle: python {__file__} verify --job-id {args.job_id}")
        print(f"  3. Deploy to target: {args.target}")
        
        return 0
        
    except FileNotFoundError as e:
        print(f"✗ Error: {e}")
        print(f"  Make sure job {args.job_id} exists in outputs/jobs/")
        return 1
    except ValueError as e:
        print(f"✗ Error: {e}")
        print(f"  Job directory exists but no canonical artifacts found")
        return 1
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1


def verify_command(args):
    """Handle verify command."""
    print("Verifying deployment bundle...")
    
    try:
        builder = JobDeploymentBuilder(outputs_root=args.outputs_root)
        
        # Determine deployment directory
        if args.deployment_dir:
            deployment_dir = args.deployment_dir
            print(f"Using specified deployment directory: {deployment_dir}")
        else:
            # Auto-locate most recent deployment
            deployments_root = args.outputs_root / "jobs" / args.job_id / "deployments"
            if not deployments_root.exists():
                print(f"✗ No deployments found for job: {args.job_id}")
                print(f"  Expected directory: {deployments_root}")
                return 1
            
            # Find most recent deployment
            deployment_dirs = []
            for item in deployments_root.iterdir():
                if item.is_dir() and item.name.startswith("deployment_"):
                    deployment_dirs.append((item.stat().st_mtime, item))
            
            if not deployment_dirs:
                print(f"✗ No deployment directories found for job: {args.job_id}")
                return 1
            
            # Sort by modification time (newest first)
            deployment_dirs.sort(key=lambda x: x[0], reverse=True)
            deployment_dir = deployment_dirs[0][1]
            print(f"Found most recent deployment: {deployment_dir}")
        
        # Verify bundle
        success = builder.verify_bundle(deployment_dir)
        
        if success:
            print("\n" + "="*60)
            print("✓ DEPLOYMENT BUNDLE VERIFICATION PASSED")
            print("="*60)
            print(f"Deployment directory: {deployment_dir}")
            
            # Load manifest to show details
            manifest_path = deployment_dir / "deployment_manifest_v1.json"
            if manifest_path.exists():
                import json
                with open(manifest_path, 'r', encoding='utf-8') as f:
                    manifest = json.load(f)
                
                print(f"Deployment ID: {manifest.get('deployment_id', 'N/A')}")
                print(f"Job ID: {manifest.get('job_id', 'N/A')}")
                print(f"Artifacts: {manifest.get('artifact_count', 0)}")
                print(f"Created: {manifest.get('created_at', 'N/A')}")
                print(f"Target: {manifest.get('deployment_target', 'N/A')}")
            
            return 0
        else:
            print("\n" + "="*60)
            print("✗ DEPLOYMENT BUNDLE VERIFICATION FAILED")
            print("="*60)
            print("Bundle integrity check failed.")
            print("Possible issues:")
            print("  - Files have been modified")
            print("  - Files are missing")
            print("  - Hash mismatch")
            return 1
            
    except Exception as e:
        print(f"✗ Verification failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


def list_command(args):
    """Handle list command."""
    print(f"Listing deployments for job: {args.job_id}")
    
    try:
        deployments_root = args.outputs_root / "jobs" / args.job_id / "deployments"
        
        if not deployments_root.exists():
            print(f"No deployments directory found for job: {args.job_id}")
            return 0
        
        deployment_dirs = []
        for item in deployments_root.iterdir():
            if item.is_dir() and item.name.startswith("deployment_"):
                mtime = item.stat().st_mtime
                from datetime import datetime
                mtime_str = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
                deployment_dirs.append((mtime, mtime_str, item))
        
        if not deployment_dirs:
            print("No deployments found.")
            return 0
        
        # Sort by modification time (newest first)
        deployment_dirs.sort(key=lambda x: x[0], reverse=True)
        
        print(f"\nFound {len(deployment_dirs)} deployment(s):")
        print("-" * 80)
        print(f"{'Deployment ID':<40} {'Created':<20} {'Path'}")
        print("-" * 80)
        
        for mtime, mtime_str, deployment_dir in deployment_dirs:
            deployment_id = deployment_dir.name
            print(f"{deployment_id:<40} {mtime_str:<20} {deployment_dir}")
        
        return 0
        
    except Exception as e:
        print(f"✗ List failed: {e}")
        return 1


def main():
    """Main CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="Deploy Job Bundle CLI - Build and verify deterministic deployment bundles",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s build --job-id research_20240101_123456
  %(prog)s build --job-id portfolio_admission_abc123 --target staging --notes "Test deployment"
  %(prog)s verify --job-id research_20240101_123456
  %(prog)s list --job-id research_20240101_123456
        """
    )
    
    # Subcommands
    subparsers = parser.add_subparsers(dest="command", required=True, help="Command to execute")
    
    # Build command
    build_parser = subparsers.add_parser("build", help="Build deployment bundle for a job")
    build_parser.add_argument("--job-id", required=True, help="Job identifier")
    build_parser.add_argument("--target", default="production", help="Deployment target (production, staging, etc.)")
    build_parser.add_argument("--notes", default="", help="Deployment notes")
    build_parser.add_argument("--outputs-root", type=Path, default=get_outputs_root(), help="Root outputs directory")
    build_parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    
    # Verify command
    verify_parser = subparsers.add_parser("verify", help="Verify deployment bundle integrity")
    verify_parser.add_argument("--job-id", required=True, help="Job identifier")
    verify_parser.add_argument("--deployment-dir", type=Path, help="Path to deployment directory (auto-detects most recent if not specified)")
    verify_parser.add_argument("--outputs-root", type=Path, default=get_outputs_root(), help="Root outputs directory")
    verify_parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    
    # List command
    list_parser = subparsers.add_parser("list", help="List deployments for a job")
    list_parser.add_argument("--job-id", required=True, help="Job identifier")
    list_parser.add_argument("--outputs-root", type=Path, default=get_outputs_root(), help="Root outputs directory")
    list_parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(args.verbose)
    
    # Execute command
    if args.command == "build":
        return build_command(args)
    elif args.command == "verify":
        return verify_command(args)
    elif args.command == "list":
        return list_command(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())