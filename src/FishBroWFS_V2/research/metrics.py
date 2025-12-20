"""Canonical Metrics Schema for research results.

Phase 9: Standardized format for portfolio run results.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Dict


@dataclass(frozen=True)
class CanonicalMetrics:
    """
    Canonical metrics schema for research results.
    
    This is the official format for summarizing portfolio run results.
    All fields are required - missing data must be handled at extraction time.
    """
    # Identification
    run_id: str
    portfolio_id: str | None
    portfolio_version: str | None
    strategy_id: str | None
    strategy_version: str | None
    symbol: str | None
    timeframe_min: int | None
    
    # Performance (core numerical fields)
    net_profit: float
    max_drawdown: float
    profit_factor: float | None  # May be None if not available in artifacts
    sharpe: float | None  # May be None if not available in artifacts
    trades: int
    
    # Derived scores (computed from existing values only)
    score_net_mdd: float  # Net / |MDD|, raises if MDD=0
    score_final: float  # score_net_mdd * (trades ** 0.25)
    
    # Metadata
    bars: int
    start_date: str  # ISO8601 format or empty string
    end_date: str  # ISO8601 format or empty string
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CanonicalMetrics:
        """Create from dictionary."""
        return cls(**data)

