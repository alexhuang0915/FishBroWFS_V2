
"""Breakout Channel Strategy v1.

Phase 7: Channel breakout strategy using high/low.
Entry: When price breaks above channel high (breakout).
"""

from __future__ import annotations

from typing import Dict, Any, Mapping

import numpy as np

from FishBroWFS_V2.engine.types import OrderIntent, OrderRole, OrderKind, Side
from FishBroWFS_V2.engine.order_id import generate_order_id
from FishBroWFS_V2.engine.constants import ROLE_ENTRY, KIND_STOP, SIDE_BUY
from FishBroWFS_V2.strategy.spec import StrategySpec, StrategyFn


def breakout_channel_strategy(
    context: Mapping[str, Any],
    params: Mapping[str, float],
) -> Dict[str, Any]:
    """Breakout Channel Strategy implementation.
    
    Entry signal: Price breaks above channel high.
    
    Args:
        context: Execution context with features and bar_index
        params: Strategy parameters (channel_period)
        
    Returns:
        Dict with "intents" (List[OrderIntent]) and "debug" (dict)
    """
    features = context.get("features", {})
    bar_index = context.get("bar_index", 0)
    
    # Get features
    high = features.get("high")
    low = features.get("low")
    close = features.get("close")
    channel_high = features.get("channel_high")
    channel_low = features.get("channel_low")
    
    if high is None or close is None or channel_high is None:
        return {"intents": [], "debug": {"error": "Missing required features"}}
    
    # Convert to numpy arrays if needed
    if not isinstance(high, np.ndarray):
        high = np.array(high)
    if not isinstance(close, np.ndarray):
        close = np.array(close)
    if not isinstance(channel_high, np.ndarray):
        channel_high = np.array(channel_high)
    
    # Check bounds
    if bar_index >= len(high) or bar_index >= len(close) or bar_index >= len(channel_high):
        return {"intents": [], "debug": {"error": "bar_index out of bounds"}}
    
    # Need at least 1 bar
    if bar_index < 0:
        return {"intents": [], "debug": {}}
    
    curr_high = high[bar_index]
    curr_close = close[bar_index]
    curr_channel_high = channel_high[bar_index]
    
    # Check for breakout: current high breaks above channel high
    is_breakout = (
        curr_high > curr_channel_high and
        not np.isnan(curr_high) and
        not np.isnan(curr_channel_high)
    )
    
    intents = []
    if is_breakout:
        # Entry: Buy Stop at channel high (breakout level)
        order_id = generate_order_id(
            created_bar=bar_index,
            param_idx=0,
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
            price=float(curr_channel_high),
            qty=context.get("order_qty", 1),
        )
        intents.append(intent)
    
    return {
        "intents": intents,
        "debug": {
            "high": float(curr_high) if not np.isnan(curr_high) else None,
            "channel_high": float(curr_channel_high) if not np.isnan(curr_channel_high) else None,
            "is_breakout": is_breakout,
        },
    }


# Strategy specification
SPEC = StrategySpec(
    strategy_id="breakout_channel",
    version="v1",
    param_schema={
        "type": "object",
        "properties": {
            "channel_period": {"type": "number", "minimum": 1},
        },
        "required": ["channel_period"],
    },
    defaults={
        "channel_period": 20.0,
    },
    fn=breakout_channel_strategy,
)


