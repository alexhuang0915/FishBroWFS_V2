#!/usr/bin/env python3
"""
Red-Team Hardened WFS Integration Example

Demonstrates the complete Red-Team Hardened WFS implementation:
1. Scoring Guards (Anti-Gaming)
2. TSR Calibration for Mode B
3. Mode B Pipeline
4. Governance Triggers
5. Artifact Bundle Creation
6. Integration with existing WFS evaluation

This example shows how to use the new components in a realistic scenario.
"""

import sys
import os
import json
from pathlib import Path
from typing import Dict, Any

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from wfs import (
    # Enhanced Evaluation
    EnhancedRawMetrics,
    evaluate_enhanced,
    evaluate_with_mode_b,
    create_test_enhanced_raw_metrics,
    
    # Scoring Guards
    ScoringGuardConfig,
    apply_scoring_guards,
    DEFAULT_CONFIG as DEFAULT_SCORING_CONFIG,
    
    # TSR Calibration
    CalibrationMethod,
    TSRCalibrationConfig,
    calibrate_anchor_params,
    select_mode_b_anchors,
    create_mode_b_structure_filter,
    DEFAULT_CALIBRATION_CONFIG,
    
    # Mode B Pipeline
    ModeBConfig,
    create_mode_b_pipeline,
    
    # Governance Triggers
    load_policy_from_yaml,
    enforce_governance,
    create_delta_report,
    
    # Red-Team Integration
    RedTeamConfig,
    create_red_team_wfs,
    
    # Base Evaluation (for comparison)
    evaluate as base_evaluate
)


def example_scoring_guards():
    """Example 1: Applying scoring guards to raw metrics."""
    print("=" * 60)
    print("EXAMPLE 1: Scoring Guards (Anti-Gaming)")
    print("=" * 60)
    
    # Create test metrics
    raw_metrics = {
        'net_profit': 5000.0,
        'max_dd': 1000.0,
        'trades': 80,
        'avg_profit': 62.5,  # $62.5 average profit per trade
        'trades_oat': 75  # Trades in OAT neighborhood
    }
    
    # Apply scoring guards with default config
    scoring_result = apply_scoring_guards(raw_metrics, DEFAULT_SCORING_CONFIG)
    
    print(f"Raw metrics:")
    print(f"  Net profit: ${raw_metrics['net_profit']:.2f}")
    print(f"  Max DD: ${raw_metrics['max_dd']:.2f}")
    print(f"  Trades: {raw_metrics['trades']}")
    print(f"  Avg profit: ${raw_metrics['avg_profit']:.2f}")
    
    print(f"\nScoring guard results:")
    print(f"  Trade multiplier: {scoring_result['trade_multiplier']:.2f}")
    print(f"  Net/MDD ratio: {scoring_result['net_mdd_ratio']:.2f}")
    print(f"  Final score: {scoring_result['final_score']:.2f}")
    print(f"  Edge gate passed: {scoring_result['edge_gate_passed']}")
    print(f"  Cliff gate passed: {scoring_result['cliff_gate_passed']}")
    print(f"  Bimodality detected: {scoring_result.get('bimodality_detected', False)}")
    
    return scoring_result


