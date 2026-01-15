"""
Red-Team Hardened WFS Scoring Guards (Section 3.1 + 5.2)

Implements anti-gaming scoring guards for WFS Mode B:
- TradeMultiplier cap: min(Trades, T_MAX)^ALPHA
- Minimum Edge Gate: Net/Trades >= MinAvgProfit
- FinalScore: (Net/(MDD+eps)) * TradeMultiplier
- RobustScore + Cliff Gates (Section 3.1.5)
- Cluster Test Hardening (Bimodality Defense)
"""

from __future__ import annotations

import math
import numpy as np
from typing import Dict, List, Tuple, Optional, TypedDict
from dataclasses import dataclass


class RawMetrics(TypedDict):
    """Raw metrics required for scoring guards."""
    net_profit: float  # Net profit (dollars)
    max_dd: float      # Maximum drawdown (dollars, positive)
    trades: int        # Number of trades
    # Additional metrics for robust scoring
    net_profit_oat: Optional[List[float]]  # OAT neighborhood net profits
    max_dd_oat: Optional[List[float]]      # OAT neighborhood max DDs
    trades_oat: Optional[List[int]]        # OAT neighborhood trades


@dataclass
class ScoringGuardConfig:
    """Configuration for scoring guards."""
    # Trade multiplier parameters
    t_max: int = 100          # Maximum trades for cap
    alpha: float = 0.25       # Exponent for trade multiplier
    
    # Minimum edge gate
    min_avg_profit: float = 5.0  # Minimum average profit per trade (dollars)
    
    # Robust scoring parameters
    oat_neighborhood_size: int = 5  # OAT neighborhood size
    robust_cliff_threshold: float = 0.7  # Cliff gate threshold (70% of base)
    
    # Cluster test parameters
    cluster_bimodality_threshold: float = 0.3  # Bimodality detection threshold
    min_cluster_size: int = 10  # Minimum cluster size
    
    # Mode B parameters
    mode_b_enabled: bool = False
    tsr_target: Optional[float] = None  # Target signal rate for TSR calibration
    anchor_tolerance: float = 0.1  # Tolerance for anchor matching


def compute_trade_multiplier(trades: int, config: ScoringGuardConfig) -> float:
    """
    Compute trade multiplier cap: min(Trades, T_MAX)^ALPHA
    
    Args:
        trades: Number of trades
        config: Scoring guard configuration
        
    Returns:
        Trade multiplier (0.0 to T_MAX^ALPHA)
    """
    capped_trades = min(trades, config.t_max)
    if capped_trades <= 0:
        return 0.0
    return math.pow(capped_trades, config.alpha)


def compute_min_edge_gate(net_profit: float, trades: int, config: ScoringGuardConfig) -> bool:
    """
    Minimum Edge Gate: Net/Trades >= MinAvgProfit
    
    Args:
        net_profit: Net profit (dollars)
        trades: Number of trades
        config: Scoring guard configuration
        
    Returns:
        True if passes minimum edge gate, False otherwise
    """
    if trades <= 0:
        return False
    avg_profit = net_profit / trades
    return avg_profit >= config.min_avg_profit


def compute_final_score(
    net_profit: float,
    max_dd: float,
    trades: int,
    config: ScoringGuardConfig
) -> Tuple[float, Dict[str, float]]:
    """
    Compute final score with anti-gaming guards.
    
    FinalScore = (Net/(MDD+eps)) * TradeMultiplier
    
    Args:
        net_profit: Net profit (dollars)
        max_dd: Maximum drawdown (dollars, positive)
        trades: Number of trades
        config: Scoring guard configuration
        
    Returns:
        Tuple of (final_score, breakdown_dict)
    """
    eps = 1e-10  # Small epsilon to avoid division by zero
    
    # Check minimum edge gate
    passes_edge_gate = compute_min_edge_gate(net_profit, trades, config)
    if not passes_edge_gate:
        return 0.0, {
            "net_profit": net_profit,
            "max_dd": max_dd,
            "trades": trades,
            "trade_multiplier": 0.0,
            "net_mdd_ratio": 0.0,
            "final_score": 0.0,
            "edge_gate_passed": False,
            "edge_gate_reason": f"Avg profit {net_profit/trades if trades>0 else 0:.2f} < {config.min_avg_profit}"
        }
    
    # Compute trade multiplier
    trade_multiplier = compute_trade_multiplier(trades, config)
    
    # Compute Net/MDD ratio
    if max_dd <= eps:
        # If no drawdown, use net_profit as ratio (capped)
        net_mdd_ratio = min(net_profit / eps, 100.0)  # Cap at reasonable value
    else:
        net_mdd_ratio = net_profit / max_dd
    
    # Compute final score
    final_score = net_mdd_ratio * trade_multiplier
    
    return final_score, {
        "net_profit": net_profit,
        "max_dd": max_dd,
        "trades": trades,
        "trade_multiplier": trade_multiplier,
        "net_mdd_ratio": net_mdd_ratio,
        "final_score": final_score,
        "edge_gate_passed": True,
        "edge_gate_reason": ""
    }


