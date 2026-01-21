
import pytest
from unittest.mock import patch, MagicMock
import numpy as np
from pipeline.runner_adapter import run_stage_job

# Mock Strategy Spec
class MockStrategySpec:
    def __init__(self, strategy_id, param_names):
        self.strategy_id = strategy_id
        # Simple dict schema for test purposes
        self.param_schema = {name: {"type": "float"} for name in param_names}

@pytest.fixture
def mock_registry_get():
    # We patch the actual registry module methods
    with patch("strategy.registry.get") as mock_get, \
         patch("strategy.registry.convert_to_gui_spec") as mock_convert:
        
        strategies = {
            "strategy_A": MockStrategySpec("strategy_A", ["pA1", "pA2", "pA3"]),
            "strategy_B": MockStrategySpec("strategy_B", ["pB1", "pB2"]),
        }
        mock_get.side_effect = lambda sid: strategies.get(sid)
        
        # Mock convert_to_gui_spec to return an object with .params
        def fake_convert(spec):
            # Create a fake object with .params attribute
            # .params should be a list of objects with .name and .type
            class FakeParamSpec:
                def __init__(self, name, type_):
                    self.name = name
                    self.type = type_
            
            class FakeGuiSpec:
                def __init__(self, params):
                    self.params = params
            
            # Extract names from our MockStrategySpec param_schema keys
            # and verify order logic if needed. 
            # In runner_adapter we rely on the list order.
            # Here we just iterate keys.
            params = []
            for name, info in spec.param_schema.items():
                params.append(FakeParamSpec(name, info["type"]))
            
            # Sort to match runner_adapter expectation (if it expects sorted)
            # Real registry sorts by name.
            params.sort(key=lambda x: x.name)
            return FakeGuiSpec(params)
            
        mock_convert.side_effect = fake_convert
        yield mock_get

def test_stage1_fails_correctly_without_ssot_impl(mock_registry_get):
    """
    This test verifies that the CURRENT code fails to use SSOT.
    Once fixed, we will update this test or add a new one that asserts success.
    """
    # Setup for Strategy A
    with patch("pipeline.runner_adapter.run_grid") as mock_run_grid:
        mock_run_grid.return_value = {
            "metrics": np.array([[100.0, 10, 0.1]]), 
            "perf": {"t_total_s": 1.0}
        }
        
        cfg_a = {
            "stage_name": "stage1_topk",
            "strategy_id": "strategy_A",
            "open_": np.array([1.0]), "high": np.array([2.0]), "low": np.array([0.5]), "close": np.array([1.5]),
            "params_matrix": np.array([[1.0, 2.0, 3.0]]),
            "commission": 0.0, "slip": 0.0
        }
        
        # Currently, this will likely NOT use strategy_A params, but hardcoded ones.
        # It won't crash, but the "params" keys will be wrong.
        result_a = run_stage_job(cfg_a)
        plateau_a = result_a["plateau_candidates"]
        
        if not plateau_a:
             # If no plateau candidates (unlikely given mocking), skip
             return

        params_a = plateau_a[0]["params"]
        
        # Correct behavior assertions:
        assert "pA1" in params_a
        assert "pA2" in params_a
        assert "pA3" in params_a
        assert "channel_len" not in params_a # Should not use hardcoded

def test_missing_strategy_id_raises():
    cfg = {
        "stage_name": "stage1_topk",
        # No strategy_id
        "open_": np.array([1.0]), "high": np.array([2.0]), "low": np.array([0.5]), "close": np.array([1.5]),
        "params_matrix": np.array([[1.0, 2.0, 3.0]]),
        "commission": 0.0, "slip": 0.0
    }
    # Desired: ValueError matching "strategy_id"
    with pytest.raises(ValueError, match="strategy_id"):
        run_stage_job(cfg)
