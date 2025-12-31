# S2/S3 Strategy Contract

## Overview
This document defines the contract for S2 (Pullback Continuation) and S3 (Extreme Reversion) strategies in the FishBroWFS_V2 system. It specifies the common concepts, mode definitions, parameter specifications, feature requirements, and entry behaviors that must be implemented consistently.

## Common Concepts

### 1. Feature-Agnostic Design
- Strategies accept generic feature parameter names (context_feature, value_feature, A_feature, etc.)
- Binding layer maps generic names to actual feature names
- Strategy code must not hardcode specific feature names
- All feature arrays are treated as float64; boolean signals as 0.0/1.0

### 2. Source-Agnostic Design
- Features can come from Data1 or Data2 sources
- Naming conventions determine source (implementation detail)
- Strategy code is unaware of feature source

### 3. Mode-Based Architecture
Both strategies support three orthogonal mode dimensions:
- **filter_mode**: Controls optional filtering (NONE | THRESHOLD)
- **trigger_mode**: Controls entry triggering (NONE | STOP | CROSS)
- **entry_mode**: Controls entry execution (MARKET_NEXT_OPEN when trigger_mode=NONE)

### 4. Content-Addressed Identity
- Strategies have immutable content-addressed IDs
- Identity derived from function source code hash
- Ensures reproducibility and versioning

## S2 (Pullback Continuation)

### Strategy Definition
S2 implements pullback continuation logic with configurable gates:
1. **Context Gate**: Trend context feature must meet threshold
2. **Value Gate**: Pullback depth/position feature must meet threshold
3. **Filter Gate**: Optional filter feature (when filter_mode=THRESHOLD)

### Parameters

| Parameter | Type | Enum Values | Default | Description |
|-----------|------|-------------|---------|-------------|
| `filter_mode` | string | `["NONE", "THRESHOLD"]` | `"NONE"` | Filter application mode |
| `trigger_mode` | string | `["NONE", "STOP", "CROSS"]` | `"NONE"` | Trigger generation mode |
| `entry_mode` | string | `["MARKET_NEXT_OPEN"]` | `"MARKET_NEXT_OPEN"` | Entry execution mode |
| `context_threshold` | float | - | `0.0` | Threshold for context_feature |
| `value_threshold` | float | - | `0.0` | Threshold for value_feature |
| `filter_threshold` | float | - | `0.0` | Threshold for filter_feature |
| `context_feature_name` | string | - | `""` | Placeholder for actual context feature |
| `value_feature_name` | string | - | `""` | Placeholder for actual value feature |
| `filter_feature_name` | string | - | `""` | Placeholder for actual filter feature |

### Feature Requirements
- **Required**: `context_feature`, `value_feature` (both 60-minute timeframe)
- **Optional**: `filter_feature` (60-minute timeframe, required when filter_mode=THRESHOLD)

### Logic Flow
```
1. Extract feature values using parameter names
2. Apply context gate: context_feature > context_threshold (or < if negative)
3. Apply value gate: value_feature > value_threshold (or < if negative)
4. Apply filter gate if filter_mode=THRESHOLD
5. Composite signal = all gates pass
6. Generate entry based on trigger_mode
```

### Entry Behavior by Trigger Mode

#### trigger_mode=NONE
- Entry via `entry_mode=MARKET_NEXT_OPEN`
- Implemented as STOP order at next bar's open price
- Uses current close as proxy (requires adjustment in production)
- **Contract**: Must fire immediately when composite signal is True

#### trigger_mode=STOP
- Place STOP order at `value_threshold` level
- Order remains active until filled or cancelled
- **Contract**: Order price = `value_threshold`

#### trigger_mode=CROSS
- Fire once when `value_feature` crosses `value_threshold`
- Check cross from previous bar to current bar
- **Contract**: Only fires on upward cross (prev ≤ threshold < current)

### Validation Rules
1. If `filter_mode=NONE`, `filter_feature_name` may be empty
2. If `trigger_mode=NONE`, `entry_mode` must be `MARKET_NEXT_OPEN`
3. All threshold parameters support signed logic:
   - Positive threshold: feature > threshold triggers
   - Negative threshold: feature < threshold triggers
   - Zero threshold: feature ≠ 0 triggers

