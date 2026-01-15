"""
WFS Mode B Pipeline (Section 5.2)

Implements Stage 1/2/3 Pipeline Behavior for Mode B:
- Stage 1: Anchor-based entry intensity fixing
- Stage 2: Full exit plane sweeping  
- Stage 3: Union candidate pool across anchors
"""

from __future__ import annotations

import logging
from typing import Dict, List, Tuple, Optional, Any, TypedDict
from dataclasses import dataclass
import numpy as np

from wfs.scoring_guards import ScoringGuardConfig, apply_scoring_guards
from wfs.tsr_calibration import (
    TSRCalibrationConfig, AnchorPoint, calibrate_anchor_params,
    select_mode_b_anchors, create_mode_b_structure_filter
)


logger = logging.getLogger(__name__)


@dataclass
class ModeBConfig:
    """Configuration for Mode B pipeline."""
    # Stage 1: Anchor calibration
    calibration_config: TSRCalibrationConfig
    
    # Stage 2: Exit plane sweeping
    exit_param_names: List[str]
    exit_param_grids: Dict[str, List[float]]
    
    # Scoring
    scoring_config: ScoringGuardConfig
    
    # Stage 3: Union candidate selection
    min_valid_anchors: int = 3
    max_candidates_per_anchor: int = 10
    union_top_n: int = 20
    
    # Governance
    enforce_structure_test: bool = True
    require_cluster_test: bool = True


@dataclass
class ParameterSet:
    """A complete parameter set for strategy evaluation."""
    entry_params: Dict[str, float]  # Entry parameters (anchored in Mode B)
    exit_params: Dict[str, float]   # Exit parameters (swept in Stage 2)
    param_id: int                   # Unique parameter ID


@dataclass
class EvaluationResult:
    """Result of evaluating a parameter set."""
    param_set: ParameterSet
    metrics: Dict[str, float]      # Raw metrics (net_profit, max_dd, trades, etc.)
    score: float                   # Final score after guards
    score_breakdown: Dict[str, Any]  # Detailed scoring breakdown
    passed_guards: bool            # Whether passed all scoring guards


