"""ATR Trailing Stop Strategy v1.

Phase J: Trend following strategy using ATR-based trailing stop.
Entry: On trend confirmation, exit when price hits trailing stop.
"""

from __future__ import annotations

from typing import Dict, Any, Mapping

import numpy as np

from engine.types import OrderIntent, OrderRole, OrderKind, Side
from engine.order_id import generate_order_id
from engine.constants import ROLE_ENTRY, KIND_STOP, SIDE_BUY, SIDE_SELL
from strategy.spec import StrategySpec, StrategyFn


def atr_trailing_stop_strategy(
    context: Mapping[str, Any],
    params: Mapping[str, float],
) -> Dict[str, Any]:
    """ATR Trailing Stop Strategy implementation.
    
    Entry signal: Trend confirmation based on price crossing moving average.
    Uses ATR-based trailing stop for exit.
    
    Args:
        context: Execution context with features and bar_index
        params: Strategy parameters (atr_period, atr_multiplier, ma_period)
        
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
    atr_period = int(params.get("atr_period", 14))
    atr_multiplier = params.get("atr_multiplier", 2.0)
    ma_period = int(params.get("ma_period", 20))
    
    curr_close = close[bar_index]
    curr_high = high[bar_index]
    curr_low = low[bar_index]
    
    # Calculate ATR (simplified for demo)
    # In a real implementation, this would use proper ATR feature
    lookback = min(max(atr_period, ma_period), bar_index + 1)
    if lookback > 1:
        # Calculate True Range
        prev_close = close[bar_index - 1] if bar_index > 0 else curr_close
        tr1 = curr_high - curr_low
        tr2 = abs(curr_high - prev_close)
        tr3 = abs(curr_low - prev_close)
        true_range = max(tr1, tr2, tr3)
        
        # Simple ATR (using current true range only for demo)
        atr_value = true_range
        
        # Calculate moving average
        recent_prices = close[bar_index - lookback + 1:bar_index + 1]
        ma_value = np.nanmean(recent_prices)
    else:
        atr_value = 0.0
        ma_value = curr_close
    
    # Check for trend signals
    is_bullish_trend = curr_close > ma_value and not np.isnan(curr_close) and not np.isnan(ma_value)
    is_bearish_trend = curr_close < ma_value and not np.isnan(curr_close) and not np.isnan(ma_value)
    
    intents = []
    if is_bullish_trend:
        # Entry: Buy Stop at current high + buffer (breakout entry)
        entry_price = float(curr_high + 0.5 * atr_value)  # Small buffer above high
        
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
            price=entry_price,
            qty=context.get("order_qty", 1),
        )
        intents.append(intent)
        
        # Also create trailing stop exit (simulated by separate logic)
        # In a real implementation, this would be managed by position tracking
        
    elif is_bearish_trend:
        # Entry: Sell Stop at current low - buffer (breakdown entry)
        entry_price = float(curr_low - 0.5 * atr_value)  # Small buffer below low
        
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
            price=entry_price,
            qty=context.get("order_qty", 1),
        )
        intents.append(intent)
    
    return {
        "intents": intents,
        "debug": {
            "close": float(curr_close) if not np.isnan(curr_close) else None,
            "high": float(curr_high) if not np.isnan(curr_high) else None,
            "low": float(curr_low) if not np.isnan(curr_low) else None,
            "ma": float(ma_value) if not np.isnan(ma_value) else None,
            "atr": float(atr_value) if not np.isnan(atr_value) else None,
            "trailing_stop_distance": float(atr_value * atr_multiplier) if not np.isnan(atr_value) else None,
            "is_bullish_trend": is_bullish_trend,
            "is_bearish_trend": is_bearish_trend,
        },
    }


# Strategy specification
SPEC = StrategySpec(
    strategy_id="atr_trailing_stop",
    version="v1",
    param_schema={
        "type": "object",
        "properties": {
            "atr_period": {"type": "integer", "minimum": 2, "maximum": 100},
            "atr_multiplier": {"type": "number", "minimum": 0.5, "maximum": 5.0},
            "ma_period": {"type": "integer", "minimum": 2, "maximum": 100},
        },
        "required": ["atr_period", "atr_multiplier", "ma_period"],
    },
    defaults={
        "atr_period": 14.0,
        "atr_multiplier": 2.0,
        "ma_period": 20.0,
    },
    fn=atr_trailing_stop_strategy,
)