def example_tsr_calibration():
    """Example 2: TSR Calibration for Mode B anchors."""
    print("\n" + "=" * 60)
    print("EXAMPLE 2: TSR Calibration (Mode B Anchors)")
    print("=" * 60)
    
    # Create calibration config
    calibration_config = TSRCalibrationConfig(
        method=CalibrationMethod.LOGARITHMIC,
        tsr_min=0.01,  # 1% minimum signal rate
        tsr_max=0.20,  # 20% maximum signal rate
        anchor_tolerance=0.05  # 5% tolerance
    )
    
    # Create test parameter values and actual signal rates
    # In a real scenario, these would come from backtesting
    param_values = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0]
    actual_signal_rates = [0.18, 0.15, 0.12, 0.09, 0.07, 0.05, 0.04, 0.03]
    
    # Calibrate anchors
    anchors = calibrate_anchor_params(
        param_values,
        actual_signal_rates,
        calibration_config
    )
    
    print(f"Calibrated {len(anchors)} anchors for parameter 'entry_threshold':")
    for i, anchor in enumerate(anchors[:5]):  # Show first 5
        print(f"  Anchor {i+1}: param={anchor.param_value:.3f}, "
              f"target={anchor.target_tsr:.3f}, "
              f"actual={anchor.calibrated_tsr:.3f} "
              f"[{'✓' if anchor.is_valid else '✗'}]")
    
    if len(anchors) > 5:
        print(f"  ... and {len(anchors) - 5} more anchors")
    
    valid_anchors = [a for a in anchors if a.is_valid]
    print(f"\nValid anchors: {len(valid_anchors)}/{len(anchors)}")
    
    # Select anchors for Mode B
    selected_anchors, rejected_anchors = select_mode_b_anchors(anchors, min_valid_anchors=3)
    
    if selected_anchors:
        print(f"\nSelected {len(selected_anchors)} anchors for Mode B:")
        for i, anchor in enumerate(selected_anchors):
            print(f"  {i+1}. param={anchor.param_value:.3f}, TSR={anchor.target_tsr:.3f}")
        
        # Create Mode B structure filter
        filter_config = create_mode_b_structure_filter(selected_anchors, "entry_threshold")
        print(f"\nMode B structure filter created:")
        print(f"  Enabled: {filter_config['mode_b_enabled']}")
        print(f"  Anchor count: {filter_config['anchor_count']}")
        print(f"  Parameter range: {filter_config['param_range']}")
    
    return anchors


def example_mode_b_pipeline():
    """Example 3: Mode B Pipeline with anchor-based parameter optimization."""
    print("\n" + "=" * 60)
    print("EXAMPLE 3: Mode B Pipeline")
    print("=" * 60)
    
    # Create Mode B pipeline configuration
    entry_param_name = "entry_threshold"  # Parameter to anchor
    
    exit_param_names = ["exit_window", "exit_threshold", "trail_atr_mult"]
    
    exit_param_ranges = {
        "exit_window": (5, 30, 5),  # (min, max, step)
        "exit_threshold": (0.5, 2.0, 0.5),
        "trail_atr_mult": (1.0, 3.0, 0.5)
    }
    
    # Create pipeline
    pipeline = create_mode_b_pipeline(
        entry_param_name=entry_param_name,
        exit_param_names=exit_param_names,
        exit_param_ranges=exit_param_ranges,
        scoring_config=ScoringGuardConfig(mode_b_enabled=True),
        calibration_config=TSRCalibrationConfig(
            method=CalibrationMethod.LOGARITHMIC,
            tsr_min=0.01,
            tsr_max=0.20
        )
    )
    
    print(f"Mode B Pipeline created:")
    print(f"  Entry parameter to anchor: {entry_param_name}")
    print(f"  Exit parameters to sweep: {exit_param_names}")
    print(f"  Scoring guards enabled: Yes")
    print(f"  TSR calibration enabled: Yes")
    
    # Note: In a real implementation, we would run the pipeline with actual evaluation
    print("\nNote: Pipeline execution requires actual backtest evaluation function.")
    print("      See test_red_team_implementation.py for a complete example.")
    
    return pipeline


