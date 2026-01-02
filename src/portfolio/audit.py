"""
Portfolio governance audit trail (Article VI).

Append‑only JSONL logging of all governance actions for auditability.
"""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import json
import os
from typing import Dict, Any, List, Optional


class AuditTrail:
    """Append‑only audit log for portfolio governance events."""

    def __init__(self, root_dir: str = "outputs/portfolio_store") -> None:
        self.root = Path(root_dir)
        self.audit_dir = self.root / "audit"
        self.audit_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = self.audit_dir / "events.jsonl"

    def append(self, event: Dict[str, Any]) -> None:
        """
        Atomically append a single event as a JSON line.

        Guarantees:
        - One line per event (newline‑terminated)
        - File opened in append mode, flushed, fsynced
        - Event dict must be JSON‑serializable
        """
        # Ensure required fields
        if "schema_version" not in event:
            event["schema_version"] = 1
        if "ts_utc" not in event:
            event["ts_utc"] = datetime.now(timezone.utc).isoformat()

        line = json.dumps(event, separators=(",", ":"), ensure_ascii=False) + "\n"

        # Atomic append with flush+fsync
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())

    def read(self) -> List[Dict[str, Any]]:
        """
        Read all events from the log (for testing only).

        Returns:
            List of event dicts in chronological order.
        """
        if not self.log_path.exists():
            return []
        events = []
        with open(self.log_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    # skip malformed lines (should not happen)
                    continue
        return events

    def clear(self) -> None:
        """Remove the log file (for testing only)."""
        if self.log_path.exists():
            self.log_path.unlink()


# ========== Event factory helpers ==========


def make_onboard_event(
    strategy_id: str,
    version_hash: str,
    state_before: Optional[str] = None,
    state_after: str = "INCUBATION",
) -> Dict[str, Any]:
    """Create an ONBOARD event."""
    return {
        "event_type": "ONBOARD",
        "strategy_id": strategy_id,
        "details": {
            "version_hash": version_hash,
            "state_before": state_before,
            "state_after": state_after,
        },
    }


def make_admission_request_event(
    strategy_id: str,
    correlation: Optional[float] = None,
    allowed: Optional[bool] = None,
) -> Dict[str, Any]:
    """Create an ADMISSION_REQUEST event."""
    details = {}
    if correlation is not None:
        details["correlation"] = correlation
    if allowed is not None:
        details["allowed"] = allowed
    return {
        "event_type": "ADMISSION_REQUEST",
        "strategy_id": strategy_id,
        "details": details,
    }


def make_admission_decision_event(
    strategy_id: str,
    allowed: bool,
    correlation: Optional[float] = None,
    reason: Optional[str] = None,
) -> Dict[str, Any]:
    """Create an ADMISSION_DECISION event."""
    details = {"allowed": allowed}
    if correlation is not None:
        details["correlation"] = correlation
    if reason is not None:
        details["reason"] = reason
    return {
        "event_type": "ADMISSION_DECISION",
        "strategy_id": strategy_id,
        "details": details,
    }


def make_activate_event(
    strategy_id: str,
    state_before: str,
    state_after: str,
) -> Dict[str, Any]:
    """Create an ACTIVATE event."""
    return {
        "event_type": "ACTIVATE",
        "strategy_id": strategy_id,
        "details": {
            "state_before": state_before,
            "state_after": state_after,
        },
    }


def make_rebalance_event(
    allocations: Dict[str, float],
    total_capital: float = 1.0,
) -> Dict[str, Any]:
    """Create a REBALANCE event."""
    return {
        "event_type": "REBALANCE",
        "strategy_id": None,
        "details": {
            "allocations": allocations,
            "total_capital": total_capital,
        },
    }


def make_portfolio_history_update_event(
    new_returns_count: int,
    total_returns_count: Optional[int] = None,
) -> Dict[str, Any]:
    """Create a PORTFOLIO_HISTORY_UPDATE event."""
    details = {"new_returns_count": new_returns_count}
    if total_returns_count is not None:
        details["total_returns_count"] = total_returns_count
    return {
        "event_type": "PORTFOLIO_HISTORY_UPDATE",
        "strategy_id": None,
        "details": details,
    }


def make_save_state_event(
    strategy_count: int,
    has_returns: bool,
) -> Dict[str, Any]:
    """Create a SAVE_STATE event."""
    return {
        "event_type": "SAVE_STATE",
        "strategy_id": None,
        "details": {
            "strategy_count": strategy_count,
            "has_returns": has_returns,
        },
    }


def make_snapshot_event(
    tag: str,
    strategy_count: int,
    has_returns: bool,
) -> Dict[str, Any]:
    """Create a SNAPSHOT event."""
    return {
        "event_type": "SNAPSHOT",
        "strategy_id": None,
        "details": {
            "tag": tag,
            "strategy_count": strategy_count,
            "has_returns": has_returns,
        },
    }