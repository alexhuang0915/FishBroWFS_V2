#!/usr/bin/env python3
"""
Analyze strategy usage and generate governance report (KEEP/KILL/FREEZE).

This script analyzes strategy usage across:
- Research logs (outputs/research/)
- Test results (tests/strategy/)
- Configuration files (configs/strategies/)
- Documentation (docs/strategies/)

Generates governance decisions and saves reports to outputs/strategy_governance/
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from control.strategy_rotation import StrategyGovernance, DecisionStatus
from strategy.registry import load_builtin_strategies


def ensure_builtin_strategies_loaded() -> None:
    """Ensure built-in strategies are loaded."""
    try:
        load_builtin_strategies()
    except ValueError as e:
        if "already registered" not in str(e):
            raise


def main() -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Analyze strategy usage and generate governance report",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("outputs") / "strategy_governance",
        help="Directory to save governance reports",
    )
    
    parser.add_argument(
        "--save-decisions",
        action="store_true",
        default=True,
        help="Save decisions to JSON file",
    )
    
    parser.add_argument(
        "--no-save-decisions",
        action="store_false",
        dest="save_decisions",
        help="Do not save decisions",
    )
    
    parser.add_argument(
        "--save-report",
        action="store_true",
        default=True,
        help="Save comprehensive report to JSON file",
    )
    
    parser.add_argument(
        "--no-save-report",
        action="store_false",
        dest="save_report",
        help="Do not save report",
    )
    
    parser.add_argument(
        "--print-summary",
        action="store_true",
        default=True,
        help="Print summary to console",
    )
    
    parser.add_argument(
        "--no-print-summary",
        action="store_false",
        dest="print_summary",
        help="Do not print summary",
    )
    
    parser.add_argument(
        "--json-output",
        action="store_true",
        help="Output decisions in JSON format",
    )
    
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print verbose analysis details",
    )
    
    args = parser.parse_args()
    
    try:
        return run_analysis(args)
    except KeyboardInterrupt:
        print("\nAnalysis interrupted", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


def run_analysis(args) -> int:
    """Run strategy usage analysis."""
    print("🔍 Analyzing strategy usage...")
    
    # Ensure built-in strategies are loaded
    ensure_builtin_strategies_loaded()
    
    # Create governance manager
    governance = StrategyGovernance(outputs_root=args.output_dir)
    
    # Analyze usage
    print("  Analyzing research logs...")
    print("  Analyzing test results...")
    print("  Analyzing configuration files...")
    
    metrics = governance.analyze_usage()
    
    if args.verbose:
        print("\n📊 Usage Metrics:")
        for strategy_id, metric in metrics.items():
            print(f"  {strategy_id}:")
            print(f"    Last used: {metric.last_used}")
            print(f"    Days since last use: {metric.days_since_last_use}")
            print(f"    Research usage count: {metric.research_usage_count}")
            print(f"    Test passing: {metric.test_passing}")
            print(f"    Config exists: {metric.config_exists}")
            print(f"    Documentation exists: {metric.documentation_exists}")
    
    # Make decisions
    print("  Making governance decisions...")
    decisions = governance.make_decisions()
    
    # Save decisions if requested
    decisions_path = None
    if args.save_decisions:
        decisions_path = governance.save_decisions()
        print(f"  Decisions saved to: {decisions_path}")
    
    # Save report if requested
    report_path = None
    if args.save_report:
        report_path = governance.save_report()
        print(f"  Report saved to: {report_path}")
    
    # Print summary
    if args.print_summary:
        print_summary(decisions, metrics, args.verbose)
    
    # JSON output if requested
    if args.json_output:
        output_json(decisions, metrics)
    
    # Print file paths
    if decisions_path:
        print(f"\n📁 Decisions file: {decisions_path}")
    if report_path:
        print(f"📁 Report file: {report_path}")
    
    print("\n✅ Analysis complete")
    
    # Return non-zero exit code if there are KILL decisions (needs attention)
    kill_count = sum(1 for d in decisions if d.status == DecisionStatus.KILL)
    if kill_count > 0:
        print(f"⚠️  Warning: {kill_count} strategies marked for KILL (needs attention)")
        return 10
    return 0


def print_summary(decisions, metrics, verbose: bool = False) -> None:
    """Print analysis summary to console."""
    from collections import Counter
    
    # Count decisions by status
    status_counts = Counter(d.status for d in decisions)
    
    print("\n📈 Governance Summary:")
    print(f"  Total strategies: {len(decisions)}")
    print(f"  KEEP: {status_counts.get('KEEP', 0)}")
    print(f"  KILL: {status_counts.get('KILL', 0)}")
    print(f"  FREEZE: {status_counts.get('FREEZE', 0)}")
    
    # Print strategies by status
    print("\n📋 Strategies by Status:")
    
    # KEEP strategies
    keep_strategies = [d for d in decisions if d.status == DecisionStatus.KEEP]
    if keep_strategies:
        print(f"  KEEP ({len(keep_strategies)}):")
        for decision in sorted(keep_strategies, key=lambda d: d.strategy_id):
            metric = metrics.get(decision.strategy_id)
            days_info = f" (used {metric.days_since_last_use}d ago)" if metric and metric.days_since_last_use else ""
            print(f"    • {decision.strategy_id}{days_info}")
    
    # FREEZE strategies
    freeze_strategies = [d for d in decisions if d.status == DecisionStatus.FREEZE]
    if freeze_strategies:
        print(f"  FREEZE ({len(freeze_strategies)}):")
        for decision in sorted(freeze_strategies, key=lambda d: d.strategy_id):
            print(f"    • {decision.strategy_id}: {decision.reason}")
    
    # KILL strategies
    kill_strategies = [d for d in decisions if d.status == DecisionStatus.KILL]
    if kill_strategies:
        print(f"  KILL ({len(kill_strategies)}):")
        for decision in sorted(kill_strategies, key=lambda d: d.strategy_id):
            print(f"    • {decision.strategy_id}: {decision.reason}")
    
    # Recommendations
    print("\n💡 Recommendations:")
    if kill_strategies:
        print(f"  • Review {len(kill_strategies)} KILL strategies for potential removal")
    if freeze_strategies:
        print(f"  • Evaluate {len(freeze_strategies)} FREEZE strategies for promotion or removal")
    if keep_strategies:
        print(f"  • Maintain {len(keep_strategies)} KEEP strategies with regular monitoring")
    
    # Detailed metrics if verbose
    if verbose:
        print("\n📊 Detailed Metrics:")
        unused_count = sum(1 for m in metrics.values() if m.research_usage_count == 0)
        failing_tests = sum(1 for m in metrics.values() if not m.test_passing)
        no_config = sum(1 for m in metrics.values() if not m.config_exists)
        no_docs = sum(1 for m in metrics.values() if not m.documentation_exists)
        
        print(f"  Unused strategies (0 research runs): {unused_count}")
        print(f"  Strategies with failing tests: {failing_tests}")
        print(f"  Strategies without configuration: {no_config}")
        print(f"  Strategies without documentation: {no_docs}")


def output_json(decisions, metrics) -> None:
    """Output decisions and metrics in JSON format."""
    output = {
        "timestamp": datetime.now().isoformat(),
        "decisions": [d.to_dict() for d in decisions],
        "metrics": {k: v.to_dict() for k, v in metrics.items()},
        "summary": {
            "total": len(decisions),
            "keep": sum(1 for d in decisions if d.status == DecisionStatus.KEEP),
            "kill": sum(1 for d in decisions if d.status == DecisionStatus.KILL),
            "freeze": sum(1 for d in decisions if d.status == DecisionStatus.FREEZE),
        }
    }
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    sys.exit(main())