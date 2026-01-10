"""
Strategy Catalog Registry Loader

Defines available strategies with metadata and configuration references.
"""

from pathlib import Path
from typing import List, Dict, Optional
from functools import lru_cache
from enum import Enum

from pydantic import BaseModel, Field, field_validator


def get_registry_path(filename: str) -> Path:
    """Get path to registry configuration file."""
    from .. import get_config_root
    return get_config_root() / "registry" / filename


def load_yaml(path: Path) -> dict:
    """Load YAML file with proper error handling."""
    from .. import load_yaml as _load_yaml
    return _load_yaml(path)


class StrategyFamily(str, Enum):
    """Strategy family classification."""
    TREND_FOLLOWING = "trend_following"
    MEAN_REVERSION = "mean_reversion"
    BREAKOUT = "breakout"
    MOMENTUM = "momentum"
    ARBITRAGE = "arbitrage"
    MARKET_MAKING = "market_making"
    CARRY = "carry"
    VOLATILITY = "volatility"


class StrategyStatus(str, Enum):
    """Strategy status in the catalog."""
    ACTIVE = "active"
    BETA = "beta"
    DEPRECATED = "deprecated"
    EXPERIMENTAL = "experimental"


class StrategyCatalogEntry(BaseModel):
    """Entry in the strategy catalog."""
    
    id: str = Field(..., description="Strategy identifier (e.g., 's1_v1')")
    display_name: str = Field(..., description="Display name for UI")
    family: StrategyFamily = Field(..., description="Strategy family")
    status: StrategyStatus = Field(..., description="Strategy status")
    
    config_file: str = Field(
        ..., 
        description="Path to strategy configuration file (relative to configs/strategies/)"
    )
    
    # Optional fields
    description: Optional[str] = Field(None, description="Human-readable description")
    version: Optional[str] = Field(None, description="Strategy version")
    author: Optional[str] = Field(None, description="Strategy author")
    created_date: Optional[str] = Field(None, description="Creation date (YYYY-MM-DD)")
    
    supported_instruments: List[str] = Field(
        default_factory=list,
        description="List of instrument IDs this strategy supports"
    )
    supported_timeframes: List[int] = Field(
        default_factory=list,
        description="List of timeframes this strategy supports"
    )
    
    class Config:
        frozen = True
    
    @field_validator('config_file')
    @classmethod
    def validate_config_file_extension(cls, v: str) -> str:
        """Validate config file has .yaml extension."""
        if not v.endswith('.yaml'):
            raise ValueError(f"Strategy config file must be YAML: {v}")
        return v


class StrategyCatalogRegistry(BaseModel):
    """Strategy catalog registry configuration."""
    
    version: str = Field(..., description="Registry schema version")
    strategies: List[StrategyCatalogEntry] = Field(
        ..., 
        description="List of available strategies"
    )
    
    @field_validator('strategies')
    @classmethod
    def validate_strategies(cls, v: List[StrategyCatalogEntry]) -> List[StrategyCatalogEntry]:
        """Validate strategy list."""
        if not v:
            raise ValueError("strategies cannot be empty")
        
        # Check for duplicate IDs
        ids = [s.id for s in v]
        if len(ids) != len(set(ids)):
            duplicates = [id for id in ids if ids.count(id) > 1]
            raise ValueError(f"Duplicate strategy IDs: {duplicates}")
        
        return v
    
    def get_strategy_by_id(self, strategy_id: str) -> Optional[StrategyCatalogEntry]:
        """Get strategy by ID."""
        for strategy in self.strategies:
            if strategy.id == strategy_id:
                return strategy
        return None
    
    def get_active_strategies(self) -> List[StrategyCatalogEntry]:
        """Get all active strategies."""
        return [s for s in self.strategies if s.status == StrategyStatus.ACTIVE]
    
    def get_strategies_by_family(self, family: StrategyFamily) -> List[StrategyCatalogEntry]:
        """Get all strategies in a specific family."""
        return [s for s in self.strategies if s.family == family]
    
    def get_strategies_by_instrument(self, instrument_id: str) -> List[StrategyCatalogEntry]:
        """Get all strategies that support a specific instrument."""
        return [
            s for s in self.strategies 
            if not s.supported_instruments or instrument_id in s.supported_instruments
        ]
    
    def get_strategy_ids(self) -> List[str]:
        """Get list of all strategy IDs."""
        return [s.id for s in self.strategies]
    
    def get_strategy_choices(self) -> List[tuple[str, str]]:
        """Get (id, display_name) pairs for UI dropdowns."""
        return [(s.id, s.display_name) for s in self.strategies]
    
    def get_strategy_config_path(self, strategy_id: str) -> Optional[Path]:
        """
        Get full path to strategy configuration file.
        
        Args:
            strategy_id: Strategy ID
            
        Returns:
            Path to strategy config file or None if strategy not found
        """
        strategy = self.get_strategy_by_id(strategy_id)
        if strategy is None:
            return None
        
        from .. import get_config_root
        config_root = get_config_root()
        return config_root / "strategies" / strategy.config_file


@lru_cache(maxsize=1)
def load_strategy_catalog(path: Optional[Path] = None) -> StrategyCatalogRegistry:
    """
    Load strategy catalog registry from YAML file.
    
    Args:
        path: Optional path to strategy catalog YAML file.
              Defaults to configs/registry/strategy_catalog.yaml
    
    Returns:
        StrategyCatalogRegistry instance
        
    Raises:
        ConfigError: If loading or validation fails
    """
    if path is None:
        path = get_registry_path("strategy_catalog.yaml")
    
    data = load_yaml(path)
    try:
        return StrategyCatalogRegistry(**data)
    except Exception as e:
        from .. import ConfigError
        raise ConfigError(f"Failed to validate strategy catalog at {path}: {e}")