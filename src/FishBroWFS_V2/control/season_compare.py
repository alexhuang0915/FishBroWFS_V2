"""
Phase 15.1: Season-level cross-batch comparison helpers.

Contracts:
- Read-only: only reads season_index.json and artifacts/{batch_id}/summary.json
- No on-the-fly recomputation of batch summary
- Deterministic:
  - Sort by score desc
  - Tie-break by batch_id asc
  - Tie-break by job_id asc
- Robust:
  - Missing/corrupt batch summary is skipped (never 500 the whole season)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _extract_job_id(row: Any) -> Optional[str]:
    if not isinstance(row, dict):
        return None
    # canonical
    if "job_id" in row and row["job_id"] is not None:
        return str(row["job_id"])
    # common alternates (defensive)
    if "id" in row and row["id"] is not None:
        return str(row["id"])
    return None


def _extract_score(row: Any) -> Optional[float]:
    if not isinstance(row, dict):
        return None

    # canonical
    if "score" in row:
        try:
            v = row["score"]
            if v is None:
                return None
            return float(v)
        except Exception:
            return None

    # alternate: metrics.score
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


@dataclass(frozen=True)
class SeasonTopKResult:
    season: str
    k: int
    items: list[dict[str, Any]]
    skipped_batches: list[str]


def merge_season_topk(
    *,
    artifacts_root: Path,
    season_index: dict[str, Any],
    k: int,
) -> SeasonTopKResult:
    """
    Merge topk entries across batches listed in season_index.json.

    Output item schema:
      {
        "batch_id": "...",
        "job_id": "...",
        "score": 1.23,
        "row": {... original topk row ...}
      }

    Skipping rules:
    - missing summary.json -> skip batch
    - invalid json -> skip batch
    - missing topk list -> treat as empty
    """
    season = str(season_index.get("season", ""))
    batches = season_index.get("batches", [])
    if not isinstance(batches, list):
        raise ValueError("season_index.batches must be a list")

    # sanitize k
    try:
        k_int = int(k)
    except Exception:
        k_int = 20
    if k_int <= 0:
        k_int = 20

    merged: list[dict[str, Any]] = []
    skipped: list[str] = []

    # deterministic traversal order: batch_id asc
    batch_ids: list[str] = []
    for b in batches:
        if isinstance(b, dict) and "batch_id" in b:
            batch_ids.append(str(b["batch_id"]))
    batch_ids = sorted(set(batch_ids))

    for batch_id in batch_ids:
        summary_path = artifacts_root / batch_id / "summary.json"
        if not summary_path.exists():
            skipped.append(batch_id)
            continue

        try:
            summary = _read_json(summary_path)
        except Exception:
            skipped.append(batch_id)
            continue

        topk = summary.get("topk", [])
        if not isinstance(topk, list):
            # malformed topk -> treat as skip (stronger safety)
            skipped.append(batch_id)
            continue

        for row in topk:
            job_id = _extract_job_id(row)
            if job_id is None:
                # cannot tie-break deterministically without job_id
                continue
            score = _extract_score(row)
            merged.append(
                {
                    "batch_id": batch_id,
                    "job_id": job_id,
                    "score": score,
                    "row": row,
                }
            )

    def sort_key(item: dict[str, Any]) -> tuple:
        # score desc; None goes last
        score = item.get("score")
        score_is_none = score is None
        # For numeric scores: use -score
        neg_score = 0.0
        if not score_is_none:
            try:
                neg_score = -float(score)
            except Exception:
                score_is_none = True
                neg_score = 0.0

        return (
            score_is_none,     # False first, True last
            neg_score,         # smaller first -> higher score first
            str(item.get("batch_id", "")),
            str(item.get("job_id", "")),
        )

    merged_sorted = sorted(merged, key=sort_key)
    merged_sorted = merged_sorted[:k_int]

    return SeasonTopKResult(
        season=season,
        k=k_int,
        items=merged_sorted,
        skipped_batches=sorted(set(skipped)),
    )