"""
Bar Prepare State - Single Source of Truth for BAR PREPARE page.

This module defines the immutable state model for the BAR PREPARE page,
following the same pattern as active_run_state.py and UI governance state.
"""

from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


class PreparePlan(BaseModel):
    """Prepare plan configuration."""
    instruments: List[str] = Field(default_factory=list, description="Selected instruments")
    timeframes: List[str] = Field(default_factory=list, description="Selected timeframes")
    artifacts_preview: List[str] = Field(default_factory=list, description="Preview of planned artifacts (display-only)")


class BarPrepareState(BaseModel):
    """
    Immutable state for BAR PREPARE page.
    
    This is the single source of truth for committed state on Page 1.
    Dialog state must be isolated and merged only on Confirm.
    
    Invariants:
    - derived_instruments == derive_instruments_from_raw(raw_inputs).instruments
    - prepare_plan.instruments should be empty (instruments are derived, not selected)
    """
    raw_inputs: List[str] = Field(default_factory=list, description="Selected raw data files")
    derived_instruments: List[str] = Field(default_factory=list, description="Instruments derived from raw files (auto-computed)")
    prepare_plan: PreparePlan = Field(default_factory=PreparePlan, description="Prepare plan configuration")
    bar_inventory_summary: Optional[Dict[str, Any]] = Field(default=None, description="Read-only BAR inventory summary")
    confirmed: bool = Field(default=False, description="Whether the step was confirmed")
    last_updated: datetime = Field(default_factory=datetime.now, description="When state was last updated")
    
    model_config = ConfigDict(frozen=True)  # Immutable state


class BarPrepareStateHolder:
    """
    Singleton state holder for BAR PREPARE page.
    
    Similar pattern to active_run_state.py and UI governance state.
    """
    _instance: Optional['BarPrepareStateHolder'] = None
    _state: BarPrepareState = BarPrepareState()
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def get_state(self) -> BarPrepareState:
        """Get current BAR PREPARE state."""
        return self._state
    
    def update_state(self, **kwargs) -> None:
        """
        Update BAR PREPARE state with new values.
        
        Creates a new immutable state instance.
        """
        current_dict = self._state.model_dump()
        current_dict.update(kwargs)
        current_dict['last_updated'] = datetime.now()
        self._state = BarPrepareState(**current_dict)
    
    def reset_state(self) -> None:
        """Reset state to empty defaults."""
        self._state = BarPrepareState()


# Global singleton instance
bar_prepare_state = BarPrepareStateHolder()