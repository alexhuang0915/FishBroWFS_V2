"""
Ranking Explain Builder for DP6 Phase I & II.

Builds explainable ranking reports from SSOT artifacts (winners.json, plateau_report.json).
Phase I is INFO-only, context-aware, and plateau-artifact-gated.
Phase II adds WARN/ERROR severity for governance/risk layer (concentration, plateau quality, robustness).
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Dict, List, Optional, Any

from contracts.ranking_explain import (
    RankingExplainContext,
    RankingExplainSeverity,
    RankingExplainReasonCode,
    RankingExplainReasonCard,
    RankingExplainReport,
    get_context_wording,
    get_research_actions,
)
from contracts.ranking_explain_config import DEFAULT_RANKING_EXPLAIN_CONFIG
from wfs.scoring_guards import ScoringGuardConfig, compute_final_score


def build_ranking_explain_report(
    *,
    context: RankingExplainContext,
    job_id: str,
    winners: dict,
    plateau_report: dict | None,
    scoring_guard_cfg: ScoringGuardConfig,
    ranking_explain_config: Optional[Any] = None,
    warnings: List[str] | None = None,
) -> RankingExplainReport:
    """
    Build ranking explain report from SSOT artifacts.
    
    Args:
        context: CANDIDATE or FINAL_SELECTION
        job_id: Job identifier
        winners: Winners.json data (v2 schema)
        plateau_report: Plateau report data or None
        scoring_guard_cfg: Scoring guard configuration
        ranking_explain_config: Optional ranking explain configuration for Phase II
        
    Returns:
        RankingExplainReport with context-aware reason cards
    """
    # Extract scoring formula details
    scoring_details = {
        "formula": "FinalScore = (Net/(MDD+eps)) * min(Trades, T_MAX)^ALPHA",
        "t_max": scoring_guard_cfg.t_max,
        "alpha": scoring_guard_cfg.alpha,
        "min_avg_profit": scoring_guard_cfg.min_avg_profit,
        "robust_cliff_threshold": scoring_guard_cfg.robust_cliff_threshold,
    }
    
    # Use default config if not provided
    if ranking_explain_config is None:
        ranking_explain_config = DEFAULT_RANKING_EXPLAIN_CONFIG
    
    # Build reason cards based on SSOT
    reason_cards = _build_reason_cards(
        context=context,
        job_id=job_id,
        winners=winners,
        plateau_report=plateau_report,
        scoring_guard_cfg=scoring_guard_cfg,
        ranking_explain_config=ranking_explain_config,
        warnings=warnings,
    )
    
    # Create the report
    report = RankingExplainReport(
        context=context,
        job_id=job_id,
        scoring=scoring_details,
        reasons=reason_cards,
    )
    
    return report


def _build_reason_cards(
    context: RankingExplainContext,
    job_id: str,
    winners: dict,
    plateau_report: dict | None,
    scoring_guard_cfg: ScoringGuardConfig,
    ranking_explain_config: Any,
    warnings: List[str] | None,
) -> List[RankingExplainReasonCard]:
    """Build context-aware reason cards from SSOT artifacts."""
    reason_cards = []
    
    # 1. Score formula reason (always present)
    reason_cards.append(_build_score_formula_reason(context, scoring_guard_cfg))
    
    # 2. Extract metrics from winners for threshold analysis
    if "topk" in winners and winners["topk"]:
        top_candidate = winners["topk"][0]  # Highest ranked candidate
        metrics = top_candidate.get("metrics", {})
        
        # Add threshold reasons if applicable
        reason_cards.extend(
            _build_threshold_reasons(context, metrics, scoring_guard_cfg)
        )
        
        # Add metric summary reason
        reason_cards.append(
            _build_metric_summary_reason(context, metrics)
        )
        
        # Phase II: Add concentration analysis
        reason_cards.extend(
            _build_concentration_reasons(context, winners, ranking_explain_config)
        )
        
        # Phase II: Add robustness checks
        reason_cards.extend(
            _build_robustness_reasons(context, metrics, scoring_guard_cfg, ranking_explain_config)
        )
    
    # 3. Plateau artifact reasons (artifact-gated)
    if plateau_report:
        reason_cards.append(
            _build_plateau_confirmed_reason(context, plateau_report)
        )
        # Phase II: Add plateau quality evaluation
        reason_cards.extend(
            _build_plateau_quality_reasons(context, plateau_report, ranking_explain_config)
        )
    else:
        reason_cards.append(
            _build_missing_plateau_reason(context)
        )
        # Phase II: Add plateau missing artifact reason (WARN severity)
        reason_cards.append(
            _build_plateau_missing_artifact_reason(context)
        )
    
    # 4. Runtime warnings (P2)
    if warnings:
        reason_cards.extend(
            _build_warning_reasons(context, warnings)
        )
    
    return reason_cards


def _build_score_formula_reason(
    context: RankingExplainContext,
    scoring_guard_cfg: ScoringGuardConfig,
) -> RankingExplainReasonCard:
    """Build reason card for scoring formula."""
    formula_details = {
        "formula": "FinalScore = (Net/(MDD+eps)) * min(Trades, T_MAX)^ALPHA",
        "t_max": scoring_guard_cfg.t_max,
        "alpha": scoring_guard_cfg.alpha,
        "min_avg_profit": scoring_guard_cfg.min_avg_profit,
    }
    
    title, summary = get_context_wording(
        context=context,
        code=RankingExplainReasonCode.SCORE_FORMULA,
        metric_values=formula_details,
    )
    
    return RankingExplainReasonCard(
        code=RankingExplainReasonCode.SCORE_FORMULA,
        severity=RankingExplainSeverity.INFO,
        title=title,
        summary=summary,
        actions=get_research_actions(RankingExplainReasonCode.SCORE_FORMULA),
        details=formula_details,
    )


def _build_threshold_reasons(
    context: RankingExplainContext,
    metrics: Dict[str, Any],
    scoring_guard_cfg: ScoringGuardConfig,
) -> List[RankingExplainReasonCard]:
    """Build reason cards for threshold applications."""
    reasons = []
    
    net_profit = metrics.get("net_profit", 0.0)
    trades = metrics.get("trades", 0)
    max_dd = abs(metrics.get("max_dd", 0.0))  # Convert negative to positive
    
    # Check if trade count exceeds t_max
    if trades > scoring_guard_cfg.t_max:
        threshold_details = {
            "trades": trades,
            "t_max": scoring_guard_cfg.t_max,
            "capped_trades": min(trades, scoring_guard_cfg.t_max),
        }
        
        title, summary = get_context_wording(
            context=context,
            code=RankingExplainReasonCode.THRESHOLD_TMAX_APPLIED,
            metric_values=threshold_details,
        )
        
        reasons.append(RankingExplainReasonCard(
            code=RankingExplainReasonCode.THRESHOLD_TMAX_APPLIED,
            severity=RankingExplainSeverity.INFO,
            title=title,
            summary=summary,
            actions=get_research_actions(RankingExplainReasonCode.THRESHOLD_TMAX_APPLIED),
            details=threshold_details,
        ))
    
    # Check minimum average profit
    if trades > 0:
        avg_profit = net_profit / trades
        if avg_profit >= scoring_guard_cfg.min_avg_profit:
            threshold_details = {
                "avg_profit": avg_profit,
                "min_avg_profit": scoring_guard_cfg.min_avg_profit,
            }
            
            title, summary = get_context_wording(
                context=context,
                code=RankingExplainReasonCode.THRESHOLD_MIN_AVG_PROFIT_APPLIED,
                metric_values=threshold_details,
            )
            
            reasons.append(RankingExplainReasonCard(
                code=RankingExplainReasonCode.THRESHOLD_MIN_AVG_PROFIT_APPLIED,
                severity=RankingExplainSeverity.INFO,
                title=title,
                summary=summary,
                actions=get_research_actions(RankingExplainReasonCode.THRESHOLD_MIN_AVG_PROFIT_APPLIED),
                details=threshold_details,
            ))
    
    return reasons


def _build_metric_summary_reason(
    context: RankingExplainContext,
    metrics: Dict[str, Any],
) -> RankingExplainReasonCard:
    """Build reason card for metric summary."""
    net_profit = metrics.get("net_profit", 0.0)
    trades = metrics.get("trades", 0)
    max_dd = abs(metrics.get("max_dd", 0.0))  # Convert negative to positive
    
    metric_details = {
        "net_profit": net_profit,
        "max_dd": max_dd,
        "trades": trades,
    }
    
    title, summary = get_context_wording(
        context=context,
        code=RankingExplainReasonCode.METRIC_SUMMARY,
        metric_values=metric_details,
    )
    
    return RankingExplainReasonCard(
        code=RankingExplainReasonCode.METRIC_SUMMARY,
        severity=RankingExplainSeverity.INFO,
        title=title,
        summary=summary,
        actions=get_research_actions(RankingExplainReasonCode.METRIC_SUMMARY),
        details=metric_details,
    )


def _build_plateau_confirmed_reason(
    context: RankingExplainContext,
    plateau_report: Dict[str, Any],
) -> RankingExplainReasonCard:
    """Build reason card for plateau confirmation."""
    # Extract stability score from plateau report
    stability_score = plateau_report.get("stability_score", 0.0)
    
    metric_details = {
        "stability_score": stability_score,
    }
    
    title, summary = get_context_wording(
        context=context,
        code=RankingExplainReasonCode.PLATEAU_CONFIRMED,
        metric_values=metric_details,
    )
    
    return RankingExplainReasonCard(
        code=RankingExplainReasonCode.PLATEAU_CONFIRMED,
        severity=RankingExplainSeverity.INFO,
        title=title,
        summary=summary,
        actions=get_research_actions(RankingExplainReasonCode.PLATEAU_CONFIRMED),
        details=metric_details,
    )


def _build_missing_plateau_reason(
    context: RankingExplainContext,
) -> RankingExplainReasonCard:
    """Build reason card for missing plateau artifact."""
    title, summary = get_context_wording(
        context=context,
        code=RankingExplainReasonCode.DATA_MISSING_PLATEAU_ARTIFACT,
    )
    
    return RankingExplainReasonCard(
        code=RankingExplainReasonCode.DATA_MISSING_PLATEAU_ARTIFACT,
        severity=RankingExplainSeverity.INFO,
        title=title,
        summary=summary,
        actions=get_research_actions(RankingExplainReasonCode.DATA_MISSING_PLATEAU_ARTIFACT),
        details={"artifact_required": "plateau_report.json"},
    )


# Phase II helper functions
def _build_concentration_reasons(
    context: RankingExplainContext,
    winners: Dict[str, Any],
    ranking_explain_config: Any,
) -> List[RankingExplainReasonCard]:
    """Build reason cards for concentration analysis."""
    reasons = []
    
    if "topk" not in winners or not winners["topk"]:
        return reasons
    
    topk = winners["topk"]
    if len(topk) < 2:
        # Not enough candidates for concentration analysis
        return reasons
    
    # Calculate total final_score sum
    total_score = sum(candidate.get("final_score", 0.0) for candidate in topk)
    if total_score <= 0:
        return reasons
    
    # Get top candidate's score share
    top1_score = topk[0].get("final_score", 0.0)
    top1_share = top1_score / total_score if total_score > 0 else 0.0
    
    # Determine concentration level
    metric_details = {
        "top1_share": top1_share,
        "topk_count": len(topk),
        "total_score": total_score,
    }
    
    if top1_share >= ranking_explain_config.concentration_top1_error:
        # ERROR severity: high concentration risk
        metric_details["threshold"] = ranking_explain_config.concentration_top1_error
        title, summary = get_context_wording(
            context=context,
            code=RankingExplainReasonCode.CONCENTRATION_HIGH,
            metric_values=metric_details,
        )
        reasons.append(RankingExplainReasonCard(
            code=RankingExplainReasonCode.CONCENTRATION_HIGH,
            severity=RankingExplainSeverity.ERROR,
            title=title,
            summary=summary,
            actions=get_research_actions(RankingExplainReasonCode.CONCENTRATION_HIGH),
            details=metric_details,
        ))
    elif top1_share >= ranking_explain_config.concentration_top1_warn:
        # WARN severity: moderate concentration risk
        metric_details["threshold"] = ranking_explain_config.concentration_top1_warn
        title, summary = get_context_wording(
            context=context,
            code=RankingExplainReasonCode.CONCENTRATION_MODERATE,
            metric_values=metric_details,
        )
        reasons.append(RankingExplainReasonCard(
            code=RankingExplainReasonCode.CONCENTRATION_MODERATE,
            severity=RankingExplainSeverity.WARN,
            title=title,
            summary=summary,
            actions=get_research_actions(RankingExplainReasonCode.CONCENTRATION_MODERATE),
            details=metric_details,
        ))
    else:
        # INFO severity: acceptable concentration
        title, summary = get_context_wording(
            context=context,
            code=RankingExplainReasonCode.CONCENTRATION_OK,
            metric_values=metric_details,
        )
        reasons.append(RankingExplainReasonCard(
            code=RankingExplainReasonCode.CONCENTRATION_OK,
            severity=RankingExplainSeverity.INFO,
            title=title,
            summary=summary,
            actions=get_research_actions(RankingExplainReasonCode.CONCENTRATION_OK),
            details=metric_details,
        ))
    
    return reasons


def _build_plateau_quality_reasons(
    context: RankingExplainContext,
    plateau_report: Dict[str, Any],
    ranking_explain_config: Any,
) -> List[RankingExplainReasonCard]:
    """Build reason cards for plateau quality evaluation."""
    reasons = []
    
    stability_score = plateau_report.get("stability_score", 0.0)
    
    metric_details = {
        "stability_score": stability_score,
        "threshold": ranking_explain_config.plateau_stability_warn_below,
    }
    
    if stability_score >= ranking_explain_config.plateau_stability_warn_below:
        # Strong stability
        title, summary = get_context_wording(
            context=context,
            code=RankingExplainReasonCode.PLATEAU_STRONG_STABILITY,
            metric_values=metric_details,
        )
        reasons.append(RankingExplainReasonCard(
            code=RankingExplainReasonCode.PLATEAU_STRONG_STABILITY,
            severity=RankingExplainSeverity.INFO,
            title=title,
            summary=summary,
            actions=get_research_actions(RankingExplainReasonCode.PLATEAU_STRONG_STABILITY),
            details=metric_details,
        ))
    else:
        # Weak stability (WARN)
        title, summary = get_context_wording(
            context=context,
            code=RankingExplainReasonCode.PLATEAU_WEAK_STABILITY,
            metric_values=metric_details,
        )
        reasons.append(RankingExplainReasonCard(
            code=RankingExplainReasonCode.PLATEAU_WEAK_STABILITY,
            severity=RankingExplainSeverity.WARN,
            title=title,
            summary=summary,
            actions=get_research_actions(RankingExplainReasonCode.PLATEAU_WEAK_STABILITY),
            details=metric_details,
        ))
    
    return reasons


def _build_plateau_missing_artifact_reason(
    context: RankingExplainContext,
) -> RankingExplainReasonCard:
    """Build reason card for missing plateau artifact (Phase II WARN severity)."""
    title, summary = get_context_wording(
        context=context,
        code=RankingExplainReasonCode.PLATEAU_MISSING_ARTIFACT,
    )
    
    return RankingExplainReasonCard(
        code=RankingExplainReasonCode.PLATEAU_MISSING_ARTIFACT,
        severity=RankingExplainSeverity.WARN,  # Phase II: WARN severity
        title=title,
        summary=summary,
        actions=get_research_actions(RankingExplainReasonCode.PLATEAU_MISSING_ARTIFACT),
        details={"artifact_required": "plateau_report.json", "severity_explanation": "Option A: missing plateau artifact => WARN (not ERROR)"},
    )


def _build_robustness_reasons(
    context: RankingExplainContext,
    metrics: Dict[str, Any],
    scoring_guard_cfg: ScoringGuardConfig,
    ranking_explain_config: Any,
) -> List[RankingExplainReasonCard]:
    """Build reason cards for robustness checks."""
    reasons = []
    
    net_profit = metrics.get("net_profit", 0.0)
    trades = metrics.get("trades", 0)
    max_dd = abs(metrics.get("max_dd", 0.0))  # Convert negative to positive
    
    # 1. Check for missing required fields
    missing_fields = []
    required_fields = ["net_profit", "max_dd", "trades"]
    for field in required_fields:
        if field not in metrics:
            missing_fields.append(field)
    
    if missing_fields:
        metric_details = {
            "missing_fields": ", ".join(missing_fields),
            "required_fields": ", ".join(required_fields),
        }
        title, summary = get_context_wording(
            context=context,
            code=RankingExplainReasonCode.METRICS_MISSING_REQUIRED_FIELDS,
            metric_values=metric_details,
        )
        reasons.append(RankingExplainReasonCard(
            code=RankingExplainReasonCode.METRICS_MISSING_REQUIRED_FIELDS,
            severity=RankingExplainSeverity.ERROR,
            title=title,
            summary=summary,
            actions=get_research_actions(RankingExplainReasonCode.METRICS_MISSING_REQUIRED_FIELDS),
            details=metric_details,
        ))
    
    # 2. Check MDD invalid or near zero (ERROR)
    if max_dd <= ranking_explain_config.mdd_abs_min_error:
        metric_details = {
            "mdd": max_dd,
            "threshold": ranking_explain_config.mdd_abs_min_error,
        }
        title, summary = get_context_wording(
            context=context,
            code=RankingExplainReasonCode.MDD_INVALID_OR_ZERO,
            metric_values=metric_details,
        )
        reasons.append(RankingExplainReasonCard(
            code=RankingExplainReasonCode.MDD_INVALID_OR_ZERO,
            severity=RankingExplainSeverity.ERROR,
            title=title,
            summary=summary,
            actions=get_research_actions(RankingExplainReasonCode.MDD_INVALID_OR_ZERO),
            details=metric_details,
        ))
    
    # 3. Check trades too low for ranking (WARN)
    if trades < ranking_explain_config.trades_min_warn:
        metric_details = {
            "trades": trades,
            "threshold": ranking_explain_config.trades_min_warn,
        }
        title, summary = get_context_wording(
            context=context,
            code=RankingExplainReasonCode.TRADES_TOO_LOW_FOR_RANKING,
            metric_values=metric_details,
        )
        reasons.append(RankingExplainReasonCard(
            code=RankingExplainReasonCode.TRADES_TOO_LOW_FOR_RANKING,
            severity=RankingExplainSeverity.WARN,
            title=title,
            summary=summary,
            actions=get_research_actions(RankingExplainReasonCode.TRADES_TOO_LOW_FOR_RANKING),
            details=metric_details,
        ))
    
    # 4. Check average profit below minimum (WARN)
    if trades > 0:
        avg_profit = net_profit / trades
        avg_profit_threshold = ranking_explain_config.get_avg_profit_threshold(
            scoring_guard_cfg.min_avg_profit
        )
        
        if avg_profit < avg_profit_threshold:
            metric_details = {
                "avg_profit": avg_profit,
                "threshold": avg_profit_threshold,
            }
            title, summary = get_context_wording(
                context=context,
                code=RankingExplainReasonCode.AVG_PROFIT_BELOW_MIN,
                metric_values=metric_details,
            )
            reasons.append(RankingExplainReasonCard(
                code=RankingExplainReasonCode.AVG_PROFIT_BELOW_MIN,
                severity=RankingExplainSeverity.WARN,
                title=title,
                summary=summary,
                actions=get_research_actions(RankingExplainReasonCode.AVG_PROFIT_BELOW_MIN),
                details=metric_details,
            ))
    
    return reasons


def _build_warning_reasons(
    context: RankingExplainContext,
    warnings: List[str],
) -> List[RankingExplainReasonCard]:
    """Build reason cards for runtime warnings."""
    reasons = []
    
    # WARN_NUMBA_MISSING
    if RankingExplainReasonCode.WARN_NUMBA_MISSING.value in warnings:
        title, summary = get_context_wording(
            context=context,
            code=RankingExplainReasonCode.WARN_NUMBA_MISSING,
        )
        reasons.append(RankingExplainReasonCard(
            code=RankingExplainReasonCode.WARN_NUMBA_MISSING,
            severity=RankingExplainSeverity.WARN,
            title=title,
            summary=summary,
            actions=get_research_actions(RankingExplainReasonCode.WARN_NUMBA_MISSING),
        ))
        
    # WARN_ENV_MALFORMED
    if RankingExplainReasonCode.WARN_ENV_MALFORMED.value in warnings:
        # We might have details in the warning string? For now assuming simple code match
        metric_details = {"details": "Check logs for specifics"}
        title, summary = get_context_wording(
            context=context,
            code=RankingExplainReasonCode.WARN_ENV_MALFORMED,
            metric_values=metric_details
        )
        reasons.append(RankingExplainReasonCard(
            code=RankingExplainReasonCode.WARN_ENV_MALFORMED,
            severity=RankingExplainSeverity.WARN,
            title=title,
            summary=summary,
            actions=get_research_actions(RankingExplainReasonCode.WARN_ENV_MALFORMED),
            details=metric_details
        ))

    # WARN_PLATEAU_FALLBACK
    if RankingExplainReasonCode.WARN_PLATEAU_FALLBACK.value in warnings:
         metric_details = {"count": "unknown"}
         title, summary = get_context_wording(
            context=context,
            code=RankingExplainReasonCode.WARN_PLATEAU_FALLBACK,
            metric_values=metric_details
         )
         reasons.append(RankingExplainReasonCard(
            code=RankingExplainReasonCode.WARN_PLATEAU_FALLBACK,
            severity=RankingExplainSeverity.WARN,
            title=title,
            summary=summary,
            actions=get_research_actions(RankingExplainReasonCode.WARN_PLATEAU_FALLBACK),
            details=metric_details
         ))
         
    # ERR_EVIDENCE_LOOKUP (handled via banner usually, but if passed here)
    if RankingExplainReasonCode.ERR_EVIDENCE_LOOKUP.value in warnings:
         metric_details = {"error_msg": "See logs"}
         title, summary = get_context_wording(
            context=context,
            code=RankingExplainReasonCode.ERR_EVIDENCE_LOOKUP,
            metric_values=metric_details
         )
         reasons.append(RankingExplainReasonCard(
            code=RankingExplainReasonCode.ERR_EVIDENCE_LOOKUP,
            severity=RankingExplainSeverity.ERROR,
            title=title,
            summary=summary,
            actions=get_research_actions(RankingExplainReasonCode.ERR_EVIDENCE_LOOKUP),
            details=metric_details
         ))

    return reasons


def load_winners_from_file(job_dir: Path) -> Optional[Dict[str, Any]]:
    """Load winners.json from job directory."""
    winners_path = job_dir / "winners.json"
    if not winners_path.exists():
        return None
    
    try:
        with open(winners_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def load_plateau_report_from_file(job_dir: Path) -> Optional[Dict[str, Any]]:
    """Load plateau_report.json from job directory."""
    plateau_path = job_dir / "plateau_report.json"
    if not plateau_path.exists():
        return None
    
    try:
        with open(plateau_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def build_and_write_ranking_explain_report(
    job_dir: Path,
    context: RankingExplainContext,
    scoring_guard_cfg: Optional[ScoringGuardConfig] = None,
    ranking_explain_config: Optional[Any] = None,
    warnings: List[str] | None = None,
) -> bool:
    """
    Build and write ranking_explain.json artifact to job directory.
    
    Args:
        job_dir: Job directory path
        context: CANDIDATE or FINAL_SELECTION
        scoring_guard_cfg: Scoring guard configuration (uses default if None)
        ranking_explain_config: Optional ranking explain configuration for Phase II
        
    Returns:
        True if successful, False otherwise
    """
    # Use default config if not provided
    if scoring_guard_cfg is None:
        scoring_guard_cfg = ScoringGuardConfig()
    
    # Extract job_id from directory name
    job_id = job_dir.name
    
    # Load SSOT artifacts
    winners = load_winners_from_file(job_dir)
    if winners is None:
        # Cannot build report without winners
        return False
    
    plateau_report = load_plateau_report_from_file(job_dir)
    
    # Build the report
    report = build_ranking_explain_report(
        context=context,
        job_id=job_id,
        winners=winners,
        plateau_report=plateau_report,
        scoring_guard_cfg=scoring_guard_cfg,
        ranking_explain_config=ranking_explain_config,
        warnings=warnings,
    )
    
    # Write the artifact with canonical filename ranking_explain_report.json
    output_path = job_dir / "ranking_explain_report.json"
    try:
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report.model_dump(), f, indent=2, default=str)
        return True
    except (OSError, TypeError):
        return False


__all__ = [
    "build_ranking_explain_report",
    "build_and_write_ranking_explain_report",
    "load_winners_from_file",
    "load_plateau_report_from_file",
]