
"""Strategy runner - adapter between strategy and engine.

Phase 7: Validates params, calls strategy function, returns intents.
"""

from __future__ import annotations

import logging
from typing import Dict, Any, List

from FishBroWFS_V2.engine.types import OrderIntent
from FishBroWFS_V2.strategy.registry import get
from FishBroWFS_V2.strategy.spec import StrategySpec

logger = logging.getLogger(__name__)


def run_strategy(
    strategy_id: str,
    features: Dict[str, Any],
    params: Dict[str, float],
    context: Dict[str, Any],
) -> List[OrderIntent]:
    """Run a strategy and return order intents.
    
    This function:
    1. Validates params (missing values use defaults, extra keys allowed but logged)
    2. Calls strategy function
    3. Returns intents (does NOT fill, does NOT compute indicators)
    
    Args:
        strategy_id: Strategy identifier
        features: Features/indicators dict (e.g., {"sma_fast": array, "sma_slow": array})
        params: Strategy parameters dict (e.g., {"fast_period": 10, "slow_period": 20})
        context: Execution context (e.g., {"bar_index": 100, "order_qty": 1})
        
    Returns:
        List of OrderIntent
        
    Raises:
        KeyError: If strategy not found
        ValueError: If strategy output is invalid
    """
    # Get strategy spec
    spec: StrategySpec = get(strategy_id)
    
    # Merge context and features for strategy input
    strategy_input = {**context, "features": features}
    
    # Validate and merge params with defaults
    validated_params = _validate_params(params, spec)
    
    # Call strategy function
    result = spec.fn(strategy_input, validated_params)
    
    # Validate output
    if not isinstance(result, dict):
        raise ValueError(f"Strategy '{strategy_id}' must return dict, got {type(result)}")
    
    if "intents" not in result:
        raise ValueError(f"Strategy '{strategy_id}' output must contain 'intents' key")
    
    intents = result["intents"]
    if not isinstance(intents, list):
        raise ValueError(f"Strategy '{strategy_id}' intents must be list, got {type(intents)}")
    
    # Validate each intent
    for i, intent in enumerate(intents):
        if not isinstance(intent, OrderIntent):
            raise ValueError(
                f"Strategy '{strategy_id}' intent[{i}] must be OrderIntent, got {type(intent)}"
            )
    
    return intents


def _validate_params(params: Dict[str, float], spec: StrategySpec) -> Dict[str, float]:
    """Validate and merge params with defaults.
    
    Rules:
    - Missing params use defaults
    - Extra keys allowed but logged
    - Type validation (minimal)
    
    Args:
        params: User-provided parameters
        spec: Strategy specification
        
    Returns:
        Validated parameters dict (merged with defaults)
    """
    validated = dict(spec.defaults)  # Start with defaults
    
    # Override with user params
    for key, value in params.items():
        if key not in spec.defaults:
            # Extra key - log but allow
            logger.warning(
                f"Strategy '{spec.strategy_id}': extra parameter '{key}' not in schema, "
                f"will be ignored"
            )
            continue
        
        # Type validation (minimal - just check it's numeric)
        if not isinstance(value, (int, float)):
            raise ValueError(
                f"Strategy '{spec.strategy_id}': parameter '{key}' must be numeric, "
                f"got {type(value)}"
            )
        
        validated[key] = float(value)
    
    return validated