def compute_robust_stats(
    net_profit_base: float,
    max_dd_base: float,
    trades_base: int,
    net_profit_oat: List[float],
    max_dd_oat: List[float],
    trades_oat: List[int],
    config: ScoringGuardConfig
) -> Tuple[float, Dict[str, float]]:
    """
    Compute robust score with OAT (One-At-A-Time) neighborhood analysis.
    
    RobustScore = BaseScore * RobustnessFactor
    RobustnessFactor = min(1.0, median(neighbor_scores) / base_score)
    
    Cliff Gate: If any neighbor score < base_score * cliff_threshold, fail.
    
    Args:
        net_profit_base: Base net profit
        max_dd_base: Base max drawdown
        trades_base: Base trades
        net_profit_oat: List of OAT neighborhood net profits
        max_dd_oat: List of OAT neighborhood max DDs
        trades_oat: List of OAT neighborhood trades
        config: Scoring guard configuration
        
    Returns:
        Tuple of (robust_score, breakdown_dict)
    """
    # Compute base score
    base_score, base_breakdown = compute_final_score(
        net_profit_base, max_dd_base, trades_base, config
    )
    
    if base_score <= 0:
        return 0.0, {
            **base_breakdown,
            "robust_score": 0.0,
            "robustness_factor": 0.0,
            "cliff_gate_passed": False,
            "cliff_gate_reason": "Base score <= 0"
        }
    
    # Compute neighbor scores
    neighbor_scores = []
    valid_neighbors = 0
    
    for i in range(len(net_profit_oat)):
        if i >= len(max_dd_oat) or i >= len(trades_oat):
            continue
            
        neighbor_score, _ = compute_final_score(
            net_profit_oat[i], max_dd_oat[i], trades_oat[i], config
        )
        neighbor_scores.append(neighbor_score)
        valid_neighbors += 1
    
    if valid_neighbors == 0:
        # No valid neighbors, use base score
        return base_score, {
            **base_breakdown,
            "robust_score": base_score,
            "robustness_factor": 1.0,
            "cliff_gate_passed": True,
            "cliff_gate_reason": "No valid neighbors"
        }
    
    # Check cliff gate
    cliff_threshold = config.robust_cliff_threshold
    cliff_failures = 0
    for score in neighbor_scores:
        if score < base_score * cliff_threshold:
            cliff_failures += 1
    
    if cliff_failures > 0:
        return 0.0, {
            **base_breakdown,
            "robust_score": 0.0,
            "robustness_factor": 0.0,
            "cliff_gate_passed": False,
            "cliff_gate_reason": f"{cliff_failures} neighbors below {cliff_threshold*100:.0f}% of base"
        }
    
    # Compute robustness factor (median neighbor score / base score)
    median_neighbor_score = np.median(neighbor_scores) if neighbor_scores else 0.0
    robustness_factor = min(1.0, median_neighbor_score / base_score) if base_score > 0 else 0.0
    
    # Compute robust score
    robust_score = base_score * robustness_factor
    
    return robust_score, {
        **base_breakdown,
        "robust_score": robust_score,
        "robustness_factor": robustness_factor,
        "cliff_gate_passed": True,
        "cliff_gate_reason": "",
        "neighbor_scores_count": valid_neighbors,
        "median_neighbor_score": float(median_neighbor_score)
    }


