# S2/S3 Testing Strategy

## Overview
This document defines the testing strategy for S2 and S3 strategies, with particular focus on NONE mode support, mode combinations, and integration with the existing testing framework.

## Testing Objectives

### Primary Objectives
1. **Verify NONE mode functionality** for both filter_mode and trigger_mode
2. **Validate mode combinations** produce correct behavior
3. **Ensure research runner compatibility** with `allow_build=False`
4. **Confirm feature-agnostic design** works with binding layer
5. **Test error handling** for missing features and invalid configurations

### Secondary Objectives
1. **Performance testing** of mode logic
2. **Edge case testing** for threshold boundaries
3. **Integration testing** with existing registry and GUI
4. **Regression testing** against existing strategy patterns

## Test Categories

### 1. Unit Tests
- **Location**: `tests/test_s2_v1.py`, `tests/test_s3_v1.py`
- **Focus**: Individual strategy functions, parameter validation, mode logic
- **Tools**: pytest, unittest.mock

### 2. Integration Tests
- **Location**: `tests/test_strategy_registry_contains_s2_s3.py`
- **Focus**: Registry integration, research runner compatibility
- **Tools**: pytest with temporary directories

### 3. Mode Combination Tests
- **Location**: `tests/test_s2_modes.py`, `tests/test_s3_modes.py`
- **Focus**: Exhaustive testing of mode combinations
- **Tools**: pytest parameterization

### 4. Contract Compliance Tests
- **Location**: `tests/test_s2s3_contract.py`
- **Focus**: Compliance with S2S3_CONTRACT.md specifications
- **Tools**: pytest with contract validation

## Test Design for NONE Modes

### 1. filter_mode=NONE Tests

#### S2 filter_mode=NONE
```python
def test_s2_filter_mode_none_skips_filter():
    """Test that filter_mode=NONE skips filter gate entirely."""
    # Setup: Create context with features
    # Set filter_mode=NONE, filter_feature missing
    # Should still generate signal if context/value gates pass
    # Assert: No error, filter_gate=True in debug
```

#### S3 filter_mode=NONE
```python
def test_s3_filter_mode_none_skips_filter():
    """Test that filter_mode=NONE skips filter gate entirely."""
    # Setup: Create context with A_feature only
    # Set filter_mode=NONE, filter_feature missing
    # Should still generate signal if signal gate passes
    # Assert: No error, filter_gate=True in debug
```

### 2. trigger_mode=NONE Tests

#### S2 trigger_mode=NONE with entry_mode=MARKET_NEXT_OPEN
```python
def test_s2_trigger_mode_none_generates_market_next_open():
    """Test that trigger_mode=NONE generates MARKET_NEXT_OPEN order."""
    # Setup: All gates pass, trigger_mode=NONE
    # Should generate STOP order (proxy for MARKET_NEXT_OPEN)
    # Assert: One OrderIntent with kind=STOP
```

#### S3 trigger_mode=NONE with entry_mode=MARKET_NEXT_OPEN
```python
def test_s3_trigger_mode_none_generates_market_next_open():
    """Test that trigger_mode=NONE generates MARKET_NEXT_OPEN order."""
    # Setup: Signal passes, trigger_mode=NONE
    # Should generate STOP order
    # Assert: One OrderIntent with kind=STOP
```

### 3. Combined NONE Mode Tests

#### S2 filter_mode=NONE + trigger_mode=NONE
```python
def test_s2_both_none_modes():
    """Test S2 with both filter_mode=NONE and trigger_mode=NONE."""
    # Setup: No filter_feature, trigger_mode=NONE
    # Should work without filter_feature
    # Should generate MARKET_NEXT_OPEN order
    # Assert: Successful execution
```

#### S3 filter_mode=NONE + trigger_mode=NONE + compare_mode=A_ONLY
```python
def test_s3_minimal_configuration():
    """Test S3 with minimal configuration (all NONE modes, A_ONLY)."""
    # Setup: Only A_feature provided
    # Should work with minimal feature set
    # Assert: Successful execution
```

## Test Data Design

### 1. Mock Feature Arrays
```python
def create_mock_features():
    """Create mock feature arrays for testing."""
    return {
        "trend_strength": np.array([0.1, 0.6, 0.7, 0.8]),  # context_feature
        "retracement_pct": np.array([-0.3, -0.2, -0.1, 0.0]),  # value_feature
        "volatility": np.array([0.05, 0.06, 0.07, 0.08]),  # filter_feature
        "price": np.array([100.0, 101.0, 102.0, 103.0]),  # A_feature
        "sma_20": np.array([99.0, 100.0, 101.0, 102.0]),  # B_feature
        "close": np.array([100.0, 101.0, 102.0, 103.0]),  # For MARKET_NEXT_OPEN proxy
    }
```

### 2. Parameter Sets for Mode Combinations

