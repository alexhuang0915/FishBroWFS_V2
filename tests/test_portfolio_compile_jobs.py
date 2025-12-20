"""Test portfolio compiler.

Phase 8: Test compilation produces correct job configs.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from FishBroWFS_V2.portfolio.compiler import compile_portfolio
from FishBroWFS_V2.portfolio.loader import load_portfolio_spec
from FishBroWFS_V2.strategy.registry import load_builtin_strategies, clear


@pytest.fixture(autouse=True)
def setup_registry() -> None:
    """Setup strategy registry before each test."""
    clear()
    load_builtin_strategies()
    yield
    clear()


def test_compile_enabled_legs_only(tmp_path: Path) -> None:
    """Test compilation only includes enabled legs."""
    yaml_content = """
portfolio_id: "test"
version: "v1"
legs:
  - leg_id: "leg1"
    symbol: "CME.MNQ"
    timeframe_min: 60
    session_profile: "src/FishBroWFS_V2/data/profiles/CME_MNQ_v2.yaml"
    strategy_id: "sma_cross"
    strategy_version: "v1"
    params:
      fast_period: 10.0
      slow_period: 20.0
    enabled: true
  - leg_id: "leg2"
    symbol: "TWF.MXF"
    timeframe_min: 60
    session_profile: "src/FishBroWFS_V2/data/profiles/TWF_MXF_v2.yaml"
    strategy_id: "mean_revert_zscore"
    strategy_version: "v1"
    params:
      zscore_threshold: -2.0
    enabled: false  # Disabled
"""
    
    spec_path = tmp_path / "test.yaml"
    spec_path.write_text(yaml_content, encoding="utf-8")
    
    spec = load_portfolio_spec(spec_path)
    jobs = compile_portfolio(spec)
    
    # Should only have 1 job (leg1 enabled, leg2 disabled)
    assert len(jobs) == 1
    assert jobs[0]["leg_id"] == "leg1"


def test_compile_job_has_required_keys(tmp_path: Path) -> None:
    """Test compiled jobs have all required keys."""
    yaml_content = """
portfolio_id: "test"
version: "v1"
legs:
  - leg_id: "leg1"
    symbol: "CME.MNQ"
    timeframe_min: 60
    session_profile: "src/FishBroWFS_V2/data/profiles/CME_MNQ_v2.yaml"
    strategy_id: "sma_cross"
    strategy_version: "v1"
    params:
      fast_period: 10.0
      slow_period: 20.0
    enabled: true
    tags: ["test"]
"""
    
    spec_path = tmp_path / "test.yaml"
    spec_path.write_text(yaml_content, encoding="utf-8")
    
    spec = load_portfolio_spec(spec_path)
    jobs = compile_portfolio(spec)
    
    assert len(jobs) == 1
    job = jobs[0]
    
    # Check required keys
    required_keys = {
        "portfolio_id",
        "portfolio_version",
        "leg_id",
        "symbol",
        "timeframe_min",
        "session_profile",
        "strategy_id",
        "strategy_version",
        "params",
    }
    
    assert required_keys.issubset(job.keys())
    
    # Check values
    assert job["portfolio_id"] == "test"
    assert job["portfolio_version"] == "v1"
    assert job["leg_id"] == "leg1"
    assert job["symbol"] == "CME.MNQ"
    assert job["timeframe_min"] == 60
    assert job["strategy_id"] == "sma_cross"
    assert job["strategy_version"] == "v1"
    assert job["params"] == {"fast_period": 10.0, "slow_period": 20.0}
    assert job["tags"] == ["test"]
