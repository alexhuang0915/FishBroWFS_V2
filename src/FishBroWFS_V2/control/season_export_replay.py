"""
Phase 16: Export Pack Replay Mode.

Allows compare endpoints to work from an exported season package
without requiring access to the original artifacts/ directory.

Key contracts:
- Read-only: only reads from exports root, never writes
- Deterministic: same ordering as original compare endpoints
- Fallback: if replay_index.json missing, raise FileNotFoundError
- No artifacts dependency: does not require artifacts/ directory
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


@dataclass(frozen=True)
class ReplaySeasonTopkResult:
    season: str
    k: int
    items: list[dict[str, Any]]
    skipped_batches: list[str]


@dataclass(frozen=True)
class ReplaySeasonBatchCardsResult:
    season: str
    batches: list[dict[str, Any]]
    skipped_summaries: list[str]


@dataclass(frozen=True)
class ReplaySeasonLeaderboardResult:
    season: str
    group_by: str
    per_group: int
    groups: list[dict[str, Any]]


def load_replay_index(exports_root: Path, season: str) -> dict[str, Any]:
    """
    Load replay_index.json from an exported season package.
    
    Raises:
        FileNotFoundError: if replay_index.json does not exist
        ValueError: if JSON is invalid
    """
    replay_path = exports_root / "seasons" / season / "replay_index.json"
    if not replay_path.exists():
        raise FileNotFoundError(f"replay_index.json not found for season {season}")
    
    text = replay_path.read_text(encoding="utf-8")
    return json.loads(text)


def replay_season_topk(
    exports_root: Path,
    season: str,
    k: int = 20,
) -> ReplaySeasonTopkResult:
    """
    Replay cross-batch TopK from exported season package.
    
    Implementation mirrors merge_season_topk but uses replay_index.json
    instead of reading artifacts/{batch_id}/summary.json.
    """
    replay_index = load_replay_index(exports_root, season)
    
    all_items: list[dict[str, Any]] = []
    skipped_batches: list[str] = []
    
    for batch_info in replay_index.get("batches", []):
        batch_id = batch_info.get("batch_id", "")
        summary = batch_info.get("summary")
        
        if summary is None:
            skipped_batches.append(batch_id)
            continue
        
        topk = summary.get("topk", [])
        if not isinstance(topk, list):
            skipped_batches.append(batch_id)
            continue
        
        # Add batch_id to each item for traceability
        for item in topk:
            if isinstance(item, dict):
                item_copy = dict(item)
                item_copy["_batch_id"] = batch_id
                all_items.append(item_copy)
    
    # Sort by score descending (best effort)
    def _score_key(item: dict[str, Any]) -> float:
        score = item.get("score")
        if isinstance(score, (int, float)):
            return float(score)
        return -float("inf")
    
    sorted_items = sorted(all_items, key=_score_key, reverse=True)
    topk_items = sorted_items[:k] if k > 0 else sorted_items
    
    return ReplaySeasonTopkResult(
        season=season,
        k=k,
        items=topk_items,
        skipped_batches=skipped_batches,
    )


def replay_season_batch_cards(
    exports_root: Path,
    season: str,
) -> ReplaySeasonBatchCardsResult:
    """
    Replay batch-level compare cards from exported season package.
    
    Implementation mirrors build_season_batch_cards but uses replay_index.json.
    Deterministic ordering: batches sorted by batch_id ascending.
    """
    replay_index = load_replay_index(exports_root, season)
    
    batches: list[dict[str, Any]] = []
    skipped_summaries: list[str] = []
    
    # Sort batches by batch_id for deterministic output
    batch_infos = replay_index.get("batches", [])
    sorted_batch_infos = sorted(batch_infos, key=lambda b: b.get("batch_id", ""))
    
    for batch_info in sorted_batch_infos:
        batch_id = batch_info.get("batch_id", "")
        summary = batch_info.get("summary")
        index = batch_info.get("index")
        
        if summary is None:
            skipped_summaries.append(batch_id)
            continue
        
        # Build batch card
        card: dict[str, Any] = {
            "batch_id": batch_id,
            "summary": summary,
        }
        
        if index is not None:
            card["index"] = index
        
        batches.append(card)
    
    return ReplaySeasonBatchCardsResult(
        season=season,
        batches=batches,
        skipped_summaries=skipped_summaries,
    )


def replay_season_leaderboard(
    exports_root: Path,
    season: str,
    group_by: str = "strategy_id",
    per_group: int = 3,
) -> ReplaySeasonLeaderboardResult:
    """
    Replay grouped leaderboard from exported season package.
    
    Implementation mirrors build_season_leaderboard but uses replay_index.json.
    """
    replay_index = load_replay_index(exports_root, season)
    
    # Collect all items with grouping key
    items_by_group: dict[str, list[dict[str, Any]]] = {}
    
    for batch_info in replay_index.get("batches", []):
        summary = batch_info.get("summary")
        if summary is None:
            continue
        
        topk = summary.get("topk", [])
        if not isinstance(topk, list):
            continue
        
        for item in topk:
            if not isinstance(item, dict):
                continue
            
            # Extract grouping key
            group_key = item.get(group_by, "")
            if not isinstance(group_key, str):
                group_key = str(group_key)
            
            if group_key not in items_by_group:
                items_by_group[group_key] = []
            
            items_by_group[group_key].append(item)
    
    # Sort items within each group by score descending
    def _score_key(item: dict[str, Any]) -> float:
        score = item.get("score")
        if isinstance(score, (int, float)):
            return float(score)
        return -float("inf")
    
    groups: list[dict[str, Any]] = []
    for group_key, group_items in items_by_group.items():
        sorted_items = sorted(group_items, key=_score_key, reverse=True)
        top_items = sorted_items[:per_group] if per_group > 0 else sorted_items
        
        groups.append({
            "key": group_key,
            "items": top_items,
            "total": len(group_items),
        })
    
    # Sort groups by key for deterministic output
    groups_sorted = sorted(groups, key=lambda g: g["key"])
    
    return ReplaySeasonLeaderboardResult(
        season=season,
        group_by=group_by,
        per_group=per_group,
        groups=groups_sorted,
    )