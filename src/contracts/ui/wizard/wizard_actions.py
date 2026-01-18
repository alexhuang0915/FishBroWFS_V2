"""
Wizard Action Definitions - Actions that can be performed in wizard workflows.

This module defines wizard actions and their governance validation,
integrating with v1.7 UI governance state for zero-silent action policies.
"""

from enum import Enum
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict

from .wizard_steps import WizardStep
from .wizard_state import WizardState, WizardValidationResult, ValidationSeverity
from contracts.ui_governance_state import UiActionType, validate_action_for_target


class WizardActionType(str, Enum):
    """Type of wizard action."""
    
    # Navigation actions
    WIZARD_START = "wizard_start"
    WIZARD_NEXT = "wizard_next"
    WIZARD_PREVIOUS = "wizard_previous"
    WIZARD_CANCEL = "wizard_cancel"
    WIZARD_COMPLETE = "wizard_complete"
    
    # Selection actions
    SELECT_STRATEGY = "select_strategy"
    SELECT_TIMEFRAME = "select_timeframe"
    SELECT_INSTRUMENT = "select_instrument"
    SELECT_MODE = "select_mode"
    SELECT_JOB = "select_job"
    SELECT_GATE = "select_gate"
    SELECT_FIX = "select_fix"
    
    # Execution actions
    SUBMIT_JOB = "submit_job"
    APPLY_FIX = "apply_fix"
    VERIFY_FIX = "verify_fix"
    
    # Validation actions
    VALIDATE_STEP = "validate_step"
    FETCH_GATE_SUMMARY = "fetch_gate_summary"
    FETCH_JOB_STATUS = "fetch_job_status"
    
    # UI actions
    SHOW_EXPLANATION = "show_explanation"
    SHOW_RECOMMENDATIONS = "show_recommendations"


class WizardAction(BaseModel):
    """Wizard action with context."""
    
    action_type: WizardActionType = Field(..., description="Type of action")
    target_step: Optional[WizardStep] = Field(default=None, description="Target wizard step")
    context: Dict[str, Any] = Field(default_factory=dict, description="Action context")
    timestamp: float = Field(default_factory=lambda: datetime.now().timestamp(), description="Action timestamp")
    
    model_config = ConfigDict(frozen=True)
    
    def to_ui_action_target(self) -> str:
        """Convert wizard action to UI action target string."""
        # Map wizard actions to UI action targets for governance validation
        mapping = {
            WizardActionType.SUBMIT_JOB: "job_submit",
            WizardActionType.APPLY_FIX: "gate_fix_apply",
            WizardActionType.VERIFY_FIX: "gate_fix_verify",
            WizardActionType.FETCH_GATE_SUMMARY: "gate_summary",
            WizardActionType.FETCH_JOB_STATUS: "job_status",
            WizardActionType.SHOW_EXPLANATION: "explain_view",
            WizardActionType.SHOW_RECOMMENDATIONS: "recommendations_view",
        }
        
        target = mapping.get(self.action_type)
        if target:
            return f"wizard://{target}"
        
        # Default mapping for navigation actions
        return f"wizard://{self.action_type.value}"


