"""Governance evaluator - rule engine for candidate decisions.

Reads artifacts from stage run directories and applies governance rules
to produce KEEP/FREEZE/DROP decisions for each candidate.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from FishBroWFS_V2.core.artifact_reader import (
    read_config_snapshot,
    read_manifest,
    read_metrics,
    read_winners,
)
from FishBroWFS_V2.core.config_hash import stable_config_hash
from FishBroWFS_V2.core.governance_schema import (
    Decision,
    EvidenceRef,
    GovernanceItem,
    GovernanceReport,
)
from FishBroWFS_V2.core.winners_schema import is_winners_v2


# Rule thresholds (MVP - locked)
R2_DEGRADE_THRESHOLD = 0.20  # 20% degradation threshold for R2
R3_DENSITY_THRESHOLD = 3  # Minimum count for R3 FREEZE (same strategy_id)


def normalize_candidate(
    item: Dict[str, Any],
    config_snapshot: Optional[Dict[str, Any]] = None,
    is_v2: bool = False,
) -> Tuple[str, Dict[str, Any], Dict[str, Any]]:
    """
    Normalize candidate from winners.json to (strategy_id, params_dict, metrics_subset).
    
    Handles both v2 and legacy formats gracefully.
    
    Args:
        item: Candidate item from winners.json topk list
        config_snapshot: Optional config snapshot to extract params from
        is_v2: Whether item is from v2 schema (fast path)
        
    Returns:
        Tuple of (strategy_id, params_dict, metrics_subset)
        - strategy_id: Strategy identifier
        - params_dict: Normalized params dict
        - metrics_subset: Metrics dict extracted from item
    """
    # Fast path for v2 schema
    if is_v2:
        strategy_id = item.get("strategy_id", "unknown")
        params_dict = item.get("params", {})
        
        # Extract metrics from v2 structure
        metrics_subset = {}
        metrics = item.get("metrics", {})
        
        # Legacy fields (for backward compatibility)
        if "net_profit" in metrics:
            metrics_subset["net_profit"] = float(metrics["net_profit"])
        if "trades" in metrics:
            metrics_subset["trades"] = int(metrics["trades"])
        if "max_dd" in metrics:
            metrics_subset["max_dd"] = float(metrics["max_dd"])
        if "proxy_value" in metrics:
            metrics_subset["proxy_value"] = float(metrics["proxy_value"])
        
        # Also check top-level (legacy compatibility)
        if "net_profit" in item:
            metrics_subset["net_profit"] = float(item["net_profit"])
        if "trades" in item:
            metrics_subset["trades"] = int(item["trades"])
        if "max_dd" in item:
            metrics_subset["max_dd"] = float(item["max_dd"])
        if "proxy_value" in item:
            metrics_subset["proxy_value"] = float(item["proxy_value"])
        
        return strategy_id, params_dict, metrics_subset
    
    # Legacy path (backward compatibility)
    # Extract metrics subset (varies by stage)
    metrics_subset = {}
    if "proxy_value" in item:
        metrics_subset["proxy_value"] = float(item["proxy_value"])
    if "net_profit" in item:
        metrics_subset["net_profit"] = float(item["net_profit"])
    if "trades" in item:
        metrics_subset["trades"] = int(item["trades"])
    if "max_dd" in item:
        metrics_subset["max_dd"] = float(item["max_dd"])
    
    # MVP: Use fixed strategy_id (donchian_atr)
    # Future: Extract from config_snapshot or item metadata
    strategy_id = "donchian_atr"
    
    # Extract params_dict
    # Priority: 1) item["params"], 2) config_snapshot params, 3) fallback to param_id-based dict
    params_dict = item.get("params", {})
    
    if not params_dict and config_snapshot:
        # Try to extract from config_snapshot
        # MVP: If params_matrix is in config_snapshot, extract row by param_id
        # For now, use param_id as fallback
        param_id = item.get("param_id")
        if param_id is not None:
            # MVP fallback: Create minimal params dict from param_id
            # Future: Extract actual params from params_matrix in config_snapshot
            params_dict = {"param_id": int(param_id)}
    
    if not params_dict:
        # Final fallback: use param_id if available
        param_id = item.get("param_id")
        if param_id is not None:
            params_dict = {"param_id": int(param_id)}
        else:
            params_dict = {}
    
    return strategy_id, params_dict, metrics_subset


def generate_candidate_id(strategy_id: str, params_dict: Dict[str, Any]) -> str:
    """
    Generate stable candidate_id from strategy_id and params_dict.
    
    Format: {strategy_id}:{params_hash[:12]}
    
    Args:
        strategy_id: Strategy identifier
        params_dict: Parameters dict (must be JSON-serializable)
        
    Returns:
        Stable candidate_id string
    """
    # Compute stable hash of params_dict
    params_hash = stable_config_hash(params_dict)
    
    # Use first 12 chars of hash
    hash_short = params_hash[:12]
    
    return f"{strategy_id}:{hash_short}"


def find_stage2_candidate(
    candidate_param_id: int,
    stage2_winners: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """
    Find Stage2 candidate matching param_id.
    
    Args:
        candidate_param_id: param_id from Stage1 winner
        stage2_winners: List of Stage2 winners
        
    Returns:
        Matching Stage2 candidate dict, or None if not found
    """
    for item in stage2_winners:
        if item.get("param_id") == candidate_param_id:
            return item
    return None


def extract_key_metric(
    metrics: Dict[str, Any],
    candidate_metrics: Dict[str, Any],
    metric_name: str,
) -> Optional[float]:
    """
    Extract key metric with fallback logic.
    
    Priority:
    1. candidate_metrics[metric_name]
    2. metrics[metric_name]
    3. Fallback: net_profit / max_dd (if both exist)
    4. None
    
    Args:
        metrics: Stage metrics dict
        candidate_metrics: Candidate-specific metrics dict
        metric_name: Metric name to extract
        
    Returns:
        Metric value (float), or None if not found
    """
    # Try candidate_metrics first
    if metric_name in candidate_metrics:
        val = candidate_metrics[metric_name]
        if isinstance(val, (int, float)):
            return float(val)
    
    # Try stage metrics
    if metric_name in metrics:
        val = metrics[metric_name]
        if isinstance(val, (int, float)):
            return float(val)
    
    # Fallback: net_profit / max_dd (if both exist)
    if metric_name in ("finalscore", "net_over_mdd"):
        net_profit = candidate_metrics.get("net_profit") or metrics.get("net_profit")
        max_dd = candidate_metrics.get("max_dd") or metrics.get("max_dd")
        if net_profit is not None and max_dd is not None:
            if abs(max_dd) > 1e-10:  # Avoid division by zero
                return float(net_profit) / abs(float(max_dd))
            elif float(net_profit) > 0:
                return float("inf")  # Positive profit with zero DD
            else:
                return float("-inf")  # Negative profit with zero DD
    
    return None


def apply_rule_r1(
    candidate: Dict[str, Any],
    stage2_winners: List[Dict[str, Any]],
    is_v2: bool = False,
) -> Tuple[bool, str]:
    """
    Rule R1: Evidence completeness.
    
    If candidate appears in Stage1 winners but:
    - Cannot find corresponding Stage2 metrics (or Stage2 did not run successfully)
    -> DROP (reason: unverified)
    
    Args:
        candidate: Candidate from Stage1 winners
        stage2_winners: List of Stage2 winners
        is_v2: Whether candidates are v2 schema
        
    Returns:
        Tuple of (should_drop, reason)
    """
    # For v2: use candidate_id for matching
    if is_v2:
        candidate_id = candidate.get("candidate_id")
        if candidate_id is None:
            return True, "missing_candidate_id"
        
        # Find matching candidate by candidate_id
        for item in stage2_winners:
            if item.get("candidate_id") == candidate_id:
                return False, ""
        
        return True, "unverified"
    
    # Legacy path: use param_id
    param_id = candidate.get("param_id")
    if param_id is None:
        # Try to extract from source (v2 fallback)
        source = candidate.get("source", {})
        param_id = source.get("param_id")
        if param_id is None:
            # Try metrics (v2 fallback)
            metrics = candidate.get("metrics", {})
            param_id = metrics.get("param_id")
            if param_id is None:
                return True, "missing_param_id"
    
    stage2_match = find_stage2_candidate(param_id, stage2_winners)
    if stage2_match is None:
        return True, "unverified"
    
    return False, ""


def apply_rule_r2(
    candidate: Dict[str, Any],
    stage1_metrics: Dict[str, Any],
    stage2_candidate: Dict[str, Any],
    stage2_metrics: Dict[str, Any],
) -> Tuple[bool, str]:
    """
    Rule R2: Confirm stability.
    
    If candidate's key metrics degrade > threshold in Stage2 vs Stage1 -> DROP.
    
    Priority:
    1. finalscore or net_over_mdd
    2. Fallback: net_profit / max_dd
    
    Args:
        candidate: Candidate from Stage1 winners
        stage1_metrics: Stage1 metrics dict
        stage2_candidate: Matching Stage2 candidate
        stage2_metrics: Stage2 metrics dict
        
    Returns:
        Tuple of (should_drop, reason)
    """
    # Extract Stage1 metric
    stage1_val = extract_key_metric(
        stage1_metrics,
        candidate,
        "finalscore",
    )
    if stage1_val is None:
        stage1_val = extract_key_metric(
            stage1_metrics,
            candidate,
            "net_over_mdd",
        )
    if stage1_val is None:
        # Fallback: net_profit / max_dd
        stage1_val = extract_key_metric(
            stage1_metrics,
            candidate,
            "net_over_mdd",
        )
    
    # Extract Stage2 metric
    stage2_val = extract_key_metric(
        stage2_metrics,
        stage2_candidate,
        "finalscore",
    )
    if stage2_val is None:
        stage2_val = extract_key_metric(
            stage2_metrics,
            stage2_candidate,
            "net_over_mdd",
        )
    if stage2_val is None:
        # Fallback: net_profit / max_dd
        stage2_val = extract_key_metric(
            stage2_metrics,
            stage2_candidate,
            "net_over_mdd",
        )
    
    # If either metric is missing, cannot apply R2
    if stage1_val is None or stage2_val is None:
        return False, ""
    
    # Check degradation
    if stage1_val == 0.0:
        # Avoid division by zero
        if stage2_val < 0.0:
            return True, f"degraded_from_zero_to_negative"
        return False, ""
    
    degradation_ratio = (stage1_val - stage2_val) / abs(stage1_val)
    if degradation_ratio > R2_DEGRADE_THRESHOLD:
        return True, f"degraded_{degradation_ratio:.2%}"
    
    return False, ""


def apply_rule_r3(
    candidate: Dict[str, Any],
    all_stage1_winners: List[Dict[str, Any]],
) -> Tuple[bool, str]:
    """
    Rule R3: Plateau hint (MVP simplified version).
    
    If same strategy_id appears >= threshold times in Stage1 topk -> FREEZE.
    
    MVP version: Count occurrences of same strategy_id (simplified).
    Future: Geometric distance/clustering analysis.
    
    Args:
        candidate: Candidate from Stage1 winners
        all_stage1_winners: All Stage1 winners (for density calculation)
        
    Returns:
        Tuple of (should_freeze, reason)
    """
    strategy_id, _, _ = normalize_candidate(candidate)
    
    # Count occurrences of same strategy_id
    count = 0
    for item in all_stage1_winners:
        item_strategy_id, _, _ = normalize_candidate(item)
        if item_strategy_id == strategy_id:
            count += 1
    
    if count >= R3_DENSITY_THRESHOLD:
        return True, f"density_{count}_over_threshold_{R3_DENSITY_THRESHOLD}"
    
    return False, ""


def evaluate_governance(
    *,
    stage0_dir: Path,
    stage1_dir: Path,
    stage2_dir: Path,
) -> GovernanceReport:
    """
    Evaluate governance rules on candidates from Stage1 winners.
    
    Reads artifacts from three stage directories and applies rules:
    - R1: Evidence completeness (DROP if Stage2 missing)
    - R2: Confirm stability (DROP if metrics degrade > threshold)
    - R3: Plateau hint (FREEZE if density over threshold)
    
    Args:
        stage0_dir: Path to Stage0 run directory
        stage1_dir: Path to Stage1 run directory
        stage2_dir: Path to Stage2 run directory
        
    Returns:
        GovernanceReport with decisions for each candidate
    """
    # Read artifacts
    stage0_manifest = read_manifest(stage0_dir)
    stage0_metrics = read_metrics(stage0_dir)
    stage0_winners = read_winners(stage0_dir)
    stage0_config = read_config_snapshot(stage0_dir)
    
    stage1_manifest = read_manifest(stage1_dir)
    stage1_metrics = read_metrics(stage1_dir)
    stage1_winners = read_winners(stage1_dir)
    stage1_config = read_config_snapshot(stage1_dir)
    
    stage2_manifest = read_manifest(stage2_dir)
    stage2_metrics = read_metrics(stage2_dir)
    stage2_winners = read_winners(stage2_dir)
    stage2_config = read_config_snapshot(stage2_dir)
    
    # Extract candidates from Stage1 winners (topk)
    stage1_topk = stage1_winners.get("topk", [])
    
    # Check if winners is v2 schema
    stage1_is_v2 = is_winners_v2(stage1_winners)
    
    # Get git_sha and created_at from Stage1 manifest
    git_sha = stage1_manifest.get("git_sha", "unknown")
    created_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    # Build governance items
    items: List[GovernanceItem] = []
    
    for candidate in stage1_topk:
        # Normalize candidate (pass stage1_config for params extraction, and is_v2 flag)
        strategy_id, params_dict, metrics_subset = normalize_candidate(
            candidate, stage1_config, is_v2=stage1_is_v2
        )
        
        # Generate candidate_id
        candidate_id = generate_candidate_id(strategy_id, params_dict)
        
        # Apply rules
        reasons: List[str] = []
        evidence: List[EvidenceRef] = []
        decision = Decision.KEEP  # Default
        
        # R1: Evidence completeness
        # Check if Stage2 is v2 (for candidate matching)
        stage2_is_v2 = is_winners_v2(stage2_winners)
        should_drop_r1, reason_r1 = apply_rule_r1(
            candidate, stage2_winners.get("topk", []), is_v2=stage2_is_v2
        )
        if should_drop_r1:
            decision = Decision.DROP
            reasons.append(f"R1: {reason_r1}")
            # Add evidence
            evidence.append(
                EvidenceRef(
                    run_id=stage1_manifest.get("run_id", "unknown"),
                    stage_name="stage1_topk",
                    artifact_paths=["manifest.json", "metrics.json", "winners.json"],
                    key_metrics={
                        "param_id": candidate.get("param_id"),
                        **metrics_subset,
                    },
                )
            )
            # Create item and continue (no need to check R2/R3)
            items.append(
                GovernanceItem(
                    candidate_id=candidate_id,
                    decision=decision,
                    reasons=reasons,
                    evidence=evidence,
                    created_at=created_at,
                    git_sha=git_sha,
                )
            )
            continue
        
        # R2: Confirm stability
        # Find Stage2 candidate (support both v2 and legacy)
        if stage1_is_v2:
            candidate_id = candidate.get("candidate_id")
            stage2_candidate = None
            if candidate_id:
                for item in stage2_winners.get("topk", []):
                    if item.get("candidate_id") == candidate_id:
                        stage2_candidate = item
                        break
        else:
            param_id = candidate.get("param_id")
            if param_id is None:
                # Try source/metrics fallback
                source = candidate.get("source", {})
                param_id = source.get("param_id") or candidate.get("metrics", {}).get("param_id")
            stage2_candidate = find_stage2_candidate(
                param_id,
                stage2_winners.get("topk", []),
            ) if param_id is not None else None
        if stage2_candidate is not None:
            should_drop_r2, reason_r2 = apply_rule_r2(
                candidate,
                stage1_metrics,
                stage2_candidate,
                stage2_metrics,
            )
            if should_drop_r2:
                decision = Decision.DROP
                reasons.append(f"R2: {reason_r2}")
                # Add evidence
                evidence.append(
                    EvidenceRef(
                        run_id=stage1_manifest.get("run_id", "unknown"),
                        stage_name="stage1_topk",
                        artifact_paths=["manifest.json", "metrics.json", "winners.json"],
                        key_metrics={
                            "param_id": candidate.get("param_id"),
                            **metrics_subset,
                        },
                    )
                )
                evidence.append(
                    EvidenceRef(
                        run_id=stage2_manifest.get("run_id", "unknown"),
                        stage_name="stage2_confirm",
                        artifact_paths=["manifest.json", "metrics.json", "winners.json"],
                        key_metrics={
                            "param_id": stage2_candidate.get("param_id"),
                            "net_profit": stage2_candidate.get("net_profit"),
                            "trades": stage2_candidate.get("trades"),
                            "max_dd": stage2_candidate.get("max_dd"),
                        },
                    )
                )
                # Create item and continue (no need to check R3)
                items.append(
                    GovernanceItem(
                        candidate_id=candidate_id,
                        decision=decision,
                        reasons=reasons,
                        evidence=evidence,
                        created_at=created_at,
                        git_sha=git_sha,
                    )
                )
                continue
        
        # R3: Plateau hint (needs normalized strategy_id)
        should_freeze_r3, reason_r3 = apply_rule_r3(candidate, stage1_topk)
        if should_freeze_r3:
            decision = Decision.FREEZE
            reasons.append(f"R3: {reason_r3}")
        
        # Add evidence (always include Stage1 and Stage2 if available)
        evidence.append(
            EvidenceRef(
                run_id=stage1_manifest.get("run_id", "unknown"),
                stage_name="stage1_topk",
                artifact_paths=["manifest.json", "metrics.json", "winners.json", "config_snapshot.json"],
                key_metrics={
                    "param_id": candidate.get("param_id"),
                    **metrics_subset,
                    "stage_planned_subsample": stage1_metrics.get("stage_planned_subsample"),
                    "param_subsample_rate": stage1_metrics.get("param_subsample_rate"),
                    "params_effective": stage1_metrics.get("params_effective"),
                },
            )
        )
        if stage2_candidate is not None:
            evidence.append(
                EvidenceRef(
                    run_id=stage2_manifest.get("run_id", "unknown"),
                    stage_name="stage2_confirm",
                    artifact_paths=["manifest.json", "metrics.json", "winners.json", "config_snapshot.json"],
                    key_metrics={
                        "param_id": stage2_candidate.get("param_id"),
                        "net_profit": stage2_candidate.get("net_profit"),
                        "trades": stage2_candidate.get("trades"),
                        "max_dd": stage2_candidate.get("max_dd"),
                        "param_subsample_rate": stage2_metrics.get("param_subsample_rate"),
                        "params_effective": stage2_metrics.get("params_effective"),
                    },
                )
            )
        
        # Create item
        items.append(
            GovernanceItem(
                candidate_id=candidate_id,
                decision=decision,
                reasons=reasons,
                evidence=evidence,
                created_at=created_at,
                git_sha=git_sha,
            )
        )
    
    # Build metadata
    metadata = {
        "governance_id": stage1_manifest.get("run_id", "unknown"),  # Use Stage1 run_id as base
        "season": stage1_manifest.get("season", "unknown"),
        "created_at": created_at,
        "git_sha": git_sha,
        "stage0_run_id": stage0_manifest.get("run_id", "unknown"),
        "stage1_run_id": stage1_manifest.get("run_id", "unknown"),
        "stage2_run_id": stage2_manifest.get("run_id", "unknown"),
        "total_candidates": len(items),
        "decisions": {
            "KEEP": sum(1 for item in items if item.decision == Decision.KEEP),
            "FREEZE": sum(1 for item in items if item.decision == Decision.FREEZE),
            "DROP": sum(1 for item in items if item.decision == Decision.DROP),
        },
    }
    
    return GovernanceReport(items=items, metadata=metadata)
