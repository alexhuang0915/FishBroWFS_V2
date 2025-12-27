
"""Winners schema v2 (SSOT).

Defines the v2 schema for winners.json with enhanced metadata.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List


WINNERS_SCHEMA_VERSION = "v2"


@dataclass(frozen=True)
class WinnerItemV2:
    """
    Winner item in v2 schema.
    
    Each item represents a top-K candidate with complete metadata.
    """
    candidate_id: str  # Format: {strategy_id}:{param_id} (temporary) or {strategy_id}:{params_hash[:12]} (future)
    strategy_id: str  # Strategy identifier (e.g., "donchian_atr")
    symbol: str  # Symbol identifier (e.g., "CME.MNQ" or "UNKNOWN")
    timeframe: str  # Timeframe (e.g., "60m" or "UNKNOWN")
    params: Dict[str, Any]  # Parameters dict (may be empty {} if not available)
    score: float  # Ranking score (finalscore, net_profit, or proxy_value)
    metrics: Dict[str, Any]  # Performance metrics (must include legacy fields: net_profit, max_dd, trades, param_id)
    source: Dict[str, Any]  # Source metadata (param_id, run_id, stage_name)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


def build_winners_v2_dict(
    *,
    stage_name: str,
    run_id: str,
    generated_at: str | None = None,
    topk: List[WinnerItemV2],
    notes: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    Build winners.json v2 structure.
    
    Args:
        stage_name: Stage identifier
        run_id: Run ID
        generated_at: ISO8601 timestamp (defaults to now if None)
        topk: List of WinnerItemV2 items
        notes: Additional notes dict (will be merged with default notes)
        
    Returns:
        Winners dict with v2 schema
    """
    if generated_at is None:
        generated_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    default_notes = {
        "schema": WINNERS_SCHEMA_VERSION,
    }
    
    if notes:
        default_notes.update(notes)
    
    return {
        "schema": WINNERS_SCHEMA_VERSION,
        "stage_name": stage_name,
        "generated_at": generated_at,
        "topk": [item.to_dict() for item in topk],
        "notes": default_notes,
    }


def is_winners_v2(winners: Dict[str, Any]) -> bool:
    """
    Check if winners dict is v2 schema.
    
    Args:
        winners: Winners dict
        
    Returns:
        True if v2 schema, False otherwise
    """
    # Check top-level schema field
    if winners.get("schema") == WINNERS_SCHEMA_VERSION:
        return True
    
    # Check notes.schema field (legacy check)
    notes = winners.get("notes", {})
    if isinstance(notes, dict) and notes.get("schema") == WINNERS_SCHEMA_VERSION:
        return True
    
    return False


def is_winners_legacy(winners: Dict[str, Any]) -> bool:
    """
    Check if winners dict is legacy (v1) schema.
    
    Args:
        winners: Winners dict
        
    Returns:
        True if legacy schema, False otherwise
    """
    # If it's v2, it's not legacy
    if is_winners_v2(winners):
        return False
    
    # Legacy format: {"topk": [...], "notes": {"schema": "v1"}} or just {"topk": [...]}
    if "topk" in winners:
        # Check if items have v2 structure (candidate_id, strategy_id, etc.)
        topk = winners.get("topk", [])
        if topk and isinstance(topk[0], dict):
            # If first item has candidate_id, it's v2
            if "candidate_id" in topk[0]:
                return False
        return True
    
    return False


