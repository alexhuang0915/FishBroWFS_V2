
"""Test portfolio artifacts hash stability.

Phase 8: Test hash is deterministic and changes with spec changes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from FishBroWFS_V2.portfolio.artifacts import compute_portfolio_hash, write_portfolio_artifacts
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


def test_hash_same_spec_consistent(tmp_path: Path) -> None:
    """Test hash is consistent for same spec."""
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
    params:
      fast_period: 10.0
      slow_period: 20.0
    enabled: true
"""
    
    spec_path = tmp_path / "test.yaml"
    spec_path.write_text(yaml_content, encoding="utf-8")
    
    spec = load_portfolio_spec(spec_path)
    
    # Compute hash multiple times
    hash1 = compute_portfolio_hash(spec)
    hash2 = compute_portfolio_hash(spec)
    hash3 = compute_portfolio_hash(spec)
    
    # All hashes should be identical
    assert hash1 == hash2 == hash3
    assert len(hash1) == 40  # SHA1 hex string length


def test_hash_different_order_consistent(tmp_path: Path) -> None:
    """Test hash is consistent even if legs are in different order."""
    yaml_content1 = """
portfolio_id: "test"
version: "v1"
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
  - leg_id: "leg2"
    symbol: "TWF.MXF"
    timeframe_min: 60
    session_profile: "configs/profiles/TWF_MXF_v2.yaml"
    strategy_id: "mean_revert_zscore"
    strategy_version: "v1"
    params:
      zscore_threshold: -2.0
    enabled: true
"""
    
    yaml_content2 = """
portfolio_id: "test"
version: "v1"
legs:
  - leg_id: "leg2"  # Different order
    symbol: "TWF.MXF"
    timeframe_min: 60
    session_profile: "configs/profiles/TWF_MXF_v2.yaml"
    strategy_id: "mean_revert_zscore"
    strategy_version: "v1"
    params:
      zscore_threshold: -2.0
    enabled: true
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
"""
    
    spec_path1 = tmp_path / "test1.yaml"
    spec_path1.write_text(yaml_content1, encoding="utf-8")
    
    spec_path2 = tmp_path / "test2.yaml"
    spec_path2.write_text(yaml_content2, encoding="utf-8")
    
    spec1 = load_portfolio_spec(spec_path1)
    spec2 = load_portfolio_spec(spec_path2)
    
    hash1 = compute_portfolio_hash(spec1)
    hash2 = compute_portfolio_hash(spec2)
    
    # Hashes should be identical (legs are sorted by leg_id before hashing)
    assert hash1 == hash2


def test_hash_changes_with_param_change(tmp_path: Path) -> None:
    """Test hash changes when params change."""
    yaml_content1 = """
portfolio_id: "test"
version: "v1"
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
"""
    
    yaml_content2 = """
portfolio_id: "test"
version: "v1"
legs:
  - leg_id: "leg1"
    symbol: "CME.MNQ"
    timeframe_min: 60
    session_profile: "configs/profiles/CME_MNQ_v2.yaml"
    strategy_id: "sma_cross"
    strategy_version: "v1"
    params:
      fast_period: 15.0  # Changed
      slow_period: 20.0
    enabled: true
"""
    
    spec_path1 = tmp_path / "test1.yaml"
    spec_path1.write_text(yaml_content1, encoding="utf-8")
    
    spec_path2 = tmp_path / "test2.yaml"
    spec_path2.write_text(yaml_content2, encoding="utf-8")
    
    spec1 = load_portfolio_spec(spec_path1)
    spec2 = load_portfolio_spec(spec_path2)
    
    hash1 = compute_portfolio_hash(spec1)
    hash2 = compute_portfolio_hash(spec2)
    
    # Hashes should be different
    assert hash1 != hash2


def test_write_artifacts_creates_files(tmp_path: Path) -> None:
    """Test write_portfolio_artifacts creates all required files."""
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
    params:
      fast_period: 10.0
      slow_period: 20.0
    enabled: true
"""
    
    spec_path = tmp_path / "test.yaml"
    spec_path.write_text(yaml_content, encoding="utf-8")
    
    spec = load_portfolio_spec(spec_path)
    jobs = compile_portfolio(spec)
    
    out_dir = tmp_path / "artifacts"
    artifact_paths = write_portfolio_artifacts(spec, jobs, out_dir)
    
    # Check all files exist
    assert (out_dir / "portfolio_spec_snapshot.yaml").exists()
    assert (out_dir / "compiled_jobs.json").exists()
    assert (out_dir / "portfolio_index.json").exists()
    assert (out_dir / "portfolio_hash.txt").exists()
    
    # Check hash file content
    hash_content = (out_dir / "portfolio_hash.txt").read_text(encoding="utf-8").strip()
    computed_hash = compute_portfolio_hash(spec)
    assert hash_content == computed_hash
    
    # Check index contains hash
    import json
    index_content = json.loads((out_dir / "portfolio_index.json").read_text(encoding="utf-8"))
    assert index_content["portfolio_hash"] == computed_hash


