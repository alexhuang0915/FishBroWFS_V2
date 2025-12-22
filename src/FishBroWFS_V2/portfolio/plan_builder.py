
"""
Phase 17 rev2: Portfolio Plan Builder (deterministic, read‑only over exports).

Contracts:
- Only reads from exports tree (no artifacts, no engine).
- Deterministic tie‑break ordering.
- Controlled mutation: writes only under outputs/portfolio/plans/{plan_id}/
- Hash chain audit (plan_manifest.json with self‑hash).
- Enrichment via batch_api (optional, best‑effort).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP, getcontext
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# pydantic ValidationError not used; removed to avoid import error

from FishBroWFS_V2.contracts.portfolio.plan_payloads import PlanCreatePayload
from FishBroWFS_V2.contracts.portfolio.plan_models import (
    ConstraintsReport,
    PlannedCandidate,
    PlannedWeight,
    PlanSummary,
    PortfolioPlan,
    SourceRef,
)

# LEGAL gateway for artifacts reads
from FishBroWFS_V2.control import batch_api  # Phase 14.1 read-only gateway

# Use existing repo utilities
from FishBroWFS_V2.control.artifacts import (
    canonical_json_bytes,
    compute_sha256,
    write_atomic_json,
)

# Write‑scope guard
from FishBroWFS_V2.utils.write_scope import create_plan_scope

getcontext().prec = 40


# -----------------------------
# Helpers: canonical json + sha256
# -----------------------------
def canonical_json(obj: Any) -> str:
    # Use repo standard canonical_json_bytes and decode to string
    return canonical_json_bytes(obj).decode("utf-8")


def sha256_bytes(b: bytes) -> str:
    return compute_sha256(b)


def sha256_text(s: str) -> str:
    return sha256_bytes(s.encode("utf-8"))


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_text_atomic(path: Path, text: str) -> None:
    # deterministic-ish atomic write
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


# -----------------------------
# Candidate input model (loose)
# -----------------------------
@dataclass(frozen=True)
class CandidateIn:
    candidate_id: str
    strategy_id: str
    dataset_id: str
    params: Dict[str, Any]
    score: float
    season: str
    source_batch: str
    source_export: str


def _candidate_sort_key(c: CandidateIn) -> Tuple:
    # score DESC => use negative
    params_canon = canonical_json(c.params)
    return (-float(c.score), c.strategy_id, c.dataset_id, c.source_batch, params_canon, c.candidate_id)


def _candidate_id(c: CandidateIn) -> str:
    # Deterministic candidate_id from core fields
    # NOTE: do not include export_name here; source_export stored separately.
    payload = {
        "strategy_id": c.strategy_id,
        "dataset_id": c.dataset_id,
        "params": c.params,
        "source_batch": c.source_batch,
        "season": c.season,
    }
    return "cand_" + sha256_text(canonical_json(payload))[:16]


# -----------------------------
# Selection constraints
# -----------------------------
@dataclass
class SelectionReport:
    max_per_strategy_truncated: Dict[str, int] = None  # type: ignore
    max_per_dataset_truncated: Dict[str, int] = None   # type: ignore

    def __post_init__(self):
        if self.max_per_strategy_truncated is None:
            self.max_per_strategy_truncated = {}
        if self.max_per_dataset_truncated is None:
            self.max_per_dataset_truncated = {}


def apply_selection_constraints(
    candidates_sorted: List[CandidateIn],
    top_n: int,
    max_per_strategy: int,
    max_per_dataset: int,
) -> Tuple[List[CandidateIn], SelectionReport]:
    limited = candidates_sorted[:top_n]
    per_strat: Dict[str, int] = {}
    per_ds: Dict[str, int] = {}
    selected: List[CandidateIn] = []
    rep = SelectionReport()

    for c in limited:
        s_ok = per_strat.get(c.strategy_id, 0) < max_per_strategy
        d_ok = per_ds.get(c.dataset_id, 0) < max_per_dataset

        if not s_ok:
            rep.max_per_strategy_truncated[c.strategy_id] = rep.max_per_strategy_truncated.get(c.strategy_id, 0) + 1
        if not d_ok:
            rep.max_per_dataset_truncated[c.dataset_id] = rep.max_per_dataset_truncated.get(c.dataset_id, 0) + 1

        if s_ok and d_ok:
            selected.append(c)
            per_strat[c.strategy_id] = per_strat.get(c.strategy_id, 0) + 1
            per_ds[c.dataset_id] = per_ds.get(c.dataset_id, 0) + 1

    return selected, rep


# -----------------------------
# Weighting + clip + renorm
# -----------------------------
@dataclass(frozen=True)
class WeightItem:
    candidate_id: str
    weight: float


def _to_dec(x: float) -> Decimal:
    return Decimal(str(x))


def _round_dec(x: Decimal, places: int = 12) -> Decimal:
    q = Decimal("1." + ("0" * places))
    return x.quantize(q, rounding=ROUND_HALF_UP)


def clip_and_renormalize_deterministic(
    items: List[WeightItem],
    min_w: float,
    max_w: float,
    *,
    places: int = 12,
    tol: float = 1e-9,
) -> Tuple[List[WeightItem], Dict[str, Any]]:
    if not items:
        return [], {
            "max_weight_clipped": [],
            "min_weight_clipped": [],
            "renormalization_applied": False,
            "renormalization_factor": None,
        }

    min_d = _to_dec(min_w)
    max_d = _to_dec(max_w)
    max_clipped_ids: set[str] = set()
    min_clipped_ids: set[str] = set()

    clipped: List[Tuple[str, Decimal]] = []
    for it in items:
        w = _to_dec(it.weight)
        if w > max_d:
            w = max_d
            max_clipped_ids.add(it.candidate_id)
        if w < min_d:
            w = min_d
            min_clipped_ids.add(it.candidate_id)
        clipped.append((it.candidate_id, w))

    total = sum(w for _, w in clipped)
    if total == Decimal("0"):
        # deterministic fallback: equal
        n = Decimal(len(clipped))
        eq = Decimal("1") / n
        clipped = [(cid, eq) for cid, _ in clipped]
        total = sum(w for _, w in clipped)

    scaled = [(cid, (w / total)) for cid, w in clipped]
    rounded = [(cid, _round_dec(w, places)) for cid, w in scaled]
    rounded_total = sum(w for _, w in rounded)

    one = Decimal("1")
    unit = Decimal("1") / (Decimal(10) ** places)
    residual = one - rounded_total

    ticks = int((residual / unit).to_integral_value(rounding=ROUND_HALF_UP))
    order = sorted(range(len(rounded)), key=lambda i: rounded[i][0])  # cid asc
    updated = [(cid, w) for cid, w in rounded]  # keep as tuple

    if ticks != 0:
        step = unit if ticks > 0 else -unit
        ticks_abs = abs(ticks)
        idx = 0
        while ticks_abs > 0:
            i = order[idx % len(order)]
            cid, w = updated[i]
            new_w = w + step
            if Decimal("0") <= new_w <= Decimal("1"):
                updated[i] = (cid, new_w)
                ticks_abs -= 1
            idx += 1

    final_total = sum(w for _, w in updated)
    # Convert to floats
    out_map = {cid: float(w) for cid, w in updated}
    out_items = [WeightItem(it.candidate_id, out_map[it.candidate_id]) for it in items]

    renormalization_applied = bool(max_clipped_ids or min_clipped_ids or (abs(float(rounded_total) - 1.0) > tol))
    renormalization_factor = float(Decimal("1") / total) if total != Decimal("0") and renormalization_applied else None

    report = {
        "max_weight_clipped": sorted(list(max_clipped_ids)),
        "min_weight_clipped": sorted(list(min_clipped_ids)),
        "renormalization_applied": renormalization_applied,
        "renormalization_factor": renormalization_factor,
        "final_total": float(final_total),
    }
    return out_items, report


def assign_weights_equal(selected: List[CandidateIn], min_w: float, max_w: float) -> Tuple[List[WeightItem], Dict[str, Any]]:
    n = len(selected)
    base = 1.0 / n
    items = [WeightItem(c.candidate_id, base) for c in selected]
    return clip_and_renormalize_deterministic(items, min_w, max_w)


def assign_weights_bucket_equal(
    selected: List[CandidateIn],
    bucket_by: List[str],
    min_w: float,
    max_w: float,
) -> Tuple[List[WeightItem], Dict[str, Any]]:
    # Build buckets
    def bucket_key(c: CandidateIn) -> Tuple:
        k = []
        for b in bucket_by:
            if b == "dataset_id":
                k.append(c.dataset_id)
            elif b == "strategy_id":
                k.append(c.strategy_id)
            else:
                raise ValueError(f"Unknown bucket key: {b}")
        return tuple(k)

    buckets: Dict[Tuple, List[CandidateIn]] = {}
    for c in selected:
        buckets.setdefault(bucket_key(c), []).append(c)

    num_buckets = len(buckets)
    bucket_weight = 1.0 / num_buckets

    items: List[WeightItem] = []
    for k in sorted(buckets.keys()):  # deterministic bucket ordering
        members = buckets[k]
        w_each = bucket_weight / len(members)
        for c in sorted(members, key=_candidate_sort_key):  # deterministic in-bucket
            items.append(WeightItem(c.candidate_id, w_each))

    return clip_and_renormalize_deterministic(items, min_w, max_w)


def assign_weights_score_weighted(selected: List[CandidateIn], min_w: float, max_w: float) -> Tuple[List[WeightItem], Dict[str, Any]]:
    scores = [float(c.score) for c in selected]
    sum_scores = sum(scores)

    items: List[WeightItem] = []
    if sum_scores > 0 and all(s > 0 for s in scores):
        for c in selected:
            items.append(WeightItem(c.candidate_id, float(c.score) / sum_scores))
    else:
        # deterministic fallback: rank-based weights (higher score gets larger weight)
        ranked = sorted(selected, key=_candidate_sort_key)
        # ranked is already score desc via _candidate_sort_key (negative score)
        n = len(ranked)
        # weights proportional to (n-rank)
        denom = n * (n + 1) / 2
        for i, c in enumerate(ranked):
            w = (n - i) / denom
            items.append(WeightItem(c.candidate_id, w))

    return clip_and_renormalize_deterministic(items, min_w, max_w)


# -----------------------------
# Export pack loading
# -----------------------------
def export_dir(exports_root: Path, season: str, export_name: str) -> Path:
    return exports_root / "seasons" / season / export_name


def load_export_manifest(exports_root: Path, season: str, export_name: str) -> Tuple[Dict[str, Any], str]:
    p = export_dir(exports_root, season, export_name) / "manifest.json"
    if not p.exists():
        raise FileNotFoundError(str(p))
    data = read_json(p)
    # Deterministic manifest hash uses canonical json (not raw bytes) for stability
    export_manifest_sha256 = sha256_text(canonical_json(data))
    return data, export_manifest_sha256


def load_candidates(exports_root: Path, season: str, export_name: str) -> Tuple[List[CandidateIn], str]:
    p = export_dir(exports_root, season, export_name) / "candidates.json"
    if not p.exists():
        raise FileNotFoundError(str(p))
    raw_bytes = p.read_bytes()
    candidates_sha256 = sha256_bytes(raw_bytes)

    arr = json.loads(raw_bytes.decode("utf-8"))
    if not isinstance(arr, list):
        raise ValueError("candidates.json must be a list")

    out: List[CandidateIn] = []
    for row in arr:
        out.append(
            CandidateIn(
                candidate_id=row["candidate_id"],
                strategy_id=row["strategy_id"],
                dataset_id=row["dataset_id"],
                params=row.get("params", {}) or {},
                score=float(row["score"]),
                season=row.get("season", season),
                source_batch=row["source_batch"],
                source_export=row.get("source_export", export_name),
            )
        )
    return out, candidates_sha256


# -----------------------------
# Legacy summary computation (for backward compatibility)
# -----------------------------
from collections import defaultdict
from typing import Dict, List

from FishBroWFS_V2.contracts.portfolio.plan_models import PlanSummary


def _bucket_key(candidate, bucket_by: List[str]) -> str:
    """
    Deterministic bucket key.
    Example: bucket_by=["dataset_id"] => "dataset_id=ds1"
    Multiple fields => "dataset_id=ds1|strategy_id=stratA"
    """
    parts = []
    for f in bucket_by:
        v = getattr(candidate, f, None)
        parts.append(f"{f}={v}")
    return "|".join(parts)


def _compute_summary_legacy(universe: list, weights: list, bucket_by: List[str]) -> PlanSummary:
    """
    universe: List[PlannedCandidate]
    weights:  List[PlannedWeight] (candidate_id, weight)
    """
    # Map candidate_id -> weight
    wmap: Dict[str, float] = {w.candidate_id: float(w.weight) for w in weights}

    total_candidates = len(universe)
    total_weight = sum(wmap.get(c.candidate_id, 0.0) for c in universe)

    # bucket counts / weights
    b_counts: Dict[str, int] = defaultdict(int)
    b_weights: Dict[str, float] = defaultdict(float)

    for c in universe:
        b = _bucket_key(c, bucket_by)
        b_counts[b] += 1
        b_weights[b] += wmap.get(c.candidate_id, 0.0)

    # concentration_herfindahl = sum_i w_i^2
    herf = 0.0
    for c in universe:
        w = wmap.get(c.candidate_id, 0.0)
        herf += w * w

    # Optional new fields (best effort)
    # concentration_top1/top3 from sorted weights
    ws_sorted = sorted([wmap.get(c.candidate_id, 0.0) for c in universe], reverse=True)
    top1 = ws_sorted[0] if ws_sorted else 0.0
    top3 = sum(ws_sorted[:3]) if ws_sorted else 0.0

    return PlanSummary(
        # legacy fields
        total_candidates=total_candidates,
        total_weight=float(total_weight),
        bucket_counts=dict(b_counts),
        bucket_weights=dict(b_weights),
        concentration_herfindahl=float(herf),
        # new optional fields
        num_selected=total_candidates,
        num_buckets=len(b_counts),
        bucket_by=list(bucket_by),
        concentration_top1=float(top1),
        concentration_top3=float(top3),
    )


# -----------------------------
# Plan ID + building
# -----------------------------
def compute_plan_id(export_manifest_sha256: str, candidates_file_sha256: str, payload: PlanCreatePayload) -> str:
    pid = sha256_text(
        canonical_json(
            {
                "export_manifest_sha256": export_manifest_sha256,
                "candidates_file_sha256": candidates_file_sha256,
                "payload": json.loads(payload.model_dump_json()),
            }
        )
    )[:16]
    return "plan_" + pid


def build_portfolio_plan_from_export(
    *,
    exports_root: Path,
    season: str,
    export_name: str,
    payload: PlanCreatePayload,
    # batch_api needs artifacts_root; passing in is allowed.
    artifacts_root: Optional[Path] = None,
) -> PortfolioPlan:
    """
    Read-only over exports tree.
    Enrichment (optional) uses batch_api as the ONLY allowed artifacts access.

    Raises:
      FileNotFoundError: export missing
      ValueError: business rule invalid (e.g. no candidates selected)
    """
    _manifest, export_manifest_sha256 = load_export_manifest(exports_root, season, export_name)
    candidates, candidates_sha256 = load_candidates(exports_root, season, export_name)
    candidates_file_sha256 = candidates_sha256
    candidates_items_sha256 = None

    candidates_sorted = sorted(candidates, key=_candidate_sort_key)

    selected, sel_rep = apply_selection_constraints(
        candidates_sorted,
        payload.top_n,
        payload.max_per_strategy,
        payload.max_per_dataset,
    )

    if not selected:
        raise ValueError("No candidates selected for plan")

    # Weighting
    bucket_by = [str(b) for b in payload.bucket_by]  # ensure List[str]
    if payload.weighting == "bucket_equal":
        weight_items, w_rep = assign_weights_bucket_equal(selected, bucket_by, payload.min_weight, payload.max_weight)
        reason = "bucket_equal"
    elif payload.weighting == "equal":
        weight_items, w_rep = assign_weights_equal(selected, payload.min_weight, payload.max_weight)
        reason = "equal"
    elif payload.weighting == "score_weighted":
        weight_items, w_rep = assign_weights_score_weighted(selected, payload.min_weight, payload.max_weight)
        reason = "score_weighted"
    else:
        raise ValueError(f"Unknown weighting policy: {payload.weighting}")

    # Build planned universe + weights
    # weight_items order matches construction; but we also want stable mapping by candidate_id
    w_map = {wi.candidate_id: wi.weight for wi in weight_items}

    universe: List[PlannedCandidate] = []
    weights: List[PlannedWeight] = []

    # Deterministic universe order: use selected order (already deterministic)
    for c in selected:
        cid = c.candidate_id
        universe.append(
            PlannedCandidate(
                candidate_id=cid,
                strategy_id=c.strategy_id,
                dataset_id=c.dataset_id,
                params=c.params,
                score=float(c.score),
                season=season,
                source_batch=c.source_batch,
                source_export=export_name,
            )
        )
        weights.append(
            PlannedWeight(
                candidate_id=cid,
                weight=float(w_map[cid]),
                reason=reason,
            )
        )

    # Enrichment via batch_api (optional)
    if payload.enrich_with_batch_api:
        if artifacts_root is None:
            # No artifacts root => cannot enrich, but should not fail
            artifacts_root = None

        if artifacts_root is not None:
            # cache per batch_id to keep deterministic + efficient
            cache: Dict[str, Dict[str, Any]] = {}
            for pc in universe:
                bid = pc.source_batch
                if bid not in cache:
                    cache[bid] = {"batch_state": None, "batch_counts": None, "batch_metrics": None}
                    # batch_state + counts
                    try:
                        if "batch_state" in payload.enrich_fields or "batch_counts" in payload.enrich_fields:
                            # use batch_api.read_execution
                            ex = batch_api.read_execution(artifacts_root, bid)
                            cache[bid]["batch_state"] = batch_api.get_batch_state(ex)
                            cache[bid]["batch_counts"] = batch_api.count_states(ex)
                    except Exception:
                        pass
                    # batch_metrics
                    try:
                        if "batch_metrics" in payload.enrich_fields:
                            s = batch_api.read_summary(artifacts_root, bid)
                            cache[bid]["batch_metrics"] = s.get("metrics", {})
                    except Exception:
                        pass
                # assign enrichment
                pc.batch_state = cache[bid]["batch_state"]
                pc.batch_counts = cache[bid]["batch_counts"]
                pc.batch_metrics = cache[bid]["batch_metrics"]

    # Build constraints report
    constraints_report = ConstraintsReport(
        max_per_strategy_truncated=sel_rep.max_per_strategy_truncated,
        max_per_dataset_truncated=sel_rep.max_per_dataset_truncated,
        max_weight_clipped=w_rep.get("max_weight_clipped", []),
        min_weight_clipped=w_rep.get("min_weight_clipped", []),
        renormalization_applied=w_rep.get("renormalization_applied", False),
        renormalization_factor=w_rep.get("renormalization_factor"),
    )

    # Build plan summary (legacy schema for backward compatibility)
    plan_summary = _compute_summary_legacy(universe, weights, bucket_by)

    # Build source ref
    source_ref = SourceRef(
        season=season,
        export_name=export_name,
        export_manifest_sha256=export_manifest_sha256,
        candidates_sha256=candidates_sha256,
        candidates_file_sha256=candidates_file_sha256,
        candidates_items_sha256=candidates_items_sha256,
    )

    # Build plan ID
    plan_id = compute_plan_id(export_manifest_sha256, candidates_file_sha256, payload)

    # Build portfolio plan
    plan = PortfolioPlan(
        plan_id=plan_id,
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
        source=source_ref,
        config=payload.model_dump(),
        universe=universe,
        weights=weights,
        constraints_report=constraints_report,
        summaries=plan_summary,
    )
    return plan


def _plan_dir(outputs_root: Path, plan_id: str) -> Path:
    return outputs_root / "portfolio" / "plans" / plan_id


def write_plan_package(outputs_root: Path, plan) -> Path:
    """
    Controlled mutation ONLY:
      outputs/portfolio/plans/{plan_id}/

    Idempotent:
      if plan_dir exists -> do not rewrite.
    """
    pdir = _plan_dir(outputs_root, plan.plan_id)
    if pdir.exists():
        return pdir

    # Ensure directory
    ensure_dir(pdir)

    # Create write scope for this plan directory
    scope = create_plan_scope(pdir)

    # Helper to write a file with scope validation
    def write_scoped(rel_path: str, content: str) -> None:
        scope.assert_allowed_rel(rel_path)
        write_text_atomic(pdir / rel_path, content)

    # 1) portfolio_plan.json (canonical)
    plan_obj = plan.model_dump() if hasattr(plan, "model_dump") else plan
    plan_json = canonical_json(plan_obj)
    write_scoped("portfolio_plan.json", plan_json)

    # 2) plan_metadata.json (minimal)
    meta = {
        "plan_id": plan.plan_id,
        "generated_at_utc": getattr(plan, "generated_at_utc", None),
        "source": plan.source.model_dump() if hasattr(plan, "source") else None,
        "note": (plan.config.get("note") if hasattr(plan, "config") and isinstance(plan.config, dict) else None),
    }
    write_scoped("plan_metadata.json", canonical_json(meta))

    # 3) plan_checksums.json (flat dict)
    checksums = {}
    for rel in ["plan_metadata.json", "portfolio_plan.json"]:
        # Reading already‑written files is safe; they are inside the scope.
        checksums[rel] = sha256_bytes((pdir / rel).read_bytes())
    write_scoped("plan_checksums.json", canonical_json(checksums))

    # 4) plan_manifest.json (two-phase self hash)
    portfolio_plan_sha256 = sha256_bytes((pdir / "portfolio_plan.json").read_bytes())
    checksums = json.loads((pdir / "plan_checksums.json").read_text(encoding="utf-8"))

    # Source hashes
    export_manifest_sha256 = getattr(plan.source, "export_manifest_sha256", None)
    candidates_sha256 = getattr(plan.source, "candidates_sha256", None)
    candidates_file_sha256 = getattr(plan.source, "candidates_file_sha256", None)
    candidates_items_sha256 = getattr(plan.source, "candidates_items_sha256", None)

    # Build files listing (sorted by rel_path asc)
    files = []
    for rel_path in ["portfolio_plan.json", "plan_metadata.json", "plan_checksums.json"]:
        file_path = pdir / rel_path
        if file_path.exists():
            files.append({
                "rel_path": rel_path,
                "sha256": sha256_bytes(file_path.read_bytes())
            })
    # Sort by rel_path
    files.sort(key=lambda x: x["rel_path"])
    
    # Compute files_sha256 (concatenated hashes)
    concatenated = "".join(f["sha256"] for f in files)
    files_sha256 = sha256_bytes(concatenated.encode("utf-8"))

    # Build manifest with fields expected by tests
    manifest_base = {
        "manifest_type": "plan",
        "manifest_version": "1.0",
        "id": plan.plan_id,
        "plan_id": plan.plan_id,
        "generated_at_utc": getattr(plan, "generated_at_utc", None),
        "source": plan.source.model_dump() if hasattr(plan.source, "model_dump") else plan.source,
        "config": plan.config if isinstance(plan.config, dict) else plan.config.model_dump(),
        "summaries": plan.summaries.model_dump() if hasattr(plan.summaries, "model_dump") else plan.summaries,
        "export_manifest_sha256": export_manifest_sha256,
        "candidates_sha256": candidates_sha256,
        "candidates_file_sha256": candidates_file_sha256,
        "candidates_items_sha256": candidates_items_sha256,
        "portfolio_plan_sha256": portfolio_plan_sha256,
        "checksums": checksums,
        "files": files,
        "files_sha256": files_sha256,
    }

    manifest_path = pdir / "plan_manifest.json"
    # phase-1
    write_scoped("plan_manifest.json", canonical_json(manifest_base))
    # self-hash of phase-1 canonical bytes
    manifest_sha256 = sha256_bytes(manifest_path.read_bytes())
    # phase-2
    manifest_final = dict(manifest_base)
    manifest_final["manifest_sha256"] = manifest_sha256
    write_scoped("plan_manifest.json", canonical_json(manifest_final))

    return pdir


