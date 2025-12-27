
"""Tests for Strategy Registry (Phase 12)."""

from __future__ import annotations

from typing import Any, Dict

import pytest

from strategy.param_schema import ParamSpec
from strategy.registry import (
    StrategySpecForGUI,
    StrategyRegistryResponse,
    convert_to_gui_spec,
    get_strategy_registry,
    register,
    clear,
    load_builtin_strategies,
)
from strategy.spec import StrategySpec


def create_dummy_strategy_fn(context: Dict[str, Any], params: Dict[str, float]) -> Dict[str, Any]:
    """Dummy strategy function for testing."""
    return {"intents": [], "debug": {}}


def test_param_spec_schema() -> None:
    """Test ParamSpec schema validation."""
    # Test int parameter
    int_param = ParamSpec(
        name="window",
        type="int",
        min=5,
        max=100,
        step=5,
        default=20,
        help="Lookback window size"
    )
    assert int_param.name == "window"
    assert int_param.type == "int"
    assert int_param.min == 5
    assert int_param.max == 100
    assert int_param.default == 20
    
    # Test float parameter
    float_param = ParamSpec(
        name="threshold",
        type="float",
        min=0.0,
        max=1.0,
        step=0.1,
        default=0.5,
        help="Signal threshold"
    )
    assert float_param.type == "float"
    assert float_param.min == 0.0
    
    # Test enum parameter
    enum_param = ParamSpec(
        name="mode",
        type="enum",
        choices=["fast", "slow", "adaptive"],
        default="fast",
        help="Operation mode"
    )
    assert enum_param.type == "enum"
    assert enum_param.choices == ["fast", "slow", "adaptive"]
    
    # Test bool parameter
    bool_param = ParamSpec(
        name="enabled",
        type="bool",
        default=True,
        help="Enable feature"
    )
    assert bool_param.type == "bool"
    assert bool_param.default is True


def test_strategy_spec_for_gui() -> None:
    """Test StrategySpecForGUI schema."""
    params = [
        ParamSpec(
            name="window",
            type="int",
            min=10,
            max=200,
            default=50,
            help="Window size"
        )
    ]
    
    spec = StrategySpecForGUI(
        strategy_id="test_strategy_v1",
        params=params
    )
    
    assert spec.strategy_id == "test_strategy_v1"
    assert len(spec.params) == 1
    assert spec.params[0].name == "window"


def test_strategy_registry_response() -> None:
    """Test StrategyRegistryResponse schema."""
    params = [
        ParamSpec(
            name="param1",
            type="int",
            default=10,
            help="Test parameter"
        )
    ]
    
    strategy = StrategySpecForGUI(
        strategy_id="test_strategy",
        params=params
    )
    
    response = StrategyRegistryResponse(
        strategies=[strategy]
    )
    
    assert len(response.strategies) == 1
    assert response.strategies[0].strategy_id == "test_strategy"


def test_convert_to_gui_spec() -> None:
    """Test conversion from internal StrategySpec to GUI format."""
    # Create a dummy strategy spec
    internal_spec = StrategySpec(
        strategy_id="dummy_strategy_v1",
        version="v1",
        param_schema={
            "window": {
                "type": "int",
                "minimum": 10,
                "maximum": 100,
                "step": 5,
                "description": "Lookback window"
            },
            "threshold": {
                "type": "float",
                "minimum": 0.0,
                "maximum": 1.0,
                "description": "Signal threshold"
            }
        },
        defaults={
            "window": 20,
            "threshold": 0.5
        },
        fn=create_dummy_strategy_fn
    )
    
    # Convert to GUI spec
    gui_spec = convert_to_gui_spec(internal_spec)
    
    assert gui_spec.strategy_id == "dummy_strategy_v1"
    assert len(gui_spec.params) == 2
    
    # Check window parameter
    window_param = next(p for p in gui_spec.params if p.name == "window")
    assert window_param.type == "int"
    assert window_param.min == 10
    assert window_param.max == 100
    assert window_param.step == 5
    assert window_param.default == 20
    assert "Lookback window" in window_param.help
    
    # Check threshold parameter
    threshold_param = next(p for p in gui_spec.params if p.name == "threshold")
    assert threshold_param.type == "float"
    assert threshold_param.min == 0.0
    assert threshold_param.max == 1.0
    assert threshold_param.default == 0.5


