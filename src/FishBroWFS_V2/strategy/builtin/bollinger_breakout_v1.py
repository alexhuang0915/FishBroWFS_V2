"""Bollinger Breakout Strategy v1.

Phase J: Volatility expansion strategy using Bollinger Band breakout.
Entry: When price breaks above upper band (bullish breakout) or below lower band (bearish breakout).
"""

from __future__ import annotations

from typing import Dict, Any, Mapping

import numpy as np

from FishBroWFS_V2.engine.types import OrderIntent, OrderRole, OrderKind, Side
from FishBroWFS_V2.engine.order_id import generate_order_id
from FishBroWFS_V2.engine.constants import ROLE_ENTRY, KIND_STOP, SIDE_BUY, SIDE_SELL
from FishBroWFS_V2.strategy.spec import StrategySpec, StrategyFn


def bollinger_breakout_strategy(
    context: Mapping[str, Any],
    params: Mapping[str, float],
) -> Dict[str, Any]:
    """Bollinger Breakout Strategy implementation.
    
    Entry signal: Price breaks above upper band (bullish) or below lower band (bearish).
    
    Args:
        context: Execution context with features and bar_index
        params: Strategy parameters (bb_period, bb_std)
        
    Returns:
        Dict with "intents" (List[OrderIntent]) and "debug" (dict)
    """
    features = context.get("features", {})
    bar_index = context.get("bar_index", 0)
    
    # Get features
    close = features.get("close")
    high = features.get("high")
    low = features.get("low")
    
    if close is None or high is None or low is None:
        return {"intents": [], "debug": {"error": "Missing price features"}}
    
    # Convert to numpy arrays if needed
    if not isinstance(close, np.ndarray):
        close = np.array(close)
    if not isinstance(high, np.ndarray):
        high = np.array(high)
    if not isinstance(low, np.ndarray):
        low = np.array(low)
    
    # Check bounds
    if bar_index >= len(close) or bar_index >= len(high) or bar_index >= len(low):
        return {"intents": [], "debug": {"error": "bar_index out of bounds"}}
    
    # Need at least 1 bar
    if bar_index < 0:
        return {"intents": [], "debug": {}}
    
    # Get parameters
    bb_period = int(params.get("bb_period", 20))
    bb_std = params.get("bb_std", 2.0)
    
    curr_close = close[bar_index]
    curr_high = high[bar_index]
    curr_low = low[bar_index]
    
    # Calculate Bollinger Bands (simplified for demo)
    # In a real implementation, this would use proper Bollinger Band features
    lookback = min(bb_period, bar_index + 1)
    if lookback > 1:
        recent_prices = close[bar_index - lookback + 1:bar_index + 1]
        sma = np.nanmean(recent_prices)
        std = np.nanstd(recent_prices)
        
        upper_band = sma + bb_std * std
        lower_band = sma - bb_std * std
    else:
        sma = curr_close
        std = 0.0
        upper_band = curr_close
        lower_band = curr_close
    
    # Check for breakout conditions
    is_bullish_breakout = (
        curr_high > upper_band and 
        not np.isnan(curr_high) and 
        not np.isnan(upper_band)
    )
    
    is_bearish_breakout = (
        curr_low < lower_band and 
        not np.isnan(curr_low) and 
        not np.isnan(lower_band)
    )
    
    intents = []
    if is_bullish_breakout:
        # Entry: Buy Stop at upper band (breakout level)
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
            price=float(upper_band),
            qty=context.get("order_qty", 1),
        )
        intents.append(intent)
    
    elif is_bearish_breakout:
        # Entry: Sell Stop at lower band (breakout level)
        order_id = generate_order_id(
            created_bar=bar_index,
            param_idx=0,
            role=ROLE_ENTRY,
            kind=KIND_STOP,
            side=SIDE_SELL,
        )
        
        intent = OrderIntent(
            order_id=order_id,
            created_bar=bar_index,
            role=OrderRole.ENTRY,
            kind=OrderKind.STOP,
            side=Side.SELL,
            price=float(lower_band),
            qty=context.get("order_qty", 1),
        )
        intents.append(intent)
    
    return {
        "intents": intents,
        "debug": {
            "close": float(curr_close) if not np.isnan(curr_close) else None,
            "high": float(curr_high) if not np.isnan(curr_high) else None,
            "low": float(curr_low) if not np.isnan(curr_low) else None,
            "sma": float(sma) if not np.isnan(sma) else None,
            "upper_band": float(upper_band) if not np.isnan(upper_band) else None,
            "lower_band": float(lower_band) if not np.isnan(lower_band) else None,
            "is_bullish_breakout": is_bullish_breakout,
            "is_bearish_breakout": is_bearish_breakout,
        },
    }


# Strategy specification
SPEC = StrategySpec(
    strategy_id="bollinger_breakout",
    version="v1",
    param_schema={
        "type": "object",
        "properties": {
            "bb_period": {"type": "integer", "minimum": 2, "maximum": 100},
            "bb_std": {"type": "number", "minimum": 0.5, "maximum": 5.0},
        },
        "required": ["bb_period", "bb_std"],
    },
    defaults={
        "bb_period": 20.0,
        "bb_std": 2.0,
    },
    fn=bollinger_breakout_strategy,
)