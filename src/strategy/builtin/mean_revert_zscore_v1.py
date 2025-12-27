
"""Mean Reversion Z-Score Strategy v1.

Phase 7: Mean reversion strategy using z-score.
Entry: When z-score is below threshold (oversold).
"""

from __future__ import annotations

from typing import Dict, Any, Mapping

import numpy as np

from engine.types import OrderIntent, OrderRole, OrderKind, Side
from engine.order_id import generate_order_id
from engine.constants import ROLE_ENTRY, KIND_LIMIT, SIDE_BUY
from strategy.spec import StrategySpec, StrategyFn


def mean_revert_zscore_strategy(
    context: Mapping[str, Any],
    params: Mapping[str, float],
) -> Dict[str, Any]:
    """Mean Reversion Z-Score Strategy implementation.
    
    Entry signal: Z-score below threshold (oversold, mean reversion buy).
    
    Args:
        context: Execution context with features and bar_index
        params: Strategy parameters (zscore_threshold)
        
    Returns:
        Dict with "intents" (List[OrderIntent]) and "debug" (dict)
    """
    features = context.get("features", {})
    bar_index = context.get("bar_index", 0)
    
    # Get features
    zscore = features.get("zscore")
    close = features.get("close")
    
    if zscore is None or close is None:
        return {"intents": [], "debug": {"error": "Missing zscore or close features"}}
    
    # Convert to numpy arrays if needed
    if not isinstance(zscore, np.ndarray):
        zscore = np.array(zscore)
    if not isinstance(close, np.ndarray):
        close = np.array(close)
    
    # Check bounds
    if bar_index >= len(zscore) or bar_index >= len(close):
        return {"intents": [], "debug": {"error": "bar_index out of bounds"}}
    
    # Need at least 1 bar
    if bar_index < 0:
        return {"intents": [], "debug": {}}
    
    curr_zscore = zscore[bar_index]
    curr_close = close[bar_index]
    threshold = params.get("zscore_threshold", -2.0)
    
    # Check for oversold condition: z-score below threshold
    is_oversold = (
        curr_zscore < threshold and
        not np.isnan(curr_zscore) and
        not np.isnan(curr_close)
    )
    
    intents = []
    if is_oversold:
        # Entry: Buy Limit at current close (mean reversion)
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
    
    return {
        "intents": intents,
        "debug": {
            "zscore": float(curr_zscore) if not np.isnan(curr_zscore) else None,
            "close": float(curr_close) if not np.isnan(curr_close) else None,
            "threshold": threshold,
            "is_oversold": is_oversold,
        },
    }


# Strategy specification
SPEC = StrategySpec(
    strategy_id="mean_revert_zscore",
    version="v1",
    param_schema={
        "type": "object",
        "properties": {
            "zscore_threshold": {"type": "number"},
        },
        "required": ["zscore_threshold"],
    },
    defaults={
        "zscore_threshold": -2.0,
    },
    fn=mean_revert_zscore_strategy,
)