def example_governance_triggers():
    """Example 4: Governance trigger enforcement."""
    print("\n" + "=" * 60)
    print("EXAMPLE 4: Governance Triggers")
    print("=" * 60)
    
    # Load policy from YAML
    policy_path = Path(__file__).parent.parent / "configs" / "strategies" / "wfs" / "red_team_policy.yaml"
    
    if policy_path.exists():
        policy = load_policy_from_yaml(str(policy_path))
        print(f"Loaded governance policy")
        print(f"  Mode B required: {policy.require_mode_b}")
        print(f"  Scoring guards required: {policy.require_scoring_guards}")
        print(f"  Min avg profit: ${policy.min_avg_profit}")
        
        # Create test check data
        check_data = {
            "mode_b": {
                "anchors": [1, 2, 3, 4],
                "anchor_errors": [0.01, 0.02, 0.03, 0.04]
            },
            "scoring": {
                "avg_profit": 8.5,
                "trades": 75
            },
            "cluster": {
                "bimodality_score": 0.15
            },
            "params": {
                "entry_threshold": 1.5,
                "exit_window": 20
            }
        }
        
        # Enforce governance
        passed, enforcement_report = enforce_governance(policy, check_data)
        
        print(f"\nGovernance enforcement report:")
        print(f"  Compliance passed: {passed}")
        print(f"  Violations: {len(enforcement_report['violations'])}")
        print(f"  Warnings: {len(enforcement_report['warnings'])}")
        
        if enforcement_report['violations']:
            for violation in enforcement_report['violations']:
                print(f"    - {violation}")
        else:
            print(f"  All governance checks passed ✓")
        
        # Create delta report (comparing with baseline)
        baseline = {"score": 35.0, "trades": 50}
        current = {"score": 42.5, "trades": 80}
        
        delta_report = create_delta_report(baseline, current)
        print(f"\nDelta report:")
        print(f"  Hashes match: {delta_report['hashes_match']}")
        print(f"  Total changes: {delta_report['summary']['total_changes']}")
        print(f"  Added: {delta_report['summary']['added']}, "
              f"Removed: {delta_report['summary']['removed']}, "
              f"Modified: {delta_report['summary']['modified']}")
        
        return enforcement_report, delta_report
    else:
        print(f"Policy file not found at {policy_path}")
        print("Creating sample policy for demonstration...")
        
        # Create a simple policy object
        from wfs.governance_triggers import GovernancePolicy
        sample_policy = GovernancePolicy(
            require_scoring_guards=True,
            min_avg_profit=5.0,
            require_cluster_test=True,
            max_bimodality_score=0.3
        )
        
        print(f"Sample policy created with:")
        print(f"  Scoring guards required: {sample_policy.require_scoring_guards}")
        print(f"  Min avg profit: ${sample_policy.min_avg_profit}")
        
        return None, None


def example_enhanced_evaluation():
    """Example 5: Enhanced evaluation with scoring guards."""
    print("\n" + "=" * 60)
    print("EXAMPLE 5: Enhanced WFS Evaluation")
    print("=" * 60)
    
    # Create enhanced raw metrics
    enhanced_raw = create_test_enhanced_raw_metrics(
        rf=2.5,  # Return Factor
        wfe=0.75,  # Walk-Forward Efficiency
        ecr=2.8,  # Efficiency to Capital Ratio
        trades=120,
        pass_rate=0.85,
        ulcer_index=8.0,
        max_underwater_days=15,
        net_profit=7500.0,
        max_dd=1200.0,
        avg_profit=62.5,
        trades_oat=110
    )
    
    # Run base evaluation (original 5D scoring)
    base_result = base_evaluate(enhanced_raw)
    
    # Run enhanced evaluation (with scoring guards)
    enhanced_result = evaluate_enhanced(enhanced_raw)
    
    print(f"Base evaluation (5D scoring):")
    print(f"  Grade: {base_result.grade}")
    print(f"  Total weighted score: {base_result.scores['total_weighted']:.2f}")
    print(f"  Tradable: {base_result.is_tradable}")
    
    print(f"\nEnhanced evaluation (with scoring guards):")
    print(f"  Grade: {enhanced_result.grade}")
    print(f"  Total weighted score: {enhanced_result.scores['total_weighted']:.2f}")
    print(f"  Tradable: {enhanced_result.is_tradable}")
    
    if enhanced_result.scoring_guard_result:
        print(f"  Scoring guard final score: {enhanced_result.final_score_guarded:.2f}")
        print(f"  Edge gate passed: {enhanced_result.edge_gate_passed}")
        print(f"  Summary: {enhanced_result.summary}")
    
    return base_result, enhanced_result


