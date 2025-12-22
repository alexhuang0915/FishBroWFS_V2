
"""Pydantic schema for winners_v2.json validation.

Validates winners v2 structure with KPI metrics.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from typing import Any, Dict, List, Optional


class WinnerRow(BaseModel):
    """
    Winner row schema.
    
    Represents a single winner with strategy info and KPI metrics.
    """
    strategy_id: str
    symbol: str
    timeframe: str
    params: Dict[str, Any] = Field(default_factory=dict)
    
    # Required KPI metrics
    net_profit: float
    max_drawdown: float
    trades: int
    
    # Optional metrics
    win_rate: Optional[float] = None
    sharpe: Optional[float] = None
    sqn: Optional[float] = None
    
    # Evidence links (if already present)
    evidence: Dict[str, str] = Field(default_factory=dict)  # pointers/paths if already present
    
    # Additional fields from v2 schema (for backward compatibility)
    candidate_id: Optional[str] = None
    score: Optional[float] = None
    metrics: Optional[Dict[str, Any]] = None
    source: Optional[Dict[str, Any]] = None


class WinnersV2(BaseModel):
    """
    Winners v2 schema.
    
    Validates winners_v2.json structure with rows and metadata.
    Supports both v2 format (with topk) and normalized format (with rows).
    """
    config_hash: str  # Required top-level field for DIRTY check contract
    schema_version: Optional[str] = None  # "v2" or "schema" field
    run_id: Optional[str] = None
    stage: Optional[str] = None  # stage_name
    rows: List[WinnerRow] = Field(default_factory=list)
    meta: Dict[str, Any] = Field(default_factory=dict)
    
    # Additional fields from v2 schema (for backward compatibility)
    schema_name: Optional[str] = Field(default=None, alias="schema")  # "v2" - renamed to avoid conflict
    stage_name: Optional[str] = None
    generated_at: Optional[str] = None
    topk: Optional[List[Dict[str, Any]]] = None
    notes: Optional[Dict[str, Any]] = None
    
    model_config = ConfigDict(extra="allow", populate_by_name=True)  # Allow extra fields and support alias


