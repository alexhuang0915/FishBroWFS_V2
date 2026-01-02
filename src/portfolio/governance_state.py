"""
Portfolio Governance State Machine (Constitution‑compliant).

Implements the lifecycle state machine defined in Article III of the Portfolio Governance Constitution.
Enforces immutability, adjacency, and death‑is‑final rules.
"""
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, Any, Optional, Set, Tuple
from pydantic import BaseModel, Field, ConfigDict, field_validator

from .models.governance_models import StrategyState


# ========== Strategy Record (Pydantic v2) ==========

class StrategyRecord(BaseModel):
    """Immutable record of a strategy's governance state."""
    strategy_id: str = Field(..., description="Unique identifier (e.g., 'S2_001')")
    version_hash: str = Field(..., description="Hash of strategy source + parameters")
    state: StrategyState = Field(..., description="Current lifecycle state")
    config: Dict[str, Any] = Field(
        default_factory=dict,
        description="Frozen configuration parameters (immutable after CANDIDATE)"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp of record creation"
    )
    metrics: Dict[str, float] = Field(
        default_factory=dict,
        description="Performance metrics (updated periodically)"
    )

    model_config = ConfigDict(frozen=False)  # allow updates but enforce immutability via validation

    @field_validator("state")
    @classmethod
    def validate_state_transition(cls, v: StrategyState, info) -> StrategyState:
        # Immutability enforcement is handled by GovernanceStateMachine.apply_update
        return v

    def is_immutable(self) -> bool:
        """Return True if the strategy has passed INCUBATION (i.e., version_hash and config are frozen)."""
        return self.state != StrategyState.INCUBATION


# ========== Governance State Machine ==========

class GovernanceStateMachine:
    """
    Enforces the adjacency list of allowed state transitions.

    Adjacency list derived from Article III of the Constitution:
    - INCUBATION → CANDIDATE
    - CANDIDATE → PAPER_TRADING
    - PAPER_TRADING → LIVE
    - LIVE → PROBATION
    - PROBATION → LIVE
    - PROBATION → RETIRED
    - LIVE → RETIRED
    - PROBATION → FREEZE
    - LIVE → FREEZE
    - FREEZE → RETIRED
    - FREEZE → PROBATION
    - FREEZE → LIVE

    Death is final: RETIRED cannot transition to any other state.
    Promotion ladder: no shortcuts (e.g., INCUBATION → LIVE forbidden).
    """
    _ADJACENCY: Set[Tuple[StrategyState, StrategyState]] = {
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

    @classmethod
    def can_transition(cls, from_state: StrategyState, to_state: StrategyState) -> bool:
        """Return True if the transition is allowed by the adjacency list."""
        return (from_state, to_state) in cls._ADJACENCY

    @classmethod
    def assert_transition(cls, from_state: StrategyState, to_state: StrategyState) -> None:
        """Raise ValueError if the transition is not allowed."""
        if not cls.can_transition(from_state, to_state):
            raise ValueError(
                f"Transition {from_state} → {to_state} is not allowed "
                f"(allowed transitions: {cls._ADJACENCY})"
            )

    @classmethod
    def apply_update(cls, record: StrategyRecord, new_state: StrategyState, **updates) -> StrategyRecord:
        """
        Apply a state transition and optional field updates, enforcing immutability.

        Rules:
        1. Transition must be allowed (assert_transition) unless new_state == record.state (no‑op).
        2. If record.state > INCUBATION (i.e., immutable), version_hash and config cannot be changed.
        3. Updates to other fields (metrics, etc.) are permitted.

        Returns a new StrategyRecord with updated fields (original record is unchanged).
        """
        if new_state != record.state:
            cls.assert_transition(record.state, new_state)

        # Enforce immutability of version_hash and config after INCUBATION
        if record.is_immutable():
            if "version_hash" in updates and updates["version_hash"] != record.version_hash:
                raise ValueError(
                    f"version_hash cannot be changed after INCUBATION (strategy {record.strategy_id})"
                )
            if "config" in updates and updates["config"] != record.config:
                raise ValueError(
                    f"config cannot be changed after INCUBATION (strategy {record.strategy_id})"
                )

        # Build updated dict
        updated = record.model_dump()
        updated["state"] = new_state
        for key, value in updates.items():
            if key in ("strategy_id", "created_at"):
                raise ValueError(f"{key} cannot be updated")
            updated[key] = value

        return StrategyRecord(**updated)


# ========== Convenience Functions ==========

def create_strategy_record(
    strategy_id: str,
    version_hash: str,
    config: Optional[Dict[str, Any]] = None,
    initial_state: StrategyState = StrategyState.INCUBATION,
) -> StrategyRecord:
    """Create a new strategy record with default fields."""
    return StrategyRecord(
        strategy_id=strategy_id,
        version_hash=version_hash,
        state=initial_state,
        config=config or {},
        metrics={},
    )


def transition_strategy(
    record: StrategyRecord,
    to_state: StrategyState,
    **updates,
) -> StrategyRecord:
    """High‑level wrapper that applies a state transition and returns the updated record."""
    return GovernanceStateMachine.apply_update(record, to_state, **updates)