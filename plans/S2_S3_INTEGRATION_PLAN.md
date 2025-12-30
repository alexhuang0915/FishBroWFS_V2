# S2/S3 Integration Plan with Existing Registry

## Overview
This document outlines the integration plan for S2 and S3 strategies with the existing FishBroWFS_V2 strategy registry, following established patterns and ensuring backward compatibility.

## File Structure

### 1. Strategy Implementation Files
```
src/strategy/builtin/
├── s2_v1.py          # S2 (Pullback Continuation) implementation
├── s3_v1.py          # S3 (Extreme Reversion) implementation
└── __init__.py       # Updated to export new strategies
```

### 2. Configuration Files
```
configs/strategies/
├── S2/
│   └── features.json    # S2 feature requirements (JSON fallback)
└── S3/
    └── features.json    # S3 feature requirements (JSON fallback)
```

### 3. Test Files
```
tests/
├── test_s2_v1.py        # S2 unit tests
├── test_s3_v1.py        # S3 unit tests
└── test_strategy_registry_contains_s2_s3.py  # Integration tests
```

## Implementation Details

### 1. S2 Implementation File (`src/strategy/builtin/s2_v1.py`)

```python
"""S2 (Pullback Continuation) Strategy v1.

Phase X: Mode-based pullback continuation strategy with configurable gates.
"""

from __future__ import annotations

from typing import Dict, Any, Mapping
import numpy as np

from engine.types import OrderIntent, OrderRole, OrderKind, Side
from engine.order_id import generate_order_id
from engine.constants import ROLE_ENTRY, KIND_STOP, SIDE_BUY
from strategy.spec import StrategySpec, StrategyFn
from contracts.strategy_features import StrategyFeatureRequirements, FeatureRef


def s2_strategy(context: Mapping[str, Any], params: Mapping[str, float]) -> Dict[str, Any]:
    """S2 (Pullback Continuation) strategy implementation."""
    # Implementation as defined in S2_S3_STRATEGY_FUNCTION_DESIGN.md
    # ... (full implementation)


def feature_requirements() -> StrategyFeatureRequirements:
    """Return the feature requirements for S2 strategy."""
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


# Strategy specification
SPEC = StrategySpec(
    strategy_id="S2",
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
            "filter_mode", "trigger_mode", "entry_mode",
            "context_threshold", "value_threshold", "filter_threshold",
            "context_feature_name", "value_feature_name", "filter_feature_name"
        ],
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
        "filter_feature_name": ""
    },
    fn=s2_strategy,
)
```

### 2. S3 Implementation File (`src/strategy/builtin/s3_v1.py`)

```python
"""S3 (Extreme Reversion) Strategy v1.

Phase X: Mode-based extreme reversion strategy with configurable signal computation.
"""

from __future__ import annotations

from typing import Dict, Any, Mapping
import numpy as np

from engine.types import OrderIntent, OrderRole, OrderKind, Side
from engine.order_id import generate_order_id
from engine.constants import ROLE_ENTRY, KIND_STOP, SIDE_BUY
from strategy.spec import StrategySpec, StrategyFn
from contracts.strategy_features import StrategyFeatureRequirements, FeatureRef


def s3_strategy(context: Mapping[str, Any], params: Mapping[str, float]) -> Dict[str, Any]:
    """S3 (Extreme Reversion) strategy implementation."""
    # Implementation as defined in S2_S3_STRATEGY_FUNCTION_DESIGN.md
    # ... (full implementation)


def feature_requirements() -> StrategyFeatureRequirements:
    """Return the feature requirements for S3 strategy."""
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
            "filter_mode", "trigger_mode", "entry_mode", "compare_mode",
            "signal_threshold", "filter_threshold",
            "A_feature_name", "B_feature_name", "filter_feature_name"
        ],
    },
    defaults={
        "filter_mode": "NONE",
        "trigger_mode": "NONE",
        "entry_mode": "MARKET_NEXT_OPEN",
        "compare_mode": "A_ONLY",
        "signal_threshold": 0.0,
        "filter_threshold": 0.0,
        "A_feature_name": "",
        "B_feature_name": "",
        "filter_feature_name": ""
    },
    fn=s3_strategy,
)
```

### 3. Update `src/strategy/builtin/__init__.py`

```python
"""Built-in strategies package."""

from strategy.builtin import (
    sma_cross_v1,
    breakout_channel_v1,
    mean_revert_zscore_v1,
    rsi_reversal_v1,
    bollinger_breakout_v1,
    atr_trailing_stop_v1,
    s1_v1,
    s2_v1,      # New
    s3_v1,      # New
)

__all__ = [
    "sma_cross_v1",
    "breakout_channel_v1",
    "mean_revert_zscore_v1",
    "rsi_reversal_v1",
    "bollinger_breakout_v1",
    "atr_trailing_stop_v1",
    "s1_v1",
    "s2_v1",    # New
    "s3_v1",    # New
]
```