## S3 (Extreme Reversion)

### Strategy Definition
S3 implements extreme reversion logic with configurable signal computation:
1. **Signal Computation**: Based on compare_mode (A_ONLY | DIFF | RATIO)
2. **Signal Gate**: Computed signal must meet threshold
3. **Filter Gate**: Optional filter feature (when filter_mode=THRESHOLD)

### Parameters

| Parameter | Type | Enum Values | Default | Description |
|-----------|------|-------------|---------|-------------|
| `filter_mode` | string | `["NONE", "THRESHOLD"]` | `"NONE"` | Filter application mode |
| `trigger_mode` | string | `["NONE", "STOP", "CROSS"]` | `"NONE"` | Trigger generation mode |
| `entry_mode` | string | `["MARKET_NEXT_OPEN"]` | `"MARKET_NEXT_OPEN"` | Entry execution mode |
| `compare_mode` | string | `["A_ONLY", "DIFF", "RATIO"]` | `"A_ONLY"` | Signal computation mode |
| `signal_threshold` | float | - | `0.0` | Threshold for computed signal |
| `filter_threshold` | float | - | `0.0` | Threshold for filter_feature |
| `A_feature_name` | string | - | `""` | Placeholder for actual A feature |
| `B_feature_name` | string | - | `""` | Placeholder for actual B feature |
| `filter_feature_name` | string | - | `""` | Placeholder for actual filter feature |

### Feature Requirements
- **Required**: `A_feature` (60-minute timeframe)
- **Optional**: `B_feature` (required when compare_mode≠A_ONLY), `filter_feature` (required when filter_mode=THRESHOLD)

### Signal Computation Modes

#### compare_mode=A_ONLY
- Signal = `A_feature`
- **Contract**: Use A_feature directly as signal value

#### compare_mode=DIFF
- Signal = `A_feature - B_feature`
- **Contract**: Simple subtraction, no scaling

#### compare_mode=RATIO
- Signal = `safe_div(A_feature, B_feature)`
- **Contract**: Use safe division (return 0.0 when denominator=0)

### Logic Flow
```
1. Extract feature values using parameter names
2. Compute signal based on compare_mode
3. Apply signal gate: signal > signal_threshold (or < if negative)
4. Apply filter gate if filter_mode=THRESHOLD
5. Composite signal = all gates pass
6. Generate entry based on trigger_mode
```

### Entry Behavior by Trigger Mode
Same as S2, but using `signal_threshold` instead of `value_threshold`.

### Validation Rules
1. If `filter_mode=NONE`, `filter_feature_name` may be empty
2. If `trigger_mode=NONE`, `entry_mode` must be `MARKET_NEXT_OPEN`
3. If `compare_mode≠A_ONLY`, `B_feature_name` must be non-empty
4. For `compare_mode=RATIO`, implement safe division (denominator protection)

## Common Mode Semantics

### filter_mode
- **NONE**: Skip filter gate entirely (filter_gate = True)
- **THRESHOLD**: Apply `filter_threshold` to `filter_feature`
- **Contract**: When THRESHOLD, filter_feature must be provided

### trigger_mode
- **NONE**: Immediate entry via MARKET_NEXT_OPEN
- **STOP**: Place stop order at threshold level
- **CROSS**: Fire once when threshold crossed
- **Contract**: All modes require composite signal to be True

### entry_mode
- **MARKET_NEXT_OPEN**: Entry at next bar's open
- **Contract**: Only valid when `trigger_mode=NONE`

## Feature Requirements Contract

### Declaration Methods
Strategies must provide feature requirements via:
1. **Python Method**: `feature_requirements()` returning `StrategyFeatureRequirements`
2. **JSON File**: `configs/strategies/{strategy_id}/features.json`

### Binding Layer Responsibilities
1. Map generic feature names to actual feature names
2. Validate required features exist
3. Inject actual feature names into parameters
4. Handle optional features based on mode configuration

