"""S3 Strategy v1 (Extreme Reversion).

Phase 13: Extreme reversion strategy using gate-based processing.
Entry: Context gate + value gate (oversold condition) + optional filter gate.
Supports multiple trigger modes (NONE, STOP, CROSS) and filter modes (NONE, THRESHOLD).
"""

from __future__ import annotations

from typing import Dict, Any, Mapping

import numpy as np

from engine.engine_types import OrderIntent, OrderRole, OrderKind, Side
from engine.order_id import generate_order_id
from engine.constants import ROLE_ENTRY, KIND_STOP, SIDE_BUY
from strategy.spec import StrategySpec, StrategyFn
from contracts.strategy_features import StrategyFeatureRequirements, FeatureRef


def apply_threshold(feature_value: float, threshold: float) -> bool:
    """Check if feature meets threshold condition.
    
    Positive threshold: feature > threshold triggers
    Negative threshold: feature < threshold triggers
    Zero threshold: feature != 0 triggers
    """
    if threshold >= 0:
        return feature_value > threshold
    else:
        return feature_value < threshold


def s3_strategy(context: Mapping[str, Any], params: Mapping[str, float]) -> Dict[str, Any]:
    """S3 (Extreme Reversion) strategy implementation.
    
    Logic flow:
    1. Extract feature values using parameter names
    2. Apply context gate (context_feature > context_threshold)
    3. Apply value gate (value_feature < value_threshold) - OVERSOLD condition
    4. Apply filter gate if filter_mode=THRESHOLD
    5. Compute composite signal (all gates must pass)
    6. Based on trigger_mode:
       - NONE: Generate MARKET_NEXT_OPEN order
       - STOP: Place stop order at threshold level
       - CROSS: Fire once when threshold crossed
    
    Args:
        context: Execution context with features and bar_index
        params: Strategy parameters (see param_schema)
        
    Returns:
        Dict with "intents" (List[OrderIntent]) and "debug" (dict)
    """
    # 1. Extract context and features
    features = context.get("features", {})
    bar_index = context.get("bar_index", 0)
    
    # 2. Get feature arrays using parameter names
    context_feature_name = params.get("context_feature_name", "")
    value_feature_name = params.get("value_feature_name", "")
    filter_feature_name = params.get("filter_feature_name", "")
    
    context_arr = features.get(context_feature_name)
    value_arr = features.get(value_feature_name)
    filter_arr = features.get(filter_feature_name) if filter_feature_name else None
    
    # 3. Validate feature arrays
    if context_arr is None or value_arr is None:
        return {"intents": [], "debug": {"error": "Missing required features"}}
    
    # 4. Validate array lengths (should be same for all features)
    if len(context_arr) != len(value_arr):
        return {"intents": [], "debug": {"error": "Feature arrays have different lengths"}}
    
    if filter_arr is not None and len(filter_arr) != len(context_arr):
        return {"intents": [], "debug": {"error": "Filter feature array has different length"}}
    
    # 5. Get current values
    if bar_index >= len(context_arr):
        return {"intents": [], "debug": {"error": "bar_index out of bounds"}}
    
    # Handle NaN values
    context_val = float(context_arr[bar_index])
    value_val = float(value_arr[bar_index])
    filter_val = float(filter_arr[bar_index]) if filter_arr is not None and bar_index < len(filter_arr) else 0.0
    
    # Check for NaN values (NaN comparisons always return False)
    if np.isnan(context_val) or np.isnan(value_val):
        return {"intents": [], "debug": {"error": "NaN feature value", "context_nan": np.isnan(context_val), "value_nan": np.isnan(value_val)}}
    
    # 6. Apply gates
    context_gate = apply_threshold(context_val, params.get("context_threshold", 0.0))
    
    # EXTREME REVERSION: value_feature < value_threshold (oversold condition)
    # Always use less-than comparison for oversold condition
    value_threshold = params.get("value_threshold", 0.0)
    value_gate = value_val < value_threshold
    
    filter_gate = True
    filter_mode = params.get("filter_mode", "NONE")
    if filter_mode == "THRESHOLD" and filter_arr is not None:
        # Check for NaN in filter value
        if np.isnan(filter_val):
            return {"intents": [], "debug": {"error": "NaN filter feature value"}}
        filter_gate = apply_threshold(filter_val, params.get("filter_threshold", 0.0))
    
    # 7. Composite signal
    signal = context_gate and value_gate and filter_gate
    
    # 7. Generate intents based on trigger_mode
    intents = []
    debug = {
        "context_value": context_val,
        "value_value": value_val,
        "filter_value": filter_val if filter_arr is not None else None,
        "context_gate": context_gate,
        "value_gate": value_gate,
        "filter_gate": filter_gate if filter_mode == "THRESHOLD" else None,
        "signal": signal,
        "trigger_mode": params.get("trigger_mode", "NONE")
    }
    
    if signal:
        trigger_mode = params.get("trigger_mode", "NONE")
        
        if trigger_mode == "NONE":
            # MARKET_NEXT_OPEN entry (implemented as STOP at next bar's open)
            # Use current close as proxy for next open
            price = float(features.get("close", [0])[bar_index]) if "close" in features else 0.0
            
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
                price=price,
                qty=context.get("order_qty", 1),
            )
            intents.append(intent)
            
        elif trigger_mode == "STOP":
            # Place stop order at value_threshold level
            price = params.get("value_threshold", 0.0)
            
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
                price=price,
                qty=context.get("order_qty", 1),
            )
            intents.append(intent)
            
        elif trigger_mode == "CROSS":
            # Fire once when threshold crossed (check previous bar)
            if bar_index > 0:
                prev_value = float(value_arr[bar_index - 1])
                curr_value = value_val
                threshold = params.get("value_threshold", 0.0)
                
                # Check for cross DOWN (oversold): previous above, current below threshold
                # For extreme reversion, we want to enter when value crosses BELOW threshold
                cross_down = prev_value >= threshold and curr_value < threshold
                
                if cross_down:
                    # Use current value as entry price
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
                        price=curr_value,
                        qty=context.get("order_qty", 1),
                    )
                    intents.append(intent)
    
    return {"intents": intents, "debug": debug}


