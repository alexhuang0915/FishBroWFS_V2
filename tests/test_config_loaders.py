"""
Test Config Constitution v1 Loaders

Verify that the new config loaders work correctly.
"""

import pytest
from pathlib import Path

from src.config import (
    # Registry loaders
    load_timeframes, TimeframeRegistry,
    load_instruments, InstrumentRegistry,
    load_datasets, DatasetRegistry,
    load_strategy_catalog, StrategyCatalogRegistry,
    
    # Profile loader
    load_profile, ProfileConfig,
    
    # Strategy loader
    load_strategy, StrategyConfig,
    
    # Portfolio loader
    load_portfolio_config, PortfolioConfig,
    
    # Errors
    ConfigError, ConfigValidationError, ConfigNotFoundError,
)


def test_load_timeframes():
    """Test loading timeframe registry."""
    timeframes = load_timeframes()
    
    assert isinstance(timeframes, TimeframeRegistry)
    assert timeframes.version == "1.0"
    assert timeframes.allowed_timeframes == [15, 30, 60, 120, 240]
    assert timeframes.default == 60
    
    # Test helper methods
    assert timeframes.get_display_name(60) == "1h"
    assert timeframes.get_display_name(15) == "15m"
    assert timeframes.get_display_name(120) == "2h"
    
    choices = timeframes.get_timeframe_choices()
    assert len(choices) == 5
    assert (60, "1h") in choices


def test_load_instruments():
    """Test loading instrument registry."""
    instruments = load_instruments()
    
    assert isinstance(instruments, InstrumentRegistry)
    assert instruments.version == "1.0"
    assert len(instruments.instruments) >= 2  # CME.MNQ and TWF.MXF
    
    # Test finding instruments
    mnq = instruments.get_instrument_by_id("CME.MNQ")
    assert mnq is not None
    assert mnq.id == "CME.MNQ"
    assert mnq.display_name == "E-mini Nasdaq-100"
    assert mnq.profile == "CME_MNQ_v2"
    assert mnq.currency == "USD"
    
    # Test default instrument
    assert instruments.default == "CME.MNQ"
    
    # Test helper methods
    choices = instruments.get_instrument_choices()
    assert len(choices) >= 2
    assert any(id == "CME.MNQ" for id, _ in choices)


def test_load_datasets():
    """Test loading dataset registry."""
    datasets = load_datasets()
    
    assert isinstance(datasets, DatasetRegistry)
    assert datasets.version == "1.0"
    assert len(datasets.datasets) >= 1
    
    # Test finding dataset
    mnq_dataset = datasets.get_dataset_by_id("CME.MNQ.60m.2020-2024")
    assert mnq_dataset is not None
    assert mnq_dataset.instrument_id == "CME.MNQ"
    assert mnq_dataset.timeframe == 60
    assert mnq_dataset.storage_type == "npz"
    
    # Test URI resolution
    uri = datasets.resolve_uri("CME.MNQ.60m.2020-2024", "2026Q1")
    assert uri is not None
    assert "{season}" not in uri  # Should be replaced
    assert "2026Q1" in uri


def test_load_strategy_catalog():
    """Test loading strategy catalog."""
    catalog = load_strategy_catalog()
    
    assert isinstance(catalog, StrategyCatalogRegistry)
    assert catalog.version == "1.0"
    assert len(catalog.strategies) >= 1
    
    # Test finding strategy
    s1 = catalog.get_strategy_by_id("s1_v1")
    assert s1 is not None
    assert s1.id == "s1_v1"
    assert s1.display_name == "Stage 1 Strategy"
    assert s1.config_file == "s1_v1.yaml"
    
    # Test config path resolution
    config_path = catalog.get_strategy_config_path("s1_v1")
    assert config_path is not None
    assert config_path.name == "s1_v1.yaml"
    assert config_path.exists()


def test_load_profile():
    """Test loading profile with mandatory cost model."""
    profile = load_profile("CME_MNQ_v2")
    
    assert isinstance(profile, ProfileConfig)
    assert profile.version == "2.0"
    assert profile.symbol == "CME.MNQ"
    
    # Test mandatory cost model
    assert profile.cost_model is not None
    assert hasattr(profile.cost_model, 'commission_per_side_usd')
    assert hasattr(profile.cost_model, 'slippage_per_side_usd')
    
    # Test cost calculations
    commission = profile.get_total_commission(sides=2)
    slippage = profile.get_total_slippage(sides=2)
    total_cost = profile.get_total_cost(sides=2)
    
    assert commission == profile.cost_model.commission_per_side_usd * 2
    assert slippage == profile.cost_model.slippage_per_side_usd * 2
    assert total_cost == commission + slippage
    
    # Test SHA256 hash
    assert profile.sha256 is not None
    assert len(profile.sha256) == 64  # SHA256 hex digest length


