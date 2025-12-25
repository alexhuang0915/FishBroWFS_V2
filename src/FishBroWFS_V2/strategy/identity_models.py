"""Pydantic models for strategy identity and registry.

Implements immutable, content-addressed strategy identity system that replaces
filesystem iteration order, Python import order, list index/enumerate/incremental
counters, filename or class name as primary key.

Models:
- StrategyIdentity: Immutable content-addressed identity
- StrategyManifest: Registry manifest with deterministic ordering
- StrategyRegistryEntry: Complete strategy entry with metadata
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, validator

from FishBroWFS_V2.core.ast_identity import (
    StrategyIdentity,
    compute_strategy_id_from_source,
    compute_strategy_id_from_function,
    compute_strategy_id_from_file,
)


class StrategyIdentityModel(BaseModel):
    """Immutable strategy identity based on canonical AST hash.
    
    This model represents the content-addressed identity of a strategy,
    derived from its canonical AST representation (ast-c14n-v1).
    
    Properties:
    - Deterministic: Same AST → same identity regardless of location
    - Immutable: Identity cannot change without changing strategy logic
    - Content-addressed: Identity derived from strategy content, not metadata
    """
    
    model_config = ConfigDict(frozen=True)
    
    strategy_id: str = Field(
        ...,
        description="Content-addressed strategy ID (64-character hex SHA-256 hash)",
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$"
    )
    
    source_hash: Optional[str] = Field(
        None,
        description="Optional source hash for verification (64-character hex)",
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$"
    )
    
    @validator('strategy_id', 'source_hash')
    def validate_hex_string(cls, v: Optional[str]) -> Optional[str]:
        """Validate that string is a valid hex representation."""
        if v is None:
            return v
        try:
            int(v, 16)
        except ValueError:
            raise ValueError(f"Invalid hex string: {v}")
        return v
    
    @classmethod
    def from_source(cls, source_code: str) -> StrategyIdentityModel:
        """Create StrategyIdentityModel from source code."""
        strategy_id = compute_strategy_id_from_source(source_code)
        return cls(strategy_id=strategy_id, source_hash=strategy_id)
    
    @classmethod
    def from_function(cls, func) -> StrategyIdentityModel:
        """Create StrategyIdentityModel from function."""
        strategy_id = compute_strategy_id_from_function(func)
        return cls(strategy_id=strategy_id, source_hash=strategy_id)
    
    @classmethod
    def from_file(cls, filepath: Path | str) -> StrategyIdentityModel:
        """Create StrategyIdentityModel from file."""
        strategy_id = compute_strategy_id_from_file(filepath)
        return cls(strategy_id=strategy_id, source_hash=strategy_id)
    
    @classmethod
    def from_core_identity(cls, identity: StrategyIdentity) -> StrategyIdentityModel:
        """Create StrategyIdentityModel from core StrategyIdentity."""
        return cls(
            strategy_id=identity.strategy_id,
            source_hash=identity.source_hash
        )
    
    def to_core_identity(self) -> StrategyIdentity:
        """Convert to core StrategyIdentity object."""
        return StrategyIdentity(
            strategy_id=self.strategy_id,
            source_hash=self.source_hash
        )
    
    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, StrategyIdentityModel):
            return False
        return self.strategy_id == other.strategy_id
    
    def __hash__(self) -> int:
        # Use integer representation of first 16 chars for hash
        return int(self.strategy_id[:16], 16)
    
    def __str__(self) -> str:
        return self.strategy_id


class StrategyMetadata(BaseModel):
    """Strategy metadata for human consumption.
    
    Contains human-readable information about the strategy that doesn't
    affect its identity. This metadata can change without changing the
    strategy's content-addressed identity.
    """
    
    model_config = ConfigDict(frozen=True)
    
    name: str = Field(
        ...,
        description="Human-readable strategy name",
        min_length=1,
        max_length=100
    )
    
    version: str = Field(
        ...,
        description="Strategy version (e.g., 'v1', 'v2.1')",
        min_length=1,
        max_length=20
    )
    
    description: Optional[str] = Field(
        None,
        description="Strategy description for documentation",
        max_length=1000
    )
    
    author: Optional[str] = Field(
        None,
        description="Strategy author or maintainer",
        max_length=100
    )
    
    created_at: Optional[datetime] = Field(
        None,
        description="When the strategy was created"
    )
    
    tags: List[str] = Field(
        default_factory=list,
        description="Strategy tags for categorization"
    )


class StrategyParamSchema(BaseModel):
    """Strategy parameter schema for validation and UI generation.
    
    This is a simplified representation of the parameter schema that
    can be used for validation and UI generation without affecting
    the strategy's identity.
    """
    
    model_config = ConfigDict(frozen=True)
    
    param_schema: Dict[str, Any] = Field(
        ...,
        description="Parameter schema (jsonschema-like dict)"
    )
    
    defaults: Dict[str, float] = Field(
        default_factory=dict,
        description="Default parameter values"
    )
    
    @validator('param_schema')
    def validate_param_schema(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        """Validate parameter schema structure."""
        if not isinstance(v, dict):
            raise ValueError("param_schema must be a dict")
        return v
    
    @validator('defaults')
    def validate_defaults(cls, v: Dict[str, float]) -> Dict[str, float]:
        """Validate defaults structure."""
        if not isinstance(v, dict):
            raise ValueError("defaults must be a dict")
        # Ensure all values are numeric
        for key, value in v.items():
            if not isinstance(value, (int, float)):
                raise ValueError(f"Default value for '{key}' must be numeric")
        return v


class StrategyRegistryEntry(BaseModel):
    """Complete strategy registry entry.
    
    Contains all information needed to register, identify, and execute
    a strategy. The identity is immutable and content-addressed, while
    metadata and schema can be updated independently.
    """
    
    model_config = ConfigDict(frozen=True)
    
    identity: StrategyIdentityModel = Field(
        ...,
        description="Immutable content-addressed strategy identity"
    )
    
    metadata: StrategyMetadata = Field(
        ...,
        description="Human-readable strategy metadata"
    )
    
    param_schema: StrategyParamSchema = Field(
        ...,
        description="Strategy parameter schema"
    )
    
    # Function reference (not serialized)
    fn: Optional[Any] = Field(
        None,
        description="Strategy function (not serialized)",
        exclude=True
    )
    
    @property
    def strategy_id(self) -> str:
        """Get the content-addressed strategy ID."""
        return self.identity.strategy_id
    
    @property
    def name(self) -> str:
        """Get the human-readable strategy name."""
        return self.metadata.name
    
    @property
    def version(self) -> str:
        """Get the strategy version."""
        return self.metadata.version
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization (excludes fn)."""
        return self.model_dump(exclude={'fn'})
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> StrategyRegistryEntry:
        """Create from dictionary (excludes fn)."""
        return cls(**data)


