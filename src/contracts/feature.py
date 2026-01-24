"""
Feature Contracts (Layer 1).

Defines how features (viewpoints) are declared and registered.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class FeatureCategory(str, Enum):
    """Category of the feature."""
    TECHNICAL = "technical"   # RSI, MACD, etc.
    STATISTICAL = "statistical" # Z-Score, Volatility
    FUNDAMENTAL = "fundamental" # (Future use)
    CUSTOM = "custom"


class FeatureDataType(str, Enum):
    """Data type of the feature output."""
    FLOAT = "float"
    BOOL = "bool"
    INT = "int"
    CATEGORY = "category"


class OutputColumn(BaseModel):
    """Definition of a single column produced by a feature."""
    name_suffix: str = Field(..., description="Suffix appended to feature name (e.g., '_slope')")
    dtype: FeatureDataType
    description: Optional[str] = None


class FeatureDefinition(BaseModel):
    """
    Declarative definition of a Feature.
    
    A feature is a pure function: Data -> DataFrame[Columns].
    """
    feature_id: str = Field(..., description="Unique ID (e.g., 'rsi_14')")
    family_name: str = Field(..., description="Family name (e.g., 'RSI')")
    category: FeatureCategory
    
    # Parameters that define this specific instance
    params: Dict[str, Any] = Field(default_factory=dict, description="Deterministic parameters")
    
    # Implementation details
    handler_path: str = Field(..., description="Python path to handler function/class")
    
    # Output Schema
    outputs: List[OutputColumn] = Field(..., description="List of output columns")
    
    # Versioning
    version: str = "1.0.0"
    
    def compute_fingerprint(self) -> str:
        """Compute robust hash of definition (ID + params + version)."""
        import hashlib
        import json
        
        # Canonical JSON of critical fields
        payload = {
            "id": self.feature_id,
            "params": self.params,
            "handler": self.handler_path,
            "version": self.version
        }
        canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(canonical.encode()).hexdigest()
