"""
Portfolio Build State - SSOT for Portfolio Construction step.
"""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, ConfigDict


class PortfolioBuildState(BaseModel):
    """Immutable state for portfolio build configuration and latest build."""
    season: Optional[str] = Field(default=None, description="Selected season")
    timeframe: Optional[str] = Field(default=None, description="Selected timeframe")
    candidate_run_ids: List[str] = Field(default_factory=list, description="Selected candidate run IDs")
    build_job_id: Optional[str] = Field(default=None, description="Latest portfolio build job id")
    portfolio_id: Optional[str] = Field(default=None, description="Latest portfolio id")
    confirmed: bool = Field(default=False, description="Whether build settings were confirmed")
    last_updated: datetime = Field(default_factory=datetime.now, description="When state was last updated")

    model_config = ConfigDict(frozen=True)


class PortfolioBuildStateHolder:
    """Singleton state holder for Portfolio Build step."""
    _instance: Optional["PortfolioBuildStateHolder"] = None
    _state: PortfolioBuildState = PortfolioBuildState()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def get_state(self) -> PortfolioBuildState:
        """Get current portfolio build state."""
        return self._state

    def update_state(self, **kwargs) -> None:
        """Update portfolio build state."""
        current_dict = self._state.model_dump()
        current_dict.update(kwargs)
        current_dict["last_updated"] = datetime.now()
        self._state = PortfolioBuildState(**current_dict)

    def reset_state(self) -> None:
        """Reset portfolio build state to defaults."""
        self._state = PortfolioBuildState()


portfolio_build_state = PortfolioBuildStateHolder()