def test_load_strategy():
    """Test loading strategy with determinism."""
    strategy = load_strategy("s1_v1")
    
    assert isinstance(strategy, StrategyConfig)
    assert strategy.version == "1.0"
    assert strategy.strategy_id == "s1_v1"
    
    # Test determinism section
    assert strategy.determinism is not None
    assert strategy.determinism.default_seed == 42
    
    # Test seed precedence
    assert strategy.get_effective_seed(job_seed=100) == 100  # job.seed takes precedence
    assert strategy.get_effective_seed(job_seed=None) == 42  # strategy.default_seed
    
    # Test parameters
    assert "fast_period" in strategy.parameters
    assert "slow_period" in strategy.parameters
    assert "threshold" in strategy.parameters
    
    # Test parameter validation
    params = {"fast_period": 10, "slow_period": 30, "threshold": 0.5}
    validated = strategy.validate_parameters(params)
    assert validated["fast_period"] == 10
    assert validated["slow_period"] == 30
    assert validated["threshold"] == 0.5
    
    # Test SHA256 hash
    assert strategy.sha256 is not None


def test_load_portfolio_config():
    """Test loading portfolio governance config."""
    portfolio = load_portfolio_config("governance.yaml")
    
    assert isinstance(portfolio, PortfolioConfig)
    assert portfolio.version == "2.0"
    
    # Test risk model
    assert portfolio.risk_model == "vol_target"
    assert "vol_target" in portfolio.allowed_risk_models
    
    # Test bucket slots
    assert len(portfolio.bucket_slots) >= 4
    assert "Trend" in portfolio.bucket_slots
    assert portfolio.bucket_slots["Trend"].slots == 2
    
    # Test policies
    assert portfolio.correlation_policy is not None
    assert portfolio.drawdown_policy is not None
    assert portfolio.risk_budget_policy is not None
    assert portfolio.breaker_policy is not None
    
    # Test helper methods
    total_slots = portfolio.get_total_slots()
    assert total_slots >= 7  # Sum of bucket slots
    
    # Test SHA256 hash
    assert portfolio.sha256 is not None


def test_config_error_handling():
    """Test config error handling."""
    # Test non-existent file
    with pytest.raises(ConfigNotFoundError):
        load_timeframes(Path("non_existent.yaml"))
    
    # Test invalid YAML (would raise ConfigValidationError)
    # This requires creating a temporary invalid YAML file
    import tempfile
    import yaml
    
    with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
        f.write("invalid: yaml: : :")  # Invalid YAML
        temp_path = Path(f.name)
    
    try:
        from src.config import load_yaml
        with pytest.raises(ConfigValidationError):
            load_yaml(temp_path)
    finally:
        temp_path.unlink()


def test_config_caching():
    """Test that config loaders use caching."""
    import time
    
    # First load should cache
    start = time.time()
    timeframes1 = load_timeframes()
    load1_time = time.time() - start
    
    # Second load should be faster (from cache)
    start = time.time()
    timeframes2 = load_timeframes()
    load2_time = time.time() - start
    
    # Same object (cached)
    assert timeframes1 is timeframes2
    
    # Second load should be significantly faster
    # (though with small files, difference might be minimal)
    assert load2_time <= load1_time * 2  # Allow some variance


if __name__ == "__main__":
    # Run tests directly
    test_load_timeframes()
    print("✓ Timeframe registry loader test passed")
    
    test_load_instruments()
    print("✓ Instrument registry loader test passed")
    
    test_load_datasets()
    print("✓ Dataset registry loader test passed")
    
    test_load_strategy_catalog()
    print("✓ Strategy catalog loader test passed")
    
    test_load_profile()
    print("✓ Profile loader test passed")
    
    test_load_strategy()
    print("✓ Strategy loader test passed")
    
    test_load_portfolio_config()
    print("✓ Portfolio config loader test passed")
    
    print("\n✅ All config loader tests passed!")