#### S2 Parameter Matrix
```python
S2_PARAM_MATRIX = [
    # (filter_mode, trigger_mode, context_threshold, value_threshold, expected_behavior)
    ("NONE", "NONE", 0.5, -0.2, "MARKET_NEXT_OPEN"),
    ("NONE", "STOP", 0.5, -0.2, "STOP_ORDER"),
    ("NONE", "CROSS", 0.5, -0.2, "CROSS_TRIGGER"),
    ("THRESHOLD", "NONE", 0.5, -0.2, "MARKET_NEXT_OPEN_WITH_FILTER"),
    ("THRESHOLD", "STOP", 0.5, -0.2, "STOP_WITH_FILTER"),
    ("THRESHOLD", "CROSS", 0.5, -0.2, "CROSS_WITH_FILTER"),
]
```

#### S3 Parameter Matrix
```python
S3_PARAM_MATRIX = [
    # (filter_mode, trigger_mode, compare_mode, signal_threshold, expected_behavior)
    ("NONE", "NONE", "A_ONLY", 1.0, "MARKET_NEXT_OPEN"),
    ("NONE", "STOP", "DIFF", 0.5, "STOP_ORDER"),
    ("NONE", "CROSS", "RATIO", 2.0, "CROSS_TRIGGER"),
    ("THRESHOLD", "NONE", "A_ONLY", 1.0, "MARKET_NEXT_OPEN_WITH_FILTER"),
    ("THRESHOLD", "STOP", "DIFF", 0.5, "STOP_WITH_FILTER"),
    ("THRESHOLD", "CROSS", "RATIO", 2.0, "CROSS_WITH_FILTER"),
]
```

## Test Implementation Patterns

### 1. Parameterized Tests
```python
import pytest

@pytest.mark.parametrize("filter_mode,trigger_mode,compare_mode", [
    ("NONE", "NONE", "A_ONLY"),
    ("NONE", "STOP", "DIFF"),
    ("THRESHOLD", "CROSS", "RATIO"),
])
def test_s3_mode_combinations(filter_mode, trigger_mode, compare_mode):
    """Test various mode combinations for S3."""
    # Test implementation
    pass
```

### 2. Fixture-Based Test Setup
```python
import pytest
import numpy as np

@pytest.fixture
def mock_context():
    """Create mock execution context."""
    return {
        "features": create_mock_features(),
        "bar_index": 2,
        "order_qty": 1,
    }

@pytest.fixture
def s2_base_params():
    """Base parameters for S2 tests."""
    return {
        "context_feature_name": "trend_strength",
        "value_feature_name": "retracement_pct",
        "filter_feature_name": "volatility",
        "context_threshold": 0.5,
        "value_threshold": -0.2,
        "filter_threshold": 0.06,
    }
```

### 3. Contract Validation Tests
```python
def test_s2_contract_compliance():
    """Test S2 compliance with contract specifications."""
    # Load contract from S2S3_CONTRACT.md
    # Validate parameter schema matches contract
    # Validate feature requirements match contract
    # Validate mode semantics match contract
    pass
```

## Specific Test Cases for NONE Mode Support

### Test Case 1: Missing Optional Features with NONE Modes
```python
def test_s2_missing_filter_feature_with_filter_mode_none():
    """S2 should work without filter_feature when filter_mode=NONE."""
    context = {
        "features": {
            "trend_strength": np.array([0.6]),
            "retracement_pct": np.array([-0.3]),
            # No filter_feature
        },
        "bar_index": 0,
    }
    params = {
        "filter_mode": "NONE",
        "trigger_mode": "NONE",
        "context_feature_name": "trend_strength",
        "value_feature_name": "retracement_pct",
        "filter_feature_name": "",  # Empty string
        "context_threshold": 0.5,
        "value_threshold": -0.2,
    }
    
    result = s2_strategy(context, params)
    assert "intents" in result
    # Should not raise error about missing filter_feature
```

### Test Case 2: NONE Mode with Threshold Zero
```python
def test_s2_none_mode_with_zero_threshold():
    """Test NONE modes with zero thresholds (feature != 0 logic)."""
    context = {
        "features": {
            "trend_strength": np.array([0.1]),  # Non-zero
            "retracement_pct": np.array([0.05]),  # Non-zero
        },
        "bar_index": 0,
    }
    params = {
        "filter_mode": "NONE",
        "trigger_mode": "NONE",
        "context_threshold": 0.0,  # Zero threshold
        "value_threshold": 0.0,   # Zero threshold
        # ... other params
    }
    
    result = s2_strategy(context, params)
    # Should trigger because features are non-zero
    assert len(result["intents"]) > 0
```

