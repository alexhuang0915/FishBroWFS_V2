
"""Test portfolio validator.

Phase 8: Test validation raises errors for invalid specs.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from portfolio.loader import load_portfolio_spec
from portfolio.validate import validate_portfolio_spec
from strategy.registry import load_builtin_strategies, clear


@pytest.fixture(autouse=True)
def setup_registry() -> None:
    """Setup strategy registry before each test."""
    clear()
    load_builtin_strategies()
    yield
    clear()


def test_validate_empty_legs_raises(tmp_path: Path) -> None:
    """Test validating spec with empty legs raises ValueError."""
    yaml_content = """
portfolio_id: "test"
version: "v1"
legs: []
"""
    
    spec_path = tmp_path / "test.yaml"
    spec_path.write_text(yaml_content, encoding="utf-8")
    
    spec = load_portfolio_spec(spec_path)
    
    with pytest.raises(ValueError, match="at least one leg"):
        validate_portfolio_spec(spec)


def test_validate_duplicate_leg_id_raises(tmp_path: Path) -> None:
    """Test validating spec with duplicate leg_id raises ValueError."""
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
    params: {}
  - leg_id: "leg1"  # Duplicate
    symbol: "TWF.MXF"
    timeframe_min: 60
    session_profile: "configs/profiles/TWF_MXF_v2.yaml"
    strategy_id: "sma_cross"
    strategy_version: "v1"
    params: {}
"""
    
    spec_path = tmp_path / "test.yaml"
    spec_path.write_text(yaml_content, encoding="utf-8")
    
    with pytest.raises(ValueError, match="Duplicate leg_id"):
        load_portfolio_spec(spec_path)


def test_validate_nonexistent_strategy_raises(tmp_path: Path) -> None:
    """Test validating spec with nonexistent strategy raises KeyError."""
    yaml_content = """
portfolio_id: "test"
version: "v1"
legs:
  - leg_id: "leg1"
    symbol: "CME.MNQ"
    timeframe_min: 60
    session_profile: "configs/profiles/CME_MNQ_v2.yaml"
    strategy_id: "nonexistent_strategy"  # Not in registry
    strategy_version: "v1"
    params: {}
"""
    
    spec_path = tmp_path / "test.yaml"
    spec_path.write_text(yaml_content, encoding="utf-8")
    
    spec = load_portfolio_spec(spec_path)
    
    with pytest.raises(KeyError, match="not found in registry"):
        validate_portfolio_spec(spec)


def test_validate_strategy_version_mismatch_raises(tmp_path: Path) -> None:
    """Test validating spec with strategy version mismatch raises ValueError."""
    yaml_content = """
portfolio_id: "test"
version: "v1"
legs:
  - leg_id: "leg1"
    symbol: "CME.MNQ"
    timeframe_min: 60
    session_profile: "configs/profiles/CME_MNQ_v2.yaml"
    strategy_id: "sma_cross"
    strategy_version: "v2"  # Mismatch (registry has v1)
    params: {}
"""
    
    spec_path = tmp_path / "test.yaml"
    spec_path.write_text(yaml_content, encoding="utf-8")
    
    spec = load_portfolio_spec(spec_path)
    
    with pytest.raises(ValueError, match="strategy_version mismatch"):
        validate_portfolio_spec(spec)


def test_validate_nonexistent_session_profile_raises(tmp_path: Path) -> None:
    """Test validating spec with nonexistent session profile raises FileNotFoundError."""
    yaml_content = """
portfolio_id: "test"
version: "v1"
legs:
  - leg_id: "leg1"
    symbol: "CME.MNQ"
    timeframe_min: 60
    session_profile: "nonexistent_profile.yaml"  # Not found
    strategy_id: "sma_cross"
    strategy_version: "v1"
    params: {}
"""
    
    spec_path = tmp_path / "test.yaml"
    spec_path.write_text(yaml_content, encoding="utf-8")
    
    spec = load_portfolio_spec(spec_path)
    
    with pytest.raises(FileNotFoundError):
        validate_portfolio_spec(spec)