def feature_requirements() -> StrategyFeatureRequirements:
    """Return the feature requirements for S3 strategy.
    
    S3 is feature-agnostic - it accepts feature names as parameters.
    However, we need to declare that it requires at least context_feature
    and value_feature, with optional filter_feature.
    
    Since the actual feature names are provided via parameters, we can't
    specify exact feature names here. Instead, we declare generic requirements
    that will be resolved by the binding layer.
    """
    return StrategyFeatureRequirements(
        strategy_id="S3",
        required=[
            # These are placeholder references - actual names come from parameters
            FeatureRef(name="context_feature", timeframe_min=60),
            FeatureRef(name="value_feature", timeframe_min=60),
        ],
        optional=[
            FeatureRef(name="filter_feature", timeframe_min=60),
        ],
        min_schema_version="v1",
        notes="S3 is feature-agnostic. Actual feature names are provided via "
              "context_feature_name, value_feature_name, and filter_feature_name "
              "parameters. The binding layer must resolve these to actual feature "
              "names before execution.",
    )


# Strategy specification
SPEC = StrategySpec(
    strategy_id="S3",
    version="v1",
    param_schema={
        "type": "object",
        "properties": {
            "filter_mode": {
                "type": "string",
                "enum": ["NONE", "THRESHOLD"],
                "default": "NONE",
                "description": "Filter application mode"
            },
            "trigger_mode": {
                "type": "string",
                "enum": ["NONE", "STOP", "CROSS"],
                "default": "NONE",
                "description": "Trigger generation mode"
            },
            "entry_mode": {
                "type": "string",
                "enum": ["MARKET_NEXT_OPEN"],
                "default": "MARKET_NEXT_OPEN",
                "description": "Entry execution mode (only when trigger_mode=NONE)"
            },
            "context_threshold": {
                "type": "number",
                "default": 0.0,
                "description": "Threshold for context_feature"
            },
            "value_threshold": {
                "type": "number",
                "default": 0.0,
                "description": "Threshold for value_feature (oversold condition: value_feature < threshold)"
            },
            "filter_threshold": {
                "type": "number",
                "default": 0.0,
                "description": "Threshold for filter_feature (only used when filter_mode=THRESHOLD)"
            },
            "context_feature_name": {
                "type": "string",
                "default": "",
                "description": "Placeholder for binding layer - actual context feature name"
            },
            "value_feature_name": {
                "type": "string",
                "default": "",
                "description": "Placeholder for binding layer - actual value feature name"
            },
            "filter_feature_name": {
                "type": "string",
                "default": "",
                "description": "Placeholder for binding layer - actual filter feature name (optional)"
            },
            "order_qty": {
                "type": "number",
                "default": 1.0,
                "minimum": 0.0,
                "description": "Order quantity (default 1)"
            }
        },
        "required": [
            "filter_mode",
            "trigger_mode",
            "entry_mode",
            "context_threshold",
            "value_threshold",
            "filter_threshold",
            "context_feature_name",
            "value_feature_name",
            "filter_feature_name",
            "order_qty"
        ],
        "additionalProperties": False,
    },
    defaults={
        "filter_mode": "NONE",
        "trigger_mode": "NONE",
        "entry_mode": "MARKET_NEXT_OPEN",
        "context_threshold": 0.0,
        "value_threshold": 0.0,
        "filter_threshold": 0.0,
        "context_feature_name": "",
        "value_feature_name": "",
        "filter_feature_name": "",
        "order_qty": 1.0,
    },
    fn=s3_strategy,
)