### Test Case 3: S3 RATIO Mode with Zero Denominator
```python
def test_s3_ratio_mode_zero_denominator():
    """Test RATIO mode handles zero denominator safely."""
    context = {
        "features": {
            "price": np.array([100.0]),
            "sma_20": np.array([0.0]),  # Zero denominator
        },
        "bar_index": 0,
    }
    params = {
        "compare_mode": "RATIO",
        "A_feature_name": "price",
        "B_feature_name": "sma_20",
        "signal_threshold": 1.0,
        # ... other params
    }
    
    result = s3_strategy(context, params)
    # Should handle zero denominator gracefully
    assert "intents" in result
    # debug should show safe division result (probably 0.0)
```

## Integration Testing Strategy

### 1. Registry Integration Tests
```python
def test_s2_registration_and_identity():
    """Test S2 registration and content-addressed identity."""
    from strategy.registry import load_builtin_strategies, get
    
    load_builtin_strategies()
    spec = get("S2")
    
    assert spec.strategy_id == "S2"
    assert spec.version == "v1"
    assert spec.immutable_id  # Should have content-addressed ID
    assert len(spec.immutable_id) == 64  # 64-char hex
```

### 2. Research Runner Compatibility Tests
```python
def test_s2_research_run_without_build():
    """Test S2 research run with allow_build=False."""
    # Similar to existing test_strategy_registry_contains_s1.py
    # Create temporary feature cache
    # Call run_research with allow_build=False
    # Should succeed without building
```

### 3. GUI Parameter Introspection Tests
```python
def test_s2_gui_parameter_introspection():
    """Test S2 parameters are GUI-introspectable."""
    from strategy.registry import get_strategy_registry
    
    load_builtin_strategies()
    registry_response = get_strategy_registry()
    
    s2_spec = next(s for s in registry_response.strategies if s.strategy_id == "S2")
    assert len(s2_spec.params) > 0
    # Check enum parameters have choices
    filter_mode_param = next(p for p in s2_spec.params if p.name == "filter_mode")
    assert filter_mode_param.choices == ["NONE", "THRESHOLD"]
```

## Test Coverage Goals

### Required Coverage
- **100% mode combination coverage**: All filter_mode × trigger_mode × compare_mode combinations
- **100% NONE mode coverage**: All NONE mode scenarios
- **90%+ line coverage**: Overall strategy function code
- **100% error path coverage**: All error handling paths

### Coverage Measurement
```bash
# Run tests with coverage
pytest tests/test_s2_v1.py tests/test_s3_v1.py --cov=src.strategy.builtin.s2_v1,src.strategy.builtin.s3_v1 --cov-report=html
```

## Test Execution Strategy

### 1. Local Development
- Run unit tests during development
- Use pytest with verbose output
- Focus on specific test categories as needed

### 2. Continuous Integration
- Run all tests on PR
- Enforce coverage thresholds
- Run integration tests with temporary directories

### 3. Pre-release Validation
- Run exhaustive mode combination tests
- Validate contract compliance
- Test with real feature data (if available)

## Test Data Management

### 1. Synthetic Test Data
- Use numpy arrays with controlled values
- Create edge cases (NaN, inf, zero, negative)
- Ensure reproducibility with fixed seeds

### 2. Real Data Sampling (Optional)
- Sample from existing feature caches
- Use small subsets for integration tests
- Ensure no dependency on specific datasets

### 3. Mock Objects
- Mock feature resolver for unit tests
- Mock binding layer for feature name mapping
- Mock research runner for integration tests

## Assertion Patterns

### 1. Order Intent Assertions
```python
def assert_order_intent(intent, expected_role, expected_kind, expected_side):
    assert intent.role == expected_role
    assert intent.kind == expected_kind
    assert intent.side == expected_side
    assert intent.price > 0  # Positive price
    assert intent.created_bar == bar_index
```

### 2. Debug Information Assertions
```python
def assert_debug_info(debug, expected_keys):
    for key in expected_keys:
        assert key in debug
    # Check specific debug values based on test scenario
    if "filter_gate" in debug:
        assert debug["filter_gate"] in [True, False, None]
```

### 3. Error Handling Assertions
```python
def test_error_handling():
    result = strategy_function(context, invalid_params)
    assert "intents" in result
    assert len(result["intents"]) == 0  # No orders on error
    assert "error" in result.get("debug", {})  # Error in debug info
```

## Test Maintenance Strategy

### 1. Test Organization
- Group tests by strategy (S2 vs S3)
- Group tests by test category (unit, integration, contract)
- Use descriptive test names that indicate mode combinations

### 2. Test Documentation
- Document test purpose in docstrings
- Include references to contract sections
- Note edge cases being tested

### 3. Test Updates
- Update tests when contract changes
- Add tests for new mode combinations
- Maintain backward compatibility for existing tests

## Conclusion
This testing strategy ensures comprehensive validation of S2 and S3 strategies, with particular emphasis on NONE mode support. By following this strategy, we can confidently deploy strategies that comply with the contract and work correctly in all mode combinations.