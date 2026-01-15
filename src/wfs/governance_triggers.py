"""
Governance Trigger Enforcement for WFS Mode B (YAML-Structure Based Policy Test)

Enforces governance triggers that auto-detect Mode B requirements and ensure
compliance with structure-based policies.
"""

from __future__ import annotations

import logging
import yaml
from typing import Dict, List, Optional, Any, TypedDict, Tuple
from dataclasses import dataclass
from pathlib import Path
import hashlib
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class GovernancePolicy:
    """Governance policy definition."""
    # Mode B requirements
    require_mode_b: bool = False
    min_anchors: int = 3
    max_anchor_error: float = 0.05  # 5% tolerance
    
    # Scoring guard requirements
    require_scoring_guards: bool = True
    min_avg_profit: float = 5.0
    max_trade_cap: int = 100
    
    # Cluster test requirements
    require_cluster_test: bool = True
    max_bimodality_score: float = 0.3
    
    # Structure test requirements
    require_structure_test: bool = True
    allowed_param_ranges: Dict[str, tuple] = None  # param_name -> (min, max)
    
    # Artifact requirements
    require_delta_report: bool = True
    artifact_validation_checks: List[str] = None


class GovernanceTrigger:
    """Governance trigger that checks compliance with policies."""
    
    def __init__(self, policy: GovernancePolicy):
        self.policy = policy
        self.violations: List[str] = []
        self.warnings: List[str] = []
        
    def check_mode_b_requirements(
        self,
        anchors: List[Any],  # List of anchor points
        anchor_errors: List[float]
    ) -> bool:
        """Check Mode B anchor requirements."""
        if not self.policy.require_mode_b:
            return True
            
        if len(anchors) < self.policy.min_anchors:
            self.violations.append(
                f"Mode B requires at least {self.policy.min_anchors} anchors, "
                f"found {len(anchors)}"
            )
            return False
            
        # Check anchor errors
        if anchor_errors:
            max_error = max(anchor_errors)
            if max_error > self.policy.max_anchor_error:
                self.violations.append(
                    f"Anchor calibration error {max_error:.3f} exceeds "
                    f"maximum allowed {self.policy.max_anchor_error}"
                )
                return False
                
        return True
    
    def check_scoring_guard_compliance(
        self,
        scoring_results: Dict[str, Any]
    ) -> bool:
        """Check scoring guard compliance."""
        if not self.policy.require_scoring_guards:
            return True
            
        # Check minimum average profit
        avg_profit = scoring_results.get("avg_profit")
        if avg_profit is not None and avg_profit < self.policy.min_avg_profit:
            self.violations.append(
                f"Average profit ${avg_profit:.2f} below minimum "
                f"${self.policy.min_avg_profit}"
            )
            return False
            
        # Check trade cap
        trades = scoring_results.get("trades", 0)
        if trades > self.policy.max_trade_cap:
            self.warnings.append(
                f"Trades {trades} exceeds recommended cap {self.policy.max_trade_cap}"
            )
            # Warning only, not a violation
            
        return True
    
    def check_cluster_test(
        self,
        cluster_results: Dict[str, Any]
    ) -> bool:
        """Check cluster test results."""
        if not self.policy.require_cluster_test:
            return True
            
        bimodality_score = cluster_results.get("bimodality_score", 0.0)
        if bimodality_score > self.policy.max_bimodality_score:
            self.violations.append(
                f"Bimodality score {bimodality_score:.3f} exceeds "
                f"maximum allowed {self.policy.max_bimodality_score}"
            )
            return False
            
        return True
    
    def check_structure_test(
        self,
        param_values: Dict[str, float]
    ) -> bool:
        """Check parameter values against allowed ranges."""
        if not self.policy.require_structure_test:
            return True
            
        if not self.policy.allowed_param_ranges:
            return True
            
        for param_name, value in param_values.items():
            if param_name in self.policy.allowed_param_ranges:
                min_val, max_val = self.policy.allowed_param_ranges[param_name]
                if value < min_val or value > max_val:
                    self.violations.append(
                        f"Parameter {param_name}={value} outside allowed "
                        f"range [{min_val}, {max_val}]"
                    )
                    return False
                    
        return True
    
    def check_artifact_compliance(
        self,
        artifact_bundle: Dict[str, Any]
    ) -> bool:
        """Check artifact bundle compliance."""
        if not self.policy.require_delta_report:
            return True
            
        # Check for delta report
        if "delta_report" not in artifact_bundle:
            self.violations.append("Missing delta report in artifact bundle")
            return False
            
        delta_report = artifact_bundle["delta_report"]
        
        # Check required fields
        required_fields = ["baseline_hash", "current_hash", "changes"]
        for field in required_fields:
            if field not in delta_report:
                self.violations.append(f"Delta report missing field: {field}")
                return False
                
        # Check validation checks if specified
        if self.policy.artifact_validation_checks:
            for check in self.policy.artifact_validation_checks:
                if check not in artifact_bundle.get("validation_checks", {}):
                    self.violations.append(f"Missing validation check: {check}")
                    return False
                    
        return True
    
    def run_all_checks(
        self,
        mode_b_data: Optional[Dict[str, Any]] = None,
        scoring_data: Optional[Dict[str, Any]] = None,
        cluster_data: Optional[Dict[str, Any]] = None,
        param_data: Optional[Dict[str, float]] = None,
        artifact_data: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, List[str], List[str]]:
        """
        Run all governance checks.
        
        Returns:
            Tuple of (passed, violations, warnings)
        """
        self.violations = []
        self.warnings = []
        
        # Check Mode B requirements
        if mode_b_data and self.policy.require_mode_b:
            anchors = mode_b_data.get("anchors", [])
            anchor_errors = mode_b_data.get("anchor_errors", [])
            if not self.check_mode_b_requirements(anchors, anchor_errors):
                logger.warning("Mode B requirements check failed")
        
        # Check scoring guard compliance
        if scoring_data and self.policy.require_scoring_guards:
            if not self.check_scoring_guard_compliance(scoring_data):
                logger.warning("Scoring guard compliance check failed")
        
        # Check cluster test
        if cluster_data and self.policy.require_cluster_test:
            if not self.check_cluster_test(cluster_data):
                logger.warning("Cluster test check failed")
        
        # Check structure test
        if param_data and self.policy.require_structure_test:
            if not self.check_structure_test(param_data):
                logger.warning("Structure test check failed")
        
        # Check artifact compliance
        if artifact_data and self.policy.require_delta_report:
            if not self.check_artifact_compliance(artifact_data):
                logger.warning("Artifact compliance check failed")
        
        passed = len(self.violations) == 0
        return passed, self.violations, self.warnings


