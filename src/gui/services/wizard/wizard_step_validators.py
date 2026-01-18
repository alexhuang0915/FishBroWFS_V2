"""
Wizard Step Validators - Validation logic for wizard steps.

This module provides step validation for wizard workflows,
implementing zero-silent validation with reason codes → explain.
"""

import logging
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any

from contracts.ui.wizard import (
    WizardState,
    WizardStep,
    WizardType,
    WizardValidationResult,
    ValidationSeverity,
    get_wizard_step_metadata,
    get_next_step,
    get_previous_step,
    requires_validation,
)
from contracts.portfolio.gate_summary_schemas import GateStatus

logger = logging.getLogger(__name__)


class WizardStepValidator(ABC):
    """Abstract base class for wizard step validators."""
    
    @abstractmethod
    def validate_current_step(self, wizard_state: WizardState) -> WizardValidationResult:
        """Validate current wizard step."""
        pass
    
    @abstractmethod
    def validate_step_transition(self, wizard_state: WizardState, target_step: WizardStep) -> WizardValidationResult:
        """Validate transition to target step."""
        pass
    
    @abstractmethod
    def get_next_step(self, wizard_state: WizardState) -> Optional[WizardStep]:
        """Get next step based on current state."""
        pass
    
    @abstractmethod
    def get_previous_step(self, wizard_state: WizardState) -> Optional[WizardStep]:
        """Get previous step based on current state."""
        pass


