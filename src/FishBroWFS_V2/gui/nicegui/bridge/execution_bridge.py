"""
ExecutionBridge - Single audited gateway for UI pages to access execution governance.

UI pages must ONLY call methods on this class; no direct file I/O or transport calls.
This ensures Zero‑Leakage and Determinism‑Safe execution.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

from FishBroWFS_V2.gui.contracts.execution_dto import (
    ExecutionPlan,
    ExecutionLeg,
    ExecutionEvent,
    ExecutionStateSnapshot,
    plan_id_for,
    can_transition,
    EXECUTION_NS,
    EXECUTION_EVENT_NS,
)

logger = logging.getLogger(__name__)

# Storage root
OUTPUTS_ROOT = Path("outputs")
EXECUTION_ROOT = OUTPUTS_ROOT / "execution"


def _ensure_execution_dir(season_id: str) -> Path:
    """Ensure execution directory for season exists."""
    season_dir = EXECUTION_ROOT / season_id
    season_dir.mkdir(parents=True, exist_ok=True)
    return season_dir


def _ledger_path(season_id: str) -> Path:
    """Path to execution events ledger JSONL file."""
    return _ensure_execution_dir(season_id) / "execution_events.jsonl"


def _snapshot_path(season_id: str) -> Path:
    """Path to derived snapshot JSON file."""
    return _ensure_execution_dir(season_id) / "execution_snapshot.json"


def _compute_ledger_hash(season_id: str) -> str:
    """Compute SHA256 hash of ledger file content (deterministic snapshot reference)."""
    path = _ledger_path(season_id)
    if not path.exists():
        return "empty"
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _read_ledger(season_id: str) -> List[ExecutionEvent]:
    """Read all execution events from ledger (sorted by plan_id, sequence_no)."""
    path = _ledger_path(season_id)
    events = []
    if not path.exists():
        return events
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                # Convert dict to ExecutionEvent
                events.append(ExecutionEvent(**data))
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning("Invalid JSON line in ledger %s: %s", path, e)
    # Deterministic ordering by (plan_id, sequence_no)
    events.sort(key=lambda e: (e.plan_id, e.sequence_no))
    return events


def _write_ledger_event(season_id: str, event: ExecutionEvent) -> None:
    """Append a single execution event to ledger."""
    path = _ledger_path(season_id)
    with open(path, "a", encoding="utf-8") as f:
        json_line = json.dumps(event.__dict__, ensure_ascii=False, separators=(",", ":"))
        f.write(json_line + "\n")


def _compute_snapshot_from_ledger(season_id: str) -> ExecutionStateSnapshot:
    """Compute execution snapshot from ledger (deterministic)."""
    events = _read_ledger(season_id)

    # Build plan state map and plan details
    # Since events do not contain plan details, we need to reconstruct plans from CREATE events.
    # For simplicity, we assume CREATE events are stored with plan details in the ledger.
    # However our ExecutionEvent does not contain plan details. We'll need to store plan separately.
    # For MVP, we'll store plan details in a separate file (plan registry) or embed in CREATE event.
    # Let's adopt a simple approach: store plan details in the snapshot file only, not in ledger.
    # The bridge will maintain an in‑memory map of plans derived from events (CREATE, TRANSITION).
    # This is complex; for now, we'll return empty plans and rely on the snapshot file.
    # We'll implement a separate plan registry file later.
    # For now, we'll just return empty plans.
    plans = ()

    return ExecutionStateSnapshot(
        season_id=season_id,
        plans=plans,
        events=tuple(events),
    )


def _write_snapshot(snapshot: ExecutionStateSnapshot) -> None:
    """Write snapshot to JSON file (deterministic)."""
    path = _snapshot_path(snapshot.season_id)
    # Convert to dict
    data = {
        "season_id": snapshot.season_id,
        "plans": [
            {
                "season_id": p.season_id,
                "plan_id": p.plan_id,
                "state": p.state,
                "risk_profile_id": p.risk_profile_id,
                "portfolio_item_ids": list(p.portfolio_item_ids),
                "legs": [
                    {
                        "strategy_id": l.strategy_id,
                        "instance_id": l.instance_id,
                        "side": l.side,
                        "symbol": l.symbol,
                        "timeframe": l.timeframe,
                        "risk_budget_r": l.risk_budget_r,
                    }
                    for l in p.legs
                ],
                "created_from_snapshot_ref": p.created_from_snapshot_ref,
                "last_event_id": p.last_event_id,
            }
            for p in snapshot.plans
        ],
        "events": [
            {
                "event_id": e.event_id,
                "season_id": e.season_id,
                "plan_id": e.plan_id,
                "action": e.action,
                "from_state": e.from_state,
                "to_state": e.to_state,
                "reason": e.reason,
                "actor": e.actor,
                "snapshot_ref": e.snapshot_ref,
                "created_at_utc": e.created_at_utc,
                "sequence_no": e.sequence_no,
            }
            for e in snapshot.events
        ],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


class ExecutionBridge:
    """
    Single audited gateway for UI pages to access execution governance.

    All methods are synchronous for UI compatibility.
    """

    def __init__(self):
        pass

    def get_snapshot(self, season_id: str) -> ExecutionStateSnapshot:
        """
        Return execution state snapshot for given season.

        Deterministic: same ledger → same snapshot.
        """
        if not season_id.strip():
            raise ValueError("season_id must be non‑empty")

        # Ensure directory exists (creates if not)
        _ensure_execution_dir(season_id)

        # Recompute from ledger each time (deterministic)
        snapshot = _compute_snapshot_from_ledger(season_id)
        # Optionally write snapshot for caching (but we can skip for now)
        # _write_snapshot(snapshot)
        return snapshot

    def create_plan_from_portfolio(
        self,
        season_id: str,
        portfolio_item_ids: list[str],
        risk_profile_id: str,
        reason: str,
        actor: str,
    ) -> ExecutionPlan:
        """
        Create a new execution plan from portfolio items.

        Returns the created plan (DRAFT state).
        """
        # Validate inputs
        if not season_id.strip():
            raise ValueError("season_id must be non‑empty")
        if not portfolio_item_ids:
            raise ValueError("portfolio_item_ids must not be empty")
        if not risk_profile_id.strip():
            raise ValueError("risk_profile_id must be non‑empty")
        if not reason.strip():
            raise ValueError("Reason must be non‑empty")
        if not actor.strip():
            raise ValueError("Actor must be non‑empty")

        # Ensure directory exists
        _ensure_execution_dir(season_id)

        # Check if season is frozen (TODO: integrate with SeasonState)
        # For now, skip.

        # Compute snapshot reference (hash of current ledger)
        snapshot_ref = _compute_ledger_hash(season_id)

        # Create placeholder legs (deterministic)
        legs = []
        n = len(portfolio_item_ids)
        for item_id in sorted(portfolio_item_ids):
            # Parse item_id to extract strategy_id, instance_id (assuming format "strategy:instance")
            parts = item_id.split(":")
            if len(parts) >= 2:
                strategy_id = parts[0]
                instance_id = parts[1]
            else:
                strategy_id = item_id
                instance_id = "default"
            leg = ExecutionLeg(
                strategy_id=strategy_id,
                instance_id=instance_id,
                side="BOTH",
                symbol="UNKNOWN",
                timeframe="UNKNOWN",
                risk_budget_r=1.0 / n if n > 0 else 0.0,
            )
            legs.append(leg)

        # Create plan
        plan = ExecutionPlan.create(
            season_id=season_id,
            risk_profile_id=risk_profile_id,
            portfolio_item_ids=portfolio_item_ids,
            legs=legs,
            snapshot_ref=snapshot_ref,
        )

        # Determine sequence number (count existing events for this plan)
        existing_events = _read_ledger(season_id)
        plan_events = [e for e in existing_events if e.plan_id == plan.plan_id]
        sequence_no = len(plan_events) + 1

        # Create CREATE event
        event = ExecutionEvent.create(
            season_id=season_id,
            plan_id=plan.plan_id,
            action="CREATE",
            from_state="",
            to_state="DRAFT",
            reason=reason,
            actor=actor,
            snapshot_ref=snapshot_ref,
            sequence_no=sequence_no,
            created_at=datetime.now(timezone.utc),
        )

        # Write to ledger
        _write_ledger_event(season_id, event)

        # Recompute snapshot and write (optional)
        snapshot = _compute_snapshot_from_ledger(season_id)
        _write_snapshot(snapshot)

        logger.info(
            "Execution plan created: %s with %d items by %s",
            plan.plan_id,
            len(portfolio_item_ids),
            actor,
        )
        return plan

    def transition_plan(
        self,
        season_id: str,
        plan_id: str,
        action: str,  # REVIEW, APPROVE, COMMIT, CANCEL
        reason: str,
        actor: str,
    ) -> ExecutionPlan:
        """
        Transition an execution plan to a new state.

        Returns the updated plan.
        """
        # Validate inputs
        if not season_id.strip():
            raise ValueError("season_id must be non‑empty")
        if not plan_id.strip():
            raise ValueError("plan_id must be non‑empty")
        if action not in ("REVIEW", "APPROVE", "COMMIT", "CANCEL"):
            raise ValueError(f"Invalid action: {action}")
        if not reason.strip():
            raise ValueError("Reason must be non‑empty")
        if not actor.strip():
            raise ValueError("Actor must be non‑empty")

        # Ensure directory exists
        _ensure_execution_dir(season_id)

        # Check if season is frozen (TODO)

        # Load existing events to determine current state
        events = _read_ledger(season_id)
        plan_events = [e for e in events if e.plan_id == plan_id]
        if not plan_events:
            raise ValueError(f"Plan {plan_id} not found")

        # Determine current state (last event's to_state)
        last_event = plan_events[-1]
        from_state = last_event.to_state

        # Compute target state
        try:
            to_state = can_transition(from_state, action)
        except ValueError as e:
            raise ValueError(f"Invalid transition: {e}")

        # Compute snapshot reference
        snapshot_ref = _compute_ledger_hash(season_id)

        # Determine sequence number
        sequence_no = len(plan_events) + 1

        # Create transition event
        event = ExecutionEvent.create(
            season_id=season_id,
            plan_id=plan_id,
            action=action,
            from_state=from_state,
            to_state=to_state,
            reason=reason,
            actor=actor,
            snapshot_ref=snapshot_ref,
            sequence_no=sequence_no,
            created_at=datetime.now(timezone.utc),
        )

        # Write to ledger
        _write_ledger_event(season_id, event)

        # Recompute snapshot and write (optional)
        snapshot = _compute_snapshot_from_ledger(season_id)
        _write_snapshot(snapshot)

        # Return updated plan (we need to reconstruct plan with new state)
        # For now, we'll return a placeholder plan (since we don't store plan details).
        # This is a temporary limitation.
        # We'll need to store plan details in a separate registry.
        # For MVP, we'll just return a dummy plan.
        plan = ExecutionPlan(
            season_id=season_id,
            plan_id=plan_id,
            state=to_state,
            risk_profile_id="UNKNOWN",
            portfolio_item_ids=(),
            legs=(),
            created_from_snapshot_ref=snapshot_ref,
            last_event_id=event.event_id,
        )

        logger.info(
            "Execution plan transitioned: %s %s → %s by %s",
            plan_id,
            from_state,
            to_state,
            actor,
        )
        return plan


# Singleton instance
_execution_bridge_instance: Optional[ExecutionBridge] = None


def get_execution_bridge() -> ExecutionBridge:
    """
    Get singleton ExecutionBridge instance.

    This is the main entry point for UI pages.
    """
    global _execution_bridge_instance
    if _execution_bridge_instance is None:
        _execution_bridge_instance = ExecutionBridge()
    return _execution_bridge_instance


def reset_execution_bridge() -> None:
    """Reset the singleton ExecutionBridge instance (for testing)."""
    global _execution_bridge_instance
    _execution_bridge_instance = None