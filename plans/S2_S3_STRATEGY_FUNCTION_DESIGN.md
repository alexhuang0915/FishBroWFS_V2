# S2/S3 Strategy Function Design

## Overview
This document defines the strategy function implementations for S2 (Pullback Continuation) and S3 (Extreme Reversion), including mode handling logic, threshold processing, and order intent generation.

## Common Design Patterns

### 1. Function Signature
Both strategies follow the existing `StrategyFn` signature:
```python
def strategy_function(context: Mapping[str, Any], params: Mapping[str, float]) -> Dict[str, Any]:
    # Returns {"intents": List[OrderIntent], "debug": dict}
```

### 2. Mode Handling Architecture
```
Input Features → Mode Gates → Signal Computation → Trigger Logic → Order Generation
     ↓              ↓              ↓                 ↓              ↓
  Feature     filter_mode      compare_mode     trigger_mode    entry_mode
  Arrays      (NONE/THRESHOLD) (S3 only)        (NONE/STOP/CROSS) (MARKET_NEXT_OPEN)
```

### 3. Common Helper Functions
```python
def apply_threshold(feature_value: float, threshold: float) -> bool:
    """Check if feature meets threshold condition."""
    if threshold >= 0:
        return feature_value > threshold
    else:
        return feature_value < threshold

def safe_div(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Safe division with zero denominator protection."""
    if denominator == 0:
        return default
    return numerator / denominator
```

## S2 (Pullback Continuation) Implementation

### Core Logic Flow
```
1. Extract feature values using parameter names
2. Apply context gate (context_feature > context_threshold)
3. Apply value gate (value_feature > value_threshold)
4. Apply filter gate if filter_mode=THRESHOLD
5. Compute composite signal (all gates must pass)
6. Based on trigger_mode:
   - NONE: Generate MARKET_NEXT_OPEN order
   - STOP: Place stop order at threshold level
   - CROSS: Fire once when threshold crossed
```

### Detailed Implementation

```python
def s2_strategy(context: Mapping[str, Any], params: Mapping[str, float]) -> Dict[str, Any]:
    """S2 (Pullback Continuation) strategy implementation."""
    
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
    
    # 4. Get current values
    if bar_index >= len(context_arr) or bar_index >= len(value_arr):
        return {"intents": [], "debug": {"error": "bar_index out of bounds"}}
    
    context_val = float(context_arr[bar_index])
    value_val = float(value_arr[bar_index])
    filter_val = float(filter_arr[bar_index]) if filter_arr is not None and bar_index < len(filter_arr) else 0.0
    
    # 5. Apply gates
    context_gate = apply_threshold(context_val, params.get("context_threshold", 0.0))
    value_gate = apply_threshold(value_val, params.get("value_threshold", 0.0))
    
    filter_gate = True
    if params.get("filter_mode") == "THRESHOLD" and filter_arr is not None:
        filter_gate = apply_threshold(filter_val, params.get("filter_threshold", 0.0))
    
    # 6. Composite signal
    signal = context_gate and value_gate and filter_gate
    
    # 7. Generate intents based on trigger_mode
    intents = []
    debug = {
        "context_value": context_val,
        "value_value": value_val,
        "filter_value": filter_val if filter_arr is not None else None,
        "context_gate": context_gate,
        "value_gate": value_gate,
        "filter_gate": filter_gate if params.get("filter_mode") == "THRESHOLD" else None,
        "signal": signal,
        "trigger_mode": params.get("trigger_mode", "NONE")
    }
    
    if signal:
        trigger_mode = params.get("trigger_mode", "NONE")
        
        if trigger_mode == "NONE":
            # MARKET_NEXT_OPEN entry (implemented as STOP at next bar's open)
            # Note: Actual open price not known yet; use current close as proxy
            # In production, this would need adjustment
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
                
                # Check for cross: previous below, current above threshold
                cross_up = prev_value <= threshold and curr_value > threshold
                
                if cross_up:
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
```

## S3 (Extreme Reversion) Implementation

### Core Logic Flow
```
1. Extract feature values using parameter names
2. Compute signal based on compare_mode:
   - A_ONLY: Use A_feature directly
   - DIFF: A_feature - B_feature
   - RATIO: safe_div(A_feature, B_feature)
3. Apply signal gate (signal > signal_threshold)
4. Apply filter gate if filter_mode=THRESHOLD
5. Compute composite signal
6. Based on trigger_mode (same as S2)
```

### Detailed Implementation

