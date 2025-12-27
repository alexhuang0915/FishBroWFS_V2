"""Strategy specification and function type definitions.

Phase 7: Strategy system core data structures.
Phase 13: Enhanced with content-addressed identity (Attack #5).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Any, Mapping, List, Optional

from engine.types import OrderIntent
from core.ast_identity import (
    StrategyIdentity,
    compute_strategy_id_from_function,
)


# Strategy function signature:
# input: (context/features: dict, params: dict)
# output: {"intents": List[OrderIntent], "debug": dict}
StrategyFn = Callable[
    [Mapping[str, Any], Mapping[str, float]],  # (context/features, params)
    Mapping[str, Any]                          # {"intents": [...], "debug": {...}}
]


@dataclass(frozen=True)
class StrategySpec:
    """Strategy specification with content-addressed identity.
    
    Contains all metadata and function for a strategy.
    
    Attributes:
        strategy_id: Unique strategy identifier (e.g., "sma_cross")
        version: Strategy version (e.g., "v1")
        param_schema: Parameter schema definition (jsonschema-like dict)
        defaults: Default parameter values (dict, key-value pairs)
        fn: Strategy function (StrategyFn)
        content_id: Content-addressed strategy ID (64-char hex, immutable)
        identity: Immutable strategy identity object (optional)
    """
    strategy_id: str
    version: str
    param_schema: Dict[str, Any]  # jsonschema-like dict, minimal
    defaults: Dict[str, float]
    fn: StrategyFn
    content_id: Optional[str] = None
    identity: Optional[StrategyIdentity] = None
    
    def __post_init__(self) -> None:
        """Validate strategy spec and compute content-addressed identity."""
        if not self.strategy_id:
            raise ValueError("strategy_id cannot be empty")
        if not self.version:
            raise ValueError("version cannot be empty")
        if not isinstance(self.param_schema, dict):
            raise ValueError("param_schema must be a dict")
        if not isinstance(self.defaults, dict):
            raise ValueError("defaults must be a dict")
        if not callable(self.fn):
            raise ValueError("fn must be callable")
        
        # Compute content-addressed identity if not provided
        if self.identity is None:
            try:
                # Compute from function source code
                content_id = compute_strategy_id_from_function(self.fn)
                identity = StrategyIdentity(content_id, source_hash=content_id)
                
                # Use object.__setattr__ because dataclass is frozen
                object.__setattr__(self, 'identity', identity)
                object.__setattr__(self, 'content_id', content_id)
            except (ValueError, OSError) as e:
                # If we can't compute identity, use a placeholder
                # This maintains backward compatibility
                object.__setattr__(self, 'content_id', self.content_id or "")
        
        # Validate content_id format if present
        if self.content_id and self.content_id != "":
            if len(self.content_id) != 64:
                raise ValueError(
                    f"content_id must be 64-character hex string, got {self.content_id}"
                )
            try:
                int(self.content_id, 16)
            except ValueError:
                raise ValueError(
                    f"content_id must be valid hex string, got {self.content_id}"
                )
    
    @property
    def immutable_id(self) -> str:
        """Get the immutable content-addressed ID.
        
        Returns the content_id if available, otherwise falls back to
        a deterministic hash of strategy_id and version.
        """
        if self.content_id and self.content_id != "":
            return self.content_id
        
        # Fallback for backward compatibility
        import hashlib
        combined = f"{self.strategy_id}::{self.version}"
        return hashlib.sha256(combined.encode('utf-8')).hexdigest()
    
    def get_identity(self) -> StrategyIdentity:
        """Get the strategy identity object.
        
        Returns the identity if available, otherwise creates a new one
        from the immutable_id.
        """
        if self.identity is not None:
            return self.identity
        
        # Create identity from immutable_id
        return StrategyIdentity(self.immutable_id)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "strategy_id": self.strategy_id,
            "version": self.version,
            "param_schema": self.param_schema,
            "defaults": self.defaults,
            "content_id": self.content_id,
            # Note: fn is not serialized
        }
    
    @classmethod
    def from_dict(
        cls,
        data: Dict[str, Any],
        fn: Optional[StrategyFn] = None
    ) -> StrategySpec:
        """Create StrategySpec from dictionary.
        
        Args:
            data: Dictionary with strategy specification
            fn: Strategy function (required if not in data)
            
        Returns:
            StrategySpec instance
        """
        # Extract function if provided in data (unlikely)
        if fn is None and "fn" in data:
            fn = data["fn"]
        
        if fn is None:
            raise ValueError("Strategy function (fn) is required")
        
        return cls(
            strategy_id=data["strategy_id"],
            version=data["version"],
            param_schema=data["param_schema"],
            defaults=data["defaults"],
            fn=fn,
            content_id=data.get("content_id"),
            identity=None  # Will be computed in __post_init__
        )
