"""
Wizard Step Definitions - Enumeration of wizard workflow steps.

This module defines the step-by-step progression through wizard workflows.
Each step corresponds to a specific UI screen or logical phase in the wizard.
"""

from enum import Enum
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


class WizardStep(str, Enum):
    """Enumeration of wizard workflow steps."""
    
    # Run Job Wizard Steps
    RUN_JOB_SELECT_STRATEGY = "run_job_select_strategy"
    RUN_JOB_SELECT_TIMEFRAME = "run_job_select_timeframe"
    RUN_JOB_SELECT_INSTRUMENT = "run_job_select_instrument"
    RUN_JOB_SELECT_MODE = "run_job_select_mode"
    RUN_JOB_CONFIGURE_PARAMS = "run_job_configure_params"
    RUN_JOB_VALIDATE_READINESS = "run_job_validate_readiness"
    RUN_JOB_CONFIRM_SUBMISSION = "run_job_confirm_submission"
    RUN_JOB_TRACK_PROGRESS = "run_job_track_progress"
    RUN_JOB_FETCH_GATE_SUMMARY = "run_job_fetch_gate_summary"
    RUN_JOB_COMPLETE = "run_job_complete"
    
    # Gate Fix Wizard Steps
    GATE_FIX_SELECT_JOB = "gate_fix_select_job"
    GATE_FIX_ANALYZE_FAILURE = "gate_fix_analyze_failure"
    GATE_FIX_SHOW_EXPLANATION = "gate_fix_show_explanation"
    GATE_FIX_RECOMMEND_ACTIONS = "gate_fix_recommend_actions"
    GATE_FIX_APPLY_FIXES = "gate_fix_apply_fixes"
    GATE_FIX_VERIFY_RESULTS = "gate_fix_verify_results"
    GATE_FIX_COMPLETE = "gate_fix_complete"
    
    # Common Steps
    WIZARD_START = "wizard_start"
    WIZARD_ERROR = "wizard_error"
    WIZARD_CANCELLED = "wizard_cancelled"


class WizardStepMetadata(BaseModel):
    """Metadata for a wizard step."""
    
    step: WizardStep = Field(..., description="The wizard step")
    title: str = Field(..., description="Human-readable title for the step")
    description: str = Field(..., description="Detailed description of the step")
    is_optional: bool = Field(default=False, description="Whether this step can be skipped")
    requires_validation: bool = Field(default=True, description="Whether validation is required before proceeding")
    next_step: Optional[WizardStep] = Field(default=None, description="Default next step")
    previous_step: Optional[WizardStep] = Field(default=None, description="Default previous step")
    
    model_config = ConfigDict(frozen=True)