def detect_bimodality_cluster(
    scores: List[float],
    config: ScoringGuardConfig
) -> Tuple[bool, Dict[str, float]]:
    """
    Detect bimodality in score distribution (cluster test hardening).
    
    Args:
        scores: List of scores to analyze
        config: Scoring guard configuration
        
    Returns:
        Tuple of (is_bimodal, cluster_stats)
    """
    if len(scores) < config.min_cluster_size * 2:
        # Not enough data for bimodality detection
        return False, {
            "is_bimodal": False,
            "reason": f"Insufficient data: {len(scores)} < {config.min_cluster_size * 2}",
            "cluster_separation": 0.0
        }
    
    # Convert to numpy array
    scores_arr = np.array(scores)
    
    # Simple bimodality detection using Hartigan's dip test approximation
    # Sort scores and look for significant gaps
    sorted_scores = np.sort(scores_arr)
    
    # Find largest gap in sorted scores
    gaps = np.diff(sorted_scores)
    max_gap_idx = np.argmax(gaps)
    max_gap = gaps[max_gap_idx]
    
    # Normalize gap by score range
    score_range = sorted_scores[-1] - sorted_scores[0]
    if score_range <= 0:
        normalized_gap = 0.0
    else:
        normalized_gap = max_gap / score_range
    
    # Check if gap indicates bimodality
    is_bimodal = normalized_gap > config.cluster_bimodality_threshold
    
    # Additional check: ensure clusters have sufficient size
    if is_bimodal:
        cluster1_size = max_gap_idx + 1
        cluster2_size = len(sorted_scores) - cluster1_size
        
        if (cluster1_size < config.min_cluster_size or 
            cluster2_size < config.min_cluster_size):
            is_bimodal = False
            reason = f"Cluster sizes too small: {cluster1_size}, {cluster2_size} < {config.min_cluster_size}"
        else:
            reason = f"Bimodal detected: gap {normalized_gap:.3f} > {config.cluster_bimodality_threshold}"
    else:
        reason = f"No bimodality: gap {normalized_gap:.3f} <= {config.cluster_bimodality_threshold}"
    
    return is_bimodal, {
        "is_bimodal": is_bimodal,
        "reason": reason,
        "cluster_separation": float(normalized_gap),
        "cluster1_size": max_gap_idx + 1 if is_bimodal else 0,
        "cluster2_size": len(sorted_scores) - (max_gap_idx + 1) if is_bimodal else 0
    }


def apply_scoring_guards(
    raw_metrics: RawMetrics,
    config: Optional[ScoringGuardConfig] = None
) -> Dict[str, any]:
    """
    Apply all scoring guards to raw metrics.
    
    Args:
        raw_metrics: Raw metrics dictionary
        config: Scoring guard configuration (uses default if None)
        
    Returns:
        Comprehensive scoring result with all guards applied
    """
    if config is None:
        config = ScoringGuardConfig()
    
    # Extract base metrics
    net_profit = raw_metrics.get("net_profit", 0.0)
    max_dd = raw_metrics.get("max_dd", 0.0)
    trades = raw_metrics.get("trades", 0)
    
    # Extract OAT metrics if available
    net_profit_oat = raw_metrics.get("net_profit_oat")
    max_dd_oat = raw_metrics.get("max_dd_oat")
    trades_oat = raw_metrics.get("trades_oat")
    
    # Compute base score
    base_score, base_breakdown = compute_final_score(
        net_profit, max_dd, trades, config
    )
    
    result = {
        "base_score": base_score,
        **base_breakdown,
        "config": {
            "t_max": config.t_max,
            "alpha": config.alpha,
            "min_avg_profit": config.min_avg_profit,
            "robust_cliff_threshold": config.robust_cliff_threshold,
            "cluster_bimodality_threshold": config.cluster_bimodality_threshold,
            "mode_b_enabled": config.mode_b_enabled
        }
    }
    
    # Apply robust scoring if OAT metrics available
    if (net_profit_oat is not None and max_dd_oat is not None and trades_oat is not None and
        len(net_profit_oat) > 0 and len(max_dd_oat) > 0 and len(trades_oat) > 0):
        
        robust_score, robust_breakdown = compute_robust_stats(
            net_profit, max_dd, trades,
            net_profit_oat, max_dd_oat, trades_oat,
            config
        )
        
        result.update({
            "robust_score": robust_score,
            **{k: v for k, v in robust_breakdown.items() if k not in base_breakdown}
        })
        
        # Use robust score as final if available
        result["final_score"] = robust_score
    else:
        result["robust_score"] = base_score
        result["final_score"] = base_score
        result["robustness_factor"] = 1.0
        result["cliff_gate_passed"] = True
        result["cliff_gate_reason"] = "No OAT metrics available"
    
    # Apply cluster test if multiple scores available
    if net_profit_oat is not None and len(net_profit_oat) >= config.min_cluster_size * 2:
        # Create scores list from OAT metrics
        oat_scores = []
        for i in range(min(len(net_profit_oat), len(max_dd_oat), len(trades_oat))):
            score, _ = compute_final_score(
                net_profit_oat[i], max_dd_oat[i], trades_oat[i], config
            )
            oat_scores.append(score)
        
        is_bimodal, cluster_stats = detect_bimodality_cluster(oat_scores, config)
        result["cluster_test"] = cluster_stats
        
        if is_bimodal:
            # Penalize bimodal distributions
            result["final_score"] *= 0.5  # 50% penalty for bimodality
            result["cluster_penalty_applied"] = True
        else:
            result["cluster_penalty_applied"] = False
    else:
        result["cluster_test"] = {
            "is_bimodal": False,
            "reason": "Insufficient OAT metrics for cluster test"
        }
        result["cluster_penalty_applied"] = False
    
    # Mode B specific logic
    if config.mode_b_enabled:
        result["mode_b"] = {
            "enabled": True,
            "tsr_target": config.tsr_target,
            "anchor_tolerance": config.anchor_tolerance,
            "note": "Mode B logic to be implemented in separate module"
        }
    
    return result