class StrategyManifest(BaseModel):
    """Strategy registry manifest with deterministic ordering.
    
    Contains all registered strategies in a deterministic order,
    suitable for serialization to StrategyManifest.json.
    
    Properties:
    - Deterministic ordering: Strategies sorted by strategy_id
    - Immutable: Manifest hash can be used for verification
    - Complete: Contains all strategy information except function objects
    """
    
    model_config = ConfigDict(frozen=True)
    
    version: str = Field(
        "ast-c14n-v1",
        description="Manifest version identifier"
    )
    
    generated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When the manifest was generated"
    )
    
    strategies: List[StrategyRegistryEntry] = Field(
        ...,
        description="Registered strategies sorted by strategy_id"
    )
    
    @validator('strategies')
    def sort_strategies(cls, v: List[StrategyRegistryEntry]) -> List[StrategyRegistryEntry]:
        """Ensure strategies are sorted by strategy_id for determinism."""
        return sorted(v, key=lambda s: s.strategy_id)
    
    def get_strategy(self, strategy_id: str) -> Optional[StrategyRegistryEntry]:
        """Get strategy by ID using binary search (O(log n))."""
        # Since strategies are sorted, we can use binary search
        left, right = 0, len(self.strategies) - 1
        while left <= right:
            mid = (left + right) // 2
            mid_id = self.strategies[mid].strategy_id
            if mid_id == strategy_id:
                return self.strategies[mid]
            elif mid_id < strategy_id:
                left = mid + 1
            else:
                right = mid - 1
        return None
    
    def has_strategy(self, strategy_id: str) -> bool:
        """Check if strategy exists in manifest."""
        return self.get_strategy(strategy_id) is not None
    
    def to_json(self, indent: int = 2) -> str:
        """Serialize manifest to JSON string with deterministic ordering."""
        # Convert to dict first, then serialize with sorted keys
        data = self.model_dump()
        return json.dumps(data, indent=indent, sort_keys=True, default=str)
    
    def save(self, filepath: Path | str) -> None:
        """Save manifest to file."""
        path = Path(filepath)
        json_str = self.to_json(indent=2)
        path.write_text(json_str, encoding='utf-8')
    
    @classmethod
    def load(cls, filepath: Path | str) -> StrategyManifest:
        """Load manifest from file."""
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"Manifest file not found: {filepath}")
        
        json_str = path.read_text(encoding='utf-8')
        data = cls.model_validate_json(json_str)
        return data
    
    @classmethod
    def from_strategy_entries(
        cls,
        entries: List[StrategyRegistryEntry]
    ) -> StrategyManifest:
        """Create manifest from strategy entries."""
        return cls(strategies=entries)