class ModeBPipeline:
    """Main Mode B pipeline implementation."""
    
    def __init__(self, config: ModeBConfig):
        self.config = config
        self.anchors: List[AnchorPoint] = []
        self.selected_anchors: List[AnchorPoint] = []
        self.candidate_pool: List[EvaluationResult] = []
        self.final_candidates: List[EvaluationResult] = []
        
    def stage1_calibrate_anchors(
        self,
        param_name: str,
        param_values: List[float],
        actual_signal_rates: List[float]
    ) -> bool:
        """
        Stage 1: Calibrate anchors for entry intensity fixing.
        
        Args:
            param_name: Name of entry parameter to anchor
            param_values: List of parameter values tested
            actual_signal_rates: Corresponding actual signal rates
            
        Returns:
            True if calibration successful, False otherwise
        """
        logger.info(f"Stage 1: Calibrating anchors for {param_name}")
        
        # Calibrate anchor points
        self.anchors = calibrate_anchor_params(
            param_values, actual_signal_rates, self.config.calibration_config
        )
        
        # Select valid anchors
        self.selected_anchors, rejected = select_mode_b_anchors(
            self.anchors, self.config.min_valid_anchors
        )
        
        if not self.selected_anchors:
            logger.error(f"Stage 1 failed: No valid anchors selected "
                        f"(need at least {self.config.min_valid_anchors})")
            return False
        
        logger.info(f"Stage 1 completed: Selected {len(self.selected_anchors)} "
                   f"anchors, rejected {len(rejected)}")
        
        # Log anchor details
        for i, anchor in enumerate(self.selected_anchors):
            logger.debug(f"  Anchor {i+1}: param={anchor.param_value}, "
                        f"target_tsr={anchor.target_tsr:.3f}, "
                        f"actual={anchor.calibrated_tsr:.3f}")
        
        return True
    
    def stage2_sweep_exit_plane(
        self,
        base_entry_params: Dict[str, float],
        evaluate_param_set_fn
    ) -> List[EvaluationResult]:
        """
        Stage 2: Sweep exit plane for each anchor.
        
        Args:
            base_entry_params: Base entry parameters (excluding anchored param)
            evaluate_param_set_fn: Function to evaluate a parameter set
                Signature: fn(ParameterSet) -> Dict[str, float] (metrics)
                
        Returns:
            List of evaluation results for all tested parameter sets
        """
        logger.info("Stage 2: Sweeping exit plane")
        
        all_results = []
        param_id = 0
        
        # For each anchor, create fixed entry params
        for anchor_idx, anchor in enumerate(self.selected_anchors):
            logger.debug(f"  Processing anchor {anchor_idx+1}/{len(self.selected_anchors)}: "
                        f"param={anchor.param_value}")
            
            # Create entry params with anchored value
            # Need to know which parameter is being anchored - this should come from config
            # For now, assume it's passed separately or stored in class
            
            # Generate exit parameter combinations
            exit_param_combinations = self._generate_exit_param_combinations()
            
            # Evaluate each exit parameter combination
            for exit_params in exit_param_combinations:
                # Create complete parameter set
                entry_params = base_entry_params.copy()
                # Add anchored parameter value (implementation depends on which param)
                # This is a placeholder - actual implementation needs to know param name
                
                param_set = ParameterSet(
                    entry_params=entry_params,
                    exit_params=exit_params,
                    param_id=param_id
                )
                param_id += 1
                
                # Evaluate parameter set
                try:
                    metrics = evaluate_param_set_fn(param_set)
                    
                    # Apply scoring guards
                    scoring_result = apply_scoring_guards({
                        "net_profit": metrics.get("net_profit", 0.0),
                        "max_dd": metrics.get("max_dd", 0.0),
                        "trades": metrics.get("trades", 0),
                        "net_profit_oat": metrics.get("net_profit_oat"),
                        "max_dd_oat": metrics.get("max_dd_oat"),
                        "trades_oat": metrics.get("trades_oat")
                    }, self.config.scoring_config)
                    
                    result = EvaluationResult(
                        param_set=param_set,
                        metrics=metrics,
                        score=scoring_result["final_score"],
                        score_breakdown=scoring_result,
                        passed_guards=scoring_result.get("edge_gate_passed", False) and 
                                     scoring_result.get("cliff_gate_passed", True)
                    )
                    
                    all_results.append(result)
                    
                except Exception as e:
                    logger.warning(f"Failed to evaluate param set {param_id}: {e}")
                    continue
        
        logger.info(f"Stage 2 completed: Evaluated {len(all_results)} parameter sets")
        return all_results
    
    def _generate_exit_param_combinations(self) -> List[Dict[str, float]]:
        """Generate all exit parameter combinations from grids."""
        param_names = list(self.config.exit_param_grids.keys())
        param_values = [self.config.exit_param_grids[name] for name in param_names]
        
        # Generate Cartesian product
        from itertools import product
        combinations = []
        
        for value_tuple in product(*param_values):
            param_dict = {name: value for name, value in zip(param_names, value_tuple)}
            combinations.append(param_dict)
        
        return combinations
    
    def stage3_build_union_pool(
        self,
        all_results: List[EvaluationResult]
    ) -> List[EvaluationResult]:
        """
        Stage 3: Build union candidate pool across anchors.
        
        Args:
            all_results: All evaluation results from Stage 2
            
        Returns:
            Top candidates from union pool
        """
        logger.info("Stage 3: Building union candidate pool")
        
        if not all_results:
            logger.warning("Stage 3: No results to process")
            return []
        
        # Filter results that passed guards
        passed_results = [r for r in all_results if r.passed_guards]
        
        if not passed_results:
            logger.warning("Stage 3: No results passed scoring guards")
            return []
        
        # Sort by score (descending)
        passed_results.sort(key=lambda r: r.score, reverse=True)
        
        # Select top N per anchor (if configured)
        if self.config.max_candidates_per_anchor > 0:
            # Group by anchor (need to extract anchor from param set)
            # This is simplified - actual implementation needs anchor mapping
            top_per_anchor = passed_results[:self.config.max_candidates_per_anchor * len(self.selected_anchors)]
        else:
            top_per_anchor = passed_results
        
        # Take top N overall
        top_n = min(self.config.union_top_n, len(top_per_anchor))
        self.final_candidates = top_per_anchor[:top_n]
        
        logger.info(f"Stage 3 completed: Selected {len(self.final_candidates)} "
                   f"candidates from {len(passed_results)} passing results")
        
        # Log top candidates
        for i, candidate in enumerate(self.final_candidates[:5]):  # Top 5
            logger.info(f"  Candidate {i+1}: score={candidate.score:.2f}, "
                       f"net={candidate.metrics.get('net_profit', 0):.0f}, "
                       f"trades={candidate.metrics.get('trades', 0)}")
        
        return self.final_candidates
    
    def run_full_pipeline(
        self,
        param_name: str,
        param_values: List[float],
        actual_signal_rates: List[float],
        base_entry_params: Dict[str, float],
        evaluate_param_set_fn
    ) -> Tuple[bool, List[EvaluationResult], Dict[str, Any]]:
        """
        Run full Mode B pipeline.
        
        Args:
            param_name: Name of parameter to anchor
            param_values: Parameter values for calibration
            actual_signal_rates: Actual signal rates for calibration
            base_entry_params: Base entry parameters
            evaluate_param_set_fn: Function to evaluate parameter sets
            
        Returns:
            Tuple of (success, final_candidates, pipeline_report)
        """
        logger.info("Starting Mode B pipeline")
        
        # Stage 1: Calibrate anchors
        if not self.stage1_calibrate_anchors(param_name, param_values, actual_signal_rates):
            return False, [], {"error": "Stage 1 calibration failed"}
        
        # Stage 2: Sweep exit plane
        all_results = self.stage2_sweep_exit_plane(
            base_entry_params, evaluate_param_set_fn
        )
        
        # Stage 3: Build union pool
        final_candidates = self.stage3_build_union_pool(all_results)
        
        # Create pipeline report
        report = self._create_pipeline_report(all_results, final_candidates)
        
        success = len(final_candidates) > 0
        logger.info(f"Mode B pipeline {'succeeded' if success else 'failed'}: "
                   f"found {len(final_candidates)} candidates")
        
        return success, final_candidates, report
    
    def _create_pipeline_report(
        self,
        all_results: List[EvaluationResult],
        final_candidates: List[EvaluationResult]
    ) -> Dict[str, Any]:
        """Create comprehensive pipeline report."""
        # Calculate statistics
        total_evaluated = len(all_results)
        passed_guards = sum(1 for r in all_results if r.passed_guards)
        guard_pass_rate = passed_guards / total_evaluated if total_evaluated > 0 else 0
        
        # Score distribution
        scores = [r.score for r in all_results]
        score_stats = {
            "min": float(np.min(scores)) if scores else 0.0,
            "max": float(np.max(scores)) if scores else 0.0,
            "mean": float(np.mean(scores)) if scores else 0.0,
            "median": float(np.median(scores)) if scores else 0.0
        }
        
        # Anchor statistics
        anchor_stats = {
            "total_anchors": len(self.anchors),
            "valid_anchors": len(self.selected_anchors),
            "anchor_values": [a.param_value for a in self.selected_anchors],
            "anchor_tsrs": [a.target_tsr for a in self.selected_anchors]
        }
        
        # Create structure filter
        structure_filter = create_mode_b_structure_filter(
            self.selected_anchors, "entry_param"  # param_name should be passed
        )
        
        return {
            "pipeline_status": "completed",
            "statistics": {
                "total_evaluated": total_evaluated,
                "passed_guards": passed_guards,
                "guard_pass_rate": guard_pass_rate,
                "final_candidates": len(final_candidates),
                "score_distribution": score_stats
            },
            "anchors": anchor_stats,
            "structure_filter": structure_filter,
            "top_candidates": [
                {
                    "param_id": c.param_set.param_id,
                    "score": c.score,
                    "net_profit": c.metrics.get("net_profit", 0.0),
                    "max_dd": c.metrics.get("max_dd", 0.0),
                    "trades": c.metrics.get("trades", 0),
                    "passed_guards": c.passed_guards
                }
                for c in final_candidates[:10]  # Top 10
            ]
        }


