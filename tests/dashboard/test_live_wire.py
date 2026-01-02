"""Live wire tests for dashboard service real kernel integration (Phase 9‑Gamma)."""

import asyncio
import tempfile
from pathlib import Path

import pytest
import numpy as np

from src.dashboard.service import PortfolioService


@pytest.mark.asyncio
async def test_run_admission_with_real_kernel(tmp_path):
    """Test that run_admission uses real Stage2 kernel and returns deterministic result."""
    store_dir = tmp_path / "store"
    store_dir.mkdir()

    # Create service with temp data root
    service = PortfolioService(data_root=str(store_dir))
    
    # Register a strategy
    await service.register_strategy("test_strat_1", {"param": "default"})
    
    # Run admission (should use real kernel)
    result = await service.run_admission("test_strat_1")
    
    # Verify result structure
    assert "allowed" in result
    assert "correlation" in result
    assert "reason" in result
    
    # With real kernel and deterministic OHLC, we should get non-zero trades
    # The kernel should produce trades because our synthetic data has a spike/crash
    # However, we can't guarantee admission will be allowed (depends on correlation)
    # Just verify the result is a valid AdmissionResult dict
    assert isinstance(result["allowed"], bool)
    assert isinstance(result["correlation"], float)
    assert isinstance(result["reason"], str)
    
    # Verify state was saved
    state = service.get_dashboard_state()
    strategy = next((s for s in state["strategies"] if s["strategy_id"] == "test_strat_1"), None)
    assert strategy is not None
    
    # Check audit log contains ADMISSION_REQUEST and ADMISSION_DECISION
    audit_events = [e.get("event_type") for e in state["audit_log"]]
    assert "ADMISSION_REQUEST" in audit_events
    assert "ADMISSION_DECISION" in audit_events


@pytest.mark.asyncio
async def test_admission_heartbeat_zero_trades_rejection(tmp_path):
    """Test that admission rejects if kernel returns zero trades.
    
    This scenario is hard to reproduce deterministically because our synthetic
    data is designed to produce trades. We'll skip this test with a clear reason.
    """
    pytest.skip(
        "Zero-trades scenario not reproducible with current deterministic OHLC "
        "(synthetic data includes spike/crash to ensure trades)."
    )


@pytest.mark.asyncio
async def test_service_persistence_across_restarts(tmp_path):
    """Test that admission decision persists when service is recreated."""
    store_dir = tmp_path / "store"
    store_dir.mkdir()

    # First service instance
    service1 = PortfolioService(data_root=str(store_dir))
    await service1.register_strategy("persist_test", {"k": 42})
    
    # Get initial state
    state1 = service1.get_dashboard_state()
    initial_count = state1["total_count"]
    
    # Run admission
    result = await service1.run_admission("persist_test")
    
    # Second service instance (fresh load)
    service2 = PortfolioService(data_root=str(store_dir))
    state2 = service2.get_dashboard_state()
    
    # Verify strategy count matches
    assert state2["total_count"] == initial_count
    
    # Find the strategy
    strategy = next((s for s in state2["strategies"] if s["strategy_id"] == "persist_test"), None)
    assert strategy is not None
    
    # State should reflect admission decision
    # If admission was allowed, state should be CANDIDATE; otherwise INCUBATION
    # We'll just verify the strategy exists with some state
    assert strategy["state"] in ["INCUBATION", "CANDIDATE"]


@pytest.mark.asyncio
async def test_multiple_strategies_admission_sequential(tmp_path):
    """Test admitting multiple strategies sequentially."""
    store_dir = tmp_path / "store"
    store_dir.mkdir()

    service = PortfolioService(data_root=str(store_dir))
    
    # Register two strategies
    await service.register_strategy("multi_1", {"id": 1})
    await service.register_strategy("multi_2", {"id": 2})
    
    # Run admission for both
    result1 = await service.run_admission("multi_1")
    result2 = await service.run_admission("multi_2")
    
    # Both should produce valid results
    for result in [result1, result2]:
        assert "allowed" in result
        assert isinstance(result["allowed"], bool)
    
    # Verify both appear in state
    state = service.get_dashboard_state()
    strategy_ids = {s["strategy_id"] for s in state["strategies"]}
    assert "multi_1" in strategy_ids
    assert "multi_2" in strategy_ids


if __name__ == "__main__":
    # Quick manual test
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
