"""
Selected Strategies State - SSOT for Strategy Selection step.

Stores the confirmed strategy selection from the Registry tab.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, ConfigDict


class SelectedStrategiesState(BaseModel):
    """Immutable state for selected strategies."""
    selected_strategy_ids: List[str] = Field(default_factory=list, description="Confirmed strategy IDs")
    confirmed: bool = Field(default=False, description="Whether selection was confirmed")
    last_updated: datetime = Field(default_factory=datetime.now, description="When state was last updated")

    model_config = ConfigDict(frozen=True)


class SelectedStrategiesStateHolder:
    """Singleton state holder for Strategy Selection step."""
    _instance: Optional["SelectedStrategiesStateHolder"] = None
    _state: SelectedStrategiesState = SelectedStrategiesState()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def get_state(self) -> SelectedStrategiesState:
        """Get current selected strategies state."""
        return self._state

    def update_state(self, **kwargs) -> None:
        """Update selected strategies state."""
        current_dict = self._state.model_dump()
        current_dict.update(kwargs)
        current_dict["last_updated"] = datetime.now()
        self._state = SelectedStrategiesState(**current_dict)

    def reset_state(self) -> None:
        """Reset selected strategies state to defaults."""
        self._state = SelectedStrategiesState()


selected_strategies_state = SelectedStrategiesStateHolder()
