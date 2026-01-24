"""
Research Contracts (Layer 2).

Defines the output of the Research Engine.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Any

from pydantic import BaseModel, Field
from contracts.strategy import StrategySpec

# Re-export key modules to avoid "not a package" errors from submodule imports
from . import research_narrative
from . import research_flow_kernel

class Trade(BaseModel):
    """A single simulated trade."""
    entry_time: datetime
    exit_time: datetime
    direction: str
    entry_price: float
    exit_price: float
    quantity: float
    pnl: float
    pnl_percent: float
    
class PerformanceMetrics(BaseModel):
    """Aggregate performance metrics."""
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    total_trades: int

class ResearchResult(BaseModel):
    """
    The immutable result of a Backtest.
    """
    run_id: str = Field(..., description="Unique ID for this run (hash of inputs)")
    strategy_hash: str
    data_snapshot_id: str
    
    metrics: PerformanceMetrics
    trades: List[Trade]
    
    # Logs/Metadata
    logs: List[str] = Field(default_factory=list)
    computed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
