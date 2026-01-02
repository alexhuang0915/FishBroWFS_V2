"""
Portfolio governance state machine and in‑memory store.

Implements the lifecycle transitions defined in Article I of the constitution.
"""
from typing import Dict, List, Optional
from datetime import datetime, timezone

from ..models.governance_models import (
    StrategyIdentity,
    StrategyState,
    ReasonCode,
    GovernanceLogEvent,
)
from .governance_logging import append_governance_event, now_utc_iso


# ========== Strategy Record ==========

class StrategyRecord:
    """In‑memory record of a strategy's governance state."""
    def __init__(
        self,
        identity: StrategyIdentity,
        state: StrategyState,
        created_utc: str,
        updated_utc: str,
        last_admission_report: Optional[str] = None,
        last_killswitch_report: Optional[str] = None,
        last_reason: Optional[ReasonCode] = None,
    ):
        self.identity = identity
        self.state = state
        self.created_utc = created_utc
        self.updated_utc = updated_utc
        self.last_admission_report = last_admission_report
        self.last_killswitch_report = last_killswitch_report
        self.last_reason = last_reason

    def to_dict(self) -> dict:
        return {
            "identity": self.identity.model_dump(),
            "state": self.state.value,
            "created_utc": self.created_utc,
            "updated_utc": self.updated_utc,
            "last_admission_report": self.last_admission_report,
            "last_killswitch_report": self.last_killswitch_report,
            "last_reason": self.last_reason.value if self.last_reason else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "StrategyRecord":
        return cls(
            identity=StrategyIdentity(**data["identity"]),
            state=StrategyState(data["state"]),
            created_utc=data["created_utc"],
            updated_utc=data["updated_utc"],
            last_admission_report=data.get("last_admission_report"),
            last_killswitch_report=data.get("last_killswitch_report"),
            last_reason=ReasonCode(data["last_reason"]) if data.get("last_reason") else None,
        )


# ========== Portfolio Governance Store ==========

class PortfolioGovernanceStore:
    """In‑memory store of all strategy records."""
    def __init__(self):
        self._records: Dict[str, StrategyRecord] = {}  # key = identity_key

    def get(self, strategy_key: str) -> Optional[StrategyRecord]:
        """Return the record for a given identity key, or None."""
        return self._records.get(strategy_key)

    def upsert(self, record: StrategyRecord) -> None:
        """Insert or replace a record."""
        key = record.identity.identity_key()
        self._records[key] = record

    def all(self) -> List[StrategyRecord]:
        """Return all records in insertion order (Python 3.7+ preserves insertion order)."""
        return list(self._records.values())

    def count_by_state(self, state: StrategyState) -> int:
        """Count records in a given state."""
        return sum(1 for r in self._records.values() if r.state == state)


# ========== Transition Validation ==========

_ALLOWED_TRANSITIONS = {
    (StrategyState.INCUBATION, StrategyState.CANDIDATE),
    (StrategyState.CANDIDATE, StrategyState.PAPER_TRADING),
    (StrategyState.PAPER_TRADING, StrategyState.LIVE),
    (StrategyState.LIVE, StrategyState.PROBATION),
    (StrategyState.PROBATION, StrategyState.LIVE),
    (StrategyState.PROBATION, StrategyState.RETIRED),
    (StrategyState.LIVE, StrategyState.RETIRED),
    (StrategyState.PROBATION, StrategyState.FREEZE),
    (StrategyState.LIVE, StrategyState.FREEZE),
    (StrategyState.FREEZE, StrategyState.RETIRED),
    (StrategyState.FREEZE, StrategyState.PROBATION),
    (StrategyState.FREEZE, StrategyState.LIVE),
}


def is_transition_allowed(from_state: StrategyState, to_state: StrategyState) -> bool:
    """Return True iff the transition is permitted by the constitution."""
    return (from_state, to_state) in _ALLOWED_TRANSITIONS


# ========== Transition Execution ==========

def transition(
    store: PortfolioGovernanceStore,
    strategy_key: str,
    to_state: StrategyState,
    reason_code: ReasonCode,
    actor: str = "worker",
    attached_artifacts: Optional[List[str]] = None,
    data_fingerprint: Optional[str] = None,
    extra: Optional[dict] = None,
) -> StrategyRecord:
    """
    Move a strategy from its current state to a new state.

    Raises ValueError if the transition is not allowed.
    Appends a GovernanceLogEvent and updates the record's timestamps.

    Returns the updated StrategyRecord.
    """
    record = store.get(strategy_key)
    if record is None:
        raise KeyError(f"No strategy record found for key {strategy_key}")

    from_state = record.state
    if not is_transition_allowed(from_state, to_state):
        raise ValueError(
            f"Transition {from_state} → {to_state} is not allowed "
            f"(allowed: {_ALLOWED_TRANSITIONS})"
        )

    # Update record
    record.state = to_state
    record.updated_utc = now_utc_iso()
    record.last_reason = reason_code
    store.upsert(record)

    # Create log event
    event = GovernanceLogEvent(
        timestamp_utc=now_utc_iso(),
        actor=actor,
        strategy_key=strategy_key,
        from_state=from_state,
        to_state=to_state,
        reason_code=reason_code,
        attached_artifacts=attached_artifacts or [],
        data_fingerprint=data_fingerprint,
        extra=extra or {},
    )
    append_governance_event(event)

    return record


# ========== Helper Functions ==========

def create_new_strategy_record(
    identity: StrategyIdentity,
    initial_state: StrategyState = StrategyState.INCUBATION,
    actor: str = "worker",
) -> StrategyRecord:
    """
    Create a new strategy record and log its creation.

    This is a convenience function for when a strategy first enters governance.
    """
    now = now_utc_iso()
    record = StrategyRecord(
        identity=identity,
        state=initial_state,
        created_utc=now,
        updated_utc=now,
    )
    # Log the creation as a transition from None to initial state
    event = GovernanceLogEvent(
        timestamp_utc=now,
        actor=actor,
        strategy_key=identity.identity_key(),
        from_state=None,
        to_state=initial_state,
        reason_code=ReasonCode.PROMOTE_TO_PAPER,  # placeholder; could be a dedicated reason
        attached_artifacts=[],
        data_fingerprint=identity.data_fingerprint,
        extra={"action": "created"},
    )
    append_governance_event(event)
    return record