### 4. Update `src/strategy/registry.py` - `load_builtin_strategies()`

```python
def load_builtin_strategies() -> None:
    """Load built-in strategies (explicit, no import side effects)."""
    from strategy.builtin import (
        sma_cross_v1,
        breakout_channel_v1,
        mean_revert_zscore_v1,
        rsi_reversal_v1,
        bollinger_breakout_v1,
        atr_trailing_stop_v1,
        s1_v1,
        s2_v1,      # New import
        s3_v1,      # New import
    )
    
    # Register built-in strategies
    register(sma_cross_v1.SPEC)
    register(breakout_channel_v1.SPEC)
    register(mean_revert_zscore_v1.SPEC)
    register(rsi_reversal_v1.SPEC)
    register(bollinger_breakout_v1.SPEC)
    register(atr_trailing_stop_v1.SPEC)
    register(s1_v1.SPEC)
    register(s2_v1.SPEC)    # New registration
    register(s3_v1.SPEC)    # New registration
```

## Configuration Files

### 1. S2 Feature Requirements JSON (`configs/strategies/S2/features.json`)

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

### 2. S3 Feature Requirements JSON (`configs/strategies/S3/features.json`)

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

## Registration Process

### 1. Content-Addressed Identity
- Both S2 and S3 will automatically get content-addressed IDs via `StrategySpec.__post_init__`
- The `compute_strategy_id_from_function` will hash the function source code
- This ensures immutable identity as required by Phase 13

### 2. Registry Integration
- Strategies are registered via `load_builtin_strategies()` call
- Registration is idempotent (duplicate content IDs are ignored)
- Strategies appear in `list_strategies()` and GUI registry

### 3. Feature Requirements Resolution
- Research runner will first try `feature_requirements()` method
- Falls back to JSON file if method not available
- Feature resolver validates requirements against available features

## Testing Integration

### 1. Unit Tests
```python
# tests/test_s2_v1.py
def test_s2_registration():
    from strategy.registry import load_builtin_strategies, get
    load_builtin_strategies()
    spec = get("S2")
    assert spec.strategy_id == "S2"
    assert spec.version == "v1"
    assert "filter_mode" in spec.param_schema.get("properties", {})

def test_s2_feature_requirements():
    from strategy.builtin.s2_v1 import feature_requirements
    req = feature_requirements()
    assert req.strategy_id == "S2"
    assert len(req.required) == 2
    assert len(req.optional) == 1
```

### 2. Integration Tests
```python
# tests/test_strategy_registry_contains_s2_s3.py
def test_registry_contains_s2_s3():
    from strategy.registry import load_builtin_strategies, list_strategies
    load_builtin_strategies()
    strategies = list_strategies()
    strategy_ids = [s.strategy_id for s in strategies]
    assert "S2" in strategy_ids
    assert "S3" in strategy_ids
```

### 3. Research Runner Tests
```python
def test_s2_research_run_without_build():
    # Test that S2 can be resolved with allow_build=False
    # Similar to existing S1 test pattern
    pass
```

## Compatibility Considerations

### 1. Backward Compatibility
- No changes to existing strategy interfaces
- Existing strategies (S1, sma_cross, etc.) remain unchanged
- Registry API remains the same

### 2. Forward Compatibility
- New mode parameters follow existing param_schema patterns
- Feature requirements use existing `StrategyFeatureRequirements` model
- Binding layer can evolve independently

### 3. System Constraints
- Must work with existing research runner and `allow_build=False` contract
- Must support content-addressed identity (Phase 13)
- Must be compatible with GUI parameter introspection (Phase 12)

## Deployment Steps

### Phase 1: Implementation
1. Create `s2_v1.py` and `s3_v1.py` in `src/strategy/builtin/`
2. Update `__init__.py` and `registry.py`
3. Create configuration JSON files

### Phase 2: Testing
1. Write unit tests for both strategies
2. Write integration tests for registry inclusion
3. Test with research runner `allow_build=False`

### Phase 3: Validation
1. Verify content-addressed identity generation
2. Test all mode combinations
3. Validate feature binding works correctly

### Phase 4: Documentation
1. Update strategy catalog documentation
2. Create usage examples
3. Document mode semantics and parameter combinations

## Risk Mitigation

### 1. Feature Binding Complexity
- **Risk**: Binding layer may not properly map generic feature names
- **Mitigation**: Provide clear documentation and validation in binding layer

### 2. Mode Combination Validation
- **Risk**: Invalid mode combinations could cause runtime errors
- **Mitigation**: Implement parameter validation in strategy function

### 3. Performance Impact
- **Risk**: Additional mode logic could impact performance
- **Mitigation**: Use efficient numpy operations and early exits

### 4. Backward Compatibility
- **Risk**: Changes to registry could break existing code
- **Mitigation**: Follow existing patterns exactly, no API changes