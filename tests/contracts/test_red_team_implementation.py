#!/usr/bin/env python3
"""
Test script for Red-Team Hardened WFS Mode B + Scoring Guards implementation.
"""

import sys
import os

# Add src directory to Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.join(current_dir, 'src')
sys.path.insert(0, src_dir)

try:
    from wfs.scoring_guards import score_with_guards, ScoringGuardConfig
    from wfs.tsr_calibration import calibrate_anchor_params, TSRCalibrationConfig, CalibrationMethod
    from wfs.mode_b_pipeline import create_mode_b_pipeline
    from wfs.governance_triggers import enforce_governance, GovernancePolicy
    from wfs.red_team_integration import create_red_team_wfs
except ImportError as e:
    print(f"Import error: {e}")
    print(f"Current Python path: {sys.path}")
    sys.exit(1)

import numpy as np


def test_scoring_guards():
    """Test scoring guards implementation."""
    print("=== Testing Scoring Guards ===")
    
    # Test 1: Good strategy
    result1 = score_with_guards(
        net_profit=2000.0,
        max_dd=400.0,
        trades=80
    )
    print(f"Test 1 (Good strategy):")
    print(f"  Final Score: {result1['final_score']:.2f}")
    print(f"  Trade Multiplier: {result1['trade_multiplier']:.2f}")
    print(f"  Net/MDD Ratio: {result1['net_mdd_ratio']:.2f}")
    print(f"  Edge Gate: {'PASS' if result1['edge_gate_passed'] else 'FAIL'}")
    
    # Test 2: Low average profit (should fail)
    result2 = score_with_guards(
        net_profit=200.0,
        max_dd=100.0,
        trades=80
    )
    print(f"\nTest 2 (Low avg profit):")
    print(f"  Final Score: {result2['final_score']:.2f}")
    print(f"  Edge Gate: {'PASS' if result2['edge_gate_passed'] else 'FAIL'}")
    if not result2['edge_gate_passed']:
        print(f"  Reason: {result2['edge_gate_reason']}")
    
    # Test 3: Custom configuration
    config = ScoringGuardConfig(
        t_max=50,
        alpha=0.3,
        min_avg_profit=10.0
    )
    result3 = score_with_guards(1500.0, 300.0, 60, config)
    print(f"\nTest 3 (Custom config):")
    print(f"  Final Score: {result3['final_score']:.2f}")
    print(f"  Config: T_MAX={config.t_max}, alpha={config.alpha}")
    
    assert all([result1['edge_gate_passed'], not result2['edge_gate_passed']])


def test_tsr_calibration():
    """Test TSR calibration for Mode B."""
    print("\n=== Testing TSR Calibration ===")
    
    # Test data
    param_values = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
    actual_rates = [0.02, 0.05, 0.08, 0.10, 0.12, 0.14, 0.16, 0.17, 0.18, 0.19]
    
    # Test linear calibration
    config = TSRCalibrationConfig(
        method=CalibrationMethod.LINEAR,
        tsr_min=0.01,
        tsr_max=0.20,
        anchor_tolerance=0.05
    )
    
    anchors = calibrate_anchor_params(param_values, actual_rates, config)
    
    print(f"Calibrated {len(anchors)} anchors:")
    valid_count = sum(1 for a in anchors if a.is_valid)
    print(f"  Valid anchors: {valid_count}/{len(anchors)}")
    
    # Show first 3 anchors
    for i, anchor in enumerate(anchors[:3]):
        status = "✓" if anchor.is_valid else "✗"
        print(f"  Anchor {i+1}: param={anchor.param_value}, "
              f"target={anchor.target_tsr:.3f}, actual={anchor.calibrated_tsr:.3f} [{status}]")
    
    assert valid_count >= 3  # Need at least 3 valid anchors


