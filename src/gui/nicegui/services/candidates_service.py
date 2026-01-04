"""Candidates service - fetch top‑K candidates."""
import logging
import os
from typing import List, Dict, Any, Optional
import requests

from .status_service import get_status

logger = logging.getLogger(__name__)

# Configurable API base via environment variable
# Default to empty string (relative path) for same-origin requests
API_BASE = os.environ.get("FISHBRO_API_BASE", "").rstrip("/")


def _fallback_candidates(k: int) -> List[Dict[str, Any]]:
    """Return fallback mock candidate data."""
    return [
        {"rank": 1, "strategy_id": "L7", "side": "Long", "sharpe": 2.45, "win_rate": 0.642, "max_dd": -0.123},
        {"rank": 2, "strategy_id": "S3", "side": "Short", "sharpe": 2.12, "win_rate": 0.618, "max_dd": -0.157},
        {"rank": 3, "strategy_id": "L2", "side": "Long", "sharpe": 1.98, "win_rate": 0.595, "max_dd": -0.101},
    ][:k]


def fetch_candidates(season: str = "2026Q1", k: int = 20) -> List[Dict[str, Any]]:
    """Fetch top‑K candidates from backend.
    
    Args:
        season: Season identifier.
        k: Number of candidates.
    
    Returns:
        List of candidate dicts.
    """
    # If backend is down, skip network call and return fallback data
    if not get_status().backend_up:
        logger.debug("Backend down, returning fallback candidates")
        return _fallback_candidates(k)
    
    # Placeholder: call appropriate endpoint when available
    try:
        # This endpoint may not exist yet; fallback to empty list
        resp = requests.get(f"{API_BASE}/seasons/{season}/compare/topk?k={k}", timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("items", [])
    except Exception as e:
        logger.warning(f"Failed to fetch candidates: {e}")
    
    # Fallback mock data
    return _fallback_candidates(k)


def get_top_candidates(top_k: int = 20, side: Optional[str] = None, sort_by: str = "Sharpe", dedup: bool = False) -> List[Dict[str, Any]]:
    """Return top‑K candidates with optional filtering and sorting."""
    candidates = fetch_candidates(k=top_k)
    # Filter by side
    if side:
        candidates = [c for c in candidates if c.get("side", "").lower() == side.lower()]
    # Sort
    if sort_by == "Sharpe":
        candidates.sort(key=lambda c: c.get("sharpe", 0), reverse=True)
    elif sort_by == "Win Rate":
        candidates.sort(key=lambda c: c.get("win_rate", 0), reverse=True)
    elif sort_by == "Max DD":
        candidates.sort(key=lambda c: c.get("max_dd", 0), reverse=False)  # lower max dd is better
    elif sort_by == "Profit Factor":
        candidates.sort(key=lambda c: c.get("profit_factor", 0), reverse=True)
    # Deduplicate by strategy_id (if dedup True)
    if dedup:
        seen = set()
        unique = []
        for c in candidates:
            sid = c.get("strategy_id")
            if sid not in seen:
                seen.add(sid)
                unique.append(c)
        candidates = unique
    return candidates[:top_k]


def get_candidate_stats(candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute aggregate statistics from a list of candidates."""
    if not candidates:
        return {"total": 0, "avg_sharpe": 0, "avg_win_rate": 0, "best_strategy": "N/A"}
    total = len(candidates)
    avg_sharpe = sum(c.get("sharpe", 0) for c in candidates) / total
    avg_win_rate = sum(c.get("win_rate", 0) for c in candidates) / total
    # Best strategy is highest Sharpe
    best = max(candidates, key=lambda c: c.get("sharpe", 0), default={})
    best_strategy = best.get("strategy_id", "N/A")
    return {
        "total": total,
        "avg_sharpe": avg_sharpe,
        "avg_win_rate": avg_win_rate,
        "best_strategy": best_strategy,
    }