"""
Red-Team Hardened WFS Integration Module

Integrates all Red-Team hardening components:
1. Scoring Guards (Section 3.1)
2. Mode B Pipeline (Section 5.2) 
3. Governance Triggers
4. Artifact Bundle with Delta Report
"""

from __future__ import annotations

import logging
import json
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from pathlib import Path
import hashlib
from datetime import datetime

from core.paths import get_outputs_root
from wfs.scoring_guards import (
    ScoringGuardConfig, apply_scoring_guards, DEFAULT_CONFIG as DEFAULT_SCORING_CONFIG
)
from wfs.tsr_calibration import (
    TSRCalibrationConfig, calibrate_anchor_params, DEFAULT_CALIBRATION_CONFIG
)
from wfs.mode_b_pipeline import ModeBPipeline, create_mode_b_pipeline
from wfs.governance_triggers import (
    GovernancePolicy, enforce_governance, create_delta_report, DEFAULT_POLICY
)


logger = logging.getLogger(__name__)


@dataclass
class RedTeamConfig:
    """Configuration for Red-Team hardened WFS."""
    # Component enable flags
    enable_scoring_guards: bool = True
    enable_mode_b: bool = False
    enable_governance: bool = True
    enable_delta_report: bool = True
    
    # Component configurations
    scoring_config: ScoringGuardConfig = None
    calibration_config: TSRCalibrationConfig = None
    governance_policy: GovernancePolicy = None
    
    # Integration settings
    artifact_output_dir: Path = get_outputs_root() / "_dp_evidence" / "red_team_wfs_mode_b"
    save_intermediate_results: bool = True
    validation_strictness: str = "strict"  # "strict", "moderate", "lenient"


