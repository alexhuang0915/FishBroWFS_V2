"""Strategy registry - single source of truth for strategies.

Phase 7: Centralized strategy registration and lookup.
Phase 12: Enhanced for GUI introspection with ParamSchema.
"""

from __future__ import annotations

from typing import Dict, List

from pydantic import BaseModel, ConfigDict

from FishBroWFS_V2.strategy.param_schema import ParamSpec
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


# Phase 12: Enhanced registry for GUI introspection
class StrategySpecForGUI(BaseModel):
    """Strategy specification for GUI consumption.
    
    Contains metadata and parameter schema for automatic UI generation.
    GUI must NOT hardcode any strategy parameters.
    """
    
    model_config = ConfigDict(frozen=True)
    
    strategy_id: str
    params: list[ParamSpec]


class StrategyRegistryResponse(BaseModel):
    """Response model for /meta/strategies endpoint."""
    
    model_config = ConfigDict(frozen=True)
    
    strategies: list[StrategySpecForGUI]


def convert_to_gui_spec(spec: StrategySpec) -> StrategySpecForGUI:
    """Convert internal StrategySpec to GUI-friendly format."""
    schema = spec.param_schema if isinstance(spec.param_schema, dict) else {}
    defaults = spec.defaults or {}
    
    # (1) 支援 object/properties 型
    if "properties" in schema and isinstance(schema.get("properties"), dict):
        props = schema.get("properties") or {}
    else:
        # (2) 支援扁平 dict 型（把每個 key 當 param）
        props = schema
    
    params: list[ParamSpec] = []
    for name, info in props.items():
        if not isinstance(info, dict):
            continue
        
        raw_type = info.get("type", "float")
        enum_vals = info.get("enum")
        
        if enum_vals is not None:
            ptype = "enum"
            choices = list(enum_vals)
        elif raw_type in ("int", "integer"):
            ptype = "int"
            choices = None
        elif raw_type in ("bool", "boolean"):
            ptype = "bool"
            choices = None
        else:
            ptype = "float"
            choices = None
        
        default = defaults.get(name, info.get("default"))
        help_text = (
            info.get("description")
            or info.get("title")
            or f"{name} parameter"
        )
        
        params.append(
            ParamSpec(
                name=name,
                type=ptype,
                min=info.get("minimum"),
                max=info.get("maximum"),
                step=info.get("step") or info.get("multipleOf"),
                choices=choices,
                default=default,
                help=help_text,
            )
        )
    
    params.sort(key=lambda p: p.name)
    return StrategySpecForGUI(strategy_id=spec.strategy_id, params=params)


def get_strategy_registry() -> StrategyRegistryResponse:
    """Get strategy registry for GUI consumption.
    
    Returns:
        StrategyRegistryResponse with all registered strategies
        converted to GUI-friendly format.
    """
    strategies = []
    for spec in list_strategies():
        gui_spec = convert_to_gui_spec(spec)
        strategies.append(gui_spec)
    
    return StrategyRegistryResponse(strategies=strategies)
