"""Portfolio specification data model.

Phase 8: Portfolio OS - versioned, auditable, replayable portfolio definitions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass(frozen=True)
class PortfolioLeg:
    """Portfolio leg definition.
    
    A leg represents one trading strategy applied to one symbol/timeframe.
    
    Attributes:
        leg_id: Unique leg identifier (e.g., "mnq_60_sma")
        symbol: Symbol identifier (e.g., "CME.MNQ")
        timeframe_min: Timeframe in minutes (e.g., 60)
        session_profile: Path to session profile YAML file or profile ID
        strategy_id: Strategy identifier (must exist in registry)
        strategy_version: Strategy version (must match registry)
        params: Strategy parameters dict (key-value pairs)
        enabled: Whether this leg is enabled (default: True)
        tags: Optional tags for categorization (default: empty list)
    """
    leg_id: str
    symbol: str
    timeframe_min: int
    session_profile: str
    strategy_id: str
    strategy_version: str
    params: Dict[str, float]
    enabled: bool = True
    tags: List[str] = field(default_factory=list)
    
    def __post_init__(self) -> None:
        """Validate leg fields."""
        if not self.leg_id:
            raise ValueError("leg_id cannot be empty")
        if not self.symbol:
            raise ValueError("symbol cannot be empty")
        if self.timeframe_min <= 0:
            raise ValueError(f"timeframe_min must be > 0, got {self.timeframe_min}")
        if not self.session_profile:
            raise ValueError("session_profile cannot be empty")
        if not self.strategy_id:
            raise ValueError("strategy_id cannot be empty")
        if not self.strategy_version:
            raise ValueError("strategy_version cannot be empty")
        if not isinstance(self.params, dict):
            raise ValueError(f"params must be dict, got {type(self.params)}")


@dataclass(frozen=True)
class PortfolioSpec:
    """Portfolio specification.
    
    Defines a portfolio as a collection of legs (trading strategies).
    
    Attributes:
        portfolio_id: Unique portfolio identifier (e.g., "mvp")
        version: Portfolio version (e.g., "2026Q1")
        data_tz: Data timezone (default: "Asia/Taipei", fixed)
        legs: List of portfolio legs
    """
    portfolio_id: str
    version: str
    data_tz: str = "Asia/Taipei"  # Fixed default
    legs: List[PortfolioLeg] = field(default_factory=list)
    
    def __post_init__(self) -> None:
        """Validate portfolio spec."""
        if not self.portfolio_id:
            raise ValueError("portfolio_id cannot be empty")
        if not self.version:
            raise ValueError("version cannot be empty")
        if self.data_tz != "Asia/Taipei":
            raise ValueError(f"data_tz must be 'Asia/Taipei' (fixed), got {self.data_tz}")
        
        # Check leg_id uniqueness
        leg_ids = [leg.leg_id for leg in self.legs]
        if len(leg_ids) != len(set(leg_ids)):
            duplicates = [lid for lid in leg_ids if leg_ids.count(lid) > 1]
            raise ValueError(f"Duplicate leg_id found: {set(duplicates)}")
