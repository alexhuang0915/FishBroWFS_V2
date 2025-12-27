"""
Execution OS Contract Tests - Determinism, Governance Rules, Zero‑Leakage.
"""

import json
import tempfile
import shutil
from pathlib import Path
import pytest

from FishBroWFS_V2.gui.nicegui.bridge.execution_bridge import (
    ExecutionBridge,
    _compute_snapshot_from_ledger,
    _write_ledger_event,
    _read_ledger,
    _compute_ledger_hash,
    OUTPUTS_ROOT,
    EXECUTION_ROOT,
)
from FishBroWFS_V2.gui.contracts.execution_dto import (
    ExecutionPlan,
    ExecutionLeg,
    ExecutionEvent,
    ExecutionStateSnapshot,
    plan_id_for,
    event_id_for,
    can_transition,
    EXECUTION_NS,
    EXECUTION_EVENT_NS,
)


@pytest.fixture
def temp_execution_dir():
    """Create a temporary execution directory for a season."""
    with tempfile.TemporaryDirectory() as tmp:
        season_dir = Path(tmp) / "execution" / "2026Q1"
        season_dir.mkdir(parents=True)
        # Monkey‑patch the OUTPUTS_ROOT and EXECUTION_ROOT to point to temp directory
        import FishBroWFS_V2.gui.nicegui.bridge.execution_bridge as mod
        original_root = mod.OUTPUTS_ROOT
        original_execution_root = mod.EXECUTION_ROOT
        mod.OUTPUTS_ROOT = Path(tmp)
        mod.EXECUTION_ROOT = Path(tmp) / "execution"
        yield season_dir
        mod.OUTPUTS_ROOT = original_root
        mod.EXECUTION_ROOT = original_execution_root


@pytest.fixture
def bridge(temp_execution_dir):
    """Create ExecutionBridge with temporary storage."""
    return ExecutionBridge()


def test_empty_snapshot(bridge):
    """Empty ledger produces empty snapshot."""
    snapshot = bridge.get_snapshot("2026Q1")
    assert snapshot.season_id == "2026Q1"
    assert snapshot.plans == ()
    assert snapshot.events == ()


def test_deterministic_plan_id():
    """Plan IDs are deterministic across runs."""
    season = "2026Q1"
    risk = "risk_moderate"
    items = ["strategy_a:instance_1", "strategy_b:instance_2"]
    id1 = plan_id_for(season, risk, items)
    id2 = plan_id_for(season, risk, items)
    assert id1 == id2
    # Different items produce different ID
    items2 = ["strategy_a:instance_1"]
    id3 = plan_id_for(season, risk, items2)
    assert id1 != id3
    # Different ordering of same items yields same ID (sorted)
    items3 = ["strategy_b:instance_2", "strategy_a:instance_1"]
    id4 = plan_id_for(season, risk, items3)
    assert id1 == id4


def test_deterministic_event_id():
    """Event IDs are deterministic across runs."""
    plan_id = "plan_123"
    from_state = "DRAFT"
    to_state = "REVIEWED"
    seq = 1
    id1 = event_id_for(plan_id, from_state, to_state, seq)
    id2 = event_id_for(plan_id, from_state, to_state, seq)
    assert id1 == id2
    # Different sequence number yields different ID
    id3 = event_id_for(plan_id, from_state, to_state, 2)
    assert id1 != id3


def test_create_plan_valid(bridge, temp_execution_dir):
    """Create a valid execution plan."""
    plan = bridge.create_plan_from_portfolio(
        season_id="2026Q1",
        portfolio_item_ids=["strategy_a:instance_1", "strategy_b:instance_2"],
        risk_profile_id="risk_moderate",
        reason="Portfolio selection ready for execution.",
        actor="user:test",
    )
    assert isinstance(plan, ExecutionPlan)
    assert plan.season_id == "2026Q1"
    assert plan.state == "DRAFT"
    assert plan.risk_profile_id == "risk_moderate"
    assert len(plan.portfolio_item_ids) == 2
    assert len(plan.legs) == 2
    # Verify ledger file exists and contains a CREATE event
    ledger_path = temp_execution_dir / "execution_events.jsonl"
    assert ledger_path.exists()
    lines = ledger_path.read_text().strip().splitlines()
    assert len(lines) == 1
    parsed = json.loads(lines[0])
    assert parsed["action"] == "CREATE"
    assert parsed["plan_id"] == plan.plan_id
    # Snapshot file should exist
    snapshot_path = temp_execution_dir / "execution_snapshot.json"
    assert snapshot_path.exists()


def test_create_plan_empty_reason_rejected(bridge):
    """Empty reason must be rejected."""
    with pytest.raises(ValueError, match="Reason must be non‑empty"):
        bridge.create_plan_from_portfolio(
            season_id="2026Q1",
            portfolio_item_ids=["s:i"],
            risk_profile_id="risk",
            reason="",
            actor="user:test",
        )