def load_policy_from_yaml(yaml_path: Path) -> GovernancePolicy:
    """Load governance policy from YAML file."""
    try:
        with open(yaml_path, 'r') as f:
            policy_data = yaml.safe_load(f)
    except Exception as e:
        logger.error(f"Failed to load policy from {yaml_path}: {e}")
        return GovernancePolicy()  # Return default policy
    
    # Parse policy data
    policy = GovernancePolicy()
    
    # Mode B settings
    mode_b = policy_data.get("mode_b", {})
    policy.require_mode_b = mode_b.get("require", False)
    policy.min_anchors = mode_b.get("min_anchors", 3)
    policy.max_anchor_error = mode_b.get("max_anchor_error", 0.05)
    
    # Scoring guard settings
    scoring = policy_data.get("scoring_guards", {})
    policy.require_scoring_guards = scoring.get("require", True)
    policy.min_avg_profit = scoring.get("min_avg_profit", 5.0)
    policy.max_trade_cap = scoring.get("max_trade_cap", 100)
    
    # Cluster test settings
    cluster = policy_data.get("cluster_test", {})
    policy.require_cluster_test = cluster.get("require", True)
    policy.max_bimodality_score = cluster.get("max_bimodality_score", 0.3)
    
    # Structure test settings
    structure = policy_data.get("structure_test", {})
    policy.require_structure_test = structure.get("require", True)
    policy.allowed_param_ranges = structure.get("allowed_param_ranges", {})
    
    # Artifact settings
    artifact = policy_data.get("artifact", {})
    policy.require_delta_report = artifact.get("require_delta_report", True)
    policy.artifact_validation_checks = artifact.get("validation_checks", [])
    
    return policy


