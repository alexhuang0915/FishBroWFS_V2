
"""Strategy specification and function type definitions.

Phase 7: Strategy system core data structures.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, Any, Mapping, List

from FishBroWFS_V2.engine.types import OrderIntent


# Strategy function signature:
# input: (context/features: dict, params: dict)
# output: {"intents": List[OrderIntent], "debug": dict}
StrategyFn = Callable[
    [Mapping[str, Any], Mapping[str, float]],  # (context/features, params)
    Mapping[str, Any]                          # {"intents": [...], "debug": {...}}
]


@dataclass(frozen=True)
class StrategySpec:
    """Strategy specification.
    
    Contains all metadata and function for a strategy.
    
    Attributes:
        strategy_id: Unique strategy identifier (e.g., "sma_cross")
        version: Strategy version (e.g., "v1")
        param_schema: Parameter schema definition (jsonschema-like dict)
        defaults: Default parameter values (dict, key-value pairs)
        fn: Strategy function (StrategyFn)
    """
    strategy_id: str
    version: str
    param_schema: Dict[str, Any]  # jsonschema-like dict, minimal
    defaults: Dict[str, float]
    fn: StrategyFn
    
    def __post_init__(self) -> None:
        """Validate strategy spec."""
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


