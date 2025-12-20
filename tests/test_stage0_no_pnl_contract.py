"""Test Stage0 contract: must NOT contain any PnL/metrics fields.

Stage0 is a proxy ranking stage and must not compute any PnL-related metrics.
This test enforces the contract by checking that Stage0Result does not contain
forbidden PnL/metrics fields.
"""

import inspect
import numpy as np

from FishBroWFS_V2.pipeline.stage0_runner import Stage0Result, run_stage0


# Blacklist of forbidden field names (PnL/metrics related)
FORBIDDEN_FIELD_NAMES = {
    "net",
    "profit",
    "mdd",
    "dd",
    "drawdown",
    "sqn",
    "sharpe",
    "winrate",
    "win_rate",
    "equity",
    "pnl",
    "return",
    "returns",
    "trades",
    "trade",
    "final",
    "score",
    "metric",
    "metrics",
}


def test_stage0_result_no_pnl_fields():
    """Test that Stage0Result dataclass does not contain forbidden PnL fields."""
    # Get all field names from Stage0Result
    if hasattr(Stage0Result, "__dataclass_fields__"):
        field_names = set(Stage0Result.__dataclass_fields__.keys())
    else:
        # Fallback: inspect annotations
        annotations = getattr(Stage0Result, "__annotations__", {})
        field_names = set(annotations.keys())
    
    # Check each field name against blacklist
    violations = []
    for field_name in field_names:
        field_lower = field_name.lower()
        for forbidden in FORBIDDEN_FIELD_NAMES:
            if forbidden in field_lower:
                violations.append(field_name)
                break
    
    assert len(violations) == 0, (
        f"Stage0Result contains forbidden PnL/metrics fields: {violations}\n"
        f"Allowed fields: {field_names}\n"
        f"Forbidden keywords: {FORBIDDEN_FIELD_NAMES}"
    )


def test_stage0_result_allowed_fields_only():
    """Test that Stage0Result only contains allowed fields."""
    # Allowed fields (from spec)
    allowed_fields = {"param_id", "proxy_value", "warmup_ok", "meta"}
    
    if hasattr(Stage0Result, "__dataclass_fields__"):
        actual_fields = set(Stage0Result.__dataclass_fields__.keys())
    else:
        annotations = getattr(Stage0Result, "__annotations__", {})
        actual_fields = set(annotations.keys())
    
    # Check that all fields are in allowed set
    unexpected = actual_fields - allowed_fields
    assert len(unexpected) == 0, (
        f"Stage0Result contains unexpected fields: {unexpected}\n"
        f"Allowed fields: {allowed_fields}\n"
        f"Actual fields: {actual_fields}"
    )


def test_stage0_runner_no_pnl_computation():
    """Test that run_stage0() does not compute PnL metrics."""
    # Generate test data
    np.random.seed(42)
    n_bars = 1000
    n_params = 50
    
    close = 10000 + np.cumsum(np.random.randn(n_bars)) * 10
    params_matrix = np.column_stack([
        np.random.randint(10, 100, size=n_params),
        np.random.randint(5, 50, size=n_params),
        np.random.uniform(1.0, 5.0, size=n_params),
    ]).astype(np.float64)
    
    # Run Stage0
    results = run_stage0(close, params_matrix)
    
    # Verify results structure
    assert len(results) == n_params
    
    for result in results:
        # Verify required fields exist
        assert hasattr(result, "param_id")
        assert hasattr(result, "proxy_value")
        
        # Verify param_id is valid
        assert isinstance(result.param_id, int)
        assert 0 <= result.param_id < n_params
        
        # Verify proxy_value is numeric (can be -inf for invalid params)
        assert isinstance(result.proxy_value, (int, float))
        
        # Verify no PnL fields exist (check attribute names)
        result_dict = result.__dict__ if hasattr(result, "__dict__") else {}
        for field_name in result_dict.keys():
            field_lower = field_name.lower()
            for forbidden in FORBIDDEN_FIELD_NAMES:
                assert forbidden not in field_lower, (
                    f"Stage0Result contains forbidden field: {field_name} "
                    f"(contains '{forbidden}')"
                )


def test_stage0_result_string_representation():
    """Test that Stage0Result string representation does not contain PnL keywords."""
    result = Stage0Result(
        param_id=0,
        proxy_value=10.5,
        warmup_ok=True,
        meta=None,
    )
    
    # Convert to string representation
    result_str = str(result).lower()
    result_repr = repr(result).lower()
    
    # Check that string representations don't contain forbidden keywords
    for forbidden in FORBIDDEN_FIELD_NAMES:
        assert forbidden not in result_str, (
            f"Stage0Result string representation contains forbidden keyword '{forbidden}': {result_str}"
        )
        assert forbidden not in result_repr, (
            f"Stage0Result repr contains forbidden keyword '{forbidden}': {result_repr}"
        )