def test_governance_triggers():
    """Test governance trigger enforcement."""
    print("\n=== Testing Governance Triggers ===")
    
    # Create policy
    policy = GovernancePolicy(
        require_mode_b=True,
        min_anchors=3,
        require_scoring_guards=True,
        min_avg_profit=5.0,
        require_cluster_test=True,
        max_bimodality_score=0.3
    )
    
    # Test data that should pass
    check_data = {
        "mode_b": {
            "anchors": [1, 2, 3, 4, 5],
            "anchor_errors": [0.01, 0.02, 0.03, 0.02, 0.01]
        },
        "scoring": {
            "avg_profit": 15.0,
            "trades": 60
        },
        "cluster": {
            "bimodality_score": 0.15
        }
    }
    
    passed, report = enforce_governance(policy, check_data)
    
    print(f"Governance check: {'PASS' if passed else 'FAIL'}")
    print(f"Violations: {report['violations']}")
    print(f"Warnings: {report['warnings']}")
    
    # Test data that should fail (low average profit)
    check_data_fail = {
        "scoring": {
            "avg_profit": 3.0,  # Below minimum
            "trades": 60
        }
    }
    
    passed_fail, report_fail = enforce_governance(policy, check_data_fail)
    print(f"\nGovernance check (should fail): {'PASS' if passed_fail else 'FAIL'}")
    if not passed_fail:
        print(f"  Expected violation: {report_fail['violations']}")
    
    assert passed and not passed_fail


def test_red_team_integration():
    """Test full Red-Team integration."""
    print("\n=== Testing Red-Team Integration ===")
    
    # Create Red-Team WFS
    red_team = create_red_team_wfs(
        enable_scoring_guards=True,
        enable_mode_b=False,  # Don't test Mode B in quick test
        enable_governance=True,
        artifact_output_dir="outputs/_dp_evidence/test_artifacts"
    )
    
    # Test scoring guards
    raw_metrics = {
        "net_profit": 2500.0,
        "max_dd": 500.0,
        "trades": 75,
        "net_profit_oat": [2400.0, 2550.0, 2450.0, 2520.0, 2480.0],
        "max_dd_oat": [510.0, 490.0, 505.0, 495.0, 500.0],
        "trades_oat": [73, 77, 74, 76, 75]
    }
    
    scoring_result = red_team.apply_scoring_guards(raw_metrics, "S1_test")
    print(f"Scoring applied: Final Score = {scoring_result['final_score']:.2f}")
    
    # Test governance
    check_data = {
        "scoring": {
            "avg_profit": 2500.0 / 75,  # ~33.33
            "trades": 75
        }
    }
    
    passed, gov_report = red_team.enforce_governance(check_data, "integration_test")
    print(f"Governance: {'PASS' if passed else 'FAIL'}")
    
    # Create artifact bundle
    artifact_bundle = red_team.create_artifact_bundle(
        baseline_results={"score": 80.0, "trades": 70},
        current_results={
            "score": scoring_result["final_score"],
            "trades": 75,
            "net_profit": 2500.0,
            "max_dd": 500.0
        },
        metadata={
            "test": "integration",
            "strategy": "S1",
            "timestamp": "2026-01-15"
        }
    )
    
    print(f"Artifact bundle created: {len(artifact_bundle)} components")
    print(f"Integrity hash: {artifact_bundle.get('integrity_hash', 'N/A')[:16]}...")
    
    # Get summary
    summary = red_team.get_summary()
    print(f"\nIntegration Summary:")
    for key, value in summary.items():
        if isinstance(value, dict):
            print(f"  {key}:")
            for k, v in value.items():
                print(f"    {k}: {v}")
        else:
            print(f"  {key}: {value}")
    
    assert all([
        scoring_result['final_score'] > 0,
        passed,
        artifact_bundle.get('integrity_hash') is not None
    ])


def main():
    """Run all tests."""
    print("Red-Team Hardened WFS Implementation Tests")
    print("=" * 50)
    
    results = []
    
    # Run tests with assertion catching
    test_functions = [
        ("Scoring Guards", test_scoring_guards),
        ("TSR Calibration", test_tsr_calibration),
        ("Governance Triggers", test_governance_triggers),
        ("Red-Team Integration", test_red_team_integration)
    ]
    
    for test_name, test_func in test_functions:
        try:
            test_func()
            passed = True
        except AssertionError:
            passed = False
        except Exception as e:
            print(f"Unexpected error in {test_name}: {e}")
            passed = False
        results.append((test_name, passed))
    
    # Print summary
    print("\n" + "=" * 50)
    print("TEST SUMMARY:")
    print("=" * 50)
    
    all_passed = True
    for test_name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{test_name:30} {status}")
        if not passed:
            all_passed = False
    
    print("=" * 50)
    if all_passed:
        print("ALL TESTS PASSED ✓")
        return 0
    else:
        print("SOME TESTS FAILED ✗")
        return 1


if __name__ == "__main__":
    # Create test output directory
    os.makedirs("outputs/_dp_evidence/test_artifacts", exist_ok=True)
    
    # Run tests
    exit_code = main()
    sys.exit(exit_code)