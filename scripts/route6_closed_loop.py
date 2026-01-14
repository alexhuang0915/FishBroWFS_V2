#!/usr/bin/env python3
"""
Route 6 Closed Loop CLI - Unified interface for Evidence → Portfolio → Deployment.

Three terminating commands:
1. evidence-aggregate: Build evidence index from job artifacts
2. portfolio-orchestrate: Orchestrate portfolio admission from evidence
3. deployment-build: Build deployment bundle from portfolio admission results

Hybrid BC v1.1 compliant: No portfolio math changes, no backend API changes.
"""

from __future__ import annotations

import sys
import argparse
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Route 6 Closed Loop: Evidence → Portfolio → Deployment",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Build evidence index
  python scripts/route6_closed_loop.py evidence-aggregate build
  
  # Orchestrate portfolio admission
  python scripts/route6_closed_loop.py portfolio-orchestrate orchestrate --evidence-index outputs/portfolio/evidence_index_v1.json
  
  # Build deployment bundle
  python scripts/route6_closed_loop.py deployment-build build --portfolio-run-record outputs/portfolio/runs/<run_id>/portfolio_run_record_v1.json
  
  # Replay/audit full chain
  python scripts/route6_closed_loop.py replay audit --audit-type evidence --evidence-index outputs/portfolio/evidence_index_v1.json
        """
    )
    
    subparsers = parser.add_subparsers(
        dest="command",
        title="commands",
        description="Available commands",
        required=True,
    )
    
    # ----------------------------------------------------------------------
    # evidence-aggregate command
    # ----------------------------------------------------------------------
    evidence_parser = subparsers.add_parser(
        "evidence-aggregate",
        help="Build evidence index from job artifacts"
    )
    evidence_parser.add_argument(
        "subcommand",
        choices=["build", "validate"],
        help="Subcommand to execute"
    )
    evidence_parser.add_argument(
        "--include-warn",
        action="store_true",
        help="Include jobs with gate_status = WARN"
    )
    evidence_parser.add_argument(
        "--include-archived",
        action="store_true",
        help="Include archived jobs (in _trash)"
    )
    evidence_parser.add_argument(
        "--include-fail",
        action="store_true",
        help="Include jobs with gate_status = FAIL"
    )
    evidence_parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Output directory for evidence index"
    )
    evidence_parser.add_argument(
        "--jobs-root",
        type=Path,
        required=True,
        help="Root directory containing job directories"
    )
    
    # ----------------------------------------------------------------------
    # portfolio-orchestrate command
    # ----------------------------------------------------------------------
    portfolio_parser = subparsers.add_parser(
        "portfolio-orchestrate",
        help="Orchestrate portfolio admission from evidence"
    )
    portfolio_parser.add_argument(
        "subcommand",
        choices=["orchestrate", "monitor"],
        help="Subcommand to execute"
    )
    portfolio_parser.add_argument(
        "--evidence-index",
        type=Path,
        required=True,
        help="Path to evidence index JSON file"
    )
    portfolio_parser.add_argument(
        "--portfolio-id",
        type=str,
        help="Portfolio ID (generated if not provided)"
    )
    portfolio_parser.add_argument(
        "--strategy",
        type=str,
        choices=["top_performers", "diversified", "manual"],
        default="top_performers",
        help="Candidate selection strategy"
    )
    portfolio_parser.add_argument(
        "--max-candidates",
        type=int,
        default=5,
        help="Maximum number of candidates to select"
    )
    portfolio_parser.add_argument(
        "--min-candidates",
        type=int,
        default=2,
        help="Minimum number of candidates required"
    )
    portfolio_parser.add_argument(
        "--correlation-threshold",
        type=float,
        default=0.7,
        help="Correlation threshold for portfolio"
    )
    portfolio_parser.add_argument(
        "--include-warn",
        action="store_true",
        help="Include jobs with WARN gate status"
    )
    portfolio_parser.add_argument(
        "--manual-job-ids",
        type=str,
        help="Comma-separated list of manual job IDs (for manual strategy)"
    )
    portfolio_parser.add_argument(
        "--portfolio-run-id",
        type=str,
        help="Portfolio run ID (for monitor command)"
    )
    portfolio_parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=300,
        help="Timeout in seconds for monitoring (default: 300)"
    )
    portfolio_parser.add_argument(
        "--poll-interval",
        type=int,
        default=5,
        help="Poll interval in seconds for monitoring (default: 5)"
    )
    portfolio_parser.add_argument(
        "--outputs-root",
        type=Path,
        required=True,
        help="Root outputs directory"
    )
    
    # ----------------------------------------------------------------------
    # deployment-build command
    # ----------------------------------------------------------------------
    deployment_parser = subparsers.add_parser(
        "deployment-build",
        help="Build deployment bundle from portfolio admission results"
    )
    deployment_parser.add_argument(
        "subcommand",
        choices=["build", "verify"],
        help="Subcommand to execute"
    )
    deployment_parser.add_argument(
        "--portfolio-run-record",
        type=Path,
        required=True,
        help="Path to portfolio_run_record_v1.json"
    )
    deployment_parser.add_argument(
        "--deployment-target",
        type=str,
        default="production",
        help="Target environment (production, staging, etc.)"
    )
    deployment_parser.add_argument(
        "--deployment-notes",
        type=str,
        default="",
        help="Notes about this deployment"
    )
    deployment_parser.add_argument(
        "--include-strategy-artifacts",
        action="store_true",
        default=True,
        help="Include strategy artifacts (default: True)"
    )
    deployment_parser.add_argument(
        "--exclude-strategy-artifacts",
        action="store_true",
        help="Exclude strategy artifacts"
    )
    deployment_parser.add_argument(
        "--outputs-root",
        type=Path,
        required=True,
        help="Root outputs directory"
    )
    
    # ----------------------------------------------------------------------
    # replay command
    # ----------------------------------------------------------------------
    replay_parser = subparsers.add_parser(
        "replay",
        help="Replay and verify evidence → portfolio → deployment chain integrity"
    )
    replay_parser.add_argument(
        "subcommand",
        choices=["audit", "replay"],
        help="Subcommand to execute"
    )
    replay_parser.add_argument(
        "--evidence-index",
        type=Path,
        help="Path to evidence_index_v1.json"
    )
    replay_parser.add_argument(
        "--portfolio-run-record",
        type=Path,
        help="Path to portfolio_run_record_v1.json"
    )
    replay_parser.add_argument(
        "--deployment-manifest",
        type=Path,
        help="Path to deployment_manifest_v1.json"
    )
    replay_parser.add_argument(
        "--audit-type",
        type=str,
        choices=["evidence", "portfolio", "deployment"],
        help="Type of audit to perform (for audit command)"
    )
    replay_parser.add_argument(
        "--outputs-root",
        type=Path,
        required=True,
        help="Root outputs directory"
    )
    
    args = parser.parse_args()
    
    # Execute the appropriate command
    if args.command == "evidence-aggregate":
        from src.core.portfolio.evidence_aggregator import main_cli as evidence_main
        
        # Build sys.argv for the evidence aggregator
        sys.argv = [
            "evidence_aggregator.py",
            args.subcommand,
            "--include-warn" if args.include_warn else "",
            "--include-archived" if args.include_archived else "",
            "--include-fail" if args.include_fail else "",
            "--output-dir",
            str(args.output_dir),
            "--jobs-root",
            str(args.jobs_root),
        ]
        # Remove empty strings
        sys.argv = [arg for arg in sys.argv if arg]
        
        return evidence_main()
    
    elif args.command == "portfolio-orchestrate":
        from src.core.portfolio.portfolio_orchestrator import main_cli as portfolio_main
        
        # Build sys.argv for the portfolio orchestrator
        sys.argv = [
            "portfolio_orchestrator.py",
            args.subcommand,
            "--evidence-index",
            str(args.evidence_index),
            "--portfolio-id" if args.portfolio_id else "",
            args.portfolio_id if args.portfolio_id else "",
            "--strategy",
            args.strategy,
            "--max-candidates",
            str(args.max_candidates),
            "--min-candidates",
            str(args.min_candidates),
            "--correlation-threshold",
            str(args.correlation_threshold),
            "--include-warn" if args.include_warn else "",
            "--manual-job-ids" if args.manual_job_ids else "",
            args.manual_job_ids if args.manual_job_ids else "",
            "--portfolio-run-id" if args.portfolio_run_id else "",
            args.portfolio_run_id if args.portfolio_run_id else "",
            "--timeout-seconds" if args.subcommand == "monitor" else "",
            str(args.timeout_seconds) if args.subcommand == "monitor" else "",
            "--poll-interval" if args.subcommand == "monitor" else "",
            str(args.poll_interval) if args.subcommand == "monitor" else "",
            "--outputs-root",
            str(args.outputs_root),
        ]
        # Remove empty strings
        sys.argv = [arg for arg in sys.argv if arg]
        
        return portfolio_main()
    
    elif args.command == "deployment-build":
        from src.core.deployment.deployment_bundle_builder import main_cli as deployment_main
        
        # Build sys.argv for the deployment bundle builder
        sys.argv = [
            "deployment_bundle_builder.py",
            args.subcommand,
            "--portfolio-run-record",
            str(args.portfolio_run_record),
            "--deployment-target",
            args.deployment_target,
            "--deployment-notes",
            args.deployment_notes,
            "--include-strategy-artifacts" if args.include_strategy_artifacts else "",
            "--exclude-strategy-artifacts" if args.exclude_strategy_artifacts else "",
            "--outputs-root",
            str(args.outputs_root),
        ]
        # Remove empty strings
        sys.argv = [arg for arg in sys.argv if arg]
        
        return deployment_main()
    
    elif args.command == "replay":
        from src.core.deployment.replay_resolver import main_cli as replay_main
        
        # Build sys.argv for the replay resolver
        sys.argv = [
            "replay_resolver.py",
            args.subcommand,
            "--evidence-index" if args.evidence_index else "",
            str(args.evidence_index) if args.evidence_index else "",
            "--portfolio-run-record" if args.portfolio_run_record else "",
            str(args.portfolio_run_record) if args.portfolio_run_record else "",
            "--deployment-manifest" if args.deployment_manifest else "",
            str(args.deployment_manifest) if args.deployment_manifest else "",
            "--audit-type" if args.audit_type else "",
            args.audit_type if args.audit_type else "",
            "--outputs-root",
            str(args.outputs_root),
        ]
        # Remove empty strings
        sys.argv = [arg for arg in sys.argv if arg]
        
        return replay_main()
    
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())