class WizardActionDecision(BaseModel):
    """Decision result for wizard action validation."""
    
    allowed: bool = Field(..., description="Whether action is allowed")
    reason_code: str = Field(..., description="Reason code for decision")
    message: str = Field(..., description="Human-readable message")
    severity: ValidationSeverity = Field(default=ValidationSeverity.INFO, description="Severity level")
    recommended_action: Optional[str] = Field(default=None, description="Recommended action if blocked")
    details: Optional[Dict[str, Any]] = Field(default=None, description="Additional details")
    
    # Link to UI governance state
    ui_governance_result: Optional[Dict[str, Any]] = Field(
        default=None, 
        description="Result from UI governance state validation"
    )
    
    model_config = ConfigDict(frozen=True)
    
    @classmethod
    def allowed(cls, reason_code: str = "ACTION_ALLOWED", message: str = "Action allowed") -> "WizardActionDecision":
        """Create an allowed decision."""
        return cls(
            allowed=True,
            reason_code=reason_code,
            message=message,
            severity=ValidationSeverity.INFO,
        )
    
    @classmethod
    def blocked(
        cls, 
        reason_code: str, 
        message: str, 
        severity: ValidationSeverity = ValidationSeverity.ERROR,
        recommended_action: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> "WizardActionDecision":
        """Create a blocked decision."""
        return cls(
            allowed=False,
            reason_code=reason_code,
            message=message,
            severity=severity,
            recommended_action=recommended_action,
            details=details,
        )
    
    @classmethod
    def from_validation_result(cls, validation_result: WizardValidationResult) -> "WizardActionDecision":
        """Create decision from validation result."""
        return cls(
            allowed=validation_result.is_valid,
            reason_code=validation_result.reason_code,
            message=validation_result.message,
            severity=validation_result.severity,
            recommended_action=validation_result.recommended_action,
            details=validation_result.details,
        )


def validate_wizard_action(
    action: WizardAction,
    wizard_state: WizardState,
    ui_context: Optional[Dict[str, Any]] = None
) -> WizardActionDecision:
    """
    Validate a wizard action against current state and UI governance.
    
    This function implements zero-silent validation:
    - Every blocked action has a reason_code → explain
    - Integrates with v1.7 UI governance state
    - Considers wizard-specific business rules
    
    Args:
        action: Wizard action to validate
        wizard_state: Current wizard state
        ui_context: Optional UI context for governance validation
        
    Returns:
        WizardActionDecision with validation result
    """
    from datetime import datetime
    
    # Check UI governance state first (v1.7 integration)
    ui_target = action.to_ui_action_target()
    ui_validation = validate_action_for_target(ui_target, ui_context or {})
    
    if not ui_validation.get("enabled", True):
        return WizardActionDecision.blocked(
            reason_code="UI_GOVERNANCE_BLOCKED",
            message=f"Action blocked by UI governance: {ui_validation.get('reason', 'Unknown reason')}",
            severity=ValidationSeverity.BLOCKING,
            recommended_action="Check UI governance state or contact administrator",
            details={"ui_validation": ui_validation},
        )
    
    # Wizard-specific validation based on action type
    if action.action_type == WizardActionType.WIZARD_NEXT:
        return _validate_next_action(wizard_state, action)
    
    elif action.action_type == WizardActionType.WIZARD_PREVIOUS:
        return _validate_previous_action(wizard_state, action)
    
    elif action.action_type == WizardActionType.SUBMIT_JOB:
        return _validate_submit_job_action(wizard_state, action)
    
    elif action.action_type == WizardActionType.APPLY_FIX:
        return _validate_apply_fix_action(wizard_state, action)
    
    elif action.action_type in [
        WizardActionType.SELECT_STRATEGY,
        WizardActionType.SELECT_TIMEFRAME,
        WizardActionType.SELECT_INSTRUMENT,
        WizardActionType.SELECT_MODE,
        WizardActionType.SELECT_JOB,
        WizardActionType.SELECT_GATE,
        WizardActionType.SELECT_FIX,
    ]:
        return _validate_selection_action(wizard_state, action)
    
    # Default: allow action
    return WizardActionDecision.allowed(
        reason_code="WIZARD_ACTION_ALLOWED",
        message=f"Action {action.action_type.value} allowed",
    )


def _validate_next_action(wizard_state: WizardState, action: WizardAction) -> WizardActionDecision:
    """Validate NEXT navigation action."""
    # Check if current step validation allows proceeding
    if not wizard_state.can_proceed():
        blocking_reason = wizard_state.get_blocking_reason()
        return WizardActionDecision.blocked(
            reason_code="STEP_VALIDATION_FAILED",
            message=f"Cannot proceed: {blocking_reason or 'Validation failed'}",
            severity=ValidationSeverity.BLOCKING,
            recommended_action="Fix validation issues before proceeding",
            details={
                "current_step": wizard_state.current_step,
                "validation": wizard_state.current_validation.model_dump() if wizard_state.current_validation else None,
            },
        )
    
    # Check if wizard is in error state
    if wizard_state.status == wizard_state.status.ERROR:
        return WizardActionDecision.blocked(
            reason_code="WIZARD_IN_ERROR_STATE",
            message="Wizard is in error state, cannot proceed",
            severity=ValidationSeverity.BLOCKING,
            recommended_action="Restart wizard or fix error",
        )
    
    return WizardActionDecision.allowed(
        reason_code="NEXT_STEP_ALLOWED",
        message="Can proceed to next step",
    )


def _validate_previous_action(wizard_state: WizardState, action: WizardAction) -> WizardActionDecision:
    """Validate PREVIOUS navigation action."""
    # Check if there is a previous step to go back to
    if not wizard_state.previous_step:
        return WizardActionDecision.blocked(
            reason_code="NO_PREVIOUS_STEP",
            message="No previous step to go back to",
            severity=ValidationSeverity.WARNING,
            recommended_action="Start over or cancel wizard",
        )
    
    return WizardActionDecision.allowed(
        reason_code="PREVIOUS_STEP_ALLOWED",
        message="Can go back to previous step",
    )


def _validate_submit_job_action(wizard_state: WizardState, action: WizardAction) -> WizardActionDecision:
    """Validate SUBMIT_JOB action."""
    # Check if wizard is in correct state
    if wizard_state.wizard_type != wizard_state.wizard_type.RUN_JOB:
        return WizardActionDecision.blocked(
            reason_code="WRONG_WIZARD_TYPE",
            message="Submit job action only available in Run Job Wizard",
            severity=ValidationSeverity.ERROR,
            recommended_action="Switch to Run Job Wizard",
        )
    
    # Check if all required selections are made
    selections = wizard_state.selections
    if not selections.selected_strategies:
        return WizardActionDecision.blocked(
            reason_code="NO_STRATEGY_SELECTED",
            message="No strategy selected",
            severity=ValidationSeverity.BLOCKING,
            recommended_action="Select at least one strategy",
        )
    
    if not selections.selected_timeframes:
        return WizardActionDecision.blocked(
            reason_code="NO_TIMEFRAME_SELECTED",
            message="No timeframe selected",
            severity=ValidationSeverity.BLOCKING,
            recommended_action="Select at least one timeframe",
        )
    
    if not selections.selected_instrument:
        return WizardActionDecision.blocked(
            reason_code="NO_INSTRUMENT_SELECTED",
            message="No instrument selected",
            severity=ValidationSeverity.BLOCKING,
            recommended_action="Select an instrument",
        )
    
    if not selections.selected_mode:
        return WizardActionDecision.blocked(
            reason_code="NO_MODE_SELECTED",
            message="No run mode selected",
            severity=ValidationSeverity.BLOCKING,
            recommended_action="Select a run mode",
        )
    
    return WizardActionDecision.allowed(
        reason_code="JOB_SUBMISSION_READY",
        message="Job submission ready",
    )


def _validate_apply_fix_action(wizard_state: WizardState, action: WizardAction) -> WizardActionDecision:
    """Validate APPLY_FIX action."""
    # Check if wizard is in correct state
    if wizard_state.wizard_type != wizard_state.wizard_type.GATE_FIX:
        return WizardActionDecision.blocked(
            reason_code="WRONG_WIZARD_TYPE",
            message="Apply fix action only available in Gate Fix Wizard",
            severity=ValidationSeverity.ERROR,
            recommended_action="Switch to Gate Fix Wizard",
        )
    
    # Check if job is selected
    if not wizard_state.selections.selected_job_id:
        return WizardActionDecision.blocked(
            reason_code="NO_JOB_SELECTED",
            message="No job selected for gate fix",
            severity=ValidationSeverity.BLOCKING,
            recommended_action="Select a job with gate failures",
        )
    
    # Check if gates are selected
    if not wizard_state.selections.selected_gate_ids:
        return WizardActionDecision.blocked(
            reason_code="NO_GATES_SELECTED",
            message="No gates selected for fixing",
            severity=ValidationSeverity.BLOCKING,
            recommended_action="Select gates to fix",
        )
    
    # Check if fixes are selected
    if not wizard_state.selections.selected_fixes:
        return WizardActionDecision.blocked(
            reason_code="NO_FIXES_SELECTED",
            message="No fixes selected to apply",
            severity=ValidationSeverity.BLOCKING,
            recommended_action="Select fixes to apply",
        )
    
    return WizardActionDecision.allowed(
        reason_code="FIX_APPLICATION_READY",
        message="Gate fixes ready to apply",
    )


def _validate_selection_action(wizard_state: WizardState, action: WizardAction) -> WizardActionDecision:
    """Validate selection actions."""
    # Basic validation for selection actions
    if not action.context:
        return WizardActionDecision.blocked(
            reason_code="NO_SELECTION_DATA",
            message="No selection data provided",
            severity=ValidationSeverity.WARNING,
            recommended_action="Provide selection data in context",
        )
    
    return WizardActionDecision.allowed(
        reason_code="SELECTION_VALID",
        message="Selection action valid",
    )


# Import datetime at module level for default factory
from datetime import datetime