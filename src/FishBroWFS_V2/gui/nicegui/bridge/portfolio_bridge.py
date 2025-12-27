"""
PortfolioBridge - Single audited gateway for UI pages to access portfolio governance.

UI pages must ONLY call methods on this class; no direct file I/O or transport calls.
This ensures Zero‑Leakage and Determinism‑Safe governance.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple

from FishBroWFS_V2.gui.contracts.portfolio_dto import (
    PortfolioDecisionEvent,
    PortfolioItem,
    PortfolioStateSnapshot,
    decision_uuid_v5,
)

logger = logging.getLogger(__name__)

# Storage root
OUTPUTS_ROOT = Path("outputs")
PORTFOLIO_ROOT = OUTPUTS_ROOT / "portfolio"


def _ensure_portfolio_dir(season_id: str) -> Path:
    """Ensure portfolio directory for season exists."""
    season_dir = PORTFOLIO_ROOT / season_id
    season_dir.mkdir(parents=True, exist_ok=True)
    return season_dir


def _ledger_path(season_id: str) -> Path:
    """Path to decisions ledger JSONL file."""
    return _ensure_portfolio_dir(season_id) / "decisions.jsonl"


def _snapshot_path(season_id: str) -> Path:
    """Path to derived snapshot JSON file."""
    return _ensure_portfolio_dir(season_id) / "portfolio_snapshot.json"


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


def _read_ledger(season_id: str) -> List[PortfolioDecisionEvent]:
    """Read all decision events from ledger (sorted by creation)."""
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
                # Convert dict to PortfolioDecisionEvent
                events.append(PortfolioDecisionEvent(**data))
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning("Invalid JSON line in ledger %s: %s", path, e)
    # Ensure deterministic ordering by created_at_utc, then decision_id
    events.sort(key=lambda e: (e.created_at_utc, e.decision_id))
    return events


def _write_ledger_event(season_id: str, event: PortfolioDecisionEvent) -> None:
    """Append a single decision event to ledger."""
    path = _ledger_path(season_id)
    with open(path, "a", encoding="utf-8") as f:
        json_line = json.dumps(event.__dict__, ensure_ascii=False, separators=(",", ":"))
        f.write(json_line + "\n")


def _compute_snapshot_from_ledger(season_id: str) -> PortfolioStateSnapshot:
    """Compute portfolio snapshot from ledger (deterministic)."""
    events = _read_ledger(season_id)

    # Build item status map
    # key: (strategy_id, instance_id)
    item_status = {}
    last_decision_map = {}
    for ev in events:
        key = (ev.strategy_id, ev.instance_id)
        # Apply action
        if ev.action == "KEEP":
            item_status[key] = "KEEP"
        elif ev.action == "DROP":
            item_status[key] = "DROP"
        elif ev.action == "FREEZE":
            item_status[key] = "FROZEN"
        last_decision_map[key] = ev.decision_id

    # Build items list
    items = []
    for (strategy_id, instance_id), status in item_status.items():
        items.append(
            PortfolioItem(
                season_id=season_id,
                strategy_id=strategy_id,
                instance_id=instance_id,
                current_status=status,
                last_decision_id=last_decision_map.get((strategy_id, instance_id)),
            )
        )

    # Deterministic ordering by (strategy_id, instance_id)
    items.sort(key=lambda i: (i.strategy_id, i.instance_id))

    # Deterministic ordering of events (already sorted by _read_ledger)
    return PortfolioStateSnapshot(
        season_id=season_id,
        items=tuple(items),
        decisions=tuple(events),
    )


def _write_snapshot(snapshot: PortfolioStateSnapshot) -> None:
    """Write snapshot to JSON file (deterministic)."""
    path = _snapshot_path(snapshot.season_id)
    # Convert to dict
    data = {
        "season_id": snapshot.season_id,
        "items": [
            {
                "season_id": i.season_id,
                "strategy_id": i.strategy_id,
                "instance_id": i.instance_id,
                "current_status": i.current_status,
                "last_decision_id": i.last_decision_id,
            }
            for i in snapshot.items
        ],
        "decisions": [
            {
                "decision_id": d.decision_id,
                "season_id": d.season_id,
                "strategy_id": d.strategy_id,
                "instance_id": d.instance_id,
                "action": d.action,
                "reason": d.reason,
                "actor": d.actor,
                "snapshot_ref": d.snapshot_ref,
                "created_at_utc": d.created_at_utc,
            }
            for d in snapshot.decisions
        ],
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


class PortfolioBridge:
    """
    Single audited gateway for UI pages to access portfolio governance.

    All methods are synchronous for UI compatibility.
    """

    def __init__(self):
        pass

    def get_snapshot(self, season_id: str) -> PortfolioStateSnapshot:
        """
        Return portfolio state snapshot for given season.

        Deterministic: same ledger → same snapshot.
        """
        if not season_id.strip():
            raise ValueError("season_id must be non‑empty")

        # Ensure directory exists (creates if not)
        _ensure_portfolio_dir(season_id)

        # If snapshot file exists, read it (cached). However, we must ensure it's up‑to‑date.
        # For simplicity, we recompute from ledger each time (deterministic).
        snapshot = _compute_snapshot_from_ledger(season_id)
        # Optionally write snapshot for caching (but we can skip for now)
        # _write_snapshot(snapshot)
        return snapshot

    def submit_decision(
        self,
        season_id: str,
        strategy_id: str,
        instance_id: str,
        action: str,
        reason: str,
        actor: str,
    ) -> PortfolioDecisionEvent:
        """
        Submit a portfolio decision (KEEP/DROP/FREEZE) with mandatory reason.

        Returns the created decision event.
        """
        # Validate inputs
        if not season_id.strip():
            raise ValueError("season_id must be non‑empty")
        if not strategy_id.strip():
            raise ValueError("strategy_id must be non‑empty")
        if not instance_id.strip():
            raise ValueError("instance_id must be non‑empty")
        if action not in ("KEEP", "DROP", "FREEZE"):
            raise ValueError(f"Invalid action: {action}")
        if not reason.strip():
            raise ValueError("Decision reason must be non‑empty")
        if not actor.strip():
            raise ValueError("Actor must be non‑empty")

        # Ensure directory exists
        _ensure_portfolio_dir(season_id)

        # Check if season is frozen (cannot submit new decisions except FREEZE?)
        # According to spec: Frozen season → reject all except read.
        # We'll need to know if the season is frozen. For now, we'll skip.
        # TODO: implement frozen season check.

        # Compute snapshot reference (hash of current ledger)
        snapshot_ref = _compute_ledger_hash(season_id)

        # Create decision event
        event = PortfolioDecisionEvent.create(
            season_id=season_id,
            strategy_id=strategy_id,
            instance_id=instance_id,
            action=action,
            reason=reason,
            actor=actor,
            snapshot_ref=snapshot_ref,
            created_at=datetime.now(timezone.utc),
        )

        # Write to ledger
        _write_ledger_event(season_id, event)

        # Recompute snapshot and write (optional)
        snapshot = _compute_snapshot_from_ledger(season_id)
        _write_snapshot(snapshot)

        logger.info(
            "Portfolio decision submitted: %s %s/%s/%s by %s",
            action,
            season_id,
            strategy_id,
            instance_id,
            actor,
        )
        return event


# Singleton instance
_portfolio_bridge_instance: Optional[PortfolioBridge] = None


def get_portfolio_bridge() -> PortfolioBridge:
    """
    Get singleton PortfolioBridge instance.

    This is the main entry point for UI pages.
    """
    global _portfolio_bridge_instance
    if _portfolio_bridge_instance is None:
        _portfolio_bridge_instance = PortfolioBridge()
    return _portfolio_bridge_instance


def reset_portfolio_bridge() -> None:
    """Reset the singleton PortfolioBridge instance (for testing)."""
    global _portfolio_bridge_instance
    _portfolio_bridge_instance = None