def test_create_plan_empty_portfolio_rejected(bridge):
    """Empty portfolio_item_ids must be rejected."""
    with pytest.raises(ValueError, match="portfolio_item_ids must not be empty"):
        bridge.create_plan_from_portfolio(
            season_id="2026Q1",
            portfolio_item_ids=[],
            risk_profile_id="risk",
            reason="reason",
            actor="user:test",
        )


def test_transition_plan_valid(bridge, temp_execution_dir):
    """Transition a plan through valid states."""
    # First create a plan
    plan = bridge.create_plan_from_portfolio(
        season_id="2026Q1",
        portfolio_item_ids=["s:i"],
        risk_profile_id="risk",
        reason="create",
        actor="user:test",
    )
    # Transition to REVIEWED
    plan2 = bridge.transition_plan(
        season_id="2026Q1",
        plan_id=plan.plan_id,
        action="REVIEW",
        reason="Ready for review",
        actor="user:reviewer",
    )
    assert plan2.state == "REVIEWED"
    # Transition to APPROVED
    plan3 = bridge.transition_plan(
        season_id="2026Q1",
        plan_id=plan.plan_id,
        action="APPROVE",
        reason="Approved by governance",
        actor="user:approver",
    )
    assert plan3.state == "APPROVED"
    # Transition to COMMITTED
    plan4 = bridge.transition_plan(
        season_id="2026Q1",
        plan_id=plan.plan_id,
        action="COMMIT",
        reason="Committed to execution",
        actor="user:executor",
    )
    assert plan4.state == "COMMITTED"
    # Verify ledger has four events
    events = _read_ledger("2026Q1")
    assert len(events) == 4
    assert [e.action for e in events] == ["CREATE", "REVIEW", "APPROVE", "COMMIT"]
    assert [e.to_state for e in events] == ["DRAFT", "REVIEWED", "APPROVED", "COMMITTED"]


def test_transition_plan_invalid_action_rejected(bridge, temp_execution_dir):
    """Invalid action must be rejected."""
    plan = bridge.create_plan_from_portfolio(
        season_id="2026Q1",
        portfolio_item_ids=["s:i"],
        risk_profile_id="risk",
        reason="create",
        actor="user:test",
    )
    with pytest.raises(ValueError, match="Invalid action"):
        bridge.transition_plan(
            season_id="2026Q1",
            plan_id=plan.plan_id,
            action="INVALID",
            reason="reason",
            actor="user:test",
        )


def test_transition_plan_invalid_transition_rejected(bridge, temp_execution_dir):
    """Invalid state transition must be rejected."""
    plan = bridge.create_plan_from_portfolio(
        season_id="2026Q1",
        portfolio_item_ids=["s:i"],
        risk_profile_id="risk",
        reason="create",
        actor="user:test",
    )
    # Cannot APPROVE from DRAFT (must REVIEW first)
    with pytest.raises(ValueError, match="Invalid transition"):
        bridge.transition_plan(
            season_id="2026Q1",
            plan_id=plan.plan_id,
            action="APPROVE",
            reason="skip review",
            actor="user:test",
        )


def test_transition_plan_empty_reason_rejected(bridge, temp_execution_dir):
    """Empty reason must be rejected."""
    plan = bridge.create_plan_from_portfolio(
        season_id="2026Q1",
        portfolio_item_ids=["s:i"],
        risk_profile_id="risk",
        reason="create",
        actor="user:test",
    )
    with pytest.raises(ValueError, match="Reason must be non‑empty"):
        bridge.transition_plan(
            season_id="2026Q1",
            plan_id=plan.plan_id,
            action="REVIEW",
            reason="",
            actor="user:test",
        )


def test_cancel_transition(bridge, temp_execution_dir):
    """CANCEL action transitions to CANCELLED."""
    plan = bridge.create_plan_from_portfolio(
        season_id="2026Q1",
        portfolio_item_ids=["s:i"],
        risk_profile_id="risk",
        reason="create",
        actor="user:test",
    )
    plan2 = bridge.transition_plan(
        season_id="2026Q1",
        plan_id=plan.plan_id,
        action="CANCEL",
        reason="Cancelled by user",
        actor="user:test",
    )
    assert plan2.state == "CANCELLED"
    # Cannot cancel again (terminal state)
    with pytest.raises(ValueError, match="Cannot cancel terminal state"):
        bridge.transition_plan(
            season_id="2026Q1",
            plan_id=plan.plan_id,
            action="CANCEL",
            reason="again",
            actor="user:test",
        )


