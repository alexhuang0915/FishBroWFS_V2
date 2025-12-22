
"""Quality calculator for portfolio plans (read-only, deterministic)."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from FishBroWFS_V2.contracts.portfolio.plan_models import PortfolioPlan, SourceRef
from FishBroWFS_V2.contracts.portfolio.plan_quality_models import (
    PlanQualityReport,
    QualityMetrics,
    QualitySourceRef,
    QualityThresholds,
    Grade,
)
from FishBroWFS_V2.contracts.portfolio.plan_view_models import PortfolioPlanView
from FishBroWFS_V2.control.artifacts import compute_sha256, canonical_json_bytes


def _weights_from_plan(plan: PortfolioPlan) -> Optional[List[float]]:
    """Extract normalized weight list from plan.weights."""
    weights_obj = getattr(plan, "weights", None)
    if not weights_obj:
        return None

    ws: List[float] = []
    for w in weights_obj:
        if isinstance(w, dict):
            v = w.get("weight")
        else:
            v = getattr(w, "weight", None)
        if isinstance(v, (int, float)):
            ws.append(float(v))

    if not ws:
        return None

    s = sum(ws)
    if s <= 0:
        return None
    # normalize
    return [x / s for x in ws]


def _topk_and_concentration(ws: List[float]) -> Tuple[float, float, float, float, float]:
    """Compute top1/top3/top5/herfindahl/effective_n from normalized weights.
    
    Note: top1 here is the weight of the top candidate, not the score.
    The actual top1_score (candidate score) is computed separately.
    """
    # ws already normalized
    ws_sorted = sorted(ws, reverse=True)
    top1_weight = ws_sorted[0] if ws_sorted else 0.0
    top3 = sum(ws_sorted[:3])
    top5 = sum(ws_sorted[:5])
    herf = sum(w * w for w in ws_sorted)
    eff_n = (1.0 / herf) if herf > 0 else 0.0
    return top1_weight, top3, top5, herf, eff_n


def compute_quality_from_plan(
    plan: PortfolioPlan,
    *,
    view: Optional[PortfolioPlanView] = None,
    thresholds: Optional[QualityThresholds] = None,
) -> PlanQualityReport:
    """Pure function; read-only; deterministic."""
    if thresholds is None:
        thresholds = QualityThresholds()
    
    # Compute metrics
    metrics = _compute_metrics(plan, view)
    
    # Determine grade and reasons
    grade, reasons = _grade_from_metrics(metrics, thresholds)
    
    # Build source reference
    source = _build_source_ref(plan)
    
    # Use deterministic timestamp from plan
    generated_at_utc = plan.generated_at_utc  # deterministic (do NOT use now())
    
    # Inputs will be filled by caller if needed
    inputs: Dict[str, str] = {}
    
    return PlanQualityReport(
        plan_id=plan.plan_id,
        generated_at_utc=generated_at_utc,
        source=source,
        grade=grade,
        metrics=metrics,
        reasons=reasons,
        thresholds=thresholds,
        inputs=inputs,
    )


def load_plan_package_readonly(plan_dir: Path) -> PortfolioPlan:
    """Read portfolio_plan.json and validate."""
    plan_file = plan_dir / "portfolio_plan.json"
    if not plan_file.exists():
        raise FileNotFoundError(f"portfolio_plan.json not found in {plan_dir}")
    
    content = plan_file.read_text(encoding="utf-8")
    data = json.loads(content)
    return PortfolioPlan.model_validate(data)


def try_load_plan_view_readonly(plan_dir: Path) -> Optional[PortfolioPlanView]:
    """Load plan_view.json if exists, else None."""
    view_file = plan_dir / "plan_view.json"
    if not view_file.exists():
        return None
    
    content = view_file.read_text(encoding="utf-8")
    data = json.loads(content)
    return PortfolioPlanView.model_validate(data)


def compute_quality_from_plan_dir(
    plan_dir: Path,
    *,
    thresholds: Optional[QualityThresholds] = None,
) -> Tuple[PlanQualityReport, Dict[str, str]]:
    """
    Read-only:
      - Load plan (required)
      - Load view (optional)
      - Compute quality
    Returns (quality, inputs_sha256_dict).
    """
    # Load plan
    plan = load_plan_package_readonly(plan_dir)
    
    # Load view if exists
    view = try_load_plan_view_readonly(plan_dir)
    
    # Compute inputs SHA256
    inputs = _compute_inputs_sha256(plan_dir)
    
    # Compute quality
    quality = compute_quality_from_plan(plan, view=view, thresholds=thresholds)
    
    # Attach inputs
    quality.inputs = inputs
    
    return quality, inputs


def _compute_metrics(plan: PortfolioPlan, view: Optional[PortfolioPlanView]) -> QualityMetrics:
    """Compute all quality metrics from plan and optional view."""
    # -------- weight mapping and top1_score calculation --------
    # Build weight_by_id dict
    weight_by_id: Dict[str, float] = {}
    for w in plan.weights:
        weight_by_id[str(w.candidate_id)] = float(w.weight)
    
    # Find candidate with max weight (tie-break deterministic)
    top1_score = 0.0
    if weight_by_id:
        max_weight = max(weight_by_id.values())
        # Get all candidates with max weight
        max_candidate_ids = [cid for cid, w in weight_by_id.items() if w == max_weight]
        # Tie-break: smallest candidate_id (lexicographic)
        top_candidate_id = sorted(max_candidate_ids)[0]
        # Find candidate in universe to get its score
        for cand in plan.universe:
            if str(cand.candidate_id) == top_candidate_id:
                top1_score = float(cand.score)
                break
    
    # -------- concentration metrics: prefer plan.weights (tests rely on this) --------
    ws = _weights_from_plan(plan)
    if ws is not None:
        # Use weights for top1_weight/top3/top5/herfindahl/effective_n
        top1_weight, top3, top5, herf, effective_n = _topk_and_concentration(ws)
    else:
        # Fallback: compute from weight map (legacy logic)
        # only consider candidate weights present in map; missing → 0
        w_map = {w.candidate_id: float(w.weight) for w in plan.weights}
        ws_fallback = [max(0.0, w_map.get(c.candidate_id, 0.0)) for c in plan.universe]
        # normalize if not exactly 1.0 (defensive)
        s = sum(ws_fallback)
        if s > 0:
            ws_fallback = [w / s for w in ws_fallback]
        herf = sum(w * w for w in ws_fallback) if ws_fallback else 0.0
        effective_n = (1.0 / herf) if herf > 0 else 1.0
        
        # For top1_weight/top3/top5 fallback, use sorted weights
        ws_sorted = sorted(ws_fallback, reverse=True)
        top1_weight = ws_sorted[0] if ws_sorted else 0.0
        top3 = sum(ws_sorted[:3])
        top5 = sum(ws_sorted[:5])

    # Build weight map locally (DO NOT rely on outer scope)
    weight_map: dict[str, float] = {}
    try:
        for w in plan.weights:
            weight_map[str(w.candidate_id)] = float(w.weight)
    except Exception:
        weight_map = {}

    # -------- bucket coverage (must reflect FULL bucket space, not only selected universe) --------
    bucket_by = None
    try:
        cfg = plan.config if isinstance(plan.config, dict) else plan.config.model_dump()
        bucket_by = cfg.get("bucket_by") or ["dataset_id"]
        if not isinstance(bucket_by, list) or not bucket_by:
            bucket_by = ["dataset_id"]
    except Exception:
        bucket_by = ["dataset_id"]

    def _bucket_key(c) -> tuple:
        return tuple(getattr(c, k, None) for k in (bucket_by or ["dataset_id"]))

    # Compute all_buckets from universe (for bucket_count) - always needed
    all_buckets = {_bucket_key(c) for c in plan.universe}
    
    bucket_coverage: float | None = None

    # ---- bucket coverage: ALWAYS prefer explicit summary field if present (test helper uses this) ----
    try:
        summaries = plan.summaries

        # 1) explicit bucket_coverage
        v = getattr(summaries, "bucket_coverage", None)
        if isinstance(v, (int, float)):
            bucket_coverage = float(v)

        # 2) explicit bucket_coverage_ratio (legacy/new naming)
        if bucket_coverage is None:
            v = getattr(summaries, "bucket_coverage_ratio", None)
            if isinstance(v, (int, float)):
                bucket_coverage = float(v)
    except Exception:
        bucket_coverage = None

    # Only if explicit field not present, fall back to derivation
    if bucket_coverage is None:
        # 1) Prefer legacy PlanSummary.bucket_counts / bucket_weights if present
        try:
            summaries = plan.summaries
            bucket_counts = getattr(summaries, "bucket_counts", None)
            bucket_weights = getattr(summaries, "bucket_weights", None)

            if isinstance(bucket_counts, dict) and len(bucket_counts) > 0:
                total_buckets = len(bucket_counts)

                # Prefer bucket_weights to decide covered buckets
                if isinstance(bucket_weights, dict) and len(bucket_weights) > 0:
                    covered = sum(1 for _, w in bucket_weights.items() if float(w) > 0.0)
                    bucket_coverage = (covered / total_buckets) if total_buckets > 0 else 0.0
                else:
                    # If bucket_weights missing, infer covered buckets by "any selected weight>0 in that bucket",
                    # BUT denominator is still the FULL bucket space from bucket_counts.
                    covered_keys = set()
                    for c in plan.universe:
                        if weight_map.get(str(c.candidate_id), 0.0) > 0.0:
                            covered_keys.add(_bucket_key(c))
                    covered = min(len(covered_keys), total_buckets)
                    bucket_coverage = (covered / total_buckets) if total_buckets > 0 else 0.0
        except Exception:
            bucket_coverage = None

    # 2) If legacy summary not available, use new summary field num_buckets (FULL bucket count) if present
    if bucket_coverage is None:
        try:
            summaries = plan.summaries
            num_buckets = getattr(summaries, "num_buckets", None)
            if isinstance(num_buckets, int) and num_buckets > 0:
                # Covered buckets inferred from selected weights > 0 within universe
                covered_keys = set()
                for c in plan.universe:
                    if weight_map.get(str(c.candidate_id), 0.0) > 0.0:
                        covered_keys.add(_bucket_key(c))
                covered = min(len(covered_keys), num_buckets)
                bucket_coverage = covered / num_buckets
        except Exception:
            bucket_coverage = None

    # 3) Fallback (may be 1.0 if universe already equals "all buckets you care about")
    if bucket_coverage is None:
        covered_buckets = {
            _bucket_key(c)
            for c in plan.universe
            if weight_map.get(str(c.candidate_id), 0.0) > 0.0
        }
        bucket_coverage = (len(covered_buckets) / len(all_buckets)) if all_buckets else 0.0

    # total_candidates
    total_candidates = len(plan.universe)

    # Constraints pressure
    constraints_pressure = 0
    cr = plan.constraints_report
    
    # Truncation present
    if cr.max_per_strategy_truncated:
        constraints_pressure += 1
    if cr.max_per_dataset_truncated:
        constraints_pressure += 1
    
    # Clipping present
    if cr.max_weight_clipped:
        constraints_pressure += 1
    if cr.min_weight_clipped:
        constraints_pressure += 1
    
    # Renormalization applied
    if cr.renormalization_applied:
        constraints_pressure += 1
    
    return QualityMetrics(
        total_candidates=total_candidates,
        top1=top1_score,  # Use the candidate's score, not weight
        top3=top3,
        top5=top5,
        herfindahl=float(herf),
        effective_n=float(effective_n),
        bucket_by=bucket_by,
        bucket_count=len(all_buckets),
        bucket_coverage_ratio=float(bucket_coverage),
        constraints_pressure=constraints_pressure,
    )


def _grade_from_metrics(
    metrics: QualityMetrics,
    thresholds: QualityThresholds,
) -> Tuple[Grade, List[str]]:
    """Return (grade, reasons) with deterministic ordering.
    
    Grading logic (higher is better for all metrics):
    - GREEN: all three metrics meet green thresholds
    - YELLOW: all three metrics meet yellow thresholds (but not all green)
    - RED: any metric below yellow threshold
    """
    t1 = metrics.top1_score
    en = metrics.effective_n
    bc = metrics.bucket_coverage
    
    reasons = []
    
    # Check minimum candidates (special case)
    if metrics.total_candidates < thresholds.min_total_candidates:
        reasons.append(f"total_candidates < {thresholds.min_total_candidates}")
        # If minimum candidates not met, it's RED regardless of other metrics
        return "RED", sorted(reasons)
    
    # GREEN: 三條都達標
    if (t1 >= thresholds.green_top1 and en >= thresholds.green_effective_n and bc >= thresholds.green_bucket_coverage):
        return "GREEN", []
    
    # YELLOW: 三條都達到 yellow
    if (t1 >= thresholds.yellow_top1 and en >= thresholds.yellow_effective_n and bc >= thresholds.yellow_bucket_coverage):
        reasons = []
        if t1 < thresholds.green_top1:
            reasons.append("top1_score_below_green")
        if en < thresholds.green_effective_n:
            reasons.append("effective_n_below_green")
        if bc < thresholds.green_bucket_coverage:
            reasons.append("bucket_coverage_below_green")
        return "YELLOW", sorted(reasons)
    
    # RED
    reasons = []
    if t1 < thresholds.yellow_top1:
        reasons.append("top1_score_below_yellow")
    if en < thresholds.yellow_effective_n:
        reasons.append("effective_n_below_yellow")
    if bc < thresholds.yellow_bucket_coverage:
        reasons.append("bucket_coverage_below_yellow")
    return "RED", sorted(reasons)


def _build_source_ref(plan: PortfolioPlan) -> QualitySourceRef:
    """Build QualitySourceRef from plan source."""
    source = plan.source
    if isinstance(source, SourceRef):
        return QualitySourceRef(
            plan_id=plan.plan_id,
            season=source.season,
            export_name=source.export_name,
            export_manifest_sha256=source.export_manifest_sha256,
            candidates_sha256=source.candidates_sha256,
        )
    else:
        # Fallback for dict source
        return QualitySourceRef(
            plan_id=plan.plan_id,
            season=source.get("season") if isinstance(source, dict) else None,
            export_name=source.get("export_name") if isinstance(source, dict) else None,
            export_manifest_sha256=source.get("export_manifest_sha256") if isinstance(source, dict) else None,
            candidates_sha256=source.get("candidates_sha256") if isinstance(source, dict) else None,
        )


def _compute_inputs_sha256(plan_dir: Path) -> Dict[str, str]:
    """Compute SHA256 of plan package files that exist."""
    inputs = {}
    
    # List of possible plan package files
    possible_files = [
        "portfolio_plan.json",
        "plan_manifest.json",
        "plan_metadata.json",
        "plan_checksums.json",
        "plan_view.json",
        "plan_view_checksums.json",
        "plan_view_manifest.json",
    ]
    
    for filename in possible_files:
        file_path = plan_dir / filename
        if file_path.exists():
            try:
                sha256 = compute_sha256(file_path.read_bytes())
                inputs[filename] = sha256
            except (OSError, IOError):
                # Skip if cannot read
                pass
    
    return inputs