class RunJobStepValidator(WizardStepValidator):
    """Step validator for Run Job Wizard."""
    
    def validate_current_step(self, wizard_state: WizardState) -> WizardValidationResult:
        """Validate current step in Run Job Wizard."""
        current_step = wizard_state.current_step
        selections = wizard_state.selections
        
        # Check if step requires validation
        if not requires_validation(current_step):
            return WizardValidationResult(
                is_valid=True,
                reason_code="STEP_NO_VALIDATION_REQUIRED",
                message=f"Step {current_step.value} does not require validation",
                severity=ValidationSeverity.INFO,
            )
        
        # Step-specific validation
        if current_step == WizardStep.RUN_JOB_SELECT_STRATEGY:
            return self._validate_select_strategy(selections)
        
        elif current_step == WizardStep.RUN_JOB_SELECT_TIMEFRAME:
            return self._validate_select_timeframe(selections)
        
        elif current_step == WizardStep.RUN_JOB_SELECT_INSTRUMENT:
            return self._validate_select_instrument(selections)
        
        elif current_step == WizardStep.RUN_JOB_SELECT_MODE:
            return self._validate_select_mode(selections)
        
        elif current_step == WizardStep.RUN_JOB_VALIDATE_READINESS:
            return self._validate_readiness(wizard_state)
        
        elif current_step == WizardStep.RUN_JOB_CONFIRM_SUBMISSION:
            return self._validate_confirmation(wizard_state)
        
        # Default validation for other steps
        return WizardValidationResult(
            is_valid=True,
            reason_code="STEP_VALIDATION_PASSED",
            message=f"Step {current_step.value} validation passed",
            severity=ValidationSeverity.INFO,
        )
    
    def validate_step_transition(self, wizard_state: WizardState, target_step: WizardStep) -> WizardValidationResult:
        """Validate transition to target step in Run Job Wizard."""
        current_step = wizard_state.current_step
        
        # Check if target step is valid next step
        expected_next = get_next_step(current_step)
        if expected_next and target_step != expected_next:
            return WizardValidationResult(
                is_valid=False,
                reason_code="INVALID_STEP_TRANSITION",
                message=f"Cannot transition from {current_step.value} to {target_step.value}",
                severity=ValidationSeverity.WARNING,
                recommended_action=f"Expected next step: {expected_next.value}",
            )
        
        # Validate current step before allowing transition
        current_validation = self.validate_current_step(wizard_state)
        if not current_validation.is_valid:
            return current_validation
        
        return WizardValidationResult(
            is_valid=True,
            reason_code="STEP_TRANSITION_VALID",
            message=f"Transition from {current_step.value} to {target_step.value} is valid",
            severity=ValidationSeverity.INFO,
        )
    
    def get_next_step(self, wizard_state: WizardState) -> Optional[WizardStep]:
        """Get next step for Run Job Wizard."""
        current_step = wizard_state.current_step
        
        # Get default next step from metadata
        next_step = get_next_step(current_step)
        
        # Special handling for certain steps
        if current_step == WizardStep.RUN_JOB_VALIDATE_READINESS:
            # Check if readiness validation passed
            validation = self._validate_readiness(wizard_state)
            if not validation.is_valid:
                # Stay on readiness step if validation failed
                return None
        
        return next_step
    
    def get_previous_step(self, wizard_state: WizardState) -> Optional[WizardStep]:
        """Get previous step for Run Job Wizard."""
        return get_previous_step(wizard_state.current_step)
    
    def _validate_select_strategy(self, selections) -> WizardValidationResult:
        """Validate strategy selection."""
        if not selections.selected_strategies:
            return WizardValidationResult(
                is_valid=False,
                reason_code="NO_STRATEGY_SELECTED",
                message="No strategy selected",
                severity=ValidationSeverity.BLOCKING,
                recommended_action="Select at least one strategy",
            )
        
        return WizardValidationResult(
            is_valid=True,
            reason_code="STRATEGY_SELECTION_VALID",
            message=f"Selected {len(selections.selected_strategies)} strategy(ies)",
            severity=ValidationSeverity.INFO,
        )
    
    def _validate_select_timeframe(self, selections) -> WizardValidationResult:
        """Validate timeframe selection."""
        if not selections.selected_timeframes:
            return WizardValidationResult(
                is_valid=False,
                reason_code="NO_TIMEFRAME_SELECTED",
                message="No timeframe selected",
                severity=ValidationSeverity.BLOCKING,
                recommended_action="Select at least one timeframe",
            )
        
        return WizardValidationResult(
            is_valid=True,
            reason_code="TIMEFRAME_SELECTION_VALID",
            message=f"Selected {len(selections.selected_timeframes)} timeframe(s)",
            severity=ValidationSeverity.INFO,
        )
    
    def _validate_select_instrument(self, selections) -> WizardValidationResult:
        """Validate instrument selection."""
        if not selections.selected_instrument:
            return WizardValidationResult(
                is_valid=False,
                reason_code="NO_INSTRUMENT_SELECTED",
                message="No instrument selected",
                severity=ValidationSeverity.BLOCKING,
                recommended_action="Select an instrument",
            )
        
        return WizardValidationResult(
            is_valid=True,
            reason_code="INSTRUMENT_SELECTION_VALID",
            message=f"Selected instrument: {selections.selected_instrument}",
            severity=ValidationSeverity.INFO,
        )
    
    def _validate_select_mode(self, selections) -> WizardValidationResult:
        """Validate mode selection."""
        if not selections.selected_mode:
            return WizardValidationResult(
                is_valid=False,
                reason_code="NO_MODE_SELECTED",
                message="No run mode selected",
                severity=ValidationSeverity.BLOCKING,
                recommended_action="Select a run mode",
            )
        
        # Validate mode value
        valid_modes = ["backtest", "research", "live"]
        if selections.selected_mode.lower() not in valid_modes:
            return WizardValidationResult(
                is_valid=False,
                reason_code="INVALID_MODE_SELECTED",
                message=f"Invalid run mode: {selections.selected_mode}",
                severity=ValidationSeverity.ERROR,
                recommended_action=f"Select one of: {', '.join(valid_modes)}",
            )
        
        return WizardValidationResult(
            is_valid=True,
            reason_code="MODE_SELECTION_VALID",
            message=f"Selected mode: {selections.selected_mode}",
            severity=ValidationSeverity.INFO,
        )
    
    def _validate_readiness(self, wizard_state: WizardState) -> WizardValidationResult:
        """Validate system readiness for job submission."""
        selections = wizard_state.selections
        
        # Check if all required selections are made
        if not all([
            selections.selected_strategies,
            selections.selected_timeframes,
            selections.selected_instrument,
            selections.selected_mode,
        ]):
            return WizardValidationResult(
                is_valid=False,
                reason_code="INCOMPLETE_SELECTIONS",
                message="Incomplete selections for job submission",
                severity=ValidationSeverity.BLOCKING,
                recommended_action="Complete all required selections",
            )
        
        # Check gate summary if available
        if wizard_state.gate_summary:
            gate_status = wizard_state.gate_summary.overall_status
            if gate_status == GateStatus.REJECT:
                return WizardValidationResult(
                    is_valid=False,
                    reason_code="GATE_SUMMARY_REJECTED",
                    message="System gates are rejecting job submission",
                    severity=ValidationSeverity.BLOCKING,
                    recommended_action="Fix gate issues before submitting job",
                )
            elif gate_status == GateStatus.WARN:
                return WizardValidationResult(
                    is_valid=True,
                    reason_code="GATE_SUMMARY_WARNING",
                    message="System gates have warnings but submission is allowed",
                    severity=ValidationSeverity.WARNING,
                    recommended_action="Review gate warnings before proceeding",
                )
        
        return WizardValidationResult(
            is_valid=True,
            reason_code="SYSTEM_READY",
            message="System ready for job submission",
            severity=ValidationSeverity.INFO,
        )
    
    def _validate_confirmation(self, wizard_state: WizardState) -> WizardValidationResult:
        """Validate job confirmation step."""
        # Check if job has been submitted
        if not wizard_state.submitted_job_id:
            return WizardValidationResult(
                is_valid=False,
                reason_code="JOB_NOT_SUBMITTED",
                message="Job has not been submitted yet",
                severity=ValidationSeverity.BLOCKING,
                recommended_action="Submit job before confirmation",
            )
        
        return WizardValidationResult(
            is_valid=True,
            reason_code="JOB_SUBMITTED",
            message=f"Job {wizard_state.submitted_job_id} submitted successfully",
            severity=ValidationSeverity.INFO,
        )


