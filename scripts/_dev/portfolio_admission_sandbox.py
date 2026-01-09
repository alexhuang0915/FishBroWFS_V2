#!/usr/bin/env python3
"""
Portfolio Admission Sandbox MVP (Phase4-B.1)

Standalone UI sandbox to demonstrate Phase4-B.1 analytics:
- Correlation analysis on daily returns (vs equity series)
- Portfolio stacking with integer lots allocation
- Budget alerts from rolling MDD (3M ≤ 12%, 6M ≤ 18%, full ≤ 25%)
- Marginal contribution analysis with noise buffer (ΔSharpe analysis)
- Money-sense MDD amount display (percentage + absolute currency)

This script can be run standalone to visualize admission results.
"""

import json
import sys
import os
from pathlib import Path
from typing import Dict, Any, List, Optional
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def load_admission_report(portfolio_id: str) -> Optional[Dict[str, Any]]:
    """Load admission report for a portfolio."""
    admission_dir = project_root / "outputs" / "portfolios" / portfolio_id / "admission"
    
    # Try to load admission_report.json v1.0
    report_path = admission_dir / "admission_report.json"
    if report_path.exists():
        with open(report_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    # Fallback to legacy admission_decision.json
    decision_path = admission_dir / "admission_decision.json"
    if decision_path.exists():
        with open(decision_path, 'r', encoding='utf-8') as f:
            decision = json.load(f)
        
        # Create minimal report from decision
        return {
            "version": "1.0",
            "portfolio_id": portfolio_id,
            "generated_at": datetime.now().isoformat(),
            "decision": decision,
            "analytics": {
                "note": "Legacy decision format - Phase4-B.1 analytics not available"
            }
        }
    
    return None

def display_correlation_analysis(report: Dict[str, Any]):
    """Display correlation analysis results."""
    analytics = report.get("analytics", {})
    correlation = analytics.get("correlation_analysis", {})
    
    print("\n" + "="*80)
    print("CORRELATION ANALYSIS (Daily Returns)")
    print("="*80)
    
    if not correlation:
        print("No correlation analysis data available")
        return
    
    # Basic stats
    method = correlation.get("method", "unknown")
    warning_threshold = correlation.get("warning_threshold", 0.7)
    reject_threshold = correlation.get("reject_threshold", 0.85)
    
    print(f"Method: {method}")
    print(f"Warning threshold: {warning_threshold:.3f}")
    print(f"Reject threshold: {reject_threshold:.3f}")
    
    # Violations
    violations = correlation.get("violations", [])
    warnings = correlation.get("warnings", [])
    
    if violations:
        print(f"\n❌ Correlation Violations ({len(violations)} pairs):")
        for v in violations[:5]:  # Show first 5
            print(f"  {v.get('pair', '?')}: {v.get('correlation', 0):.3f}")
        if len(violations) > 5:
            print(f"  ... and {len(violations) - 5} more")
    else:
        print("\n✅ No correlation violations")
    
    if warnings:
        print(f"\n⚠️  Correlation Warnings ({len(warnings)} pairs):")
        for w in warnings[:5]:
            print(f"  {w.get('pair', '?')}: {w.get('correlation', 0):.3f}")
        if len(warnings) > 5:
            print(f"  ... and {len(warnings) - 5} more")
    else:
        print("\n✅ No correlation warnings")

def display_portfolio_stacking(report: Dict[str, Any]):
    """Display portfolio stacking results."""
    analytics = report.get("analytics", {})
    stacking = analytics.get("portfolio_stacking", {})
    
    print("\n" + "="*80)
    print("PORTFOLIO STACKING (Integer Lots Allocation)")
    print("="*80)
    
    if not stacking:
        print("No portfolio stacking data available")
        return
    
    # Allocation details
    total_capital = stacking.get("total_capital", 0)
    risk_budget = stacking.get("risk_budget", 0)
    risk_used = stacking.get("risk_used", 0)
    
    print(f"Total Capital: ${total_capital:,.2f}")
    print(f"Risk Budget: {risk_budget:.1%}")
    print(f"Risk Used: {risk_used:.1%} ({risk_used/risk_budget*100:.1f}% of budget)")
    
    # Allocated strategies
    allocations = stacking.get("allocations", [])
    if allocations:
        print(f"\nAllocated Strategies ({len(allocations)}):")
        print("-" * 60)
        print(f"{'Strategy':<20} {'Lots':<10} {'Weight':<10} {'Risk':<10} {'Capital':<10}")
        print("-" * 60)
        
        for alloc in allocations:
            strategy = alloc.get("strategy_id", "unknown")
            lots = alloc.get("lots", 0)
            weight = alloc.get("weight", 0)
            risk = alloc.get("risk_contribution", 0)
            capital = alloc.get("capital_allocation", 0)
            
            print(f"{strategy:<20} {lots:<10} {weight:<10.3f} {risk:<10.3f} ${capital:<10,.0f}")
    else:
        print("\nNo strategies allocated")

def display_budget_alerts(report: Dict[str, Any]):
    """Display budget alerts from rolling MDD."""
    analytics = report.get("analytics", {})
    budget_alerts = analytics.get("budget_alerts", {})
    
    print("\n" + "="*80)
    print("BUDGET ALERTS (Rolling MDD)")
    print("="*80)
    
    if not budget_alerts:
        print("No budget alerts data available")
        return
    
    # Alert thresholds
    thresholds = budget_alerts.get("thresholds", {})
    print(f"Thresholds: 3M ≤ {thresholds.get('3m', 12)}%, "
          f"6M ≤ {thresholds.get('6m', 18)}%, "
          f"Full ≤ {thresholds.get('full', 25)}%")
    
    # Actual MDD values
    mdd_values = budget_alerts.get("mdd_values", {})
    alerts = budget_alerts.get("alerts", [])
    
    print(f"\nRolling MDD Values:")
    for period, value in mdd_values.items():
        print(f"  {period}: {value:.1f}%")
    
    if alerts:
        print(f"\n🚨 BUDGET ALERTS ({len(alerts)}):")
        for alert in alerts:
            period = alert.get("period", "unknown")
            mdd = alert.get("mdd_pct", 0)
            threshold = alert.get("threshold_pct", 0)
            print(f"  ❌ {period}: {mdd:.1f}% > {threshold:.1f}% threshold")
    else:
        print("\n✅ All rolling MDD within budget limits")

def display_marginal_contribution(report: Dict[str, Any]):
    """Display marginal contribution analysis."""
    analytics = report.get("analytics", {})
    marginal = analytics.get("marginal_contribution", {})
    
    print("\n" + "="*80)
    print("MARGINAL CONTRIBUTION ANALYSIS (ΔSharpe)")
    print("="*80)
    
    if not marginal:
        print("No marginal contribution data available")
        return
    
    noise_buffer = marginal.get("noise_buffer", 0.05)
    print(f"Noise buffer: |ΔSharpe| < {noise_buffer:.3f} => NO_SIGNAL")
    
    contributions = marginal.get("contributions", [])
    if contributions:
        print(f"\nMarginal Contributions ({len(contributions)} strategies):")
        print("-" * 70)
        print(f"{'Strategy':<20} {'ΔSharpe':<12} {'Signal':<15} {'Interpretation':<25}")
        print("-" * 70)
        
        for contrib in contributions:
            strategy = contrib.get("strategy_id", "unknown")
            delta_sharpe = contrib.get("delta_sharpe", 0)
            signal = contrib.get("signal", "UNKNOWN")
            interpretation = contrib.get("interpretation", "")
            
            # Color coding
            if signal == "POSITIVE":
                signal_display = "✅ POSITIVE"
            elif signal == "NEGATIVE":
                signal_display = "❌ NEGATIVE"
            elif signal == "NO_SIGNAL":
                signal_display = "⚪ NO_SIGNAL"
            else:
                signal_display = signal
            
            print(f"{strategy:<20} {delta_sharpe:<12.3f} {signal_display:<15} {interpretation:<25}")
    else:
        print("\nNo marginal contribution data")

def display_money_sense_mdd(report: Dict[str, Any]):
    """Display money-sense MDD amounts."""
    analytics = report.get("analytics", {})
    money_mdd = analytics.get("money_sense_mdd", {})
    
    print("\n" + "="*80)
    print("MONEY-SENSE MDD (Dual Representation)")
    print("="*80)
    
    if not money_mdd:
        print("No money-sense MDD data available")
        return
    
    # MDD values
    mdd_pct = money_mdd.get("mdd_pct", 0)
    mdd_abs = money_mdd.get("mdd_abs", 0)
    currency = money_mdd.get("currency", "USD")
    total_capital = money_mdd.get("total_capital", 0)
    
    print(f"Total Capital: ${total_capital:,.2f} {currency}")
    print(f"\nMaximum Drawdown:")
    print(f"  Percentage: {mdd_pct:.1f}%")
    print(f"  Absolute: ${mdd_abs:,.2f} {currency}")
    
    # Context
    if mdd_abs > 0:
        print(f"\nContext:")
        print(f"  • Equivalent to {mdd_abs/1000:.1f} thousand {currency}")
        print(f"  • Represents {mdd_pct:.1f}% of portfolio value")
        print(f"  • Risk per $10k invested: ${mdd_pct*100:,.0f}")

def plot_correlation_matrix(report: Dict[str, Any], save_path: Optional[Path] = None):
    """Plot correlation matrix if data available."""
    analytics = report.get("analytics", {})
    correlation = analytics.get("correlation_analysis", {})
    
    if not correlation:
        return
    
    matrix = correlation.get("matrix")
    labels = correlation.get("labels")
    
    if not matrix or not labels:
        return
    
    try:
        import matplotlib.pyplot as plt
        import numpy as np
        
        fig, ax = plt.subplots(figsize=(10, 8))
        
        # Create heatmap
        im = ax.imshow(matrix, cmap='RdYlBu_r', vmin=-1, vmax=1)
        
        # Add colorbar
        cbar = ax.figure.colorbar(im, ax=ax)
        cbar.ax.set_ylabel('Correlation', rotation=-90, va="bottom")
        
        # Set labels
        ax.set_xticks(np.arange(len(labels)))
        ax.set_yticks(np.arange(len(labels)))
        ax.set_xticklabels(labels, rotation=45, ha='right')
        ax.set_yticklabels(labels)
        
        # Add correlation values
        for i in range(len(labels)):
            for j in range(len(labels)):
                text = ax.text(j, i, f'{matrix[i][j]:.2f}',
                              ha="center", va="center", 
                              color="black" if abs(matrix[i][j]) < 0.5 else "white",
                              fontsize=8)
        
        ax.set_title("Correlation Matrix (Daily Returns)")
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=150)
            print(f"\n📊 Correlation matrix saved to: {save_path}")
        else:
            plt.show()
            
        plt.close()
    except Exception as e:
        print(f"Warning: Could not plot correlation matrix: {e}")

