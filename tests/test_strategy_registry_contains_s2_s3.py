"""Test that the default strategy registry contains S2 and S3."""

from __future__ import annotations

import pytest
from strategy.registry import load_builtin_strategies


def test_default_strategy_registry_contains_s2():
    """Ensure S2 is registered in the default strategy registry."""
    # Load builtin strategies (idempotent)
    load_builtin_strategies()
    
    # Get the default registry (global module-level registry)
    from strategy.registry import get, list_strategies
    
    # Verify S2 exists
    spec = get("S2")
    assert spec.strategy_id == "S2"
    assert spec.version == "v1"
    
    # Verify via list
    strategies = list_strategies()
    strategy_ids = [s.strategy_id for s in strategies]
    assert "S2" in strategy_ids


def test_default_strategy_registry_contains_s3():
    """Ensure S3 is registered in the default strategy registry."""
    # Load builtin strategies (idempotent)
    load_builtin_strategies()
    
    from strategy.registry import get, list_strategies
    
    # Verify S3 exists
    spec = get("S3")
    assert spec.strategy_id == "S3"
    assert spec.version == "v1"
    
    # Verify via list
    strategies = list_strategies()
    strategy_ids = [s.strategy_id for s in strategies]
    assert "S3" in strategy_ids


def test_s2_feature_requirements():
    """Ensure S2 provides feature requirements."""
    from strategy.registry import get, load_builtin_strategies
    load_builtin_strategies()
    
    spec = get("S2")
    
    # S2 has a module-level feature_requirements function
    # We can import it directly
    from strategy.builtin.s2_v1 import feature_requirements
    req = feature_requirements()
    
    from contracts.strategy_features import StrategyFeatureRequirements
    assert isinstance(req, StrategyFeatureRequirements)
    assert req.strategy_id == "S2"
    # Should have at least context_feature and value_feature
    assert len(req.required) >= 2
    # Should have optional filter_feature
    assert len(req.optional) >= 1


def test_s3_feature_requirements():
    """Ensure S3 provides feature requirements."""
    from strategy.registry import get, load_builtin_strategies
    load_builtin_strategies()
    
    spec = get("S3")
    
    # S3 has a module-level feature_requirements function
    from strategy.builtin.s3_v1 import feature_requirements
    req = feature_requirements()
    
    from contracts.strategy_features import StrategyFeatureRequirements
    assert isinstance(req, StrategyFeatureRequirements)
    assert req.strategy_id == "S3"
    # Should have at least context_feature and value_feature
    assert len(req.required) >= 2
    # Should have optional filter_feature
    assert len(req.optional) >= 1


def test_s2_parameter_schema():
    """Verify S2 parameter schema has all required fields."""
    from strategy.registry import get, load_builtin_strategies
    load_builtin_strategies()
    
    spec = get("S2")
    schema = spec.param_schema
    
    # Check required properties
    assert "properties" in schema
    props = schema["properties"]
    
    # Required parameter fields
    required_params = [
        "filter_mode", "trigger_mode", "entry_mode",
        "context_threshold", "value_threshold", "filter_threshold",
        "context_feature_name", "value_feature_name", "filter_feature_name",
        "order_qty"
    ]
    
    for param in required_params:
        assert param in props, f"Missing parameter {param} in S2 schema"
    
    # Check enum values
    assert props["filter_mode"]["enum"] == ["NONE", "THRESHOLD"]
    assert props["trigger_mode"]["enum"] == ["NONE", "STOP", "CROSS"]
    assert props["entry_mode"]["enum"] == ["MARKET_NEXT_OPEN"]
    
    # Check defaults
    defaults = spec.defaults
    assert defaults["filter_mode"] == "NONE"
    assert defaults["trigger_mode"] == "NONE"
    assert defaults["entry_mode"] == "MARKET_NEXT_OPEN"
    assert defaults["order_qty"] == 1.0


def test_s3_parameter_schema():
    """Verify S3 parameter schema has all required fields."""
    from strategy.registry import get, load_builtin_strategies
    load_builtin_strategies()
    
    spec = get("S3")
    schema = spec.param_schema
    
    # Check required properties
    assert "properties" in schema
    props = schema["properties"]
    
    # Required parameter fields
    required_params = [
        "filter_mode", "trigger_mode", "entry_mode",
        "context_threshold", "value_threshold", "filter_threshold",
        "context_feature_name", "value_feature_name", "filter_feature_name",
        "order_qty"
    ]
    
    for param in required_params:
        assert param in props, f"Missing parameter {param} in S3 schema"
    
    # Check enum values
    assert props["filter_mode"]["enum"] == ["NONE", "THRESHOLD"]
    assert props["trigger_mode"]["enum"] == ["NONE", "STOP", "CROSS"]
    assert props["entry_mode"]["enum"] == ["MARKET_NEXT_OPEN"]
    
    # Check defaults
    defaults = spec.defaults
    assert defaults["filter_mode"] == "NONE"
    assert defaults["trigger_mode"] == "NONE"
    assert defaults["entry_mode"] == "MARKET_NEXT_OPEN"
    assert defaults["order_qty"] == 1.0


def test_registry_deterministic():
    """Ensure registry loading is deterministic (same order each time)."""
    from strategy.registry import clear, load_builtin_strategies, list_strategies
    
    # Clear and load twice
    clear()
    load_builtin_strategies()
    first = [s.strategy_id for s in list_strategies()]
    
    clear()
    load_builtin_strategies()
    second = [s.strategy_id for s in list_strategies()]
    
    assert first == second, "Registry loading is not deterministic"
    assert "S2" in first
    assert "S3" in first


if __name__ == "__main__":
    pytest.main([__file__, "-v"])