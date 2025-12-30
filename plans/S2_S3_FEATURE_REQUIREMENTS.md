# S2/S3 Feature Requirements Design

## Overview
This document defines the feature requirements specification for S2 (Pullback Continuation) and S3 (Extreme Reversion) strategies, following the existing pattern in FishBroWFS_V2.

## Design Principles

1. **Feature-Agnostic Declaration**: Strategies declare required feature categories (context, value, filter) rather than specific feature names, allowing binding layer flexibility.

2. **Optional Features**: Support optional features based on mode configuration (e.g., filter_feature when filter_mode=THRESHOLD, B_feature when compare_mode≠A_ONLY).

3. **Timeframe Consistency**: All features within a strategy should use the same timeframe (default 60 minutes) for alignment.

4. **Dual Provision Methods**: Support both Python method (`feature_requirements()`) and JSON file (`configs/strategies/{strategy_id}/features.json`) patterns.

## S2 (Pullback Continuation) Feature Requirements

### Required Features
| Feature Category | Required | Description | Notes |
|-----------------|----------|-------------|-------|
| `context_feature` | Yes | Trend context feature (e.g., trend strength, direction) | Must be float64 array |
| `value_feature` | Yes | Pullback depth/position feature (e.g., retracement percentage) | Must be float64 array |
| `filter_feature` | Conditional | Optional filter feature | Required only when filter_mode=THRESHOLD |

### Feature Requirements Specification

#### Python Method Implementation
```python
def feature_requirements() -> StrategyFeatureRequirements:
    return StrategyFeatureRequirements(
        strategy_id="S2",
        required=[
            FeatureRef(name="context_feature", timeframe_min=60),
            FeatureRef(name="value_feature", timeframe_min=60),
        ],
        optional=[
            FeatureRef(name="filter_feature", timeframe_min=60),
        ],
        min_schema_version="v1",
        notes="S2 (Pullback Continuation) - context_feature and value_feature are required; filter_feature is optional depending on filter_mode."
    )
```

#### JSON File Format (`configs/strategies/S2/features.json`)
```json
{
  "strategy_id": "S2",
  "required": [
    {
      "name": "context_feature",
      "timeframe_min": 60
    },
    {
      "name": "value_feature",
      "timeframe_min": 60
    }
  ],
  "optional": [
    {
      "name": "filter_feature",
      "timeframe_min": 60
    }
  ],
  "min_schema_version": "v1",
  "notes": "S2 (Pullback Continuation) - context_feature and value_feature are required; filter_feature is optional depending on filter_mode."
}
```

### Binding Layer Responsibilities
1. Map generic feature names (`context_feature`, `value_feature`, `filter_feature`) to actual feature names based on configuration.
2. Validate that required features exist in the feature cache.
3. Inject actual feature names into strategy parameters before execution.

## S3 (Extreme Reversion) Feature Requirements

### Required Features
| Feature Category | Required | Description | Notes |
|-----------------|----------|-------------|-------|
| `A_feature` | Yes | Primary feature for signal computation | Must be float64 array |
| `B_feature` | Conditional | Secondary feature for DIFF/RATIO modes | Required when compare_mode≠A_ONLY |
| `filter_feature` | Conditional | Optional filter feature | Required only when filter_mode=THRESHOLD |

### Feature Requirements Specification

#### Python Method Implementation
```python
def feature_requirements() -> StrategyFeatureRequirements:
    return StrategyFeatureRequirements(
        strategy_id="S3",
        required=[
            FeatureRef(name="A_feature", timeframe_min=60),
        ],
        optional=[
            FeatureRef(name="B_feature", timeframe_min=60),
            FeatureRef(name="filter_feature", timeframe_min=60),
        ],
        min_schema_version="v1",
        notes="S3 (Extreme Reversion) - A_feature is required; B_feature is optional depending on compare_mode; filter_feature is optional depending on filter_mode."
    )
```

#### JSON File Format (`configs/strategies/S3/features.json`)
```json
{
  "strategy_id": "S3",
  "required": [
    {
      "name": "A_feature",
      "timeframe_min": 60
    }
  ],
  "optional": [
    {
      "name": "B_feature",
      "timeframe_min": 60
    },
    {
      "name": "filter_feature",
      "timeframe_min": 60
    }
  ],
  "min_schema_version": "v1",
  "notes": "S3 (Extreme Reversion) - A_feature is required; B_feature is optional depending on compare_mode; filter_feature is optional depending on filter_mode."
}
```

## Common Implementation Patterns

### 1. Feature Resolution Flow
```
Research Runner → Strategy Feature Requirements → Feature Resolver
      ↓
  Validate required features exist
      ↓
  If allow_build=False and missing → Error
      ↓
  If allow_build=True → Build missing features
      ↓
  Return FeatureBundle with actual feature arrays
```

### 2. Binding Layer Integration
The binding layer must:
1. Read strategy parameters (including `*_feature_name` placeholders)
2. Map generic feature categories to actual feature names
3. Inject actual feature names into the execution context
4. Ensure feature arrays are available in the FeatureBundle

### 3. Mode-Dependent Validation
- **S2**: If `filter_mode=THRESHOLD`, validate `filter_feature` exists
- **S3**: If `compare_mode=DIFF` or `compare_mode=RATIO`, validate `B_feature` exists
- **Both**: If `filter_mode=THRESHOLD`, validate `filter_feature` exists

### 4. Timeframe Handling
- All features use 60-minute timeframe by default
- Binding layer must ensure consistent timeframe across all features
- Feature resolver will resample if necessary (when allow_build=True)

## Implementation Examples

### S2 Feature Requirements Class (Optional Enhancement)
For better type safety and validation, we could create dedicated classes:

```python
class S2FeatureRequirements:
    def __init__(
        self,
        context_feature: str,
        value_feature: str,
        filter_feature: Optional[str] = None
    ):
        self.context_feature = context_feature
        self.value_feature = value_feature
        self.filter_feature = filter_feature
    
    def to_strategy_requirements(self) -> StrategyFeatureRequirements:
        required = [
            FeatureRef(name=self.context_feature, timeframe_min=60),
            FeatureRef(name=self.value_feature, timeframe_min=60),
        ]
        optional = []
        if self.filter_feature:
            optional.append(FeatureRef(name=self.filter_feature, timeframe_min=60))
        
        return StrategyFeatureRequirements(
            strategy_id="S2",
            required=required,
            optional=optional,
            min_schema_version="v1",
            notes="S2 feature requirements"
        )
```

### Integration with Research Runner
The research runner will:
1. Load strategy spec from registry
2. Call `feature_requirements()` method if available
3. Fall back to JSON file if method not available
4. Pass requirements to feature resolver
5. Validate all required features are present

## Testing Considerations

1. **Unit Tests**: Verify feature requirements method returns correct structure
2. **Integration Tests**: Test research runner with `allow_build=False` contract
3. **Mode Validation Tests**: Test that missing optional features don't cause errors when modes don't require them
4. **Binding Tests**: Test feature name mapping and injection

## Backward Compatibility

1. Follows existing S1 pattern with `feature_requirements()` method
2. Compatible with existing feature resolver and research runner
3. Uses same `StrategyFeatureRequirements` and `FeatureRef` models
4. Supports both Python and JSON provision methods