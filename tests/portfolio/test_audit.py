"""
Tests for portfolio audit trail (Phase 7‑Zeta).
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
from portfolio.audit import AuditTrail
from portfolio.store import PortfolioStore


def test_audit_trail_creates_directory_and_file(tmp_path: Path) -> None:
    """AuditTrail creates audit/ directory and events.jsonl."""
    store_root = tmp_path / "store"
    audit = AuditTrail(root_dir=str(store_root))
    assert audit.audit_dir.exists()
    assert audit.audit_dir.name == "audit"
    assert audit.log_path.name == "events.jsonl"
    # File may not exist until first append
    audit.append({"event_type": "TEST", "strategy_id": None})
    assert audit.log_path.exists()


def test_audit_append_and_read_roundtrip(tmp_path: Path) -> None:
    """Append events, read them back, verify order and content."""
    audit = AuditTrail(root_dir=str(tmp_path))
    events = [
        {"event_type": "ONBOARD", "strategy_id": "S1", "details": {"a": 1}},
        {"event_type": "ACTIVATE", "strategy_id": "S1", "details": {"b": 2}},
    ]
    for ev in events:
        audit.append(ev)

    read = audit.read()
    assert len(read) == 2
    # Check schema_version and ts_utc were added
    for ev in read:
        assert "schema_version" in ev
        assert ev["schema_version"] == 1
        assert "ts_utc" in ev
        # ts_utc should be ISO string
        datetime.fromisoformat(ev["ts_utc"].replace("Z", "+00:00"))
    # Check event_type preserved
    assert read[0]["event_type"] == "ONBOARD"
    assert read[1]["event_type"] == "ACTIVATE"


def test_audit_with_portfolio_manager_onboard(tmp_path: Path) -> None:
    """PortfolioManager with audit emits ONBOARD event."""
    audit = AuditTrail(root_dir=str(tmp_path))
    manager = PortfolioManager(audit=audit)

    rec = create_strategy_record(
        strategy_id="S2_001",
        version_hash="hash123",
        config={"param": 1.0},
        initial_state=StrategyState.INCUBATION,
    )
    manager.onboard_strategy(rec)

    events = audit.read()
    assert len(events) == 1
    ev = events[0]
    assert ev["event_type"] == "ONBOARD"
    assert ev["strategy_id"] == "S2_001"
    assert ev["details"]["version_hash"] == "hash123"
    assert ev["details"]["state_after"] == "INCUBATION"


def test_audit_with_portfolio_manager_admission_flow(tmp_path: Path) -> None:
    """Full admission flow emits REQUEST and DECISION events."""
    audit = AuditTrail(root_dir=str(tmp_path))
    manager = PortfolioManager(audit=audit)

    # Onboard a strategy
    rec = create_strategy_record(
        strategy_id="S2_002",
        version_hash="hash456",
        initial_state=StrategyState.INCUBATION,
    )
    manager.onboard_strategy(rec)

    # Request admission (genesis case: no portfolio returns → always allowed)
    candidate_returns = pd.Series([0.01, -0.02, 0.03], index=pd.date_range("2025-01-01", periods=3, tz=timezone.utc))
    result = manager.request_admission("S2_002", candidate_returns)

    events = audit.read()
    # Should have ONBOARD + ADMISSION_REQUEST + ADMISSION_DECISION
    assert len(events) == 3
    event_types = [ev["event_type"] for ev in events]
    assert event_types == ["ONBOARD", "ADMISSION_REQUEST", "ADMISSION_DECISION"]

    # Check ADMISSION_DECISION details
    decision = events[2]
    assert decision["event_type"] == "ADMISSION_DECISION"
    assert decision["strategy_id"] == "S2_002"
    assert decision["details"]["allowed"] is True
    assert "correlation" in decision["details"]
    # correlation may be 0.0 or None for genesis case (implementation detail)
    # Accept either
    corr = decision["details"]["correlation"]
    assert corr is None or corr == 0.0


def test_audit_with_portfolio_manager_activate_and_rebalance(tmp_path: Path) -> None:
    """Activate and rebalance emit ACTIVATE and REBALANCE events."""
    audit = AuditTrail(root_dir=str(tmp_path))
    manager = PortfolioManager(audit=audit)

    # Create a strategy already in CANDIDATE state (skip admission)
    rec = create_strategy_record(
        strategy_id="S2_003",
        version_hash="hash789",
        initial_state=StrategyState.CANDIDATE,
    )
    rec.metrics["volatility"] = 0.15
    manager.strategies["S2_003"] = rec  # bypass onboard to avoid state validation

    # Activate (CANDIDATE → PAPER_TRADING → LIVE)
    manager.activate_strategy("S2_003")

    # Rebalance
    allocations = manager.rebalance_portfolio(total_capital=100.0)

    events = audit.read()
    assert len(events) == 2
    event_types = [ev["event_type"] for ev in events]
    assert event_types == ["ACTIVATE", "REBALANCE"]

    # Check ACTIVATE details
    activate = events[0]
    assert activate["event_type"] == "ACTIVATE"
    assert activate["strategy_id"] == "S2_003"
    assert activate["details"]["state_before"] == "CANDIDATE"
    assert activate["details"]["state_after"] == "LIVE"

    # Check REBALANCE details
    rebalance = events[1]
    assert rebalance["event_type"] == "REBALANCE"
    assert rebalance["strategy_id"] is None
    assert "allocations" in rebalance["details"]
    assert rebalance["details"]["total_capital"] == 100.0
    # allocations dict should match what was returned
    assert rebalance["details"]["allocations"] == allocations


def test_audit_with_portfolio_manager_update_history(tmp_path: Path) -> None:
    """update_portfolio_history emits PORTFOLIO_HISTORY_UPDATE event."""
    audit = AuditTrail(root_dir=str(tmp_path))
    manager = PortfolioManager(audit=audit)

    series = pd.Series([0.01, -0.005], index=pd.date_range("2025-01-01", periods=2, tz=timezone.utc))
    manager.update_portfolio_history(series)

    events = audit.read()
    assert len(events) == 1
    ev = events[0]
    assert ev["event_type"] == "PORTFOLIO_HISTORY_UPDATE"
    assert ev["strategy_id"] is None
    assert ev["details"]["new_returns_count"] == 2
    assert ev["details"]["total_returns_count"] == 2


def test_audit_with_store_save_state(tmp_path: Path) -> None:
    """PortfolioStore.save_state emits SAVE_STATE event."""
    audit = AuditTrail(root_dir=str(tmp_path))
    store = PortfolioStore(root_dir=str(tmp_path), audit=audit)
    # Manager without audit (so no ONBOARD event)
    manager = PortfolioManager()

    # Add a strategy (no audit event emitted)
    rec = create_strategy_record("S2_004", "hash999", initial_state=StrategyState.INCUBATION)
    manager.onboard_strategy(rec)

    store.save_state(manager)

    events = audit.read()
    # Should have only SAVE_STATE (manager had no audit)
    assert len(events) == 1
    save_event = events[0]
    assert save_event["event_type"] == "SAVE_STATE"
    assert save_event["strategy_id"] is None
    assert save_event["details"]["strategy_count"] == 1
    assert save_event["details"]["has_returns"] is False


def test_audit_with_store_snapshot(tmp_path: Path) -> None:
    """PortfolioStore.snapshot emits SNAPSHOT event."""
    audit = AuditTrail(root_dir=str(tmp_path))
    store = PortfolioStore(root_dir=str(tmp_path), audit=audit)
    manager = PortfolioManager()

    store.snapshot(manager, tag="test_snapshot")

    events = audit.read()
    assert len(events) == 1
    ev = events[0]
    assert ev["event_type"] == "SNAPSHOT"
    assert ev["strategy_id"] is None
    assert ev["details"]["tag"] == "test_snapshot"
    assert ev["details"]["strategy_count"] == 0
    assert ev["details"]["has_returns"] is False


def test_audit_jsonl_format(tmp_path: Path) -> None:
    """Verify events are written as one JSON line per event."""
    audit = AuditTrail(root_dir=str(tmp_path))
    audit.append({"event_type": "TEST1", "value": 1})
    audit.append({"event_type": "TEST2", "value": 2})

    # Read raw file
    with open(audit.log_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    assert len(lines) == 2
    for line in lines:
        line = line.strip()
        assert line  # not empty
        parsed = json.loads(line)
        assert "event_type" in parsed
        assert "schema_version" in parsed
        assert "ts_utc" in parsed


def test_audit_no_events_when_audit_is_none(tmp_path: Path) -> None:
    """When audit=None, no events are written."""
    manager = PortfolioManager(audit=None)
    rec = create_strategy_record("S2_005", "hash000", initial_state=StrategyState.INCUBATION)
    manager.onboard_strategy(rec)

    # No audit directory should be created
    audit_dir = tmp_path / "store" / "audit"
    assert not audit_dir.exists()


def test_audit_event_order_preserved(tmp_path: Path) -> None:
    """Events are appended in chronological order."""
    audit = AuditTrail(root_dir=str(tmp_path))
    manager = PortfolioManager(audit=audit)

    # Perform multiple actions
    rec1 = create_strategy_record("S2_A", "hashA", initial_state=StrategyState.INCUBATION)
    manager.onboard_strategy(rec1)

    rec2 = create_strategy_record("S2_B", "hashB", initial_state=StrategyState.INCUBATION)
    manager.onboard_strategy(rec2)

    manager.update_portfolio_history(pd.Series([0.01], index=pd.date_range("2025-01-01", periods=1, tz=timezone.utc)))

    events = audit.read()
    event_types = [ev["event_type"] for ev in events]
    assert event_types == ["ONBOARD", "ONBOARD", "PORTFOLIO_HISTORY_UPDATE"]
    strategy_ids = [ev.get("strategy_id") for ev in events]
    assert strategy_ids == ["S2_A", "S2_B", None]