# Step metadata registry
WIZARD_STEP_METADATA: Dict[WizardStep, WizardStepMetadata] = {
    # Run Job Wizard Steps
    WizardStep.RUN_JOB_SELECT_STRATEGY: WizardStepMetadata(
        step=WizardStep.RUN_JOB_SELECT_STRATEGY,
        title="Select Strategy",
        description="Choose one or more trading strategies to run",
        is_optional=False,
        requires_validation=True,
        next_step=WizardStep.RUN_JOB_SELECT_TIMEFRAME,
        previous_step=WizardStep.WIZARD_START,
    ),
    WizardStep.RUN_JOB_SELECT_TIMEFRAME: WizardStepMetadata(
        step=WizardStep.RUN_JOB_SELECT_TIMEFRAME,
        title="Select Timeframe",
        description="Choose one or more timeframes for the strategy",
        is_optional=False,
        requires_validation=True,
        next_step=WizardStep.RUN_JOB_SELECT_INSTRUMENT,
        previous_step=WizardStep.RUN_JOB_SELECT_STRATEGY,
    ),
    WizardStep.RUN_JOB_SELECT_INSTRUMENT: WizardStepMetadata(
        step=WizardStep.RUN_JOB_SELECT_INSTRUMENT,
        title="Select Instrument",
        description="Choose the financial instrument to trade",
        is_optional=False,
        requires_validation=True,
        next_step=WizardStep.RUN_JOB_SELECT_MODE,
        previous_step=WizardStep.RUN_JOB_SELECT_TIMEFRAME,
    ),
    WizardStep.RUN_JOB_SELECT_MODE: WizardStepMetadata(
        step=WizardStep.RUN_JOB_SELECT_MODE,
        title="Select Run Mode",
        description="Choose the execution mode (backtest, research, live)",
        is_optional=False,
        requires_validation=True,
        next_step=WizardStep.RUN_JOB_CONFIGURE_PARAMS,
        previous_step=WizardStep.RUN_JOB_SELECT_INSTRUMENT,
    ),
    WizardStep.RUN_JOB_CONFIGURE_PARAMS: WizardStepMetadata(
        step=WizardStep.RUN_JOB_CONFIGURE_PARAMS,
        title="Configure Parameters",
        description="Set additional parameters like date range, season, etc.",
        is_optional=True,
        requires_validation=True,
        next_step=WizardStep.RUN_JOB_VALIDATE_READINESS,
        previous_step=WizardStep.RUN_JOB_SELECT_MODE,
    ),
    WizardStep.RUN_JOB_VALIDATE_READINESS: WizardStepMetadata(
        step=WizardStep.RUN_JOB_VALIDATE_READINESS,
        title="Validate Readiness",
        description="Check system readiness and gate status before submission",
        is_optional=False,
        requires_validation=True,
        next_step=WizardStep.RUN_JOB_CONFIRM_SUBMISSION,
        previous_step=WizardStep.RUN_JOB_CONFIGURE_PARAMS,
    ),
    WizardStep.RUN_JOB_CONFIRM_SUBMISSION: WizardStepMetadata(
        step=WizardStep.RUN_JOB_CONFIRM_SUBMISSION,
        title="Confirm Submission",
        description="Review and confirm job submission",
        is_optional=False,
        requires_validation=True,
        next_step=WizardStep.RUN_JOB_TRACK_PROGRESS,
        previous_step=WizardStep.RUN_JOB_VALIDATE_READINESS,
    ),
    WizardStep.RUN_JOB_TRACK_PROGRESS: WizardStepMetadata(
        step=WizardStep.RUN_JOB_TRACK_PROGRESS,
        title="Track Progress",
        description="Monitor job execution progress",
        is_optional=False,
        requires_validation=False,
        next_step=WizardStep.RUN_JOB_FETCH_GATE_SUMMARY,
        previous_step=WizardStep.RUN_JOB_CONFIRM_SUBMISSION,
    ),
    WizardStep.RUN_JOB_FETCH_GATE_SUMMARY: WizardStepMetadata(
        step=WizardStep.RUN_JOB_FETCH_GATE_SUMMARY,
        title="Fetch Gate Summary",
        description="Retrieve and display gate summary results",
        is_optional=False,
        requires_validation=False,
        next_step=WizardStep.RUN_JOB_COMPLETE,
        previous_step=WizardStep.RUN_JOB_TRACK_PROGRESS,
    ),
    WizardStep.RUN_JOB_COMPLETE: WizardStepMetadata(
        step=WizardStep.RUN_JOB_COMPLETE,
        title="Job Complete",
        description="Job execution completed successfully",
        is_optional=False,
        requires_validation=False,
        next_step=None,
        previous_step=WizardStep.RUN_JOB_FETCH_GATE_SUMMARY,
    ),
    
    # Gate Fix Wizard Steps
    WizardStep.GATE_FIX_SELECT_JOB: WizardStepMetadata(
        step=WizardStep.GATE_FIX_SELECT_JOB,
        title="Select Job",
        description="Choose a job with gate failures to fix",
        is_optional=False,
        requires_validation=True,
        next_step=WizardStep.GATE_FIX_ANALYZE_FAILURE,
        previous_step=WizardStep.WIZARD_START,
    ),
    WizardStep.GATE_FIX_ANALYZE_FAILURE: WizardStepMetadata(
        step=WizardStep.GATE_FIX_ANALYZE_FAILURE,
        title="Analyze Failure",
        description="Analyze gate failure reasons and root causes",
        is_optional=False,
        requires_validation=True,
        next_step=WizardStep.GATE_FIX_SHOW_EXPLANATION,
        previous_step=WizardStep.GATE_FIX_SELECT_JOB,
    ),
    WizardStep.GATE_FIX_SHOW_EXPLANATION: WizardStepMetadata(
        step=WizardStep.GATE_FIX_SHOW_EXPLANATION,
        title="Show Explanation",
        description="Display detailed explanations for gate failures",
        is_optional=False,
        requires_validation=False,
        next_step=WizardStep.GATE_FIX_RECOMMEND_ACTIONS,
        previous_step=WizardStep.GATE_FIX_ANALYZE_FAILURE,
    ),
    WizardStep.GATE_FIX_RECOMMEND_ACTIONS: WizardStepMetadata(
        step=WizardStep.GATE_FIX_RECOMMEND_ACTIONS,
        title="Recommended Actions",
        description="Show recommended actions to fix gate failures",
        is_optional=False,
        requires_validation=True,
        next_step=WizardStep.GATE_FIX_APPLY_FIXES,
        previous_step=WizardStep.GATE_FIX_SHOW_EXPLANATION,
    ),
    WizardStep.GATE_FIX_APPLY_FIXES: WizardStepMetadata(
        step=WizardStep.GATE_FIX_APPLY_FIXES,
        title="Apply Fixes",
        description="Apply selected fixes to resolve gate failures",
        is_optional=False,
        requires_validation=True,
        next_step=WizardStep.GATE_FIX_VERIFY_RESULTS,
        previous_step=WizardStep.GATE_FIX_RECOMMEND_ACTIONS,
    ),
    WizardStep.GATE_FIX_VERIFY_RESULTS: WizardStepMetadata(
        step=WizardStep.GATE_FIX_VERIFY_RESULTS,
        title="Verify Results",
        description="Verify that fixes resolved the gate failures",
        is_optional=False,
        requires_validation=True,
        next_step=WizardStep.GATE_FIX_COMPLETE,
        previous_step=WizardStep.GATE_FIX_APPLY_FIXES,
    ),
    WizardStep.GATE_FIX_COMPLETE: WizardStepMetadata(
        step=WizardStep.GATE_FIX_COMPLETE,
        title="Gate Fix Complete",
        description="Gate failures have been successfully resolved",
        is_optional=False,
        requires_validation=False,
        next_step=None,
        previous_step=WizardStep.GATE_FIX_VERIFY_RESULTS,
    ),
    
    # Common Steps
    WizardStep.WIZARD_START: WizardStepMetadata(
        step=WizardStep.WIZARD_START,
        title="Wizard Start",
        description="Starting point for wizard workflows",
        is_optional=False,
        requires_validation=False,
        next_step=None,  # Depends on wizard type
        previous_step=None,
    ),
    WizardStep.WIZARD_ERROR: WizardStepMetadata(
        step=WizardStep.WIZARD_ERROR,
        title="Error",
        description="Wizard encountered an error",
        is_optional=False,
        requires_validation=False,
        next_step=None,
        previous_step=None,
    ),
    WizardStep.WIZARD_CANCELLED: WizardStepMetadata(
        step=WizardStep.WIZARD_CANCELLED,
        title="Cancelled",
        description="Wizard was cancelled by user",
        is_optional=False,
        requires_validation=False,
        next_step=None,
        previous_step=None,
    ),
}


def get_wizard_step_metadata(step: WizardStep) -> WizardStepMetadata:
    """Get metadata for a wizard step."""
    return WIZARD_STEP_METADATA[step]


def get_next_step(current_step: WizardStep) -> Optional[WizardStep]:
    """Get the default next step for a given step."""
    metadata = get_wizard_step_metadata(current_step)
    return metadata.next_step


def get_previous_step(current_step: WizardStep) -> Optional[WizardStep]:
    """Get the default previous step for a given step."""
    metadata = get_wizard_step_metadata(current_step)
    return metadata.previous_step


def is_step_optional(step: WizardStep) -> bool:
    """Check if a step is optional."""
    metadata = get_wizard_step_metadata(step)
    return metadata.is_optional


def requires_validation(step: WizardStep) -> bool:
    """Check if a step requires validation before proceeding."""
    metadata = get_wizard_step_metadata(step)
    return metadata.requires_validation