"""
Decision Gate State - SSOT for Decision/Gate step.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict


class DecisionGateState(BaseModel):
    """Immutable state for decision gate review."""
    reviewed_job_id: Optional[str] = Field(default=None, description="Last reviewed job id")
    confirmed: bool = Field(default=False, description="Whether decision gate review was confirmed")
    last_updated: datetime = Field(default_factory=datetime.now, description="When state was last updated")

    model_config = ConfigDict(frozen=True)


class DecisionGateStateHolder:
    """Singleton state holder for Decision/Gate step."""
    _instance: Optional["DecisionGateStateHolder"] = None
    _state: DecisionGateState = DecisionGateState()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def get_state(self) -> DecisionGateState:
        """Get current decision gate state."""
        return self._state

    def update_state(self, **kwargs) -> None:
        """Update decision gate state."""
        current_dict = self._state.model_dump()
        current_dict.update(kwargs)
        current_dict["last_updated"] = datetime.now()
        self._state = DecisionGateState(**current_dict)

    def reset_state(self) -> None:
        """Reset decision gate state to defaults."""
        self._state = DecisionGateState()


decision_gate_state = DecisionGateStateHolder()
