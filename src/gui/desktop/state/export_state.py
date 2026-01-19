"""
Export State - SSOT for MultiCharts export step.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict


class ExportState(BaseModel):
    """Immutable state for export actions."""
    last_export_path: Optional[str] = Field(default=None, description="Last export file path")
    last_export_label: Optional[str] = Field(default=None, description="Label for last export")
    confirmed: bool = Field(default=False, description="Whether export step was confirmed")
    last_updated: datetime = Field(default_factory=datetime.now, description="When state was last updated")

    model_config = ConfigDict(frozen=True)


class ExportStateHolder:
    """Singleton state holder for Export step."""
    _instance: Optional["ExportStateHolder"] = None
    _state: ExportState = ExportState()

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def get_state(self) -> ExportState:
        """Get current export state."""
        return self._state

    def update_state(self, **kwargs) -> None:
        """Update export state."""
        current_dict = self._state.model_dump()
        current_dict.update(kwargs)
        current_dict["last_updated"] = datetime.now()
        self._state = ExportState(**current_dict)

    def reset_state(self) -> None:
        """Reset export state to defaults."""
        self._state = ExportState()


export_state = ExportStateHolder()