def test_ledger_hash_stable(bridge, temp_execution_dir):
    """Ledger hash is stable across writes."""
    # Empty ledger hash
    hash1 = _compute_ledger_hash("2026Q1")
    assert hash1 == "empty"

    # Add one event
    bridge.create_plan_from_portfolio(
        season_id="2026Q1",
        portfolio_item_ids=["s:i"],
        risk_profile_id="risk",
        reason="reason",
        actor="user:test",
    )
    hash2 = _compute_ledger_hash("2026Q1")
    assert hash2 != "empty"

    # Add another event, hash changes
    events = _read_ledger("2026Q1")
    plan_id = events[0].plan_id
    bridge.transition_plan("2026Q1", plan_id, "REVIEW", "reason2", "user:test")
    hash3 = _compute_ledger_hash("2026Q1")
    assert hash3 != hash2

    # Re‑compute hash from same ledger should be identical
    hash3b = _compute_ledger_hash("2026Q1")
    assert hash3 == hash3b


def test_snapshot_ordering_deterministic(bridge, temp_execution_dir):
    """Snapshot events are deterministically ordered."""
    # Create two plans in arbitrary order
    plan1 = bridge.create_plan_from_portfolio(
        season_id="2026Q1",
        portfolio_item_ids=["strategy_b:instance_2"],
        risk_profile_id="risk",
        reason="plan1",
        actor="user:test",
    )
    plan2 = bridge.create_plan_from_portfolio(
        season_id="2026Q1",
        portfolio_item_ids=["strategy_a:instance_1"],
        risk_profile_id="risk",
        reason="plan2",
        actor="user:test",
    )
    # Transition plan1
    bridge.transition_plan("2026Q1", plan1.plan_id, "REVIEW", "review", "user:test")
    snapshot = bridge.get_snapshot("2026Q1")
    # Events sorted by (plan_id, sequence_no)
    events = snapshot.events
    assert len(events) == 3
    # Verify ordering: events should be sorted by (plan_id, sequence_no)
    # Compute expected ordering
    sorted_plan_ids = sorted([plan1.plan_id, plan2.plan_id])
    # Determine which plan has which events
    # plan with smaller plan_id will appear first
    first_plan_id = sorted_plan_ids[0]
    second_plan_id = sorted_plan_ids[1]
    # Expect events: CREATE for first_plan_id, CREATE for second_plan_id, REVIEW for first_plan_id
    # (since we only transitioned plan1, which could be first or second depending on plan_id)
    # Let's just verify that each plan's events are sequential and that overall ordering is correct.
    # We'll group by plan_id and check sequence numbers.
    by_plan = {}
    for ev in events:
        by_plan.setdefault(ev.plan_id, []).append(ev)
    for plan_id, evs in by_plan.items():
        seqs = [e.sequence_no for e in evs]
        assert seqs == list(range(1, len(evs) + 1))
    # Additionally, ensure that events are sorted by plan_id then sequence_no
    for i in range(len(events) - 1):
        e1 = events[i]
        e2 = events[i + 1]
        if e1.plan_id == e2.plan_id:
            assert e1.sequence_no < e2.sequence_no
        else:
            assert e1.plan_id < e2.plan_id


def test_frozen_season_protection_stub(bridge, temp_execution_dir):
    """Frozen season protection is a stub (future work)."""
    # Currently no enforcement; just ensure bridge doesn't crash.
    # This test is a placeholder.
    pass


def test_zero_leakage_page_imports():
    """Execution governance page must not import transport clients."""
    import ast
    import os
    page_path = os.path.join(
        os.path.dirname(__file__),
        "..", "..", "src", "FishBroWFS_V2", "gui", "nicegui", "pages", "execution_governance.py"
    )
    with open(page_path, "r") as f:
        tree = ast.parse(f.read())
    # Check for forbidden imports
    forbidden = {"httpx", "requests", "socket", "aiohttp", "websocket"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if any(forbidden in alias.name for forbidden in forbidden):
                    pytest.fail(f"Page imports forbidden transport: {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            if any(forbidden in node.module for forbidden in forbidden):
                pytest.fail(f"Page imports forbidden transport: {node.module}")


def test_snapshot_file_written(bridge, temp_execution_dir):
    """Snapshot JSON file is written after plan creation."""
    bridge.create_plan_from_portfolio(
        season_id="2026Q1",
        portfolio_item_ids=["s:i"],
        risk_profile_id="risk",
        reason="reason",
        actor="user:test",
    )
    snapshot_path = temp_execution_dir / "execution_snapshot.json"
    assert snapshot_path.exists()
    data = json.loads(snapshot_path.read_text())
    assert data["season_id"] == "2026Q1"
    assert len(data["events"]) == 1
    assert data["events"][0]["action"] == "CREATE"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])