# Default configuration for backward compatibility
DEFAULT_CONFIG = ScoringGuardConfig()


def score_with_guards(
    net_profit: float,
    max_dd: float,
    trades: int,
    config: Optional[ScoringGuardConfig] = None
) -> Dict[str, any]:
    """
    Simplified interface for scoring with guards.
    
    Args:
        net_profit: Net profit (dollars)
        max_dd: Maximum drawdown (dollars, positive)
        trades: Number of trades
        config: Scoring guard configuration
        
    Returns:
        Scoring result dictionary
    """
    raw_metrics: RawMetrics = {
        "net_profit": net_profit,
        "max_dd": max_dd,
        "trades": trades,
        "net_profit_oat": None,
        "max_dd_oat": None,
        "trades_oat": None
    }
    
    return apply_scoring_guards(raw_metrics, config)


# Test function
if __name__ == "__main__":
    # Test basic scoring
    print("=== Testing Scoring Guards ===")
    
    # Test 1: Good strategy
    result1 = score_with_guards(
        net_profit=1000.0,
        max_dd=200.0,
        trades=50
    )
    print(f"Test 1 (Good): Final Score = {result1['final_score']:.2f}")
    print(f"  Trade Multiplier: {result1['trade_multiplier']:.2f}")
    print(f"  Net/MDD Ratio: {result1['net_mdd_ratio']:.2f}")
    print(f"  Edge Gate: {'PASS' if result1['edge_gate_passed'] else 'FAIL'}")
    
    # Test 2: Low average profit (should fail edge gate)
    result2 = score_with_guards(
        net_profit=100.0,
        max_dd=50.0,
        trades=50
    )
    print(f"\nTest 2 (Low Avg Profit): Final Score = {result2['final_score']:.2f}")
    print(f"  Edge Gate: {'PASS' if result2['edge_gate_passed'] else 'FAIL'}")
    if not result2['edge_gate_passed']:
        print(f"  Reason: {result2['edge_gate_reason']}")
    
    # Test 3: High drawdown
    result3 = score_with_guards(
        net_profit=500.0,
        max_dd=1000.0,
        trades=30
    )
    print(f"\nTest 3 (High DD): Final Score = {result3['final_score']:.2f}")
    print(f"  Net/MDD Ratio: {result3['net_mdd_ratio']:.2f}")
    
    # Test 4: Many trades (capped by T_MAX)
    result4 = score_with_guards(
        net_profit=2000.0,
        max_dd=300.0,
        trades=200
    )
    print(f"\nTest 4 (Many Trades): Final Score = {result4['final_score']:.2f}")
    print(f"  Trade Multiplier: {result4['trade_multiplier']:.2f} (capped at {result4['config']['t_max']}^{result4['config']['alpha']})")
    
    print("\n=== All tests completed ===")
