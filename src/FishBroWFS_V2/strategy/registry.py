"""Strategy registry - single source of truth for strategies.

Phase 7: Centralized strategy registration and lookup.
Phase 12: Enhanced for GUI introspection with ParamSchema.
Phase 13: Content-addressed identity (Attack #5).
"""

from __future__ import annotations

from typing import Dict, List, Optional
import hashlib

from pydantic import BaseModel, ConfigDict

from FishBroWFS_V2.strategy.param_schema import ParamSpec
from FishBroWFS_V2.strategy.spec import StrategySpec
from FishBroWFS_V2.strategy.identity_models import (
    StrategyIdentityModel,
    StrategyRegistryEntry,
    StrategyManifest,
)


# Global registries (module-level, mutable)
_registry_by_id: Dict[str, StrategySpec] = {}  # By human-readable ID
_registry_by_content_id: Dict[str, StrategySpec] = {}  # By content-addressed ID


def register(spec: StrategySpec) -> None:
    """Register a strategy with content-addressed identity.
    
    Args:
        spec: Strategy specification
        
    Raises:
        ValueError: If strategy_id already registered with different content
        ValueError: If content_id already registered with different strategy_id
    """
    strategy_id = spec.strategy_id
    content_id = spec.immutable_id
    
    # Check for duplicate human-readable ID
    if strategy_id in _registry_by_id:
        existing = _registry_by_id[strategy_id]
        if existing.immutable_id != content_id:
            raise ValueError(
                f"Strategy '{strategy_id}' already registered with different content. "
                f"Existing content_id: {existing.immutable_id[:16]}..., "
                f"New content_id: {content_id[:16]}... "
                f"Content-addressed identity mismatch indicates different strategy logic."
            )
        # Same content, already registered
        return
    
    # Check for duplicate content-addressed ID (different human-readable ID)
    if content_id in _registry_by_content_id:
        existing = _registry_by_content_id[content_id]
        if existing.strategy_id != strategy_id:
            raise ValueError(
                f"Strategy content already registered with different ID. "
                f"Existing: '{existing.strategy_id}' (content_id: {content_id[:16]}...), "
                f"New: '{strategy_id}'. "
                f"This indicates duplicate strategy logic with different names."
            )
        # Same content, already registered with same human-readable ID
        return
    
    # Register in both indices
    _registry_by_id[strategy_id] = spec
    _registry_by_content_id[content_id] = spec


def get(strategy_id: str) -> StrategySpec:
    """Get strategy by human-readable ID.
    
    Args:
        strategy_id: Strategy identifier
        
    Returns:
        StrategySpec
        
    Raises:
        KeyError: If strategy not found
    """
    if strategy_id not in _registry_by_id:
        raise KeyError(f"Strategy '{strategy_id}' not found in registry")
    return _registry_by_id[strategy_id]


def get_by_content_id(content_id: str) -> StrategySpec:
    """Get strategy by content-addressed ID.
    
    Args:
        content_id: Content-addressed strategy ID (64-char hex)
        
    Returns:
        StrategySpec
        
    Raises:
        KeyError: If strategy not found
        ValueError: If content_id format is invalid
    """
    if len(content_id) != 64:
        raise ValueError(f"content_id must be 64-character hex string, got {content_id}")
    
    if content_id not in _registry_by_content_id:
        raise KeyError(f"Strategy with content_id '{content_id[:16]}...' not found in registry")
    return _registry_by_content_id[content_id]


def list_strategies() -> List[StrategySpec]:
    """List all registered strategies.
    
    Returns:
        List of StrategySpec, sorted by strategy_id
    """
    return sorted(_registry_by_id.values(), key=lambda s: s.strategy_id)


def list_strategies_by_content_id() -> List[StrategySpec]:
    """List all registered strategies sorted by content_id.
    
    Returns:
        List of StrategySpec, sorted by content_id
    """
    return sorted(_registry_by_content_id.values(), key=lambda s: s.immutable_id)


