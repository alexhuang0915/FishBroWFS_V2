"""
Strategy Contracts (Layer 3).

Defines the structure of a Trading Hypothesis.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class Direction(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    BOTH = "BOTH"


class StrategySpec(BaseModel):
    """
    Complete specification of a Strategy Hypothesis.
    
    Contains everything needed to instantiate and run a strategy,
    except the data itself.
    """
    strategy_id: str = Field(..., description="Unique ID for this strategy instance")
    class_path: str = Field(..., description="Python path to strategy class (e.g., 'strategies.trend.MacdCross')")
    
    # Static parameters (the hypothesis variables)
    params: Dict[str, Any] = Field(default_factory=dict, description="Strategy parameters")
    
    # Features required by this strategy
    # This explicit declaration allows the engine to pre-load/pre-compute exactly what's needed.
    required_features: List[str] = Field(default_factory=list, description="IDs of required features")
    
    # Constraints (Risk limits embedded in the hypothesis)
    max_position_size: float = 1.0
    allowed_direction: Direction = Direction.BOTH
    
    # Metadata
    author: str = "unknown"
    description: Optional[str] = None
    version: str = "1.0.0"

    def compute_hash(self) -> str:
        """Compute SHA256 hash of the full specification."""
        import hashlib
        import json
        
        payload = {
            "class": self.class_path,
            "params": self.params,
            "features": sorted(self.required_features),
            "constraints": {
                "max_pos": self.max_position_size,
                "dir": self.allowed_direction
            },
            "version": self.version
        }
        canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(canonical.encode()).hexdigest()
