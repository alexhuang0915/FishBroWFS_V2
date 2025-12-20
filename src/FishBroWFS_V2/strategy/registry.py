"""Strategy registry - single source of truth for strategies.

Phase 7: Centralized strategy registration and lookup.
"""

from __future__ import annotations

from typing import Dict, List

from FishBroWFS_V2.strategy.spec import StrategySpec


# Global registry (module-level, mutable)
_registry: Dict[str, StrategySpec] = {}


def register(spec: StrategySpec) -> None:
    """Register a strategy.
    
    Args:
        spec: Strategy specification
        
    Raises:
        ValueError: If strategy_id already registered
    """
    if spec.strategy_id in _registry:
        raise ValueError(
            f"Strategy '{spec.strategy_id}' already registered. "
            f"Use different strategy_id or unregister first."
        )
    _registry[spec.strategy_id] = spec


def get(strategy_id: str) -> StrategySpec:
    """Get strategy by ID.
    
    Args:
        strategy_id: Strategy identifier
        
    Returns:
        StrategySpec
        
    Raises:
        KeyError: If strategy not found
    """
    if strategy_id not in _registry:
        raise KeyError(f"Strategy '{strategy_id}' not found in registry")
    return _registry[strategy_id]


def list_strategies() -> List[StrategySpec]:
    """List all registered strategies.
    
    Returns:
        List of StrategySpec, sorted by strategy_id
    """
    return sorted(_registry.values(), key=lambda s: s.strategy_id)


def unregister(strategy_id: str) -> None:
    """Unregister a strategy (mainly for testing).
    
    Args:
        strategy_id: Strategy identifier
        
    Raises:
        KeyError: If strategy not found
    """
    if strategy_id not in _registry:
        raise KeyError(f"Strategy '{strategy_id}' not found in registry")
    del _registry[strategy_id]


def clear() -> None:
    """Clear all registered strategies (mainly for testing)."""
    _registry.clear()


def load_builtin_strategies() -> None:
    """Load built-in strategies (explicit, no import side effects).
    
    This function must be called explicitly to register built-in strategies.
    """
    from FishBroWFS_V2.strategy.builtin import (
        sma_cross_v1,
        breakout_channel_v1,
        mean_revert_zscore_v1,
    )
    
    # Register built-in strategies
    register(sma_cross_v1.SPEC)
    register(breakout_channel_v1.SPEC)
    register(mean_revert_zscore_v1.SPEC)
