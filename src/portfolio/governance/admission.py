"""
Admission engine implementing the three gates (integrity, diversity, correlation)
and replacement‑mode logic.
"""
import statistics
from typing import List, Optional, Tuple, Dict, Any

from ..models.governance_models import (
    StrategyIdentity,
    GovernanceParams,
    AdmissionReport,
    ReplacementReport,
    ReturnSeries,
    ReasonCode,
)
from .governance_logging import write_artifact_json, now_utc_iso, governance_root


# ========== Correlation Helper ==========

def rolling_corr(
    a: List[float],
    b: List[float],
    min_samples: int = 20,
) -> Tuple[float, bool]:
    """
    Compute Pearson correlation between two aligned series.

    Returns (correlation, sufficient_samples).
    If len(a) < min_samples, returns (0.0, False).
    """
    if len(a) != len(b):
        raise ValueError("Series lengths must match")
    if len(a) < min_samples:
        return 0.0, False

    try:
        corr = statistics.correlation(a, b)
    except statistics.StatisticsError:
        # e.g., zero variance
        corr = 0.0
    return corr, True


# ========== Diversity Gate ==========

def evaluate_diversity(
    candidate: StrategyIdentity,
    existing: List[StrategyIdentity],
    params: GovernanceParams,
    replacement_mode: bool = False,
) -> Dict[str, Any]:
    """
    Evaluate whether the candidate fits within bucket‑slot limits.

    Returns a dict with keys:
      - bucket: identified bucket tag (or None)
      - used: number of existing strategies in that bucket
      - capacity: max allowed for that bucket
      - pass: bool
      - reason: str
    """
    # Determine candidate's bucket (first matching tag)
    bucket = None
    for tag in candidate.tags:
        if tag in params.bucket_slots:
            bucket = tag
            break

    if bucket is None:
        bucket = "Other"  # fallback

    used = sum(1 for ident in existing if bucket in ident.tags)
    capacity = params.bucket_slots.get(bucket, 0)

    if replacement_mode:
        # Replacement mode waives the slot requirement
        passed = True
        reason = "replacement_mode waives diversity gate"
    else:
        passed = used < capacity
        reason = (
            f"bucket {bucket} used {used}/{capacity}"
            f" – {'slot available' if passed else 'slot full'}"
        )

    return {
        "bucket": bucket,
        "used": used,
        "capacity": capacity,
        "pass": passed,
        "reason": reason,
    }


# ========== Correlation Gate ==========

def evaluate_correlation(
    candidate_returns: ReturnSeries,
    portfolio_returns: ReturnSeries,
    member_returns: List[ReturnSeries],
    params: GovernanceParams,
) -> Dict[str, Any]:
    """
    Evaluate correlation limits.

    Returns a dict with keys:
      - corr_vs_portfolio: float
      - max_corr_vs_member: float
      - pass: bool
      - reason: str
    """
    # Align series (assuming they are already aligned by timestamp)
    a = candidate_returns.returns
    b = portfolio_returns.returns

    corr_portfolio, sufficient = rolling_corr(a, b, params.corr_min_samples)
    if not sufficient:
        return {
            "corr_vs_portfolio": 0.0,
            "max_corr_vs_member": 0.0,
            "pass": True,
            "reason": "insufficient samples for correlation",
        }

    # Compute max correlation vs any member
    max_member_corr = 0.0
    for member in member_returns:
        corr, _ = rolling_corr(a, member.returns, params.corr_min_samples)
        max_member_corr = max(max_member_corr, abs(corr))

    passed = (
        abs(corr_portfolio) <= params.corr_portfolio_hard_limit
        and max_member_corr <= params.corr_member_hard_limit
    )
    reason = (
        f"corr vs portfolio {corr_portfolio:.3f} ≤ {params.corr_portfolio_hard_limit}, "
        f"max vs member {max_member_corr:.3f} ≤ {params.corr_member_hard_limit}"
    )

    return {
        "corr_vs_portfolio": corr_portfolio,
        "max_corr_vs_member": max_member_corr,
        "pass": passed,
        "reason": reason,
    }


# ========== Dominance Proof Validation ==========