def test_get_strategy_registry_with_dummy() -> None:
    """Test get_strategy_registry with dummy strategy."""
    # Clear any existing strategies
    clear()
    
    # Register a dummy strategy
    dummy_spec = StrategySpec(
        strategy_id="test_gui_strategy_v1",
        version="v1",
        param_schema={
            "param1": {
                "type": "int",
                "minimum": 1,
                "maximum": 10,
                "description": "Test parameter 1"
            }
        },
        defaults={"param1": 5},
        fn=create_dummy_strategy_fn
    )
    
    register(dummy_spec)
    
    # Get registry response
    response = get_strategy_registry()
    
    assert len(response.strategies) == 1
    gui_spec = response.strategies[0]
    assert gui_spec.strategy_id == "test_gui_strategy_v1"
    assert len(gui_spec.params) == 1
    assert gui_spec.params[0].name == "param1"
    
    # Clean up
    clear()


def test_get_strategy_registry_with_builtin() -> None:
    """Test get_strategy_registry with built-in strategies."""
    # Clear and load built-in strategies
    clear()
    load_builtin_strategies()
    
    # Get registry response
    response = get_strategy_registry()
    
    # Should have at least the built-in strategies
    assert len(response.strategies) >= 3
    
    # Check that all strategies have params
    for strategy in response.strategies:
        assert strategy.strategy_id
        assert isinstance(strategy.params, list)
        
        # Each param should have required fields
        for param in strategy.params:
            assert param.name
            assert param.type in ["int", "float", "enum", "bool"]
            assert param.help
    
    # Clean up
    clear()


def test_meta_strategies_endpoint_compatibility() -> None:
    """Test that registry response is compatible with /meta/strategies endpoint."""
    # This test ensures the response structure matches what the API expects
    clear()
    
    # Register a simple strategy
    simple_spec = StrategySpec(
        strategy_id="simple_v1",
        version="v1",
        param_schema={
            "enabled": {
                "type": "bool",
                "description": "Enable strategy"
            }
        },
        defaults={"enabled": True},
        fn=create_dummy_strategy_fn
    )
    
    register(simple_spec)
    
    # Get response and verify structure
    response = get_strategy_registry()
    
    # Response should be JSON serializable
    import json
    json_str = response.model_dump_json()
    data = json.loads(json_str)
    
    assert "strategies" in data
    assert isinstance(data["strategies"], list)
    assert len(data["strategies"]) == 1
    
    strategy_data = data["strategies"][0]
    assert strategy_data["strategy_id"] == "simple_v1"
    assert "params" in strategy_data
    assert isinstance(strategy_data["params"], list)
    
    # Clean up
    clear()


def test_param_spec_validation() -> None:
    """Test ParamSpec validation rules."""
    # Valid int param
    ParamSpec(
        name="valid_int",
        type="int",
        min=0,
        max=100,
        default=50,
        help="Valid integer"
    )
    
    # Valid float param
    ParamSpec(
        name="valid_float",
        type="float",
        min=0.0,
        max=1.0,
        default=0.5,
        help="Valid float"
    )
    
    # Valid enum param
    ParamSpec(
        name="valid_enum",
        type="enum",
        choices=["a", "b", "c"],
        default="a",
        help="Valid enum"
    )
    
    # Valid bool param
    ParamSpec(
        name="valid_bool",
        type="bool",
        default=True,
        help="Valid boolean"
    )
    
    # Test invalid type
    with pytest.raises(ValueError):
        ParamSpec(
            name="invalid",
            type="invalid_type",  # type: ignore
            default=1,
            help="Invalid type"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


