# S2/S3 Parameter Schema Design

## Overview
This document defines the parameter schemas for S2 (Pullback Continuation) and S3 (Extreme Reversion) strategies, following the existing strategy pattern in FishBroWFS_V2.

## Common Design Principles

1. **Feature-Agnostic Design**: Strategies accept generic feature parameter names (context_feature, value_feature, etc.) that are bound to actual feature names by the binding layer.

2. **Mode-Based Configuration**: Both strategies support three mode dimensions:
   - `filter_mode`: NONE | THRESHOLD
   - `trigger_mode`: NONE | STOP | CROSS
   - `entry_mode`: MARKET_NEXT_OPEN (default when trigger_mode=NONE)

3. **Validation Rules**: Parameter schemas include validation constraints based on mode dependencies.

4. **JSON Schema Format**: Follows existing pattern using jsonschema-like dict with properties, types, enums, and validation rules.

## S2 (Pullback Continuation) Parameter Schema

### Core Parameters
| Parameter | Type | Enum Values | Default | Description |
|-----------|------|-------------|---------|-------------|
| `filter_mode` | string | `["NONE", "THRESHOLD"]` | `"NONE"` | Filter application mode |
| `trigger_mode` | string | `["NONE", "STOP", "CROSS"]` | `"NONE"` | Trigger generation mode |
| `entry_mode` | string | `["MARKET_NEXT_OPEN"]` | `"MARKET_NEXT_OPEN"` | Entry execution mode (only valid when trigger_mode=NONE) |
| `context_threshold` | float | - | `0.0` | Threshold for context_feature (positive = above threshold triggers) |
| `value_threshold` | float | - | `0.0` | Threshold for value_feature (positive = above threshold triggers) |
| `filter_threshold` | float | - | `0.0` | Threshold for filter_feature (only used when filter_mode=THRESHOLD) |
| `context_feature_name` | string | - | `""` | Placeholder for binding layer - actual feature name injected |
| `value_feature_name` | string | - | `""` | Placeholder for binding layer - actual feature name injected |
| `filter_feature_name` | string | - | `""` | Placeholder for binding layer - actual feature name injected (optional) |

### Validation Rules
1. If `filter_mode` = "NONE", `filter_feature_name` may be empty and `filter_threshold` is ignored.
2. If `trigger_mode` = "NONE", `entry_mode` must be "MARKET_NEXT_OPEN".
3. If `trigger_mode` = "STOP" or "CROSS", threshold parameters are used to determine trigger conditions.
4. All threshold parameters support both positive (above threshold) and negative (below threshold) logic based on sign.

### JSON Schema Representation
```json
{
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
      "description": "Threshold for value_feature"
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
    "filter_feature_name"
  ]
}
```

## S3 (Extreme Reversion) Parameter Schema

### Core Parameters
| Parameter | Type | Enum Values | Default | Description |
|-----------|------|-------------|---------|-------------|
| `filter_mode` | string | `["NONE", "THRESHOLD"]` | `"NONE"` | Filter application mode |
| `trigger_mode` | string | `["NONE", "STOP", "CROSS"]` | `"NONE"` | Trigger generation mode |
| `entry_mode` | string | `["MARKET_NEXT_OPEN"]` | `"MARKET_NEXT_OPEN"` | Entry execution mode (only valid when trigger_mode=NONE) |
| `compare_mode` | string | `["A_ONLY", "DIFF", "RATIO"]` | `"A_ONLY"` | Signal computation mode |
| `signal_threshold` | float | - | `0.0` | Threshold for computed signal |
| `filter_threshold` | float | - | `0.0` | Threshold for filter_feature (only used when filter_mode=THRESHOLD) |
| `A_feature_name` | string | - | `""` | Placeholder for binding layer - actual A feature name |
| `B_feature_name` | string | - | `""` | Placeholder for binding layer - actual B feature name (optional) |
| `filter_feature_name` | string | - | `""` | Placeholder for binding layer - actual filter feature name (optional) |

### Validation Rules
1. If `filter_mode` = "NONE", `filter_feature_name` may be empty and `filter_threshold` is ignored.
2. If `trigger_mode` = "NONE", `entry_mode` must be "MARKET_NEXT_OPEN".
3. If `compare_mode` != "A_ONLY", `B_feature_name` must be provided (non-empty).
4. For `compare_mode` = "RATIO", safe division must be implemented (denominator protection).
5. All threshold parameters support both positive and negative logic based on sign.

### JSON Schema Representation
```json
{
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
    "compare_mode": {
      "type": "string",
      "enum": ["A_ONLY", "DIFF", "RATIO"],
      "default": "A_ONLY",
      "description": "Signal computation mode"
    },
    "signal_threshold": {
      "type": "number",
      "default": 0.0,
      "description": "Threshold for computed signal"
    },
    "filter_threshold": {
      "type": "number",
      "default": 0.0,
      "description": "Threshold for filter_feature (only used when filter_mode=THRESHOLD)"
    },
    "A_feature_name": {
      "type": "string",
      "default": "",
      "description": "Placeholder for binding layer - actual A feature name"
    },
    "B_feature_name": {
      "type": "string",
      "default": "",
      "description": "Placeholder for binding layer - actual B feature name (optional)"
    },
    "filter_feature_name": {
      "type": "string",
      "default": "",
      "description": "Placeholder for binding layer - actual filter feature name (optional)"
    }
  },
  "required": [
    "filter_mode",
    "trigger_mode",
    "entry_mode",
    "compare_mode",
    "signal_threshold",
    "filter_threshold",
    "A_feature_name",
    "B_feature_name",
    "filter_feature_name"
  ]
}
```

## Default Values

### S2 Defaults
```python
{
    "filter_mode": "NONE",
    "trigger_mode": "NONE",
    "entry_mode": "MARKET_NEXT_OPEN",
    "context_threshold": 0.0,
    "value_threshold": 0.0,
    "filter_threshold": 0.0,
    "context_feature_name": "",
    "value_feature_name": "",
    "filter_feature_name": ""
}
```

### S3 Defaults
```python
{
    "filter_mode": "NONE",
    "trigger_mode": "NONE",
    "entry_mode": "MARKET_NEXT_OPEN",
    "compare_mode": "A_ONLY",
    "signal_threshold": 0.0,
    "filter_threshold": 0.0,
    "A_feature_name": "",
    "B_feature_name": "",
    "filter_feature_name": ""
}
```

## Implementation Notes

1. **Feature Name Parameters**: The `*_feature_name` parameters are placeholders that will be populated by the binding layer before strategy execution. The strategy function should use these names to look up features from the context.

2. **Threshold Semantics**: 
   - Positive threshold: feature > threshold triggers
   - Negative threshold: feature < threshold triggers
   - Zero threshold: feature != 0 triggers

3. **Mode Combinations**:
   - `filter_mode=NONE`: Skip filter gate entirely
   - `trigger_mode=NONE`: Use `entry_mode=MARKET_NEXT_OPEN` for immediate entry
   - `trigger_mode=STOP`: Place stop order at threshold level
   - `trigger_mode=CROSS`: Fire once when threshold is crossed

4. **Binding Layer Responsibility**: The binding layer must validate that required features exist when modes require them (e.g., B_feature when compare_mode=DIFF or RATIO).

5. **Backward Compatibility**: The schemas follow existing `param_schema` patterns used by S1 and other builtin strategies.