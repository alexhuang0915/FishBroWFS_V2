
"""SMA Cross Strategy v1.

Phase 7: Basic moving average crossover strategy.
Entry: When fast SMA crosses above slow SMA (golden cross).
"""

from __future__ import annotations

from typing import Dict, Any, Mapping

import numpy as np

from FishBroWFS_V2.engine.types import OrderIntent, OrderRole, OrderKind, Side
from FishBroWFS_V2.engine.order_id import generate_order_id
from FishBroWFS_V2.engine.constants import ROLE_ENTRY, KIND_STOP, SIDE_BUY
from FishBroWFS_V2.strategy.spec import StrategySpec, StrategyFn


def sma_cross_strategy(context: Mapping[str, Any], params: Mapping[str, float]) -> Dict[str, Any]:
    """SMA Cross Strategy implementation.
    
    Entry signal: Fast SMA crosses above slow SMA (golden cross).
    
    Args:
        context: Execution context with features and bar_index
        params: Strategy parameters (fast_period, slow_period)
        
    Returns:
        Dict with "intents" (List[OrderIntent]) and "debug" (dict)
    """
    features = context.get("features", {})
    bar_index = context.get("bar_index", 0)
    
    # Get features
    sma_fast = features.get("sma_fast")
    sma_slow = features.get("sma_slow")
    
    if sma_fast is None or sma_slow is None:
        return {"intents": [], "debug": {"error": "Missing SMA features"}}
    
    # Convert to numpy arrays if needed
    if not isinstance(sma_fast, np.ndarray):
        sma_fast = np.array(sma_fast)
    if not isinstance(sma_slow, np.ndarray):
        sma_slow = np.array(sma_slow)
    
    # Check bounds
    if bar_index >= len(sma_fast) or bar_index >= len(sma_slow):
        return {"intents": [], "debug": {"error": "bar_index out of bounds"}}
    
    # Need at least 2 bars to detect crossover
    if bar_index < 1:
        return {"intents": [], "debug": {}}
    
    # Check for golden cross (fast crosses above slow)
    prev_fast = sma_fast[bar_index - 1]
    prev_slow = sma_slow[bar_index - 1]
    curr_fast = sma_fast[bar_index]
    curr_slow = sma_slow[bar_index]
    
    # Golden cross: prev_fast <= prev_slow AND curr_fast > curr_slow
    is_golden_cross = (
        prev_fast <= prev_slow and
        curr_fast > curr_slow and
        not np.isnan(prev_fast) and
        not np.isnan(prev_slow) and
        not np.isnan(curr_fast) and
        not np.isnan(curr_slow)
    )
    
    intents = []
    if is_golden_cross:
        # Entry: Buy Stop at current fast SMA
        order_id = generate_order_id(
            created_bar=bar_index,
            param_idx=0,  # Single param set for this strategy
            role=ROLE_ENTRY,
            kind=KIND_STOP,
            side=SIDE_BUY,
        )
        
        intent = OrderIntent(
            order_id=order_id,
            created_bar=bar_index,
            role=OrderRole.ENTRY,
            kind=OrderKind.STOP,
            side=Side.BUY,
            price=float(curr_fast),
            qty=context.get("order_qty", 1),
        )
        intents.append(intent)
    
    return {
        "intents": intents,
        "debug": {
            "sma_fast": float(curr_fast) if not np.isnan(curr_fast) else None,
            "sma_slow": float(curr_slow) if not np.isnan(curr_slow) else None,
            "is_golden_cross": is_golden_cross,
        },
    }


# Strategy specification
SPEC = StrategySpec(
    strategy_id="sma_cross",
    version="v1",
    param_schema={
        "type": "object",
        "properties": {
            "fast_period": {"type": "number", "minimum": 1},
            "slow_period": {"type": "number", "minimum": 1},
        },
        "required": ["fast_period", "slow_period"],
    },
    defaults={
        "fast_period": 10.0,
        "slow_period": 20.0,
    },
    fn=sma_cross_strategy,
)


