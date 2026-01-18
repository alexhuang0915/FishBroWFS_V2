"""
Wizard State Definitions - Core state management for wizard workflows.

This module defines the wizard state model that tracks the current state
of a wizard session, including selections, validation results, and progress.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict

from .wizard_steps import WizardStep
from contracts.portfolio.gate_summary_schemas import GateSummaryV1


class WizardType(str, Enum):
    """Type of wizard workflow."""
    RUN_JOB = "run_job"
    GATE_FIX = "gate_fix"


class WizardStatus(str, Enum):
    """Status of wizard session."""
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ERROR = "error"


class ValidationSeverity(str, Enum):
    """Severity level for validation results."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    BLOCKING = "blocking"


class WizardValidationResult(BaseModel):
    """Result of wizard step validation."""
    
    is_valid: bool = Field(..., description="Whether validation passed")
    severity: ValidationSeverity = Field(default=ValidationSeverity.INFO, description="Severity level")
    reason_code: str = Field(..., description="Reason code for validation result")
    message: str = Field(..., description="Human-readable message")
    details: Optional[Dict[str, Any]] = Field(default=None, description="Additional details")
    recommended_action: Optional[str] = Field(default=None, description="Recommended action to fix")
    
    model_config = ConfigDict(frozen=True)


class WizardSelections(BaseModel):
    """User selections in the wizard."""
    
    # Run Job Wizard selections
    selected_strategies: List[str] = Field(default_factory=list, description="Selected strategy IDs")
    selected_timeframes: List[str] = Field(default_factory=list, description="Selected timeframe IDs")
    selected_instrument: Optional[str] = Field(default=None, description="Selected instrument ID")
    selected_mode: Optional[str] = Field(default=None, description="Selected run mode")
    date_range: Optional[Dict[str, str]] = Field(default=None, description="Date range selection")
    season: Optional[str] = Field(default=None, description="Season selection")
    
    # Gate Fix Wizard selections
    selected_job_id: Optional[str] = Field(default=None, description="Selected job ID for gate fix")
    selected_gate_ids: List[str] = Field(default_factory=list, description="Selected gate IDs to fix")
    selected_fixes: List[Dict[str, Any]] = Field(default_factory=list, description="Selected fixes to apply")
    
    model_config = ConfigDict(frozen=True)


