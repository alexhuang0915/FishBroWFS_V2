"""RSI Reversal Strategy v1.

Phase J: Mean reversion strategy using RSI oversold/overbought.
Entry: When RSI is below oversold threshold (buy) or above overbought threshold (sell).
"""

from __future__ import annotations

from typing import Dict, Any, Mapping

import numpy as np

from FishBroWFS_V2.engine.types import OrderIntent, OrderRole, OrderKind, Side
from FishBroWFS_V2.engine.order_id import generate_order_id
from FishBroWFS_V2.engine.constants import ROLE_ENTRY, KIND_LIMIT, SIDE_BUY, SIDE_SELL
from FishBroWFS_V2.strategy.spec import StrategySpec, StrategyFn


def rsi_reversal_strategy(
    context: Mapping[str, Any],
    params: Mapping[str, float],
) -> Dict[str, Any]:
    """RSI Reversal Strategy implementation.
    
    Entry signal: RSI below oversold threshold (buy) or above overbought threshold (sell).
    
    Args:
        context: Execution context with features and bar_index
        params: Strategy parameters (rsi_period, oversold, overbought)
        
    Returns:
        Dict with "intents" (List[OrderIntent]) and "debug" (dict)
    """
    features = context.get("features", {})
    bar_index = context.get("bar_index", 0)
    
    # Get features
    close = features.get("close")
    
    if close is None:
        return {"intents": [], "debug": {"error": "Missing close feature"}}
    
    # Convert to numpy array if needed
    if not isinstance(close, np.ndarray):
        close = np.array(close)
    
    # Check bounds
    if bar_index >= len(close):
        return {"intents": [], "debug": {"error": "bar_index out of bounds"}}
    
    # Need at least 1 bar
    if bar_index < 0:
        return {"intents": [], "debug": {}}
    
    # Get parameters
    rsi_period = int(params.get("rsi_period", 14))
    oversold = params.get("oversold", 30.0)
    overbought = params.get("overbought", 70.0)
    
    # Calculate simple RSI (simplified for demo)
    # In a real implementation, this would use a proper RSI feature
    # For now, we'll use a mock calculation
    curr_close = close[bar_index]
    
    # Mock RSI calculation: use price position relative to recent range
    lookback = min(rsi_period, bar_index + 1)
    if lookback > 1:
        recent_prices = close[bar_index - lookback + 1:bar_index + 1]
        price_min = np.nanmin(recent_prices)
        price_max = np.nanmax(recent_prices)
        if price_max > price_min:
            # Simple position indicator (0-100) as mock RSI
            mock_rsi = 100.0 * (curr_close - price_min) / (price_max - price_min)
        else:
            mock_rsi = 50.0
    else:
        mock_rsi = 50.0
    
    # Check for oversold/overbought conditions
    is_oversold = mock_rsi < oversold and not np.isnan(mock_rsi)
    is_overbought = mock_rsi > overbought and not np.isnan(mock_rsi)
    
    intents = []
    if is_oversold:
        # Entry: Buy Limit at current close (mean reversion buy)
        order_id = generate_order_id(
            created_bar=bar_index,
            param_idx=0,
            role=ROLE_ENTRY,
            kind=KIND_LIMIT,
            side=SIDE_BUY,
        )
        
        intent = OrderIntent(
            order_id=order_id,
            created_bar=bar_index,
            role=OrderRole.ENTRY,
            kind=OrderKind.LIMIT,
            side=Side.BUY,
            price=float(curr_close),
            qty=context.get("order_qty", 1),
        )
        intents.append(intent)
    
    elif is_overbought:
        # Entry: Sell Limit at current close (mean reversion sell)
        order_id = generate_order_id(
            created_bar=bar_index,
            param_idx=0,
            role=ROLE_ENTRY,
            kind=KIND_LIMIT,
            side=SIDE_SELL,
        )
        
        intent = OrderIntent(
            order_id=order_id,
            created_bar=bar_index,
            role=OrderRole.ENTRY,
            kind=OrderKind.LIMIT,
            side=Side.SELL,
            price=float(curr_close),
            qty=context.get("order_qty", 1),
        )
        intents.append(intent)
    
    return {
        "intents": intents,
        "debug": {
            "close": float(curr_close) if not np.isnan(curr_close) else None,
            "rsi": float(mock_rsi) if not np.isnan(mock_rsi) else None,
            "oversold": oversold,
            "overbought": overbought,
            "is_oversold": is_oversold,
            "is_overbought": is_overbought,
        },
    }


# Strategy specification
SPEC = StrategySpec(
    strategy_id="rsi_reversal",
    version="v1",
    param_schema={
        "type": "object",
        "properties": {
            "rsi_period": {"type": "integer", "minimum": 2, "maximum": 100},
            "oversold": {"type": "number", "minimum": 0, "maximum": 50},
            "overbought": {"type": "number", "minimum": 50, "maximum": 100},
        },
        "required": ["rsi_period", "oversold", "overbought"],
    },
    defaults={
        "rsi_period": 14.0,
        "oversold": 30.0,
        "overbought": 70.0,
    },
    fn=rsi_reversal_strategy,
)