def validate_dominance_proof(
    dominance_proof: Optional[Dict[str, float]],
) -> Tuple[bool, str]:
    """
    Check that dominance proof contains required fields and indicates dominance.

    Returns (valid, reason).
    """
    if dominance_proof is None:
        return False, "dominance_proof missing"

    required = {"expected_score_new", "expected_score_old", "risk_adj_new", "risk_adj_old"}
    missing = required - set(dominance_proof.keys())
    if missing:
        return False, f"dominance_proof missing keys: {missing}"

    new_score = dominance_proof["expected_score_new"]
    old_score = dominance_proof["expected_score_old"]
    new_risk = dominance_proof["risk_adj_new"]
    old_risk = dominance_proof["risk_adj_old"]

    if new_score <= old_score:
        return False, f"expected_score_new ({new_score}) ≤ expected_score_old ({old_score})"
    if new_risk < old_risk:
        return False, f"risk_adj_new ({new_risk}) < risk_adj_old ({old_risk})"

    return True, "dominance proven"


# ========== Main Admission Function ==========

def admit_candidate(
    candidate: StrategyIdentity,
    params: GovernanceParams,
    integrity_ok: bool,
    candidate_returns: ReturnSeries,
    portfolio_returns: ReturnSeries,
    member_returns: List[ReturnSeries],
    existing_identities: List[StrategyIdentity],
    replacement_mode: bool = False,
    replacement_target_key: Optional[str] = None,
    dominance_proof: Optional[Dict[str, float]] = None,
) -> Tuple[bool, str, Optional[str]]:
    """
    Evaluate a candidate through the three gates and produce admission artifacts.

    Returns:
      - approved: bool
      - admission_report_path: str (relative to governance root)
      - replacement_report_path: str | None

    Writes AdmissionReport (always) and ReplacementReport (if replacement_mode).
    """
    timestamp = now_utc_iso()
    gates = {}

    # ----- Integrity Gate -----
    gates["integrity"] = {
        "pass": integrity_ok,
        "reason": "integrity check from research pipeline",
    }
    if not integrity_ok:
        gates["integrity"]["reason"] = "integrity gate failed (research artifacts invalid)"

    # ----- Diversity Gate -----
    diversity = evaluate_diversity(
        candidate,
        existing_identities,
        params,
        replacement_mode=replacement_mode,
    )
    gates["diversity"] = diversity

    # ----- Correlation Gate -----
    correlation = evaluate_correlation(
        candidate_returns,
        portfolio_returns,
        member_returns,
        params,
    )
    gates["correlation"] = correlation

    # ----- Decision Logic -----
    approved = True
    reason = ""

    # 1. Integrity gate denial overrides everything
    if not integrity_ok:
        approved = False
        reason = "integrity gate failed"

    # 2. Diversity gate (unless replacement mode)
    elif not replacement_mode and not diversity["pass"]:
        approved = False
        reason = f"diversity gate failed: {diversity['reason']}"

    # 3. Correlation gate
    elif not correlation["pass"]:
        # In replacement mode, correlation failure may be overridden by dominance proof
        if replacement_mode:
            valid, dom_reason = validate_dominance_proof(dominance_proof)
            if valid:
                # Dominance proven – correlation limits waived
                gates["correlation"]["override"] = "dominance proof"
                gates["correlation"]["pass"] = True
            else:
                approved = False
                reason = f"correlation gate failed and dominance proof invalid: {dom_reason}"
        else:
            approved = False
            reason = f"correlation gate failed: {correlation['reason']}"

    # 4. Replacement mode requires a target
    if replacement_mode and replacement_target_key is None:
        approved = False
        reason = "replacement_mode True but replacement_target_key missing"

    # ----- Write AdmissionReport -----
    admission_report = AdmissionReport(
        candidate=candidate,
        timestamp_utc=timestamp,
        gates=gates,
        approved=approved,
        replacement_mode=replacement_mode,
        replacement_target=replacement_target_key,
        notes=reason,
    )
    admission_path = write_artifact_json(
        f"admission_{candidate.strategy_id}_{timestamp[:10]}.json",
        admission_report,
    )

    # ----- Write ReplacementReport if applicable -----
    replacement_path = None
    if replacement_mode and approved:
        valid, _ = validate_dominance_proof(dominance_proof)
        replacement_report = ReplacementReport(
            new_strategy_key=candidate.identity_key(),
            old_strategy_key=replacement_target_key,
            dominance_proof=dominance_proof or {},
            approved=valid,
            timestamp_utc=timestamp,
        )
        replacement_path = write_artifact_json(
            f"replacement_{candidate.strategy_id}_{timestamp[:10]}.json",
            replacement_report,
        )

    return (
        approved,
        str(admission_path.relative_to(governance_root())),
        str(replacement_path.relative_to(governance_root())) if replacement_path else None,
    )