def create_delta_report(
    baseline: Dict[str, Any],
    current: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Create delta report between baseline and current results.
    
    Args:
        baseline: Baseline results
        current: Current results
        
    Returns:
        Delta report dictionary
    """
    # Calculate hashes for comparison
    def dict_hash(d: Dict) -> str:
        """Create hash of dictionary."""
        return hashlib.sha256(
            str(sorted(d.items())).encode()
        ).hexdigest()[:16]
    
    baseline_hash = dict_hash(baseline)
    current_hash = dict_hash(current)
    
    # Find changes
    changes = {}
    
    # Compare keys
    all_keys = set(baseline.keys()) | set(current.keys())
    
    for key in all_keys:
        if key not in baseline:
            changes[key] = {"action": "added", "value": current[key]}
        elif key not in current:
            changes[key] = {"action": "removed", "value": baseline[key]}
        elif baseline[key] != current[key]:
            changes[key] = {
                "action": "modified",
                "old_value": baseline[key],
                "new_value": current[key]
            }
    
    # Calculate summary
    added = sum(1 for c in changes.values() if c["action"] == "added")
    removed = sum(1 for c in changes.values() if c["action"] == "removed")
    modified = sum(1 for c in changes.values() if c["action"] == "modified")
    
    return {
        "baseline_hash": baseline_hash,
        "current_hash": current_hash,
        "hashes_match": baseline_hash == current_hash,
        "changes": changes,
        "summary": {
            "added": added,
            "removed": removed,
            "modified": modified,
            "total_changes": len(changes)
        },
        "timestamp": datetime.now().isoformat()
    }


def enforce_governance(
    policy: GovernancePolicy,
    check_data: Dict[str, Any]
) -> Tuple[bool, Dict[str, Any]]:
    """
    Enforce governance policy with comprehensive checking.
    
    Args:
        policy: Governance policy
        check_data: Dictionary containing all check data
        
    Returns:
        Tuple of (passed, enforcement_report)
    """
    trigger = GovernanceTrigger(policy)
    
    passed, violations, warnings = trigger.run_all_checks(
        mode_b_data=check_data.get("mode_b"),
        scoring_data=check_data.get("scoring"),
        cluster_data=check_data.get("cluster"),
        param_data=check_data.get("params"),
        artifact_data=check_data.get("artifact")
    )
    
    # Create enforcement report
    report = {
        "policy_enforced": True,
        "policy_source": "governance_triggers",
        "compliance_passed": passed,
        "violations": violations,
        "warnings": warnings,
        "checks_performed": {
            "mode_b": policy.require_mode_b and "mode_b" in check_data,
            "scoring_guards": policy.require_scoring_guards and "scoring" in check_data,
            "cluster_test": policy.require_cluster_test and "cluster" in check_data,
            "structure_test": policy.require_structure_test and "params" in check_data,
            "artifact_compliance": policy.require_delta_report and "artifact" in check_data
        },
        "timestamp": datetime.now().isoformat()
    }
    
    return passed, report


# Default policy for backward compatibility
DEFAULT_POLICY = GovernancePolicy()


# Test function
if __name__ == "__main__":
    print("=== Testing Governance Triggers ===")
    
    from datetime import datetime
    
    # Create test policy
    policy = GovernancePolicy(
        require_mode_b=True,
        min_anchors=3,
        require_scoring_guards=True,
        min_avg_profit=5.0
    )
    
    # Create test data
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
            "channel_len": 20,
            "stop_mult": 2.0
        }
    }
    
    # Run enforcement
    passed, report = enforce_governance(policy, check_data)
    
    print(f"Governance check passed: {passed}")
    print(f"Violations: {report['violations']}")
    print(f"Warnings: {report['warnings']}")
    
    # Test delta report
    baseline = {"score": 85.2, "trades": 50, "net_profit": 1200.0}
    current = {"score": 87.5, "trades": 52, "net_profit": 1250.0, "new_field": "test"}
    
    delta = create_delta_report(baseline, current)
    print(f"\nDelta report:")
    print(f"  Hashes match: {delta['hashes_match']}")
    print(f"  Changes: {delta['summary']['total_changes']}")
    
    print("\n=== Governance triggers test completed ===")