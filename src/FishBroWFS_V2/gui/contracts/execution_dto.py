"""
Execution OS DTOs – Deterministic, Governance‑First Execution Plans.

All IDs are UUIDv5 deterministic.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Tuple, Optional

# Fixed UUID namespaces for deterministic IDs
EXECUTION_NS = uuid.UUID("11111111-2222-3333-4444-555555555555")
EXECUTION_EVENT_NS = uuid.UUID("66666666-7777-8888-9999-aaaaaaaaaaaa")


def uuidv5_str(ns: uuid.UUID, name: str) -> str:
    """Return deterministic UUIDv5 string."""
    return str(uuid.uuid5(ns, name))


def plan_id_for(season_id: str, risk_profile_id: str, item_ids: list[str]) -> str:
    """Deterministic plan ID from season, risk profile, and sorted portfolio item IDs."""
    items = sorted(item_ids)
    name = "|".join([season_id, risk_profile_id] + items)
    return uuidv5_str(EXECUTION_NS, name)


def event_id_for(plan_id: str, from_state: str, to_state: str, sequence_no: int) -> str:
    """Deterministic event ID from plan, transition, and sequence number."""
    name = f"{plan_id}|{from_state}|{to_state}|{sequence_no}"
    return uuidv5_str(EXECUTION_EVENT_NS, name)


@dataclass(frozen=True)
class ExecutionLeg:
    """A single leg of an execution plan (placeholder for future symbol/timeframe)."""

    strategy_id: str
    instance_id: str
    side: str  # "LONG" | "SHORT" | "BOTH" (future)
    symbol: str  # e.g. "MNQ", "MES" (string only)
    timeframe: str  # e.g. "60m" (string)
    risk_budget_r: float  # R allocation for this leg


@dataclass(frozen=True)
class ExecutionPlan:
    """An execution plan derived from portfolio items."""

    season_id: str
    plan_id: str
    state: str  # DRAFT/REVIEWED/APPROVED/COMMITTED/CANCELLED
    risk_profile_id: str
    portfolio_item_ids: Tuple[str, ...]  # deterministic list of items
    legs: Tuple[ExecutionLeg, ...]

    created_from_snapshot_ref: str  # link to SYSTEM snapshot or portfolio snapshot id
    last_event_id: Optional[str] = None

    @classmethod
    def create(
        cls,
        season_id: str,
        risk_profile_id: str,
        portfolio_item_ids: list[str],
        legs: list[ExecutionLeg],
        snapshot_ref: str,
    ) -> ExecutionPlan:
        """Create a new execution plan in DRAFT state."""
        plan_id = plan_id_for(season_id, risk_profile_id, portfolio_item_ids)
        return cls(
            season_id=season_id,
            plan_id=plan_id,
            state="DRAFT",
            risk_profile_id=risk_profile_id,
            portfolio_item_ids=tuple(sorted(portfolio_item_ids)),
            legs=tuple(sorted(legs, key=lambda l: (l.symbol, l.strategy_id, l.instance_id))),
            created_from_snapshot_ref=snapshot_ref,
            last_event_id=None,
        )


@dataclass(frozen=True)
class ExecutionEvent:
    """Append‑only event recording a state transition of an execution plan."""

    event_id: str
    season_id: str
    plan_id: str
    action: str  # "CREATE" | "REVIEW" | "APPROVE" | "COMMIT" | "CANCEL"
    from_state: str
    to_state: str
    reason: str  # REQUIRED non‑empty
    actor: str  # REQUIRED
    snapshot_ref: str  # REQUIRED (tie to forensic snapshot)
    created_at_utc: str  # server generated
    sequence_no: int

    @classmethod
    def create(
        cls,
        season_id: str,
        plan_id: str,
        action: str,
        from_state: str,
        to_state: str,
        reason: str,
        actor: str,
        snapshot_ref: str,
        sequence_no: int,
        created_at: Optional[datetime] = None,
    ) -> ExecutionEvent:
        """Create a new execution event with deterministic event ID."""
        if created_at is None:
            created_at = datetime.now(timezone.utc)
        event_id = event_id_for(plan_id, from_state, to_state, sequence_no)
        return cls(
            event_id=event_id,
            season_id=season_id,
            plan_id=plan_id,
            action=action,
            from_state=from_state,
            to_state=to_state,
            reason=reason,
            actor=actor,
            snapshot_ref=snapshot_ref,
            created_at_utc=created_at.isoformat(),
            sequence_no=sequence_no,
        )


@dataclass(frozen=True)
class ExecutionStateSnapshot:
    """Derived snapshot of all execution plans and events for a season."""

    season_id: str
    plans: Tuple[ExecutionPlan, ...]
    events: Tuple[ExecutionEvent, ...]

    @classmethod
    def from_events(cls, season_id: str, events: list[ExecutionEvent]) -> ExecutionStateSnapshot:
        """Compute snapshot from ledger events (deterministic)."""
        # Build plan state map
        plan_state = {}
        plan_legs = {}
        plan_last_event = {}
        for ev in events:
            if ev.action == "CREATE":
                # CREATE event should have been created with plan details; we need to store them.
                # For simplicity, we assume CREATE events contain plan data (they don't in this model).
                # We'll need to store plan data separately; for now, we'll skip.
                pass
            # Update plan state
            plan_state[ev.plan_id] = ev.to_state
            plan_last_event[ev.plan_id] = ev.event_id

        # Since we don't have plan details in events, we cannot reconstruct plans.
        # This is a design gap: we need to store plan details in the ledger or have a separate plan store.
        # For MVP, we'll assume plans are stored separately (e.g., in snapshot file).
        # We'll return empty plans for now; the bridge will fill them.
        plans = ()
        return cls(
            season_id=season_id,
            plans=plans,
            events=tuple(sorted(events, key=lambda e: (e.plan_id, e.sequence_no))),
        )


# State machine transition rules
ALLOWED_TRANSITIONS = {
    ("DRAFT", "REVIEWED"): "REVIEW",
    ("REVIEWED", "APPROVED"): "APPROVE",
    ("APPROVED", "COMMITTED"): "COMMIT",
}


def can_transition(from_state: str, action: str) -> str:
    """
    Return the target state for a given action, or raise ValueError if invalid.

    Actions: REVIEW, APPROVE, COMMIT, CANCEL
    """
    if action == "CANCEL":
        if from_state in ("COMMITTED", "CANCELLED"):
            raise ValueError("Cannot cancel terminal state")
        return "CANCELLED"
    for (a, b), act in ALLOWED_TRANSITIONS.items():
        if a == from_state and act == action:
            return b
    raise ValueError(f"Invalid transition: {from_state} via {action}")