
"""
Phase 15.2: Season compare batch cards + lightweight leaderboard.

Contracts:
- Read-only: reads season_index.json and artifacts/{batch_id}/summary.json
- No on-the-fly recomputation
- Deterministic:
  - Batches list sorted by batch_id asc
  - Leaderboard sorted by score desc, tie-break batch_id asc, job_id asc
- Robust:
  - Missing/corrupt summary.json => summary_ok=False, keep other fields
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_get_job_id(row: Any) -> Optional[str]:
    if not isinstance(row, dict):
        return None
    if row.get("job_id") is not None:
        return str(row["job_id"])
    if row.get("id") is not None:
        return str(row["id"])
    return None


def _safe_get_score(row: Any) -> Optional[float]:
    if not isinstance(row, dict):
        return None
    if "score" in row:
        try:
            v = row["score"]
            if v is None:
                return None
            return float(v)
        except Exception:
            return None
    m = row.get("metrics")
    if isinstance(m, dict) and "score" in m:
        try:
            v = m["score"]
            if v is None:
                return None
            return float(v)
        except Exception:
            return None
    return None


def _extract_group_key(row: Any, group_by: str) -> str:
    """
    group_by candidates:
      - "strategy_id"
      - "dataset_id"
    If not present, return "unknown".
    """
    if not isinstance(row, dict):
        return "unknown"
    v = row.get(group_by)
    if v is None:
        # sometimes nested
        meta = row.get("meta")
        if isinstance(meta, dict):
            v = meta.get(group_by)
    return str(v) if v is not None else "unknown"


@dataclass(frozen=True)
class SeasonBatchesResult:
    season: str
    batches: list[dict[str, Any]]
    skipped_summaries: list[str]


def build_season_batch_cards(
    *,
    artifacts_root: Path,
    season_index: dict[str, Any],
) -> SeasonBatchesResult:
    """
    Build deterministic batch cards for a season.

    For each batch_id in season_index.batches:
      - frozen/tags/note/index_hash/summary_hash are read from season_index (source of truth)
      - summary.json is read best-effort:
          top_job_id, top_score, topk_size
      - missing/corrupt summary => summary_ok=False
    """
    season = str(season_index.get("season", ""))
    batches_in = season_index.get("batches", [])
    if not isinstance(batches_in, list):
        raise ValueError("season_index.batches must be a list")

    # deterministic batch_id list
    by_id: dict[str, dict[str, Any]] = {}
    for b in batches_in:
        if not isinstance(b, dict) or "batch_id" not in b:
            continue
        batch_id = str(b["batch_id"])
        by_id[batch_id] = b

    batch_ids = sorted(by_id.keys())

    cards: list[dict[str, Any]] = []
    skipped: list[str] = []

    for batch_id in batch_ids:
        b = by_id[batch_id]
        card: dict[str, Any] = {
            "batch_id": batch_id,
            "frozen": bool(b.get("frozen", False)),
            "tags": list(b.get("tags", []) or []),
            "note": b.get("note", "") or "",
            "index_hash": b.get("index_hash"),
            "summary_hash": b.get("summary_hash"),
            # summary-derived
            "summary_ok": True,
            "top_job_id": None,
            "top_score": None,
            "topk_size": 0,
        }

        summary_path = artifacts_root / batch_id / "summary.json"
        if not summary_path.exists():
            card["summary_ok"] = False
            skipped.append(batch_id)
            cards.append(card)
            continue

        try:
            s = _read_json(summary_path)
            topk = s.get("topk", [])
            if not isinstance(topk, list):
                raise ValueError("summary.topk must be list")

            card["topk_size"] = len(topk)
            if len(topk) > 0:
                first = topk[0]
                card["top_job_id"] = _safe_get_job_id(first)
                card["top_score"] = _safe_get_score(first)
        except Exception:
            card["summary_ok"] = False
            skipped.append(batch_id)

        cards.append(card)

    return SeasonBatchesResult(season=season, batches=cards, skipped_summaries=sorted(set(skipped)))


def build_season_leaderboard(
    *,
    artifacts_root: Path,
    season_index: dict[str, Any],
    group_by: str = "strategy_id",
    per_group: int = 3,
) -> dict[str, Any]:
    """
    Build a grouped leaderboard from batch summaries' topk rows.

    Returns:
      {
        "season": "...",
        "group_by": "strategy_id",
        "per_group": 3,
        "groups": [
           {"key": "...", "items": [...]},
           ...
        ],
        "skipped_batches": [...]
      }
    """
    season = str(season_index.get("season", ""))
    batches_in = season_index.get("batches", [])
    if not isinstance(batches_in, list):
        raise ValueError("season_index.batches must be a list")

    if group_by not in ("strategy_id", "dataset_id"):
        raise ValueError("group_by must be 'strategy_id' or 'dataset_id'")

    try:
        per_group_i = int(per_group)
    except Exception:
        per_group_i = 3
    if per_group_i <= 0:
        per_group_i = 3

    # deterministic batch traversal: batch_id asc
    batch_ids = sorted({str(b["batch_id"]) for b in batches_in if isinstance(b, dict) and "batch_id" in b})

    merged: list[dict[str, Any]] = []
    skipped: list[str] = []

    for batch_id in batch_ids:
        p = artifacts_root / batch_id / "summary.json"
        if not p.exists():
            skipped.append(batch_id)
            continue
        try:
            s = _read_json(p)
            topk = s.get("topk", [])
            if not isinstance(topk, list):
                skipped.append(batch_id)
                continue
            for row in topk:
                job_id = _safe_get_job_id(row)
                if job_id is None:
                    continue
                score = _safe_get_score(row)
                merged.append(
                    {
                        "batch_id": batch_id,
                        "job_id": job_id,
                        "score": score,
                        "group": _extract_group_key(row, group_by),
                        "row": row,
                    }
                )
        except Exception:
            skipped.append(batch_id)
            continue

    def sort_key(it: dict[str, Any]) -> tuple:
        score = it.get("score")
        score_is_none = score is None
        neg_score = 0.0
        if not score_is_none:
            try:
                # score is not None at this point, but mypy doesn't know
                neg_score = -float(score)  # type: ignore[arg-type]
            except Exception:
                score_is_none = True
                neg_score = 0.0
        return (
            score_is_none,
            neg_score,
            str(it.get("batch_id", "")),
            str(it.get("job_id", "")),
        )

    merged_sorted = sorted(merged, key=sort_key)

    # group, keep top per_group_i in deterministic order (already sorted)
    groups: dict[str, list[dict[str, Any]]] = {}
    for it in merged_sorted:
        key = str(it.get("group", "unknown"))
        if key not in groups:
            groups[key] = []
        if len(groups[key]) < per_group_i:
            groups[key].append(
                {
                    "batch_id": it["batch_id"],
                    "job_id": it["job_id"],
                    "score": it["score"],
                    "row": it["row"],
                }
            )

    # deterministic group ordering: key asc
    out_groups = [{"key": k, "items": groups[k]} for k in sorted(groups.keys())]

    return {
        "season": season,
        "group_by": group_by,
        "per_group": per_group_i,
        "groups": out_groups,
        "skipped_batches": sorted(set(skipped)),
    }


