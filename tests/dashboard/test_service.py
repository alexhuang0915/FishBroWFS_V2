"""
Tests for dashboard service bridge (Phase 9‑Alpha).
"""
import asyncio
import json
import tempfile
from pathlib import Path

import pytest
import pandas as pd

from src.dashboard.service import PortfolioService


@pytest.mark.asyncio
async def test_register_and_reload_persists_strategy(tmp_path):
    """Register a strategy and verify it appears after a fresh service instance."""
    store_dir = tmp_path / "store"
    store_dir.mkdir()

    # First service instance
    s1 = PortfolioService(data_root=str(store_dir))
    await s1.register_strategy("s1", {"k": 1})

    # Second service instance (fresh load)
    s2 = PortfolioService(data_root=str(store_dir))
    state = s2.get_dashboard_state()

    # Verify s1 appears in strategies
    strategy_ids = [rec["strategy_id"] for rec in state["strategies"]]
    assert "s1" in strategy_ids
    assert state["total_count"] == 1
    assert state["live_count"] == 0  # still INCUBATION


@pytest.mark.asyncio
async def test_audit_visible_in_dashboard_state(tmp_path):
    """After register + admission + rebalance, audit log contains expected event types."""
    store_dir = tmp_path / "store"
    store_dir.mkdir()

    s = PortfolioService(data_root=str(store_dir))
    await s.register_strategy("s1", {"k": 1})
    await s.run_admission("s1")
    # Need to set volatility metric for rebalance to allocate
    # Find the strategy record and update metrics
    for rec in s.manager.strategies.values():
        if rec.strategy_id == "s1":
            rec.metrics["volatility"] = 0.15
            break
    await s.run_rebalance(total_capital=1.0)

    state = s.get_dashboard_state(tail_n=200)
    audit_log = state["audit_log"]

    # Collect event types
    event_types = [ev.get("event_type") for ev in audit_log]

    # Expected events (order may vary)
    expected = {
        "ONBOARD",
        "ADMISSION_REQUEST",
        "ADMISSION_DECISION",
        "SAVE_STATE",
        "REBALANCE",
        "SNAPSHOT",
    }
    # At least one of each expected type should appear
    for ev_type in expected:
        assert any(et == ev_type for et in event_types), f"Missing {ev_type} in audit log"

    # Verify JSON dicts contain required keys
    for ev in audit_log:
        assert "event_type" in ev
        assert "ts_utc" in ev
        assert "schema_version" in ev


@pytest.mark.asyncio
async def test_state_transitions_flow(tmp_path):
    """Register → admission (genesis allowed) → activate → state becomes LIVE."""
    store_dir = tmp_path / "store"
    store_dir.mkdir()

    s = PortfolioService(data_root=str(store_dir))
    await s.register_strategy("s1", {"k": 1})

    # Initially INCUBATION
    state0 = s.get_dashboard_state()
    rec0 = next(r for r in state0["strategies"] if r["strategy_id"] == "s1")
    assert rec0["state"] == "INCUBATION"

    # Admission (genesis allowed because portfolio empty)
    result = await s.run_admission("s1")
    assert result["allowed"] is True

    # Should become CANDIDATE
    state1 = s.get_dashboard_state()
    rec1 = next(r for r in state1["strategies"] if r["strategy_id"] == "s1")
    assert rec1["state"] == "CANDIDATE"

    # Activate (CANDIDATE → LIVE via PAPER_TRADING)
    await s.activate("s1")

    # Should become LIVE
    state2 = s.get_dashboard_state()
    rec2 = next(r for r in state2["strategies"] if r["strategy_id"] == "s1")
    assert rec2["state"] == "LIVE"
    assert state2["live_count"] == 1


@pytest.mark.asyncio
async def test_rebalance_allocations_sum_to_total_capital(tmp_path):
    """Rebalance allocations sum to total_capital (within epsilon)."""
    store_dir = tmp_path / "store"
    store_dir.mkdir()

    s = PortfolioService(data_root=str(store_dir))

    # Register two strategies, admit them, activate them, set volatility
    for i in range(2):
        sid = f"s{i}"
        await s.register_strategy(sid, {"k": i})
        await s.run_admission(sid)
        await s.activate(sid)
        # Set volatility metric
        for rec in s.manager.strategies.values():
            if rec.strategy_id == sid:
                rec.metrics["volatility"] = 0.1 + 0.05 * i  # 0.1, 0.15
                break

    # Rebalance with total_capital = 1.0
    allocations = await s.run_rebalance(total_capital=1.0)

    # Sum of allocations should be 1.0 (within floating epsilon)
    total = sum(allocations.values())
    assert abs(total - 1.0) < 1e-9

    # Each allocation should be positive (since volatility > 0)
    for val in allocations.values():
        assert val > 0.0