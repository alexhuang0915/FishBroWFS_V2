"""
Sanity test for imports to catch PYTHONPATH regressions.
"""
import sys

def test_contracts_import():
    """Test that contracts module can be imported."""
    import contracts
    assert contracts is not None
    
    # Try importing a submodule
    from contracts.strategy_features import StrategyFeatureRequirements
    assert StrategyFeatureRequirements is not None

def test_config_import():
    """Test that config modules can be imported."""
    from src.config.strategies import StrategyConfig
    assert StrategyConfig is not None

def test_core_import():
    """Test that core modules can be imported."""
    from src.core.features import FeatureBundle
    assert FeatureBundle is not None

if __name__ == "__main__":
    test_contracts_import()
    test_config_import()
    test_core_import()
    print("✅ All imports work")
