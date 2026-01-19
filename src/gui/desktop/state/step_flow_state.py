"""
Step Flow State - Single Source of Truth for ControlStation step navigation.

Defines the current step in the 7-step workflow. All step transitions must
flow through the ActionRouterService and update this SSOT.
"""

from enum import IntEnum
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict


class StepId(IntEnum):
    """Fixed 7-step workflow identifiers."""
    DATA_PREP = 1
    BACKTEST = 2
    WFS = 3
    STRATEGY = 4
    PORTFOLIO = 5
    DECISION = 6
    EXPORT = 7


STEP_LABELS = {
    StepId.DATA_PREP: "Data Prep",
    StepId.BACKTEST: "Backtest",
    StepId.WFS: "WFS",
    StepId.STRATEGY: "Strategy",
    StepId.PORTFOLIO: "Portfolio",
    StepId.DECISION: "Decision",
    StepId.EXPORT: "Export",
}


class StepFlowState(BaseModel):
    """Immutable state for current step in ControlStation."""
    current_step: StepId = Field(default=StepId.BACKTEST, description="Active workflow step")
    last_updated: datetime = Field(default_factory=datetime.now, description="When state was last updated")

    model_config = ConfigDict(frozen=True)


class StepFlowStateHolder:
    """Singleton state holder for step navigation."""
    _instance: Optional["StepFlowStateHolder"] = None
    _state: StepFlowState = StepFlowState()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def get_state(self) -> StepFlowState:
        """Get current step flow state."""
        return self._state

    def update_state(self, **kwargs) -> None:
        """Update step flow state with new values."""
        current_dict = self._state.model_dump()
        current_dict.update(kwargs)
        current_dict["last_updated"] = datetime.now()
        self._state = StepFlowState(**current_dict)

    def reset_state(self) -> None:
        """Reset step flow state to defaults."""
        self._state = StepFlowState()


step_flow_state = StepFlowStateHolder()
