"""
Portfolio Data Transfer Objects (DTOs) for Governance‑First Portfolio OS.

All DTOs are frozen (immutable) and have deterministic ordering.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional, Tuple


# Deterministic UUID namespace for portfolio decisions
PORTFOLIO_NS = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")


def decision_uuid_v5(fields: list[str]) -> str:
    """Generate deterministic UUIDv5 from concatenated fields."""
    name = "|".join(fields)
    return str(uuid.uuid5(PORTFOLIO_NS, name))


@dataclass(frozen=True)
class PortfolioItem:
    """Portfolio item snapshot (immutable identity)."""

    season_id: str
    strategy_id: str
    instance_id: str

    current_status: str  # "CANDIDATE" | "KEEP" | "DROP" | "FROZEN"
    last_decision_id: Optional[str]  # decision_id of the last decision affecting this item


@dataclass(frozen=True)
class PortfolioDecisionEvent:
    """Portfolio decision event (append‑only ledger)."""

    decision_id: str  # deterministic UUIDv5
    season_id: str
    strategy_id: str
    instance_id: str

    action: str  # "KEEP" | "DROP" | "FREEZE"
    reason: str  # REQUIRED, non‑empty
    actor: str  # e.g. "user:huang", "system:rule_x"

    snapshot_ref: str  # snapshot hash / id
    created_at_utc: str  # ISO string (server generated, stable)

    @classmethod
    def create(
        cls,
        season_id: str,
        strategy_id: str,
        instance_id: str,
        action: str,
        reason: str,
        actor: str,
        snapshot_ref: str,
        created_at: Optional[datetime] = None,
    ) -> PortfolioDecisionEvent:
        """Create a new decision event with deterministic ID."""
        if not reason.strip():
            raise ValueError("Decision reason must be non‑empty")
        if action not in ("KEEP", "DROP", "FREEZE"):
            raise ValueError(f"Invalid action: {action}")

        if created_at is None:
            created_at = datetime.now(timezone.utc)
        created_at_utc = created_at.isoformat()

        # Deterministic ID from fields (excluding snapshot_ref and created_at)
        fields = [
            season_id,
            strategy_id,
            instance_id,
            action,
            reason,
            actor,
            snapshot_ref,
            created_at_utc,
        ]
        decision_id = decision_uuid_v5(fields)

        return cls(
            decision_id=decision_id,
            season_id=season_id,
            strategy_id=strategy_id,
            instance_id=instance_id,
            action=action,
            reason=reason,
            actor=actor,
            snapshot_ref=snapshot_ref,
            created_at_utc=created_at_utc,
        )


@dataclass(frozen=True)
class PortfolioStateSnapshot:
    """Portfolio state snapshot (derived from ledger)."""

    season_id: str
    items: Tuple[PortfolioItem, ...]  # deterministic ordering
    decisions: Tuple[PortfolioDecisionEvent, ...]  # deterministic ordering

    @classmethod
    def empty(cls, season_id: str) -> PortfolioStateSnapshot:
        """Return an empty snapshot for a season."""
        return cls(season_id=season_id, items=(), decisions=())