class WizardState(BaseModel):
    """Complete state of a wizard session."""
    
    # Core identification
    wizard_id: str = Field(..., description="Unique identifier for wizard session")
    wizard_type: WizardType = Field(..., description="Type of wizard")
    created_at: datetime = Field(default_factory=datetime.now, description="Creation timestamp")
    updated_at: datetime = Field(default_factory=datetime.now, description="Last update timestamp")
    
    # Progress tracking
    current_step: WizardStep = Field(..., description="Current wizard step")
    previous_step: Optional[WizardStep] = Field(default=None, description="Previous wizard step")
    completed_steps: List[WizardStep] = Field(default_factory=list, description="Completed steps")
    status: WizardStatus = Field(default=WizardStatus.ACTIVE, description="Wizard status")
    
    # User selections
    selections: WizardSelections = Field(default_factory=WizardSelections, description="User selections")
    
    # Validation results
    current_validation: Optional[WizardValidationResult] = Field(
        default=None, 
        description="Current step validation result"
    )
    validation_history: List[WizardValidationResult] = Field(
        default_factory=list, 
        description="History of validation results"
    )
    
    # Job tracking (for Run Job Wizard)
    submitted_job_id: Optional[str] = Field(default=None, description="Submitted job ID")
    job_status: Optional[str] = Field(default=None, description="Current job status")
    job_progress: Optional[float] = Field(default=None, description="Job progress (0.0 to 1.0)")
    
    # Gate tracking (for Gate Fix Wizard)
    gate_summary: Optional[GateSummaryV1] = Field(default=None, description="Gate summary for selected job")
    fix_results: List[Dict[str, Any]] = Field(default_factory=list, description="Results of applied fixes")
    
    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    
    model_config = ConfigDict(frozen=True)
    
    def update_step(self, new_step: WizardStep) -> "WizardState":
        """Create a new state with updated step."""
        return self.model_copy(
            update={
                "previous_step": self.current_step,
                "current_step": new_step,
                "updated_at": datetime.now(),
                "completed_steps": self.completed_steps + [self.current_step] 
                if self.current_step not in self.completed_steps 
                else self.completed_steps,
            }
        )
    
    def update_selections(self, **updates) -> "WizardState":
        """Create a new state with updated selections."""
        new_selections = self.selections.model_copy(update=updates)
        return self.model_copy(
            update={
                "selections": new_selections,
                "updated_at": datetime.now(),
            }
        )
    
    def update_validation(self, validation: WizardValidationResult) -> "WizardState":
        """Create a new state with updated validation."""
        return self.model_copy(
            update={
                "current_validation": validation,
                "validation_history": self.validation_history + [validation],
                "updated_at": datetime.now(),
            }
        )
    
    def update_job_info(self, job_id: str, status: str, progress: Optional[float] = None) -> "WizardState":
        """Create a new state with updated job information."""
        return self.model_copy(
            update={
                "submitted_job_id": job_id,
                "job_status": status,
                "job_progress": progress,
                "updated_at": datetime.now(),
            }
        )
    
    def update_gate_summary(self, gate_summary: GateSummaryV1) -> "WizardState":
        """Create a new state with updated gate summary."""
        return self.model_copy(
            update={
                "gate_summary": gate_summary,
                "updated_at": datetime.now(),
            }
        )
    
    def mark_completed(self) -> "WizardState":
        """Mark wizard as completed."""
        return self.model_copy(
            update={
                "status": WizardStatus.COMPLETED,
                "updated_at": datetime.now(),
            }
        )
    
    def mark_cancelled(self) -> "WizardState":
        """Mark wizard as cancelled."""
        return self.model_copy(
            update={
                "status": WizardStatus.CANCELLED,
                "updated_at": datetime.now(),
            }
        )
    
    def mark_error(self, error_message: str) -> "WizardState":
        """Mark wizard as error."""
        return self.model_copy(
            update={
                "status": WizardStatus.ERROR,
                "current_step": WizardStep.WIZARD_ERROR,
                "metadata": {**self.metadata, "error_message": error_message},
                "updated_at": datetime.now(),
            }
        )
    
    def can_proceed(self) -> bool:
        """Check if wizard can proceed to next step."""
        if self.current_validation is None:
            return True
        
        # Check if validation passed or is non-blocking
        if self.current_validation.is_valid:
            return True
        
        # Check severity - INFO and WARNING can proceed, ERROR and BLOCKING cannot
        if self.current_validation.severity in [ValidationSeverity.INFO, ValidationSeverity.WARNING]:
            return True
        
        return False
    
    def get_blocking_reason(self) -> Optional[str]:
        """Get reason why wizard is blocked, if any."""
        if self.current_validation is None:
            return None
        
        if not self.current_validation.is_valid and self.current_validation.severity in [
            ValidationSeverity.ERROR, ValidationSeverity.BLOCKING
        ]:
            return self.current_validation.message
        
        return None


def create_run_job_wizard_state() -> WizardState:
    """Create initial state for Run Job Wizard."""
    return WizardState(
        wizard_id=f"run_job_{datetime.now().timestamp()}",
        wizard_type=WizardType.RUN_JOB,
        current_step=WizardStep.RUN_JOB_SELECT_STRATEGY,
        status=WizardStatus.ACTIVE,
    )


def create_gate_fix_wizard_state() -> WizardState:
    """Create initial state for Gate Fix Wizard."""
    return WizardState(
        wizard_id=f"gate_fix_{datetime.now().timestamp()}",
        wizard_type=WizardType.GATE_FIX,
        current_step=WizardStep.GATE_FIX_SELECT_JOB,
        status=WizardStatus.ACTIVE,
    )