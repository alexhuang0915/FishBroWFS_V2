"""
Tests for portfolio persistence layer (Phase 7‑Epsilon).
"""
from pathlib import Path
import json
import tempfile
from datetime import datetime, timezone

import pandas as pd
import pytest

from portfolio.governance_state import StrategyRecord, create_strategy_record
from portfolio.models.governance_models import StrategyState
from portfolio.manager import PortfolioManager
from portfolio.store import PortfolioStore


def test_load_empty_returns_safe_defaults(tmp_path: Path) -> None:
    """Store in empty tmp dir -> load_state returns strategies={}, returns=None."""
    store = PortfolioStore(root_dir=str(tmp_path))
    state = store.load_state()
    assert state["strategies"] == {}
    assert state["portfolio_returns"] is None


def test_save_and_load_strategies_roundtrip(tmp_path: Path) -> None:
    """Create manager with strategies (>=1), save, load, verify equivalence."""
    store = PortfolioStore(root_dir=str(tmp_path))
    manager = PortfolioManager()

    # Create a strategy
    rec = create_strategy_record(
        strategy_id="S2_001",
        version_hash="abc123",
        config={"param": 1.0},
        initial_state=StrategyState.INCUBATION,
    )
    rec.metrics["volatility"] = 0.15
    manager.strategies["S2_001"] = rec

    # Save state
    store.save_state(manager)

    # Load state
    loaded = store.load_state()
    strategies = loaded["strategies"]
    assert len(strategies) == 1
    assert "S2_001" in strategies

    loaded_rec = strategies["S2_001"]
    assert isinstance(loaded_rec, StrategyRecord)
    assert loaded_rec.strategy_id == "S2_001"
    assert loaded_rec.version_hash == "abc123"
    assert loaded_rec.state == StrategyState.INCUBATION
    assert loaded_rec.config == {"param": 1.0}
    assert loaded_rec.metrics["volatility"] == 0.15

    # Verify returns is None (manager had no portfolio_returns)
    assert loaded["portfolio_returns"] is None


def test_save_and_load_returns_roundtrip_preserves_index(tmp_path: Path) -> None:
    """Roundtrip of portfolio_series with datetime index."""
    store = PortfolioStore(root_dir=str(tmp_path))
    manager = PortfolioManager()

    # Create a simple series with datetime index
    idx = pd.date_range("2025-01-01", periods=5, tz=timezone.utc)
    vals = [0.01, -0.02, 0.03, 0.0, 0.005]
    series = pd.Series(vals, index=idx, name="portfolio_returns")
    manager.portfolio_returns = series

    # Save and load
    store.save_state(manager)
    loaded = store.load_state()

    loaded_series = loaded["portfolio_returns"]
    assert loaded_series is not None
    assert isinstance(loaded_series, pd.Series)
    assert len(loaded_series) == 5

    # Compare index (timestamps should be equal) - frequency may be lost during serialization
    pd.testing.assert_index_equal(loaded_series.index, idx, exact='equiv')
    pd.testing.assert_series_equal(loaded_series, series, check_dtype=False, check_freq=False, check_names=False)


def test_snapshot_creates_file_with_timestamp_tag(tmp_path: Path) -> None:
    """snapshot(tag="daily") creates a file with expected naming pattern."""
    store = PortfolioStore(root_dir=str(tmp_path))
    manager = PortfolioManager()

    # Add a dummy strategy
    rec = create_strategy_record("S2_002", "hash456", initial_state=StrategyState.CANDIDATE)
    manager.strategies["S2_002"] = rec

    # Create snapshot
    snapshot_path = store.snapshot(manager, tag="daily")

    # Verify file exists
    assert snapshot_path.exists()
    assert snapshot_path.parent == store.snapshots_dir

    # Verify filename pattern: YYYYMMDD_HHMMSS_daily.json
    filename = snapshot_path.name
    assert filename.endswith("_daily.json")
    # timestamp part: exactly 15 chars (8+1+6)
    timestamp_part = filename[:15]
    assert timestamp_part[8] == "_"
    assert timestamp_part[:8].isdigit()  # YYYYMMDD
    assert timestamp_part[9:15].isdigit()  # HHMMSS

    # Verify content includes schema_version and strategies
    with open(snapshot_path, "r", encoding="utf-8") as f:
        content = json.load(f)
    assert content["schema_version"] == 1
    assert content["tag"] == "daily"
    assert "strategies" in content
    assert "S2_002" in content["strategies"]