# Factory function for creating Mode B pipeline
def create_mode_b_pipeline(
    entry_param_name: str,
    exit_param_names: List[str],
    exit_param_ranges: Dict[str, Tuple[float, float, float]],  # (min, max, step)
    scoring_config: Optional[ScoringGuardConfig] = None,
    calibration_config: Optional[TSRCalibrationConfig] = None
) -> ModeBPipeline:
    """
    Factory function to create Mode B pipeline with sensible defaults.
    
    Args:
        entry_param_name: Name of entry parameter to anchor
        exit_param_names: List of exit parameter names to sweep
        exit_param_ranges: Dict mapping exit param names to (min, max, step)
        scoring_config: Optional scoring guard configuration
        calibration_config: Optional TSR calibration configuration
        
    Returns:
        Configured ModeBPipeline instance
    """
    # Default scoring config
    if scoring_config is None:
        scoring_config = ScoringGuardConfig(mode_b_enabled=True)
    
    # Default calibration config
    if calibration_config is None:
        calibration_config = TSRCalibrationConfig()
    
    # Create exit parameter grids
    exit_param_grids = {}
    for param_name in exit_param_names:
        if param_name in exit_param_ranges:
            min_val, max_val, step = exit_param_ranges[param_name]
            # Generate grid values
            num_steps = int((max_val - min_val) / step) + 1
            values = [min_val + i * step for i in range(num_steps)]
            exit_param_grids[param_name] = values
        else:
            # Default grid if not specified
            exit_param_grids[param_name] = [1.0, 2.0, 3.0]
    
    # Create Mode B config
    config = ModeBConfig(
        calibration_config=calibration_config,
        exit_param_names=exit_param_names,
        exit_param_grids=exit_param_grids,
        scoring_config=scoring_config,
        enforce_structure_test=True,
        require_cluster_test=True
    )
    
    return ModeBPipeline(config)