def main():
    """Main entry point."""
    print("="*80)
    print("PORTFOLIO ADMISSION SANDBOX MVP (Phase4-B.1)")
    print("="*80)
    
    # Get portfolio ID from command line or use default
    if len(sys.argv) > 1:
        portfolio_id = sys.argv[1]
    else:
        # Try to find the most recent portfolio
        portfolios_dir = project_root / "outputs" / "portfolios"
        if portfolios_dir.exists():
            portfolio_dirs = [d for d in portfolios_dir.iterdir() if d.is_dir()]
            if portfolio_dirs:
                # Sort by modification time
                portfolio_dirs.sort(key=lambda d: d.stat().st_mtime, reverse=True)
                portfolio_id = portfolio_dirs[0].name
                print(f"Using most recent portfolio: {portfolio_id}")
            else:
                print("No portfolios found in outputs/portfolios/")
                print("Please run a portfolio admission job first.")
                return
        else:
            print("Portfolios directory not found: outputs/portfolios/")
            print("Please run a portfolio admission job first.")
            return
    
    # Load admission report
    report = load_admission_report(portfolio_id)
    if not report:
        print(f"\n❌ No admission report found for portfolio: {portfolio_id}")
        print(f"Expected path: outputs/portfolios/{portfolio_id}/admission/admission_report.json")
        return
    
    print(f"\n📊 Portfolio ID: {portfolio_id}")
    print(f"Report version: {report.get('version', 'unknown')}")
    print(f"Generated at: {report.get('generated_at', 'unknown')}")
    
    # Display all analytics
    display_correlation_analysis(report)
    display_portfolio_stacking(report)
    display_budget_alerts(report)
    display_marginal_contribution(report)
    display_money_sense_mdd(report)
    
    # Plot correlation matrix
    output_dir = project_root / "outputs" / "_dp_evidence"
    output_dir.mkdir(parents=True, exist_ok=True)
    plot_path = output_dir / f"phase4b1_correlation_matrix_{portfolio_id}.png"
    plot_correlation_matrix(report, plot_path)
    
    # Summary
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    
    decision = report.get("decision", {})
    verdict = decision.get("verdict", "UNKNOWN")
    
    if verdict == "ADMITTED":
        print("✅ PORTFOLIO ADMITTED")
        admitted = decision.get("admitted_run_ids", [])
        print(f"Admitted strategies: {len(admitted)}")
    else:
        print("❌ PORTFOLIO REJECTED")
        rejected = decision.get("rejected_run_ids", [])
        print(f"Rejected strategies: {len(rejected)}")
    
    print(f"\nEvidence saved to: outputs/_dp_evidence/")
    print("To view in GUI, run the desktop application.")

if __name__ == "__main__":
    main()