class GateFixStepValidator(WizardStepValidator):
    """Step validator for Gate Fix Wizard."""
    
    def validate_current_step(self, wizard_state: WizardState) -> WizardValidationResult:
        """Validate current step in Gate Fix Wizard."""
        current_step = wizard_state.current_step
        selections = wizard_state.selections
        
        # Check if step requires validation
        if not requires_validation(current_step):
            return WizardValidationResult(
                is_valid=True,
                reason_code="STEP_NO_VALIDATION_REQUIRED",
                message=f"Step {current_step.value} does not require validation",
                severity=ValidationSeverity.INFO,
            )
        
        # Step-specific validation
        if current_step == WizardStep.GATE_FIX_SELECT_JOB:
            return self._validate_select_job(selections, wizard_state)
        
        elif current_step == WizardStep.GATE_FIX_ANALYZE_FAILURE:
            return self._validate_analyze_failure(wizard_state)
        
        elif current_step == WizardStep.GATE_FIX_RECOMMEND_ACTIONS:
            return self._validate_recommendations(wizard_state)
        
        elif current_step == WizardStep.GATE_FIX_APPLY_FIXES:
            return self._validate_apply_fixes(selections)
        
        elif current_step == WizardStep.GATE_FIX_VERIFY_RESULTS:
            return self._validate_verification(wizard_state)
        
        # Default validation for other steps
        return WizardValidationResult(
            is_valid=True,
            reason_code="STEP_VALIDATION_PASSED",
            message=f"Step {current_step.value} validation passed",
            severity=ValidationSeverity.INFO,
        )
    
    def validate_step_transition(self, wizard_state: WizardState, target_step: WizardStep) -> WizardValidationResult:
        """Validate transition to target step in Gate Fix Wizard."""
        current_step = wizard_state.current_step
        
        # Check if target step is valid next step
        expected_next = get_next_step(current_step)
        if expected_next and target_step != expected_next:
            return WizardValidationResult(
                is_valid=False,
                reason_code="INVALID_STEP_TRANSITION",
                message=f"Cannot transition from {current_step.value} to {target_step.value}",
                severity=ValidationSeverity.WARNING,
                recommended_action=f"Expected next step: {expected_next.value}",
            )
        
        # Validate current step before allowing transition
        current_validation = self.validate_current_step(wizard_state)
        if not current_validation.is_valid:
            return current_validation
        
        return WizardValidationResult(
            is_valid=True,
            reason_code="STEP_TRANSITION_VALID",
            message=f"Transition from {current_step.value} to {target_step.value} is valid",
            severity=ValidationSeverity.INFO,
        )
    
    def get_next_step(self, wizard_state: WizardState) -> Optional[WizardStep]:
        """Get next step for Gate Fix Wizard."""
        current_step = wizard_state.current_step
        
        # Get default next step from metadata
        next_step = get_next_step(current_step)
        
        # Special handling for certain steps
        if current_step == WizardStep.GATE_FIX_ANALYZE_FAILURE:
            # Check if we have gate summary to analyze
            if not wizard_state.gate_summary:
                # Stay on analyze step if no gate summary
                return None
        
        return next_step
    
    def get_previous_step(self, wizard_state: WizardState) -> Optional[WizardStep]:
        """Get previous step for Gate Fix Wizard."""
        return get_previous_step(wizard_state.current_step)
    
    def _validate_select_job(self, selections, wizard_state: WizardState) -> WizardValidationResult:
        """Validate job selection."""
        if not selections.selected_job_id:
            return WizardValidationResult(
                is_valid=False,
                reason_code="NO_JOB_SELECTED",
                message="No job selected for gate fix",
                severity=ValidationSeverity.BLOCKING,
                recommended_action="Select a job with gate failures",
            )
        
        # Check if gate summary is available
        if not wizard_state.gate_summary:
            return WizardValidationResult(
                is_valid=False,
                reason_code="GATE_SUMMARY_UNAVAILABLE",
                message="Gate summary not available for selected job",
                severity=ValidationSeverity.ERROR,
                recommended_action="Check job status and try again",
            )
        
        # Check if job has gate failures
        gate_status = wizard_state.gate_summary.overall_status
        if gate_status not in [GateStatus.REJECT, GateStatus.WARN]:
            return WizardValidationResult(
                is_valid=False,
                reason_code="NO_GATE_FAILURES",
                message="Selected job has no gate failures to fix",
                severity=ValidationSeverity.WARNING,
                recommended_action="Select a job with gate failures (REJECT or WARN status)",
            )
        
        return WizardValidationResult(
            is_valid=True,
            reason_code="JOB_SELECTION_VALID",
            message=f"Selected job {selections.selected_job_id} with {gate_status.value} gate status",
            severity=ValidationSeverity.INFO,
        )
    
    def _validate_analyze_failure(self, wizard_state: WizardState) -> WizardValidationResult:
        """Validate failure analysis step."""
        if not wizard_state.gate_summary:
            return WizardValidationResult(
                is_valid=False,
                reason_code="NO_GATE_SUMMARY",
                message="No gate summary available for analysis",
                severity=ValidationSeverity.BLOCKING,
                recommended_action="Select a job and fetch gate summary",
            )
        
        # Check if there are gates to analyze
        failing_gates = [
            gate for gate in wizard_state.gate_summary.gates
            if gate.status in [GateStatus.REJECT, GateStatus.WARN]
        ]
        
        if not failing_gates:
            return WizardValidationResult(
                is_valid=False,
                reason_code="NO_FAILING_GATES",
                message="No failing gates to analyze",
                severity=ValidationSeverity.WARNING,
                recommended_action="Select a job with gate failures",
            )
        
        return WizardValidationResult(
            is_valid=True,
            reason_code="FAILURE_ANALYSIS_VALID",
            message=f"Found {len(failing_gates)} failing gate(s) to analyze",
            severity=ValidationSeverity.INFO,
        )
    
    def _validate_recommendations(self, wizard_state: WizardState) -> WizardValidationResult:
        """Validate recommendations step."""
        # Check if we have failing gates
        if not wizard_state.gate_summary:
            return WizardValidationResult(
                is_valid=False,
                reason_code="NO_GATE_SUMMARY",
                message="No gate summary available for recommendations",
                severity=ValidationSeverity.BLOCKING,
                recommended_action="Analyze gate failures first",
            )
        
        # Check if user has selected gates to fix
        selections = wizard_state.selections
        if not selections.selected_gate_ids:
            return WizardValidationResult(
                is_valid=False,
                reason_code="NO_GATES_SELECTED",
                message="No gates selected for fixing",
                severity=ValidationSeverity.BLOCKING,
                recommended_action="Select gates to fix",
            )
        
        return WizardValidationResult(
            is_valid=True,
            reason_code="RECOMMENDATIONS_VALID",
            message=f"Selected {len(selections.selected_gate_ids)} gate(s) for fixing",
            severity=ValidationSeverity.INFO,
        )
    
    def _validate_apply_fixes(self, selections) -> WizardValidationResult:
        """Validate apply fixes step."""
        if not selections.selected_fixes:
            return WizardValidationResult(
                is_valid=False,
                reason_code="NO_FIXES_SELECTED",
                message="No fixes selected to apply",
                severity=ValidationSeverity.BLOCKING,
                recommended_action="Select fixes to apply",
            )
        
        return WizardValidationResult(
            is_valid=True,
            reason_code="FIXES_SELECTED_VALID",
            message=f"Selected {len(selections.selected_fixes)} fix(es) to apply",
            severity=ValidationSeverity.INFO,
        )
    
    def _validate_verification(self, wizard_state: WizardState) -> WizardValidationResult:
        """Validate verification step."""
        # Check if fixes were applied
        selections = wizard_state.selections
        if not selections.selected_fixes:
            return WizardValidationResult(
                is_valid=False,
                reason_code="NO_FIXES_APPLIED",
                message="No fixes have been applied yet",
                severity=ValidationSeverity.BLOCKING,
                recommended_action="Apply fixes before verification",
            )
        
        # Check if we have results to verify
        if not wizard_state.fix_results:
            return WizardValidationResult(
                is_valid=False,
                reason_code="NO_FIX_RESULTS",
                message="No fix results available for verification",
                severity=ValidationSeverity.BLOCKING,
                recommended_action="Apply fixes and wait for results",
            )
        
        return WizardValidationResult(
            is_valid=True,
            reason_code="VERIFICATION_READY",
            message=f"Ready to verify {len(selections.selected_fixes)} applied fix(es)",
            severity=ValidationSeverity.INFO,
        )


def get_step_validator_for_wizard_type(wizard_type: WizardType) -> WizardStepValidator:
    """Get step validator for wizard type."""
    if wizard_type == WizardType.RUN_JOB:
        return RunJobStepValidator()
    elif wizard_type == WizardType.GATE_FIX:
        return GateFixStepValidator()
    else:
        raise ValueError(f"Unknown wizard type: {wizard_type}")


# Factory function for creating validators
def create_step_validator(wizard_type: WizardType) -> WizardStepValidator:
    """Create a step validator for the given wizard type."""
    return get_step_validator_for_wizard_type(wizard_type)