```python
def s3_strategy(context: Mapping[str, Any], params: Mapping[str, float]) -> Dict[str, Any]:
    """S3 (Extreme Reversion) strategy implementation."""
    
    # 1. Extract context and features
    features = context.get("features", {})
    bar_index = context.get("bar_index", 0)
    
    # 2. Get feature arrays using parameter names
    A_feature_name = params.get("A_feature_name", "")
    B_feature_name = params.get("B_feature_name", "")
    filter_feature_name = params.get("filter_feature_name", "")
    
    A_arr = features.get(A_feature_name)
    B_arr = features.get(B_feature_name) if B_feature_name else None
    filter_arr = features.get(filter_feature_name) if filter_feature_name else None
    
    # 3. Validate feature arrays
    if A_arr is None:
        return {"intents": [], "debug": {"error": "Missing A_feature"}}
    
    compare_mode = params.get("compare_mode", "A_ONLY")
    if compare_mode != "A_ONLY" and B_arr is None:
        return {"intents": [], "debug": {"error": f"Missing B_feature for compare_mode={compare_mode}"}}
    
    # 4. Get current values
    if bar_index >= len(A_arr):
        return {"intents": [], "debug": {"error": "bar_index out of bounds"}}
    
    A_val = float(A_arr[bar_index])
    B_val = float(B_arr[bar_index]) if B_arr is not None and bar_index < len(B_arr) else 0.0
    filter_val = float(filter_arr[bar_index]) if filter_arr is not None and bar_index < len(filter_arr) else 0.0
    
    # 5. Compute signal based on compare_mode
    if compare_mode == "A_ONLY":
        signal_val = A_val
    elif compare_mode == "DIFF":
        signal_val = A_val - B_val
    elif compare_mode == "RATIO":
        signal_val = safe_div(A_val, B_val, default=0.0)
    else:
        signal_val = 0.0
    
    # 6. Apply gates
    signal_gate = apply_threshold(signal_val, params.get("signal_threshold", 0.0))
    
    filter_gate = True
    if params.get("filter_mode") == "THRESHOLD" and filter_arr is not None:
        filter_gate = apply_threshold(filter_val, params.get("filter_threshold", 0.0))
    
    # 7. Composite signal
    signal = signal_gate and filter_gate
    
    # 8. Generate intents based on trigger_mode
    intents = []
    debug = {
        "A_value": A_val,
        "B_value": B_val if B_arr is not None else None,
        "filter_value": filter_val if filter_arr is not None else None,
        "signal_value": signal_val,
        "compare_mode": compare_mode,
        "signal_gate": signal_gate,
        "filter_gate": filter_gate if params.get("filter_mode") == "THRESHOLD" else None,
        "signal": signal,
        "trigger_mode": params.get("trigger_mode", "NONE")
    }
    
    if signal:
        trigger_mode = params.get("trigger_mode", "NONE")
        
        if trigger_mode == "NONE":
            # MARKET_NEXT_OPEN entry
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
            # Place stop order at signal_threshold level
            price = params.get("signal_threshold", 0.0)
            
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
            # Fire once when threshold crossed
            if bar_index > 0:
                prev_signal = 0.0
                if compare_mode == "A_ONLY":
                    prev_signal = float(A_arr[bar_index - 1])
                elif compare_mode == "DIFF":
                    prev_A = float(A_arr[bar_index - 1])
                    prev_B = float(B_arr[bar_index - 1]) if B_arr is not None else 0.0
                    prev_signal = prev_A - prev_B
                elif compare_mode == "RATIO":
                    prev_A = float(A_arr[bar_index - 1])
                    prev_B = float(B_arr[bar_index - 1]) if B_arr is not None else 0.0
                    prev_signal = safe_div(prev_A, prev_B, default=0.0)
                
                curr_signal = signal_val
                threshold = params.get("signal_threshold", 0.0)
                
                # Check for cross: previous below, current above threshold
                cross_up = prev_signal <= threshold and curr_signal > threshold
                
                if cross_up:
                    # Use current signal value as entry price (or A value)
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
                        price=curr_signal,
                        qty=context.get("order_qty", 1),
                    )
                    intents.append(intent)
    
    return {"intents": intents, "debug": debug}
```

## Mode Handling Details

### 1. Filter Mode (NONE/THRESHOLD)
- **NONE**: Skip filter gate entirely (filter_gate = True)
- **THRESHOLD**: Apply threshold to filter_feature
- Implementation checks `filter_mode` parameter and conditionally applies filter

### 2. Trigger Mode (NONE/STOP/CROSS)
- **NONE**: Immediate entry via MARKET_NEXT_OPEN (STOP at next open)
- **STOP**: Place stop order at threshold level
- **CROSS**: Fire once when feature crosses threshold
- All modes require composite signal to be True

### 3. Compare Mode (S3 only: A_ONLY/DIFF/RATIO)
- **A_ONLY**: Use A_feature directly as signal
- **DIFF**: Compute A - B as signal
- **RATIO**: Compute A / B with safe division
- Validation ensures B_feature exists when needed

### 4. Entry Mode (MARKET_NEXT_OPEN)
- Only valid when `trigger_mode=NONE`
- Implemented as STOP order at next bar's open
- In practice, uses current close as proxy (requires adjustment in production)

## Error Handling and Validation

### 1. Feature Validation
- Check required features exist in context
- Validate bar_index bounds
- Handle NaN values appropriately

### 2. Mode Validation
- Validate parameter combinations (e.g., filter_mode=THRESHOLD requires filter_feature)
- Validate compare_mode requirements
- Gracefully handle invalid modes

### 3. Safe Operations
- Use `safe_div` for RATIO mode to avoid division by zero
- Check array bounds before access
- Convert to float with NaN handling

## Debug Information
Both strategies return comprehensive debug information including:
- Feature values at current bar
- Gate status (True/False)
- Signal computation results
- Mode configuration
- Error messages if any

## Performance Considerations
1. **Vectorization Potential**: Gates could be vectorized across entire array for batch processing
2. **Memory Efficiency**: Use numpy arrays directly without conversion when possible
3. **Early Exit**: Check bounds and validity early to avoid unnecessary computation
4. **Caching**: Consider caching feature arrays for repeated access