"""S1 Strategy v1.

Phase 7: Basic strategy using the 16 registry features (sma_5, sma_10, sma_20, sma_40,
hh_5, hh_10, hh_20, hh_40, ll_5, ll_10, ll_20, ll_40, atr_10, atr_14,
vx_percentile_126, vx_percentile_252) plus baseline features (ret_z_200, session_vwap).

Entry: Simple crossover of sma_5 and sma_20.
"""

from __future__ import annotations

from typing import Dict, Any, Mapping

import numpy as np

from engine.engine_types import OrderIntent, OrderRole, OrderKind, Side
from engine.order_id import generate_order_id
from engine.constants import ROLE_ENTRY, KIND_STOP, SIDE_BUY
from strategy.spec import StrategySpec, StrategyFn
from contracts.strategy_features import StrategyFeatureRequirements, FeatureRef


def s1_strategy(context: Mapping[str, Any], params: Mapping[str, float]) -> Dict[str, Any]:
    """S1 Strategy implementation.
    
    Entry signal: sma_5 crosses above sma_20 (golden cross).
    
    Args:
        context: Execution context with features and bar_index
        params: Strategy parameters (none required for S1)
        
    Returns:
        Dict with "intents" (List[OrderIntent]) and "debug" (dict)
    """
    features = context.get("features", {})
    bar_index = context.get("bar_index", 0)
    
    # Get features
    sma_5 = features.get("sma_5")
    sma_20 = features.get("sma_20")
    
    if sma_5 is None or sma_20 is None:
        return {"intents": [], "debug": {"error": "Missing SMA features"}}
    
    # Convert to numpy arrays if needed
    if not isinstance(sma_5, np.ndarray):
        sma_5 = np.array(sma_5)
    if not isinstance(sma_20, np.ndarray):
        sma_20 = np.array(sma_20)
    
    # Check bounds
    if bar_index >= len(sma_5) or bar_index >= len(sma_20):
        return {"intents": [], "debug": {"error": "bar_index out of bounds"}}
    
    # Need at least 2 bars to detect crossover
    if bar_index < 1:
        return {"intents": [], "debug": {}}
    
    # Check for golden cross (sma_5 crosses above sma_20)
    prev_sma5 = sma_5[bar_index - 1]
    prev_sma20 = sma_20[bar_index - 1]
    curr_sma5 = sma_5[bar_index]
    curr_sma20 = sma_20[bar_index]
    
    # Golden cross: prev_sma5 <= prev_sma20 AND curr_sma5 > curr_sma20
    is_golden_cross = (
        prev_sma5 <= prev_sma20 and
        curr_sma5 > curr_sma20 and
        not np.isnan(prev_sma5) and
        not np.isnan(prev_sma20) and
        not np.isnan(curr_sma5) and
        not np.isnan(curr_sma20)
    )
    
    intents = []
    if is_golden_cross:
        # Entry: Buy Stop at current sma_5
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
            price=float(curr_sma5),
            qty=context.get("order_qty", 1),
        )
        intents.append(intent)
    
    return {
        "intents": intents,
        "debug": {
            "sma_5": float(curr_sma5) if not np.isnan(curr_sma5) else None,
            "sma_20": float(curr_sma20) if not np.isnan(curr_sma20) else None,
            "is_golden_cross": is_golden_cross,
        },
    }


def feature_requirements() -> StrategyFeatureRequirements:
    """Return the feature requirements for S1 strategy."""
    return StrategyFeatureRequirements(
        strategy_id="S1",
        required=[
            FeatureRef(name="sma_5", timeframe_min=60),
            FeatureRef(name="sma_10", timeframe_min=60),
            FeatureRef(name="sma_20", timeframe_min=60),
            FeatureRef(name="sma_40", timeframe_min=60),
            FeatureRef(name="hh_5", timeframe_min=60),
            FeatureRef(name="hh_10", timeframe_min=60),
            FeatureRef(name="hh_20", timeframe_min=60),
            FeatureRef(name="hh_40", timeframe_min=60),
            FeatureRef(name="ll_5", timeframe_min=60),
            FeatureRef(name="ll_10", timeframe_min=60),
            FeatureRef(name="ll_20", timeframe_min=60),
            FeatureRef(name="ll_40", timeframe_min=60),
            FeatureRef(name="atr_10", timeframe_min=60),
            FeatureRef(name="atr_14", timeframe_min=60),
            FeatureRef(name="vx_percentile_126", timeframe_min=60),
            FeatureRef(name="vx_percentile_252", timeframe_min=60),
            FeatureRef(name="ret_z_200", timeframe_min=60),
            FeatureRef(name="session_vwap", timeframe_min=60),
        ],
        optional=[],
        min_schema_version="v1",
        notes="Raw bars (open/high/low/close/volume) are provided via outputs/shared/.../bars/resampled_60m.npz, not via features cache.",
    )


# Strategy specification
SPEC = StrategySpec(
    strategy_id="S1",
    version="v1",
    param_schema={
        "type": "object",
        "properties": {
            # No parameters required for S1
        },
        "required": [],
    },
    defaults={},
    fn=s1_strategy,
)