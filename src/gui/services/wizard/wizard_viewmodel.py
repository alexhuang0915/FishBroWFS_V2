"""
Wizard ViewModel - Core business logic for wizard workflows.

This service manages wizard state, validates actions, and orchestrates
wizard workflows with zero-silent validation and action gating.
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass, field

from contracts.ui.wizard import (
    WizardState,
    WizardStep,
    WizardType,
    WizardStatus,
    WizardAction,
    WizardActionType,
    WizardActionDecision,
    WizardValidationResult,
    ValidationSeverity,
    create_run_job_wizard_state,
    create_gate_fix_wizard_state,
    validate_wizard_action,
)
from contracts.ui_governance_state import validate_action_for_target
from contracts.portfolio.gate_reason_explain import get_gate_reason_explanation

from gui.services.supervisor_client import submit_job as supervisor_submit_job
from gui.services.cross_job_gate_summary_service import get_cross_job_gate_summary_service
from gui.services.job_lifecycle_service import JobLifecycleService

from .wizard_step_validators import get_step_validator_for_wizard_type

logger = logging.getLogger(__name__)


@dataclass
class WizardViewModel:
    """ViewModel for wizard workflows."""
    
    # Current wizard state
    state: WizardState
    
    # Services
    job_lifecycle_service: JobLifecycleService = field(default_factory=JobLifecycleService)
    gate_summary_service: Any = field(default_factory=lambda: get_cross_job_gate_summary_service())
    
    # Callbacks for UI updates
    on_state_changed: Optional[Callable[[WizardState], None]] = None
    on_action_validated: Optional[Callable[[WizardAction, WizardActionDecision], None]] = None
    on_error: Optional[Callable[[str, Dict[str, Any]], None]] = None
    
    def __post_init__(self):
        """Initialize after dataclass creation."""
        # Get step validator for wizard type
        self.step_validator = get_step_validator_for_wizard_type(self.state.wizard_type)
    
    @classmethod
    def create_run_job_wizard(cls) -> "WizardViewModel":
        """Create viewmodel for Run Job Wizard."""
        state = create_run_job_wizard_state()
        return cls(state=state)
    
    @classmethod
    def create_gate_fix_wizard(cls) -> "WizardViewModel":
        """Create viewmodel for Gate Fix Wizard."""
        state = create_gate_fix_wizard_state()
        return cls(state=state)
    
    def handle_action(self, action: WizardAction, ui_context: Optional[Dict[str, Any]] = None) -> bool:
        """
        Handle a wizard action with validation and execution.
        
        This implements zero-silent validation:
        1. Validate action against UI governance state (v1.7)
        2. Validate action against wizard business rules
        3. Execute action if allowed
        4. Update state and notify UI
        
        Args:
            action: Wizard action to handle
            ui_context: Optional UI context for governance validation
            
        Returns:
            bool: True if action was handled successfully, False otherwise
        """
        try:
            # Step 1: Validate action
            validation_result = validate_wizard_action(action, self.state, ui_context)
            
            # Notify UI about validation result
            if self.on_action_validated:
                self.on_action_validated(action, validation_result)
            
            # Step 2: Check if action is allowed
            if not validation_result.allowed:
                logger.warning(
                    f"Wizard action blocked: {action.action_type.value}, "
                    f"reason: {validation_result.reason_code}"
                )
                return False
            
            # Step 3: Execute action based on type
            success = self._execute_action(action, validation_result)
            
            if success:
                logger.debug(f"Wizard action executed: {action.action_type.value}")
            else:
                logger.error(f"Wizard action execution failed: {action.action_type.value}")
            
            return success
            
        except Exception as e:
            error_msg = f"Failed to handle wizard action {action.action_type.value}: {e}"
            logger.exception(error_msg)
            
            # Update state to error
            self.state = self.state.mark_error(error_msg)
            self._notify_state_changed()
            
            # Notify UI about error
            if self.on_error:
                self.on_error(error_msg, {"action": action.model_dump(), "exception": str(e)})
            
            return False
    
    def _execute_action(self, action: WizardAction, validation_result: WizardActionDecision) -> bool:
        """Execute a validated wizard action."""
        action_type = action.action_type
        
        if action_type == WizardActionType.WIZARD_NEXT:
            return self._execute_next_action(action)
        
        elif action_type == WizardActionType.WIZARD_PREVIOUS:
            return self._execute_previous_action(action)
        
        elif action_type == WizardActionType.WIZARD_CANCEL:
            return self._execute_cancel_action(action)
        
        elif action_type == WizardActionType.WIZARD_COMPLETE:
            return self._execute_complete_action(action)
        
        elif action_type == WizardActionType.SELECT_STRATEGY:
            return self._execute_select_strategy(action)
        
        elif action_type == WizardActionType.SELECT_TIMEFRAME:
            return self._execute_select_timeframe(action)
        
        elif action_type == WizardActionType.SELECT_INSTRUMENT:
            return self._execute_select_instrument(action)
        
        elif action_type == WizardActionType.SELECT_MODE:
            return self._execute_select_mode(action)
        
        elif action_type == WizardActionType.SELECT_JOB:
            return self._execute_select_job(action)
        
        elif action_type == WizardActionType.SELECT_GATE:
            return self._execute_select_gate(action)
        
        elif action_type == WizardActionType.SELECT_FIX:
            return self._execute_select_fix(action)
        
        elif action_type == WizardActionType.SUBMIT_JOB:
            return self._execute_submit_job(action)
        
        elif action_type == WizardActionType.APPLY_FIX:
            return self._execute_apply_fix(action)
        
        elif action_type == WizardActionType.VERIFY_FIX:
            return self._execute_verify_fix(action)
        
        elif action_type == WizardActionType.VALIDATE_STEP:
            return self._execute_validate_step(action)
        
        elif action_type == WizardActionType.FETCH_GATE_SUMMARY:
            return self._execute_fetch_gate_summary(action)
        
        elif action_type == WizardActionType.FETCH_JOB_STATUS:
            return self._execute_fetch_job_status(action)
        
        elif action_type == WizardActionType.SHOW_EXPLANATION:
            return self._execute_show_explanation(action)
        
        elif action_type == WizardActionType.SHOW_RECOMMENDATIONS:
            return self._execute_show_recommendations(action)
        
        else:
            logger.warning(f"Unknown wizard action type: {action_type}")
            return False
    
    def _execute_next_action(self, action: WizardAction) -> bool:
        """Execute NEXT navigation action."""
        # Get next step from step validator
        next_step = self.step_validator.get_next_step(self.state)
        if not next_step:
            logger.warning("No next step available")
            return False
        
        # Validate step transition
        validation = self.step_validator.validate_step_transition(self.state, next_step)
        if not validation.is_valid:
            # Update state with validation result
            self.state = self.state.update_validation(validation)
            self._notify_state_changed()
            return False
        
        # Update state to next step
        self.state = self.state.update_step(next_step)
        
        # Clear current validation (new step, fresh start)
        self.state = self.state.update_validation(
            WizardValidationResult(
                is_valid=True,
                reason_code="STEP_TRANSITION_VALID",
                message=f"Transitioned to {next_step.value}",
                severity=ValidationSeverity.INFO,
            )
        )
        
        self._notify_state_changed()
        return True
    
    def _execute_previous_action(self, action: WizardAction) -> bool:
        """Execute PREVIOUS navigation action."""
        # Get previous step from state
        previous_step = self.state.previous_step
        if not previous_step:
            logger.warning("No previous step available")
            return False
        
        # Update state to previous step
        self.state = self.state.update_step(previous_step)
        
        # Clear current validation
        self.state = self.state.update_validation(
            WizardValidationResult(
                is_valid=True,
                reason_code="STEP_BACK_VALID",
                message=f"Returned to {previous_step.value}",
                severity=ValidationSeverity.INFO,
            )
        )
        
        self._notify_state_changed()
        return True
    
    def _execute_cancel_action(self, action: WizardAction) -> bool:
        """Execute CANCEL action."""
        self.state = self.state.mark_cancelled()
        self._notify_state_changed()
        return True
    
    def _execute_complete_action(self, action: WizardAction) -> bool:
        """Execute COMPLETE action."""
        self.state = self.state.mark_completed()
        self._notify_state_changed()
        return True
    
    def _execute_select_strategy(self, action: WizardAction) -> bool:
        """Execute SELECT_STRATEGY action."""
        strategy_ids = action.context.get("strategy_ids", [])
        if not strategy_ids:
            logger.warning("No strategy IDs in selection context")
            return False
        
        # Update selections
        self.state = self.state.update_selections(selected_strategies=strategy_ids)
        
        # Validate current step with new selections
        validation = self.step_validator.validate_current_step(self.state)
        self.state = self.state.update_validation(validation)
        
        self._notify_state_changed()
        return True
    
    def _execute_select_timeframe(self, action: WizardAction) -> bool:
        """Execute SELECT_TIMEFRAME action."""
        timeframe_ids = action.context.get("timeframe_ids", [])
        if not timeframe_ids:
            logger.warning("No timeframe IDs in selection context")
            return False
        
        # Update selections
        self.state = self.state.update_selections(selected_timeframes=timeframe_ids)
        
        # Validate current step with new selections
        validation = self.step_validator.validate_current_step(self.state)
        self.state = self.state.update_validation(validation)
        
        self._notify_state_changed()
        return True
    
    def _execute_select_instrument(self, action: WizardAction) -> bool:
        """Execute SELECT_INSTRUMENT action."""
        instrument_id = action.context.get("instrument_id")
        if not instrument_id:
            logger.warning("No instrument ID in selection context")
            return False
        
        # Update selections
        self.state = self.state.update_selections(selected_instrument=instrument_id)
        
        # Validate current step with new selections
        validation = self.step_validator.validate_current_step(self.state)
        self.state = self.state.update_validation(validation)
        
        self._notify_state_changed()
        return True
    
    def _execute_select_mode(self, action: WizardAction) -> bool:
        """Execute SELECT_MODE action."""
        mode = action.context.get("mode")
        if not mode:
            logger.warning("No mode in selection context")
            return False
        
        # Update selections
        self.state = self.state.update_selections(selected_mode=mode)
        
        # Validate current step with new selections
        validation = self.step_validator.validate_current_step(self.state)
        self.state = self.state.update_validation(validation)
        
        self._notify_state_changed()
        return True
    
    def _execute_select_job(self, action: WizardAction) -> bool:
        """Execute SELECT_JOB action (for Gate Fix Wizard)."""
        job_id = action.context.get("job_id")
        if not job_id:
            logger.warning("No job ID in selection context")
            return False
        
        # Update selections
        self.state = self.state.update_selections(selected_job_id=job_id)
        
        # Fetch gate summary for selected job
        try:
            gate_summary = self.gate_summary_service.fetch_gate_summary_for_job(job_id)
            self.state = self.state.update_gate_summary(gate_summary)
        except Exception as e:
            logger.error(f"Failed to fetch gate summary for job {job_id}: {e}")
            # Continue without gate summary
        
        # Validate current step with new selections
        validation = self.step_validator.validate_current_step(self.state)
        self.state = self.state.update_validation(validation)
        
        self._notify_state_changed()
        return True
    
    def _execute_select_gate(self, action: WizardAction) -> bool:
        """Execute SELECT_GATE action."""
        gate_ids = action.context.get("gate_ids", [])
        
        # Update selections
        self.state = self.state.update_selections(selected_gate_ids=gate_ids)
        
        # Validate current step with new selections
        validation = self.step_validator.validate_current_step(self.state)
        self.state = self.state.update_validation(validation)
        
        self._notify_state_changed()
        return True
    
    def _execute_select_fix(self, action: WizardAction) -> bool:
        """Execute SELECT_FIX action."""
        fixes = action.context.get("fixes", [])
        
        # Update selections
        self.state = self.state.update_selections(selected_fixes=fixes)
        
        # Validate current step with new selections
        validation = self.step_validator.validate_current_step(self.state)
        self.state = self.state.update_validation(validation)
        
        self._notify_state_changed()
        return True
    
    def _execute_submit_job(self, action: WizardAction) -> bool:
        """Execute SUBMIT_JOB action."""
        # Prepare job parameters from selections
        selections = self.state.selections
        
        params = {
            "strategy_id": selections.selected_strategies[0] if selections.selected_strategies else None,
            "instrument": selections.selected_instrument,
            "timeframe": selections.selected_timeframes[0] if selections.selected_timeframes else None,
            "run_mode": selections.selected_mode,
            "season": selections.season or "2026",  # Default season
        }
        
        # Add date range if provided
        if selections.date_range:
            params.update(selections.date_range)
        
        # Submit job via supervisor client
        try:
            result = supervisor_submit_job(params)
            job_id = result.get("job_id")
            
            if not job_id:
                logger.error("Job submission failed: no job_id in response")
                return False
            
            # Update state with job info
            self.state = self.state.update_job_info(
                job_id=job_id,
                status="submitted",
                progress=0.0
            )
            
            logger.info(f"Job submitted successfully: {job_id}")
            
            # Validate current step
            validation = self.step_validator.validate_current_step(self.state)
            self.state = self.state.update_validation(validation)
            
            self._notify_state_changed()
            return True
            
        except Exception as e:
            logger.error(f"Job submission failed: {e}")
            
            # Update state with error validation
            validation = WizardValidationResult(
                is_valid=False,
                reason_code="JOB_SUBMISSION_FAILED",
                message=f"Job submission failed: {e}",
                severity=ValidationSeverity.ERROR,
                recommended_action="Check supervisor service and try again",
            )
            self.state = self.state.update_validation(validation)
            
            self._notify_state_changed()
            return False
    
    def _execute_apply_fix(self, action: WizardAction) -> bool:
        """Execute APPLY_FIX action."""
        # This is a placeholder - actual fix application would depend on the specific gate
        # For MVP, we'll simulate successful fix application
        
        logger.info("Applying gate fixes (simulated for MVP)")
        
        # Update state to indicate fixes applied
        self.state = self.state.update_selections(
            selected_fixes=action.context.get("applied_fixes", [])
        )
        
        # Validate current step
        validation = self.step_validator.validate_current_step(self.state)
        self.state = self.state.update_validation(validation)
        
        self._notify_state_changed()
        return True
    
    def _execute_verify_fix(self, action: WizardAction) -> bool:
        """Execute VERIFY_FIX action."""
        # This is a placeholder - actual verification would check if fixes worked
        # For MVP, we'll simulate successful verification
        
        logger.info("Verifying gate fixes (simulated for MVP)")
        
        # Validate current step
        validation = self.step_validator.validate_current_step(self.state)
        self.state = self.state.update_validation(validation)
        
        self._notify_state_changed()
        return True
    
    def _execute_validate_step(self, action: WizardAction) -> bool:
        """Execute VALIDATE_STEP action."""
        validation = self.step_validator.validate_current_step(self.state)
        self.state = self.state.update_validation(validation)
        
        self._notify_state_changed()
        return True
    
    def _execute_fetch_gate_summary(self, action: WizardAction) -> bool:
        """Execute FETCH_GATE_SUMMARY action."""
        job_id = action.context.get("job_id") or self.state.submitted_job_id
        
        if not job_id:
            logger.warning("No job ID available for fetching gate summary")
            return False
        
        try:
            gate_summary = self.gate_summary_service.fetch_gate_summary_for_job(job_id)
            self.state = self.state.update_gate_summary(gate_summary)
            
            # Validate current step
            validation = self.step_validator.validate_current_step(self.state)
            self.state = self.state.update_validation(validation)
            
            self._notify_state_changed()
            return True
            
        except Exception as e:
            logger.error(f"Failed to fetch gate summary for job {job_id}: {e}")
            return False
    
    def _execute_fetch_job_status(self, action: WizardAction) -> bool:
        """Execute FETCH_JOB_STATUS action."""
        job_id = action.context.get("job_id") or self.state.submitted_job_id
        
        if not job_id:
            logger.warning("No job ID available for fetching job status")
            return False
        
        try:
            # This would use job lifecycle service to get job status
            # For MVP, we'll simulate status fetching
            job_info = self.job_lifecycle_service.get_job_info(job_id)
            
            if job_info:
                status = job_info.get("status", "unknown")
                progress = job_info.get("progress", 0.0)
                
                # Update state with job status
                self.state = self.state.update_job_info(
                    job_id=job_id,
                    status=status,
                    progress=progress
                )
                
                logger.debug(f"Job status fetched: {job_id} - {status} ({progress:.0%})")
            else:
                logger.warning(f"Job info not found for {job_id}")
            
            # Validate current step
            validation = self.step_validator.validate_current_step(self.state)
            self.state = self.state.update_validation(validation)
            
            self._notify_state_changed()
            return True
            
        except Exception as e:
            logger.error(f"Failed to fetch job status for {job_id}: {e}")
            return False
    
    def _execute_show_explanation(self, action: WizardAction) -> bool:
        """Execute SHOW_EXPLANATION action."""
        reason_code = action.context.get("reason_code")
        if not reason_code:
            logger.warning("No reason code provided for explanation")
            return False
        
        try:
            # Get explanation from v1.4 explain dictionary
            explanation = get_gate_reason_explanation(reason_code, action.context)
            
            # Store explanation in metadata for UI to display
            metadata = self.state.metadata.copy()
            metadata["current_explanation"] = explanation
            metadata["explanation_reason_code"] = reason_code
            
            self.state = self.state.model_copy(update={"metadata": metadata})
            
            logger.debug(f"Explanation fetched for reason code: {reason_code}")
            
            self._notify_state_changed()
            return True
            
        except Exception as e:
            logger.error(f"Failed to get explanation for reason code {reason_code}: {e}")
            return False
    
    def _execute_show_recommendations(self, action: WizardAction) -> bool:
        """Execute SHOW_RECOMMENDATIONS action."""
        # This would generate recommendations based on current state
        # For MVP, we'll simulate recommendation generation
        
        recommendations = []
        
        if self.state.wizard_type == WizardType.RUN_JOB:
            recommendations = [
                {
                    "title": "Review Strategy Selection",
                    "description": "Ensure selected strategies are appropriate for your goals",
                    "action": "review_strategy",
                },
                {
                    "title": "Check Data Readiness",
                    "description": "Verify that required datasets are prepared",
                    "action": "check_data_readiness",
                },
            ]
        elif self.state.wizard_type == WizardType.GATE_FIX:
            recommendations = [
                {
                    "title": "Review Gate Failures",
                    "description": "Examine detailed gate failure explanations",
                    "action": "review_gate_failures",
                },
                {
                    "title": "Apply Recommended Fixes",
                    "description": "Apply the suggested fixes to resolve gate issues",
                    "action": "apply_fixes",
                },
            ]
        
        # Store recommendations in metadata for UI to display
        metadata = self.state.metadata.copy()
        metadata["current_recommendations"] = recommendations
        
        self.state = self.state.model_copy(update={"metadata": metadata})
        
        logger.debug(f"Generated {len(recommendations)} recommendations")
        
        self._notify_state_changed()
        return True
    
    def _notify_state_changed(self):
        """Notify UI about state change."""
        if self.on_state_changed:
            self.on_state_changed(self.state)
    
    def get_current_validation(self) -> Optional[WizardValidationResult]:
        """Get current validation result."""
        return self.state.current_validation
    
    def can_proceed(self) -> bool:
        """Check if wizard can proceed to next step."""
        return self.state.can_proceed()
    
    def get_blocking_reason(self) -> Optional[str]:
        """Get reason why wizard is blocked, if any."""
        return self.state.get_blocking_reason()
    
    def get_explanation_for_block(self) -> Optional[Dict[str, Any]]:
        """Get explanation for current block, if any."""
        validation = self.state.current_validation
        if not validation or validation.is_valid:
            return None
        
        try:
            # Get explanation from v1.4 explain dictionary
            return get_gate_reason_explanation(validation.reason_code)
        except Exception as e:
            logger.error(f"Failed to get explanation for reason code {validation.reason_code}: {e}")
            return None
    
    def get_recommended_actions(self) -> List[Dict[str, Any]]:
        """Get recommended actions based on current state."""
        recommendations = self.state.metadata.get("current_recommendations", [])
        
        # Add validation-based recommendations if blocked
        if not self.can_proceed() and self.state.current_validation:
            validation = self.state.current_validation
            if validation.recommended_action:
                recommendations.insert(0, {
                    "title": "Fix Validation Issue",
                    "description": validation.recommended_action,
                    "action": "fix_validation",
                    "priority": "high",
                })
        
        return recommendations
    
    def get_step_progress(self) -> Dict[str, Any]:
        """Get progress information for current wizard."""
        total_steps = len(self.state.completed_steps) + 1  # +1 for current step
        completed_steps = len(self.state.completed_steps)
        
        return {
            "current_step": self.state.current_step.value,
            "completed_steps": completed_steps,
            "total_steps": total_steps,
            "progress_percentage": (completed_steps / total_steps * 100) if total_steps > 0 else 0,
            "wizard_type": self.state.wizard_type.value,
            "status": self.state.status.value,
        }
    
    def get_summary(self) -> Dict[str, Any]:
        """Get summary of current wizard state."""
        selections = self.state.selections
        
        summary = {
            "wizard_id": self.state.wizard_id,
            "wizard_type": self.state.wizard_type.value,
            "current_step": self.state.current_step.value,
            "status": self.state.status.value,
            "created_at": self.state.created_at.isoformat(),
            "updated_at": self.state.updated_at.isoformat(),
        }
        
        if self.state.wizard_type == WizardType.RUN_JOB:
            summary.update({
                "selected_strategies": selections.selected_strategies,
                "selected_timeframes": selections.selected_timeframes,
                "selected_instrument": selections.selected_instrument,
                "selected_mode": selections.selected_mode,
                "submitted_job_id": self.state.submitted_job_id,
                "job_status": self.state.job_status,
                "job_progress": self.state.job_progress,
            })
        elif self.state.wizard_type == WizardType.GATE_FIX:
            summary.update({
                "selected_job_id": selections.selected_job_id,
                "selected_gate_ids": selections.selected_gate_ids,
                "gate_summary_available": self.state.gate_summary is not None,
            })
        
        return summary