# Test function
if __name__ == "__main__":
    print("=== Testing Mode B Pipeline ===")
    
    # Create mock evaluation function
    def mock_evaluate_param_set(param_set: ParameterSet) -> Dict[str, float]:
        """Mock evaluation function for testing."""
        # Simulate some metrics based on parameters
        entry_sum = sum(param_set.entry_params.values()) if param_set.entry_params else 0
        exit_sum = sum(param_set.exit_params.values()) if param_set.exit_params else 0
        
        # Simple mock metrics
        return {
            "net_profit": 1000.0 + entry_sum * 10 + exit_sum * 5,
            "max_dd": 200.0 + abs(entry_sum) * 2,
            "trades": 50 + int(entry_sum) % 30,
            "net_profit_oat": [950.0, 1020.0, 980.0, 1010.0, 990.0],
            "max_dd_oat": [210.0, 190.0, 205.0, 195.0, 200.0],
            "trades_oat": [48, 52, 49, 51, 50]
        }
    
    # Create pipeline
    pipeline = create_mode_b_pipeline(
        entry_param_name="channel_len",
        exit_param_names=["stop_mult", "profit_target"],
        exit_param_ranges={
            "stop_mult": (1.0, 3.0, 0.5),
            "profit_target": (1.5, 4.0, 0.5)
        }
    )
    
    # Mock calibration data
    param_values = [10, 20, 30, 40, 50]
    actual_signal_rates = [0.05, 0.10, 0.15, 0.18, 0.20]
    
    # Run pipeline
    success, candidates, report = pipeline.run_full_pipeline(
        param_name="channel_len",
        param_values=param_values,
        actual_signal_rates=actual_signal_rates,
        base_entry_params={"some_other_param": 1.0},
        evaluate_param_set_fn=mock_evaluate_param_set
    )
    
    print(f"Pipeline success: {success}")
    print(f"Found {len(candidates)} candidates")
    
    if success:
        print(f"\nPipeline Report:")
        print(f"  Total evaluated: {report['statistics']['total_evaluated']}")
        print(f"  Passed guards: {report['statistics']['passed_guards']} "
              f"({report['statistics']['guard_pass_rate']*100:.1f}%)")
        print(f"  Final candidates: {report['statistics']['final_candidates']}")
        print(f"  Score range: {report['statistics']['score_distribution']['min']:.2f} to "
              f"{report['statistics']['score_distribution']['max']:.2f}")
        
        print(f"\nTop 3 candidates:")
        for i, candidate in enumerate(report['top_candidates'][:3]):
            print(f"  {i+1}. Score: {candidate['score']:.2f}, "
                  f"Net: ${candidate['net_profit']:.0f}, "
                  f"Trades: {candidate['trades']}")
    
    print("\n=== Mode B pipeline test completed ===")