### Timeframe Consistency
- All features within a strategy use same timeframe (default 60 minutes)
- Binding layer ensures timeframe alignment
- Feature resolver handles resampling when needed

## Implementation Requirements

### 1. Strategy Function Signature
```python
def strategy_function(context: Mapping[str, Any], params: Mapping[str, float]) -> Dict[str, Any]:
    # Returns {"intents": List[OrderIntent], "debug": dict}
```

### 2. Error Handling
- Return empty intents list on error
- Include error details in debug dict
- Validate feature arrays exist and are accessible
- Check bar_index bounds

### 3. Debug Information
Must include in debug dict:
- Feature values at current bar
- Gate status (True/False)
- Signal computation results
- Mode configuration
- Error messages if any

### 4. Order Generation
- Use `generate_order_id()` for deterministic order IDs
- Follow existing OrderIntent patterns
- Set appropriate OrderKind, OrderRole, Side
- Include price and quantity

## Integration Contract

### 1. Registry Integration
- Strategies must be registered via `load_builtin_strategies()`
- Must have unique `strategy_id` ("S2", "S3")
- Must follow `StrategySpec` pattern with param_schema and defaults

### 2. Research Runner Compatibility
- Must work with `allow_build=False` contract
- Feature requirements must be resolvable
- Must not require runtime feature building

### 3. GUI Compatibility
- param_schema must be GUI-introspectable
- Enum values must be properly defined
- Descriptions must be human-readable

### 4. Content-Addressed Identity
- Must support Phase 13 content-addressed identity
- Identity derived from function source code
- Immutable once registered

## Testing Contract

### 1. Unit Tests Must Verify
- Strategy registration and identity
- Parameter schema validity
- Feature requirements declaration
- Mode combination validation

### 2. Integration Tests Must Verify
- Registry contains S2 and S3
- Research runner can resolve strategies
- `allow_build=False` works correctly
- NONE mode support functions properly

### 3. Validation Tests Must Verify
- All mode combinations produce valid outputs
- Threshold logic works correctly (positive/negative/zero)
- Error handling for missing features
- Safe division for RATIO mode

## Compliance Checklist

### S2 Compliance
- [ ] Implements three-gate architecture (context, value, filter)
- [ ] Supports all filter_mode values (NONE, THRESHOLD)
- [ ] Supports all trigger_mode values (NONE, STOP, CROSS)
- [ ] Implements threshold signed logic
- [ ] Provides feature_requirements() method
- [ ] Follows param_schema pattern
- [ ] Returns proper debug information
- [ ] Handles missing features gracefully

### S3 Compliance
- [ ] Implements compare_mode (A_ONLY, DIFF, RATIO)
- [ ] Implements safe division for RATIO mode
- [ ] Supports all filter_mode values
- [ ] Supports all trigger_mode values
- [ ] Provides feature_requirements() method
- [ ] Validates B_feature when required
- [ ] Returns proper debug information

### Common Compliance
- [ ] Feature-agnostic design
- [ ] Source-agnostic design
- [ ] Content-addressed identity
- [ ] Research runner compatibility
- [ ] GUI parameter introspection
- [ ] Backward compatibility
- [ ] Comprehensive error handling

## Version History

### v1.0 (Initial Contract)
- Defines S2/S3 strategy contract
- Specifies mode semantics and parameters
- Establishes feature requirements pattern
- Defines integration requirements

## Appendix: Example Configurations

### S2 Example: Simple Pullback
```json
{
  "filter_mode": "NONE",
  "trigger_mode": "CROSS",
  "entry_mode": "MARKET_NEXT_OPEN",
  "context_threshold": 0.5,
  "value_threshold": -0.2,
  "context_feature_name": "trend_strength",
  "value_feature_name": "retracement_pct"
}
```

### S3 Example: Ratio Reversion
```json
{
  "filter_mode": "THRESHOLD",
  "trigger_mode": "STOP",
  "compare_mode": "RATIO",
  "signal_threshold": 2.0,
  "filter_threshold": 0.1,
  "A_feature_name": "price",
  "B_feature_name": "sma_20",
  "filter_feature_name": "volatility"
}