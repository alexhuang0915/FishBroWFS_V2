
"""Test portfolio spec loader.

Phase 8: Test YAML/JSON loader can load and type is correct.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from portfolio.loader import load_portfolio_spec
from portfolio.spec import PortfolioLeg, PortfolioSpec


def test_load_yaml_spec(tmp_path: Path) -> None:
    """Test loading YAML portfolio spec."""
    yaml_content = """
portfolio_id: "test"
version: "v1"
data_tz: "Asia/Taipei"
legs:
  - leg_id: "leg1"
    symbol: "CME.MNQ"
    timeframe_min: 60
    session_profile: "configs/profiles/CME_MNQ_v2.yaml"
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
    
    assert isinstance(spec, PortfolioSpec)
    assert spec.portfolio_id == "test"
    assert spec.version == "v1"
    assert spec.data_tz == "Asia/Taipei"
    assert len(spec.legs) == 1
    
    leg = spec.legs[0]
    assert isinstance(leg, PortfolioLeg)
    assert leg.leg_id == "leg1"
    assert leg.symbol == "CME.MNQ"
    assert leg.timeframe_min == 60
    assert leg.strategy_id == "sma_cross"
    assert leg.strategy_version == "v1"
    assert leg.params == {"fast_period": 10.0, "slow_period": 20.0}
    assert leg.enabled is True
    assert leg.tags == ["test"]


def test_load_json_spec(tmp_path: Path) -> None:
    """Test loading JSON portfolio spec."""
    import json
    
    json_content = {
        "portfolio_id": "test",
        "version": "v1",
        "data_tz": "Asia/Taipei",
        "legs": [
            {
                "leg_id": "leg1",
                "symbol": "CME.MNQ",
                "timeframe_min": 60,
                "session_profile": "configs/profiles/CME_MNQ_v2.yaml",
                "strategy_id": "sma_cross",
                "strategy_version": "v1",
                "params": {
                    "fast_period": 10.0,
                    "slow_period": 20.0,
                },
                "enabled": True,
                "tags": ["test"],
            }
        ],
    }
    
    spec_path = tmp_path / "test.json"
    with spec_path.open("w", encoding="utf-8") as f:
        json.dump(json_content, f)
    
    spec = load_portfolio_spec(spec_path)
    
    assert isinstance(spec, PortfolioSpec)
    assert spec.portfolio_id == "test"
    assert len(spec.legs) == 1


def test_load_missing_fields_raises(tmp_path: Path) -> None:
    """Test loading spec with missing required fields raises ValueError."""
    yaml_content = """
portfolio_id: "test"
# Missing version
legs: []
"""
    
    spec_path = tmp_path / "test.yaml"
    spec_path.write_text(yaml_content, encoding="utf-8")
    
    with pytest.raises(ValueError, match="missing 'version' field"):
        load_portfolio_spec(spec_path)


def test_load_invalid_params_type_raises(tmp_path: Path) -> None:
    """Test loading spec with invalid params type raises ValueError."""
    yaml_content = """
portfolio_id: "test"
version: "v1"
legs:
  - leg_id: "leg1"
    symbol: "CME.MNQ"
    timeframe_min: 60
    session_profile: "configs/profiles/CME_MNQ_v2.yaml"
    strategy_id: "sma_cross"
    strategy_version: "v1"
    params: "invalid"  # Should be dict
"""
    
    spec_path = tmp_path / "test.yaml"
    spec_path.write_text(yaml_content, encoding="utf-8")
    
    with pytest.raises(ValueError, match="params must be dict"):
        load_portfolio_spec(spec_path)