class RedTeamHardenedWFS:
    """Main integration class for Red-Team hardened WFS."""
    
    def __init__(self, config: Optional[RedTeamConfig] = None):
        self.config = config or RedTeamConfig()
        
        # Initialize component configurations
        if self.config.scoring_config is None:
            self.config.scoring_config = DEFAULT_SCORING_CONFIG
            
        if self.config.calibration_config is None:
            self.config.calibration_config = DEFAULT_CALIBRATION_CONFIG
            
        if self.config.governance_policy is None:
            self.config.governance_policy = DEFAULT_POLICY
        
        # State
        self.mode_b_pipeline: Optional[ModeBPipeline] = None
        self.scoring_results: Dict[str, Any] = {}
        self.governance_report: Dict[str, Any] = {}
        self.artifact_bundle: Dict[str, Any] = {}
        
        # Ensure output directory exists
        self.config.artifact_output_dir.mkdir(parents=True, exist_ok=True)
    
    def apply_scoring_guards(
        self,
        raw_metrics: Dict[str, Any],
        strategy_id: str = "unknown"
    ) -> Dict[str, Any]:
        """
        Apply scoring guards to raw metrics.
        
        Args:
            raw_metrics: Raw metrics dictionary
            strategy_id: Strategy identifier for logging
            
        Returns:
            Scoring results with guards applied
        """
        if not self.config.enable_scoring_guards:
            logger.info(f"Scoring guards disabled for {strategy_id}")
            return {"final_score": raw_metrics.get("net_profit", 0.0)}
        
        logger.info(f"Applying scoring guards for {strategy_id}")
        
        # Apply scoring guards
        scoring_result = apply_scoring_guards(raw_metrics, self.config.scoring_config)
        
        # Store results
        self.scoring_results[strategy_id] = scoring_result
        
        # Save intermediate results if enabled
        if self.config.save_intermediate_results:
            self._save_intermediate_result(
                f"scoring_{strategy_id}", scoring_result
            )
        
        return scoring_result
    
    def setup_mode_b_pipeline(
        self,
        entry_param_name: str,
        exit_param_names: List[str],
        exit_param_ranges: Dict[str, Tuple[float, float, float]]
    ) -> bool:
        """
        Set up Mode B pipeline.
        
        Args:
            entry_param_name: Name of entry parameter to anchor
            exit_param_names: List of exit parameter names to sweep
            exit_param_ranges: Dict mapping exit param names to (min, max, step)
            
        Returns:
            True if setup successful, False otherwise
        """
        if not self.config.enable_mode_b:
            logger.info("Mode B pipeline disabled")
            return False
        
        try:
            self.mode_b_pipeline = create_mode_b_pipeline(
                entry_param_name=entry_param_name,
                exit_param_names=exit_param_names,
                exit_param_ranges=exit_param_ranges,
                scoring_config=self.config.scoring_config,
                calibration_config=self.config.calibration_config
            )
            logger.info(f"Mode B pipeline setup for {entry_param_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to setup Mode B pipeline: {e}")
            return False
    
    def run_mode_b_pipeline(
        self,
        param_name: str,
        param_values: List[float],
        actual_signal_rates: List[float],
        base_entry_params: Dict[str, float],
        evaluate_param_set_fn
    ) -> Tuple[bool, List[Any], Dict[str, Any]]:
        """
        Run Mode B pipeline.
        
        Args:
            param_name: Parameter name for calibration
            param_values: Parameter values for calibration
            actual_signal_rates: Actual signal rates for calibration
            base_entry_params: Base entry parameters
            evaluate_param_set_fn: Function to evaluate parameter sets
            
        Returns:
            Tuple of (success, candidates, pipeline_report)
        """
        if self.mode_b_pipeline is None:
            logger.error("Mode B pipeline not setup")
            return False, [], {"error": "Mode B pipeline not setup"}
        
        return self.mode_b_pipeline.run_full_pipeline(
            param_name=param_name,
            param_values=param_values,
            actual_signal_rates=actual_signal_rates,
            base_entry_params=base_entry_params,
            evaluate_param_set_fn=evaluate_param_set_fn
        )
    
    def enforce_governance(
        self,
        check_data: Dict[str, Any],
        context: str = "wfs_execution"
    ) -> Tuple[bool, Dict[str, Any]]:
        """
        Enforce governance policies.
        
        Args:
            check_data: Dictionary containing check data
            context: Context for logging
            
        Returns:
            Tuple of (passed, governance_report)
        """
        if not self.config.enable_governance:
            logger.info(f"Governance enforcement disabled for {context}")
            return True, {"policy_enforced": False}
        
        logger.info(f"Enforcing governance for {context}")
        
        passed, report = enforce_governance(
            self.config.governance_policy, check_data
        )
        
        # Store report
        self.governance_report[context] = report
        
        # Save intermediate results if enabled
        if self.config.save_intermediate_results:
            self._save_intermediate_result(
                f"governance_{context}", report
            )
        
        return passed, report
    
    def create_artifact_bundle(
        self,
        current_results: Dict[str, Any],
        metadata: Dict[str, Any],
        baseline_results: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create artifact bundle with delta report.
        
        Args:
            current_results: Current results
            metadata: Additional metadata
            baseline_results: Baseline results for comparison (optional)
            
        Returns:
            Complete artifact bundle
        """
        logger.info("Creating artifact bundle")
        
        # Create delta report if enabled
        delta_report = None
        if self.config.enable_delta_report and baseline_results is not None:
            delta_report = create_delta_report(baseline_results, current_results)
        
        # Assemble artifact bundle
        self.artifact_bundle = {
            "metadata": {
                **metadata,
                "created_at": datetime.now().isoformat(),
                "red_team_version": "1.0",
                "config": {
                    "enable_scoring_guards": self.config.enable_scoring_guards,
                    "enable_mode_b": self.config.enable_mode_b,
                    "enable_governance": self.config.enable_governance,
                    "enable_delta_report": self.config.enable_delta_report,
                    "validation_strictness": self.config.validation_strictness
                }
            },
            "results": current_results,
            "scoring_results": self.scoring_results,
            "governance_reports": self.governance_report,
            "delta_report": delta_report,
            "validation_checks": self._run_validation_checks(current_results)
        }
        
        # Add hash for integrity
        self.artifact_bundle["integrity_hash"] = self._calculate_bundle_hash()
        
        # Save artifact bundle
        self._save_artifact_bundle()
        
        return self.artifact_bundle
    
    def _run_validation_checks(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Run validation checks on results."""
        checks = {}
        
        # Check 1: Results structure
        checks["structure_valid"] = isinstance(results, dict)
        
        # Check 2: Required fields (if applicable)
        if "final_score" in results:
            checks["score_valid"] = isinstance(results["final_score"], (int, float))
            checks["score_positive"] = results["final_score"] >= 0
        
        # Check 3: Mode B pipeline results (if applicable)
        if self.mode_b_pipeline and hasattr(self.mode_b_pipeline, 'final_candidates'):
            checks["mode_b_candidates"] = len(self.mode_b_pipeline.final_candidates) > 0
        
        # Check 4: Governance compliance
        checks["governance_compliant"] = all(
            report.get("compliance_passed", False)
            for report in self.governance_report.values()
        )
        
        return checks
    
    def _calculate_bundle_hash(self) -> str:
        """Calculate hash of artifact bundle for integrity checking."""
        # Create a stable representation for hashing
        bundle_copy = self.artifact_bundle.copy()
        
        # Remove integrity_hash if present (circular)
        bundle_copy.pop("integrity_hash", None)
        
        # Convert to JSON string
        bundle_json = json.dumps(bundle_copy, sort_keys=True)
        
        # Calculate hash
        return hashlib.sha256(bundle_json.encode()).hexdigest()[:32]
    
    def _save_intermediate_result(self, name: str, data: Dict[str, Any]):
        """Save intermediate result to file."""
        try:
            file_path = self.config.artifact_output_dir / f"{name}.json"
            with open(file_path, 'w') as f:
                json.dump(data, f, indent=2, default=str)
            logger.debug(f"Saved intermediate result: {file_path}")
        except Exception as e:
            logger.warning(f"Failed to save intermediate result {name}: {e}")
    
    def _save_artifact_bundle(self):
        """Save artifact bundle to file."""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_path = self.config.artifact_output_dir / f"artifact_bundle_{timestamp}.json"
            
            with open(file_path, 'w') as f:
                json.dump(self.artifact_bundle, f, indent=2, default=str)
            
            logger.info(f"Saved artifact bundle: {file_path}")
            
            # Also save a latest reference
            latest_path = self.config.artifact_output_dir / "artifact_bundle_latest.json"
            latest_path.write_text(file_path.read_text())
            
        except Exception as e:
            logger.error(f"Failed to save artifact bundle: {e}")
    
    def get_summary(self) -> Dict[str, Any]:
        """Get summary of Red-Team hardened WFS execution."""
        return {
            "scoring_guards_applied": len(self.scoring_results),
            "governance_checks_performed": len(self.governance_report),
            "governance_passed": all(
                report.get("compliance_passed", False)
                for report in self.governance_report.values()
            ),
            "mode_b_enabled": self.config.enable_mode_b,
            "mode_b_pipeline_ready": self.mode_b_pipeline is not None,
            "artifact_bundle_created": bool(self.artifact_bundle),
            "artifact_integrity_hash": self.artifact_bundle.get("integrity_hash", "N/A"),
            "validation_checks": self.artifact_bundle.get("validation_checks", {})
        }


# Factory function for easy creation
def create_red_team_wfs(
    enable_scoring_guards: bool = True,
    enable_mode_b: bool = False,
    enable_governance: bool = True,
    artifact_output_dir: str = str(get_outputs_root() / "_dp_evidence" / "red_team_wfs_mode_b")
) -> RedTeamHardenedWFS:
    """
    Factory function to create Red-Team hardened WFS.
    
    Args:
        enable_scoring_guards: Enable scoring guards
        enable_mode_b: Enable Mode B pipeline
        enable_governance: Enable governance enforcement
        artifact_output_dir: Directory for artifact output
        
    Returns:
        Configured RedTeamHardenedWFS instance
    """
    config = RedTeamConfig(
        enable_scoring_guards=enable_scoring_guards,
        enable_mode_b=enable_mode_b,
        enable_governance=enable_governance,
        artifact_output_dir=Path(artifact_output_dir)
    )
    
    return RedTeamHardenedWFS(config)


# Test function
if __name__ == "__main__":
    print("=== Testing Red-Team Hardened WFS Integration ===")
    
    # Create Red-Team WFS
    red_team = create_red_team_wfs(
        enable_scoring_guards=True,
        enable_mode_b=True,
        enable_governance=True
    )
    
    # Test scoring guards
    raw_metrics = {
        "net_profit": 1500.0,
        "max_dd": 300.0,
        "trades": 60,
        "net_profit_oat": [1450.0, 1520.0, 1480.0, 1510.0, 1490.0],
        "max_dd_oat": [310.0, 290.0, 305.0, 295.0, 300.0],
        "trades_oat": [58, 62, 59, 61, 60]
    }
    
    scoring_result = red_team.apply_scoring_guards(raw_metrics, "test_strategy")
    print(f"Scoring result: Final Score = {scoring_result['final_score']:.2f}")
    
    # Test governance enforcement
    check_data = {
        "mode_b": {
            "anchors": [1, 2, 3, 4],
            "anchor_errors": [0.01, 0.02, 0.03, 0.04]
        },
        "scoring": {
            "avg_profit": 25.0,  # $25 average profit
            "trades": 60
        }
    }
    
    passed, gov_report = red_team.enforce_governance(check_data, "test_context")
    print(f"Governance passed: {passed}")
    
    # Create artifact bundle
    baseline = {"score": 80.5, "trades": 50}
    current = {"score": scoring_result["final_score"], "trades": 60}
    
    artifact_bundle = red_team.create_artifact_bundle(
        current_results=current,
        metadata={
            "strategy": "test_strategy",
            "dataset": "test_data",
            "season": "2026Q1"
        },
        baseline_results=baseline
    )
    
    print(f"Artifact bundle created: {artifact_bundle['metadata']['created_at']}")
    print(f"Integrity hash: {artifact_bundle['integrity_hash']}")
    
    # Get summary
    summary = red_team.get_summary()
    print(f"\nSummary:")
    for key, value in summary.items():
        print(f"  {key}: {value}")
    
    print("\n=== Red-Team integration test completed ===")