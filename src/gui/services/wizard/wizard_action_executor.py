"""
Wizard Action Executor - Executes wizard actions with proper error handling.

This module provides a dedicated executor for wizard actions that
handles execution, error recovery, and result tracking.
"""

import logging
from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass, field

from contracts.ui.wizard import (
    WizardAction,
    WizardActionType,
    WizardActionDecision,
    WizardState,
)
from contracts.ui_governance_state import validate_action_for_target

from .wizard_viewmodel import WizardViewModel

logger = logging.getLogger(__name__)


@dataclass
class WizardActionExecutor:
    """Executor for wizard actions with error handling."""
    
    viewmodel: WizardViewModel
    
    # Execution statistics
    execution_count: int = field(default=0, init=False)
    success_count: int = field(default=0, init=False)
    error_count: int = field(default=0, init=False)
    
    # Error handlers
    on_execution_error: Optional[Callable[[str, Dict[str, Any]], None]] = None
    on_execution_success: Optional[Callable[[WizardAction, WizardState], None]] = None
    
    def execute(self, action: WizardAction, ui_context: Optional[Dict[str, Any]] = None) -> bool:
        """
        Execute a wizard action with comprehensive error handling.
        
        Args:
            action: Wizard action to execute
            ui_context: Optional UI context for governance validation
            
        Returns:
            bool: True if execution succeeded, False otherwise
        """
        self.execution_count += 1
        
        try:
            # Step 1: Validate action with viewmodel
            success = self.viewmodel.handle_action(action, ui_context)
            
            if success:
                self.success_count += 1
                logger.debug(f"Action execution succeeded: {action.action_type.value}")
                
                # Notify success
                if self.on_execution_success:
                    self.on_execution_success(action, self.viewmodel.state)
                
                return True
            else:
                self.error_count += 1
                logger.warning(f"Action execution failed: {action.action_type.value}")
                
                # Notify error
                if self.on_execution_error:
                    self.on_execution_error(
                        f"Action execution failed: {action.action_type.value}",
                        {"action": action.model_dump(), "state": self.viewmodel.state.model_dump()}
                    )
                
                return False
                
        except Exception as e:
            self.error_count += 1
            error_msg = f"Action execution error: {action.action_type.value} - {e}"
            logger.exception(error_msg)
            
            # Update viewmodel state to error
            self.viewmodel.state = self.viewmodel.state.mark_error(error_msg)
            
            # Notify error
            if self.on_execution_error:
                self.on_execution_error(
                    error_msg,
                    {
                        "action": action.model_dump(),
                        "exception": str(e),
                        "exception_type": type(e).__name__,
                    }
                )
            
            return False
    
    def execute_batch(self, actions: list[WizardAction], ui_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Execute a batch of wizard actions.
        
        Args:
            actions: List of wizard actions to execute
            ui_context: Optional UI context for governance validation
            
        Returns:
            Dict with execution results
        """
        results = {
            "total": len(actions),
            "succeeded": 0,
            "failed": 0,
            "results": [],
        }
        
        for i, action in enumerate(actions):
            logger.debug(f"Executing batch action {i+1}/{len(actions)}: {action.action_type.value}")
            
            success = self.execute(action, ui_context)
            
            result = {
                "index": i,
                "action_type": action.action_type.value,
                "success": success,
                "state_after": self.viewmodel.state.model_dump() if success else None,
            }
            
            results["results"].append(result)
            
            if success:
                results["succeeded"] += 1
            else:
                results["failed"] += 1
            
            # Stop execution if critical error occurs
            if not success and self._is_critical_action(action):
                logger.warning(f"Stopping batch execution due to critical action failure: {action.action_type.value}")
                break
        
        return results
    
    def _is_critical_action(self, action: WizardAction) -> bool:
        """Check if an action is critical (should stop batch execution on failure)."""
        critical_actions = [
            WizardActionType.SUBMIT_JOB,
            WizardActionType.APPLY_FIX,
            WizardActionType.VERIFY_FIX,
            WizardActionType.WIZARD_NEXT,  # Navigation failures are critical
            WizardActionType.WIZARD_COMPLETE,
        ]
        
        return action.action_type in critical_actions
    
    def get_execution_stats(self) -> Dict[str, Any]:
        """Get execution statistics."""
        success_rate = (self.success_count / self.execution_count * 100) if self.execution_count > 0 else 0
        
        return {
            "execution_count": self.execution_count,
            "success_count": self.success_count,
            "error_count": self.error_count,
            "success_rate": success_rate,
            "current_state": self.viewmodel.state.model_dump(),
        }
    
    def reset_stats(self):
        """Reset execution statistics."""
        self.execution_count = 0
        self.success_count = 0
        self.error_count = 0
        logger.debug("Execution statistics reset")
    
    def create_action(self, action_type: WizardActionType, **kwargs) -> WizardAction:
        """Create a wizard action with proper context."""
        context = kwargs.get("context", {})
        target_step = kwargs.get("target_step")
        
        return WizardAction(
            action_type=action_type,
            target_step=target_step,
            context=context,
        )
    
    # Convenience methods for common actions
    
    def execute_next(self) -> bool:
        """Execute NEXT navigation action."""
        action = self.create_action(WizardActionType.WIZARD_NEXT)
        return self.execute(action)
    
    def execute_previous(self) -> bool:
        """Execute PREVIOUS navigation action."""
        action = self.create_action(WizardActionType.WIZARD_PREVIOUS)
        return self.execute(action)
    
    def execute_cancel(self) -> bool:
        """Execute CANCEL action."""
        action = self.create_action(WizardActionType.WIZARD_CANCEL)
        return self.execute(action)
    
    def execute_complete(self) -> bool:
        """Execute COMPLETE action."""
        action = self.create_action(WizardActionType.WIZARD_COMPLETE)
        return self.execute(action)
    
    def execute_select_strategy(self, strategy_ids: list[str]) -> bool:
        """Execute SELECT_STRATEGY action."""
        action = self.create_action(
            WizardActionType.SELECT_STRATEGY,
            context={"strategy_ids": strategy_ids}
        )
        return self.execute(action)
    
    def execute_select_timeframe(self, timeframe_ids: list[str]) -> bool:
        """Execute SELECT_TIMEFRAME action."""
        action = self.create_action(
            WizardActionType.SELECT_TIMEFRAME,
            context={"timeframe_ids": timeframe_ids}
        )
        return self.execute(action)
    
    def execute_select_instrument(self, instrument_id: str) -> bool:
        """Execute SELECT_INSTRUMENT action."""
        action = self.create_action(
            WizardActionType.SELECT_INSTRUMENT,
            context={"instrument_id": instrument_id}
        )
        return self.execute(action)
    
    def execute_select_mode(self, mode: str) -> bool:
        """Execute SELECT_MODE action."""
        action = self.create_action(
            WizardActionType.SELECT_MODE,
            context={"mode": mode}
        )
        return self.execute(action)
    
    def execute_submit_job(self) -> bool:
        """Execute SUBMIT_JOB action."""
        action = self.create_action(WizardActionType.SUBMIT_JOB)
        return self.execute(action)
    
    def execute_fetch_gate_summary(self, job_id: Optional[str] = None) -> bool:
        """Execute FETCH_GATE_SUMMARY action."""
        context = {}
        if job_id:
            context["job_id"] = job_id
        
        action = self.create_action(
            WizardActionType.FETCH_GATE_SUMMARY,
            context=context
        )
        return self.execute(action)
    
    def execute_show_explanation(self, reason_code: str, **context_vars) -> bool:
        """Execute SHOW_EXPLANATION action."""
        context = {"reason_code": reason_code, **context_vars}
        
        action = self.create_action(
            WizardActionType.SHOW_EXPLANATION,
            context=context
        )
        return self.execute(action)
    
    def execute_show_recommendations(self) -> bool:
        """Execute SHOW_RECOMMENDATIONS action."""
        action = self.create_action(WizardActionType.SHOW_RECOMMENDATIONS)
        return self.execute(action)
    
    def validate_current_step(self) -> bool:
        """Execute VALIDATE_STEP action."""
        action = self.create_action(WizardActionType.VALIDATE_STEP)
        return self.execute(action)


# Factory function for creating executors
def create_wizard_action_executor(viewmodel: WizardViewModel) -> WizardActionExecutor:
    """Create a wizard action executor for the given viewmodel."""
    return WizardActionExecutor(viewmodel=viewmodel)