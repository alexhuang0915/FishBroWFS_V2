"""
Operation Page State - Single Source of Truth for OPERATION tab.

This module defines the immutable state model for the OPERATION page,
following the same pattern as active_run_state.py and UI governance state.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


class RunIntent(BaseModel):
    """Run intent configuration."""
    strategies: List[str] = Field(default_factory=list, description="Selected strategy IDs")
    timeframes: List[str] = Field(default_factory=list, description="Selected timeframe IDs")
    instruments: List[str] = Field(default_factory=list, description="Selected instrument IDs")
    mode: Optional[str] = Field(default=None, description="Selected run mode")
    season: Optional[str] = Field(default=None, description="Selected season")
    start_date: Optional[str] = Field(default=None, description="Start date for backtest/research")
    end_date: Optional[str] = Field(default=None, description="End date for backtest/research")


class DataReadinessSummary(BaseModel):
    """Data readiness summary."""
    data1_status: str = Field(default="UNKNOWN", description="DATA1 readiness status")
    data2_status: str = Field(default="UNKNOWN", description="DATA2 readiness status")
    missing_reasons: List[str] = Field(default_factory=list, description="Reasons for missing data")
    dataset_mapping: Dict[str, str] = Field(default_factory=dict, description="Strategy/instrument/timeframe -> dataset mapping")


class JobTrackerSummary(BaseModel):
    """Job tracker summary."""
    last_job_id: Optional[str] = Field(default=None, description="Last submitted job ID")
    last_job_status: Optional[str] = Field(default=None, description="Last job status")
    last_update_time: Optional[datetime] = Field(default=None, description="When job status was last updated")
    total_jobs: int = Field(default=0, description="Total jobs in tracker")
    running_jobs: int = Field(default=0, description="Number of running jobs")
    pending_jobs: int = Field(default=0, description="Number of pending/queued jobs")
    completed_jobs: int = Field(default=0, description="Number of completed jobs")
    failed_jobs: int = Field(default=0, description="Number of failed jobs")
    job_list: List[Dict[str, Any]] = Field(default_factory=list, description="List of job details")


class OperationPageState(BaseModel):
    """
    Immutable state for OPERATION page.
    
    This is the single source of truth for committed state on the Operation tab.
    Dialog state must be isolated and merged only on Confirm.
    """
    run_intent: RunIntent = Field(default_factory=RunIntent, description="Run intent configuration")
    data_readiness: DataReadinessSummary = Field(default_factory=DataReadinessSummary, description="Data readiness summary")
    job_tracker: JobTrackerSummary = Field(default_factory=JobTrackerSummary, description="Job tracker summary")
    run_intent_confirmed: bool = Field(default=False, description="Whether run intent was confirmed")
    run_disabled_reason: Optional[str] = Field(default=None, description="Reason why RUN STRATEGY is disabled")
    last_updated: datetime = Field(default_factory=datetime.now, description="When state was last updated")
    
    model_config = ConfigDict(frozen=True)  # Immutable state


class OperationPageStateHolder:
    """
    Singleton state holder for OPERATION page.
    
    Similar pattern to active_run_state.py and UI governance state.
    """
    _instance: Optional['OperationPageStateHolder'] = None
    _state: OperationPageState = OperationPageState()
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def get_state(self) -> OperationPageState:
        """Get current OPERATION page state."""
        return self._state
    
    def update_state(self, **kwargs) -> None:
        """
        Update OPERATION page state with new values.
        
        Creates a new immutable state instance.
        """
        current_dict = self._state.model_dump()
        current_dict.update(kwargs)
        current_dict['last_updated'] = datetime.now()
        self._state = OperationPageState(**current_dict)
    
    def reset_state(self) -> None:
        """Reset state to empty defaults."""
        self._state = OperationPageState()


# Global singleton instance
operation_page_state = OperationPageStateHolder()