def example_red_team_integration():
    """Example 6: Complete Red-Team integration."""
    print("\n" + "=" * 60)
    print("EXAMPLE 6: Complete Red-Team Integration")
    print("=" * 60)
    
    # Create Red-Team WFS instance
    red_team = create_red_team_wfs(
        enable_scoring_guards=True,
        enable_mode_b=False,  # Disable Mode B for this example
        enable_governance=True
    )
    
    # Test metrics
    test_metrics = {
        "net_profit": 4200.0,
        "max_dd": 850.0,
        "trades": 65,
        "avg_profit": 64.6,
        "trades_oat": 60
    }
    
    # Apply scoring guards
    scoring_result = red_team.apply_scoring_guards(test_metrics, "example_strategy")
    
    print(f"Red-Team WFS instance created:")
    print(f"  Scoring guards enabled: {red_team.config.enable_scoring_guards}")
    print(f"  Mode B enabled: {red_team.config.enable_mode_b}")
    print(f"  Governance enabled: {red_team.config.enable_governance}")
    
    print(f"\nApplied scoring guards to example strategy:")
    print(f"  Final score: {scoring_result['final_score']:.2f}")
    print(f"  Edge gate: {'PASS' if scoring_result['edge_gate_passed'] else 'FAIL'}")
    
    # Test governance enforcement
    check_data = {
        "scoring": {
            "avg_profit": test_metrics["avg_profit"],
            "trades": test_metrics["trades"]
        }
    }
    
    passed, gov_report = red_team.enforce_governance(check_data, "example_context")
    print(f"\nGovernance enforcement:")
    print(f"  Passed: {passed}")
    print(f"  Violations: {len(gov_report.get('violations', []))}")
    
    # Create artifact bundle
    baseline = {"score": 35.0, "trades": 50}
    current = {"score": scoring_result["final_score"], "trades": test_metrics["trades"]}
    
    artifact_bundle = red_team.create_artifact_bundle(
        current_results=current,
        metadata={
            "strategy": "example_strategy",
            "dataset": "test_data",
            "season": "2026Q1"
        },
        baseline_results=baseline
    )
    
    print(f"\nArtifact bundle created:")
    print(f"  Components: {len(artifact_bundle)}")
    print(f"  Integrity hash: {artifact_bundle.get('integrity_hash', 'N/A')[:16]}...")
    
    # Get summary
    summary = red_team.get_summary()
    print(f"\nIntegration summary:")
    print(f"  Scoring guards applied: {summary['scoring_guards_applied']}")
    print(f"  Governance checks performed: {summary['governance_checks_performed']}")
    print(f"  Governance passed: {summary['governance_passed']}")
    print(f"  Structure valid: {summary['validation_checks'].get('structure_valid', False)}")
    
    return red_team, artifact_bundle


def main():
    """Run all examples."""
    print("RED-TEAM HARDENED WFS INTEGRATION DEMONSTRATION")
    print("=" * 60)
    print("\nThis demonstrates the complete implementation of:")
    print("1. Scoring Guards (Anti-Gaming) - Section 3.1")
    print("2. TSR Calibration - Section 5.2")
    print("3. Mode B Pipeline - Section 5.2")
    print("4. Governance Triggers - YAML-structure based policy")
    print("5. Enhanced WFS Evaluation")
    print("6. Complete Red-Team Integration")
    
    try:
        # Run all examples
        example_scoring_guards()
        example_tsr_calibration()
        example_mode_b_pipeline()
        example_governance_triggers()
        example_enhanced_evaluation()
        example_red_team_integration()
        
        print("\n" + "=" * 60)
        print("ALL EXAMPLES COMPLETED SUCCESSFULLY ✓")
        print("=" * 60)
        print("\nSummary of implemented components:")
        print("✓ Scoring Guards with trade multiplier cap and minimum edge gate")
        print("✓ RobustScore + Cliff Gates (OAT neighborhood analysis)")
        print("✓ Bimodality cluster detection")
        print("✓ TSR Calibration for Mode B anchors")
        print("✓ Mode B Pipeline with 3-stage optimization")
        print("✓ Governance trigger enforcement with YAML policies")
        print("✓ Enhanced WFS evaluation integrating 5D scoring with guards")
        print("✓ Red-Team integration with artifact bundles and integrity hashes")
        print("✓ Example YAML policy for governance")
        
    except Exception as e:
        print(f"\nError running examples: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())