def unregister(strategy_id: str) -> None:
    """Unregister a strategy (mainly for testing).
    
    Args:
        strategy_id: Strategy identifier
        
    Raises:
        KeyError: If strategy not found
    """
    if strategy_id not in _registry_by_id:
        raise KeyError(f"Strategy '{strategy_id}' not found in registry")
    
    spec = _registry_by_id[strategy_id]
    content_id = spec.immutable_id
    
    # Remove from both indices
    del _registry_by_id[strategy_id]
    if content_id in _registry_by_content_id:
        del _registry_by_content_id[content_id]


def clear() -> None:
    """Clear all registered strategies (mainly for testing)."""
    _registry_by_id.clear()
    _registry_by_content_id.clear()


def load_builtin_strategies() -> None:
    """Load built-in strategies (explicit, no import side effects).
    
    This function must be called explicitly to register built-in strategies.
    """
    from FishBroWFS_V2.strategy.builtin import (
        sma_cross_v1,
        breakout_channel_v1,
        mean_revert_zscore_v1,
        rsi_reversal_v1,
        bollinger_breakout_v1,
        atr_trailing_stop_v1,
    )
    
    # Register built-in strategies
    register(sma_cross_v1.SPEC)
    register(breakout_channel_v1.SPEC)
    register(mean_revert_zscore_v1.SPEC)
    register(rsi_reversal_v1.SPEC)
    register(bollinger_breakout_v1.SPEC)
    register(atr_trailing_stop_v1.SPEC)


def generate_manifest() -> StrategyManifest:
    """Generate strategy manifest with content-addressed identity.
    
    Returns:
        StrategyManifest containing all registered strategies
    """
    entries = []
    
    for spec in list_strategies():
        # Create identity model
        identity = StrategyIdentityModel.from_core_identity(spec.get_identity())
        
        # Create metadata
        from FishBroWFS_V2.strategy.identity_models import StrategyMetadata
        metadata = StrategyMetadata(
            name=spec.strategy_id,
            version=spec.version,
            description=f"{spec.strategy_id} strategy version {spec.version}",
            author="FishBroWFS_V2",
            tags=["builtin"] if "builtin" in spec.strategy_id else []
        )
        
        # Create param schema
        from FishBroWFS_V2.strategy.identity_models import StrategyParamSchema
        param_schema = StrategyParamSchema(
            param_schema=spec.param_schema,
            defaults=spec.defaults
        )
        
        # Create registry entry
        entry = StrategyRegistryEntry(
            identity=identity,
            metadata=metadata,
            param_schema=param_schema,
            fn=spec.fn
        )
        
        entries.append(entry)
    
    return StrategyManifest(strategies=entries)


def save_manifest(filepath: str) -> None:
    """Save strategy manifest to file.
    
    Args:
        filepath: Path to save StrategyManifest.json
    """
    manifest = generate_manifest()
    manifest.save(filepath)


def load_manifest(filepath: str) -> StrategyManifest:
    """Load strategy manifest from file.
    
    Args:
        filepath: Path to StrategyManifest.json
        
    Returns:
        StrategyManifest
    """
    return StrategyManifest.load(filepath)


# Phase 12: Enhanced registry for GUI introspection (backward compatible)
class StrategySpecForGUI(BaseModel):
    """Strategy specification for GUI consumption.
    
    Contains metadata and parameter schema for automatic UI generation.
    GUI must NOT hardcode any strategy parameters.
    """
    
    model_config = ConfigDict(frozen=True)
    
    strategy_id: str
    params: list[ParamSpec]
    content_id: Optional[str] = None  # Added for Phase 13


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
    
    # Include content_id in GUI spec
    return StrategySpecForGUI(
        strategy_id=spec.strategy_id,
        params=params,
        content_id=spec.immutable_id
    )


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