def test_snapshot_tag_sanitization(tmp_path: Path) -> None:
    """Tag with special characters is sanitized."""
    store = PortfolioStore(root_dir=str(tmp_path))
    manager = PortfolioManager()

    snapshot_path = store.snapshot(manager, tag="test/tag with spaces@and#special!")
    filename = snapshot_path.name
    # Should have sanitized the tag
    assert "test_tag_with_spaces_and_special_" in filename


def test_atomic_write_via_tmp_file(tmp_path: Path) -> None:
    """Verify atomic write uses .tmp file and os.replace."""
    store = PortfolioStore(root_dir=str(tmp_path))
    manager = PortfolioManager()

    # Initially no current_state.json
    assert not store.current_state_path.exists()

    store.save_state(manager)

    # Should have created current_state.json
    assert store.current_state_path.exists()
    # Should NOT leave a .tmp file behind
    tmp_files = list(tmp_path.glob("*.json.tmp"))
    assert len(tmp_files) == 0


def test_load_state_with_missing_file_returns_empty(tmp_path: Path) -> None:
    """When current_state.json does not exist, return empty defaults."""
    store = PortfolioStore(root_dir=str(tmp_path))
    # Ensure file does not exist
    if store.current_state_path.exists():
        store.current_state_path.unlink()

    state = store.load_state()
    assert state["strategies"] == {}
    assert state["portfolio_returns"] is None


def test_roundtrip_with_multiple_strategies_and_returns(tmp_path: Path) -> None:
    """Complex roundtrip with multiple strategies and a returns series."""
    store = PortfolioStore(root_dir=str(tmp_path))
    manager = PortfolioManager()

    # Add two strategies
    rec1 = create_strategy_record(
        "S2_A", "hash1", config={"a": 1}, initial_state=StrategyState.LIVE
    )
    rec1.metrics.update({"volatility": 0.12, "sharpe": 1.5})
    manager.strategies["S2_A"] = rec1

    rec2 = create_strategy_record(
        "S2_B", "hash2", config={"b": 2}, initial_state=StrategyState.PAPER_TRADING
    )
    rec2.metrics.update({"volatility": 0.18})
    manager.strategies["S2_B"] = rec2

    # Add portfolio returns
    idx = pd.date_range("2025-01-01", periods=3, tz=timezone.utc)
    series = pd.Series([0.01, -0.005, 0.02], index=idx)
    manager.portfolio_returns = series

    # Save and load
    store.save_state(manager)
    loaded = store.load_state()

    # Verify strategies
    strategies = loaded["strategies"]
    assert len(strategies) == 2
    assert strategies["S2_A"].strategy_id == "S2_A"
    assert strategies["S2_A"].state == StrategyState.LIVE
    assert strategies["S2_A"].metrics["volatility"] == 0.12
    assert strategies["S2_B"].strategy_id == "S2_B"
    assert strategies["S2_B"].state == StrategyState.PAPER_TRADING

    # Verify returns
    loaded_series = loaded["portfolio_returns"]
    assert loaded_series is not None
    pd.testing.assert_series_equal(loaded_series, series, check_dtype=False, check_freq=False)


def test_store_creates_directories(tmp_path: Path) -> None:
    """Store creates root and snapshots directories if they don't exist."""
    root = tmp_path / "custom_store"
    assert not root.exists()

    store = PortfolioStore(root_dir=str(root))
    # __init__ should have created directories
    assert root.exists()
    assert (root / "snapshots").exists()