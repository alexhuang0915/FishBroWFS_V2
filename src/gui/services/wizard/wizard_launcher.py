"""
Wizard Launcher Service (v1.8) - Integration entry point for wizard workflows.

This service provides the integration point between wizard workflows and the
existing UI infrastructure (ActionRouterService, UI governance state v1.7).

Key Responsibilities:
1. Launch wizard dialogs (Run Job Wizard, Gate Fix Wizard)
2. Handle wizard action routing through ActionRouterService
3. Integrate with UI governance state for zero-silent validation
4. Provide wizard completion callbacks
"""

import logging
from typing import Optional, Dict, Any, Callable
from uuid import uuid4

from PySide6.QtCore import QObject, Signal  # type: ignore

from contracts.ui.wizard import (
    WizardType,
    WizardState,
    WizardResult,
    WizardJobResult,
    WizardGateFixResult,
)
from gui.services.action_router_service import get_action_router_service
from gui.services.wizard.wizard_viewmodel import WizardViewModel
from gui.services.wizard.wizard_action_executor import create_wizard_action_executor
from gui.desktop.wizard import WizardDialog

logger = logging.getLogger(__name__)


class WizardLauncherService(QObject):
    """Service for launching and managing wizard workflows."""
    
    # Signals
    wizard_started = Signal(str, WizardType)  # wizard_id, wizard_type
    wizard_completed = Signal(str, WizardResult)  # wizard_id, result
    wizard_cancelled = Signal(str)  # wizard_id
    wizard_error = Signal(str, str)  # wizard_id, error_message
    
    def __init__(self):
        super().__init__()
        self._active_wizards: Dict[str, WizardViewModel] = {}
        self._active_dialogs: Dict[str, WizardDialog] = {}
        self._action_router = get_action_router_service()
    
    def launch_run_job_wizard(
        self,
        parent_widget=None,
        initial_selections: Optional[Dict[str, Any]] = None,
        on_complete: Optional[Callable[[WizardJobResult], None]] = None,
        on_cancel: Optional[Callable[[], None]] = None,
    ) -> str:
        """
        Launch Run Job Wizard for guided job creation.
        
        Args:
            parent_widget: Parent widget for the wizard dialog
            initial_selections: Optional initial selections (strategy, timeframe, etc.)
            on_complete: Optional callback when wizard completes successfully
            on_cancel: Optional callback when wizard is cancelled
            
        Returns:
            wizard_id: Unique identifier for the wizard session
        """
        return self._launch_wizard(
            wizard_type=WizardType.RUN_JOB,
            parent_widget=parent_widget,
            initial_selections=initial_selections,
            on_complete=on_complete,
            on_cancel=on_cancel,
        )
    
    def launch_gate_fix_wizard(
        self,
        job_id: str,
        parent_widget=None,
        initial_selections: Optional[Dict[str, Any]] = None,
        on_complete: Optional[Callable[[WizardGateFixResult], None]] = None,
        on_cancel: Optional[Callable[[], None]] = None,
    ) -> str:
        """
        Launch Gate Fix Wizard for fixing gate failures.
        
        Args:
            job_id: ID of the job with gate failures
            parent_widget: Parent widget for the wizard dialog
            initial_selections: Optional initial selections (gate, fix type, etc.)
            on_complete: Optional callback when wizard completes successfully
            on_cancel: Optional callback when wizard is cancelled
            
        Returns:
            wizard_id: Unique identifier for the wizard session
        """
        if initial_selections is None:
            initial_selections = {}
        initial_selections["job_id"] = job_id
        
        return self._launch_wizard(
            wizard_type=WizardType.GATE_FIX,
            parent_widget=parent_widget,
            initial_selections=initial_selections,
            on_complete=on_complete,
            on_cancel=on_cancel,
        )
    
    def _launch_wizard(
        self,
        wizard_type: WizardType,
        parent_widget=None,
        initial_selections: Optional[Dict[str, Any]] = None,
        on_complete: Optional[Callable] = None,
        on_cancel: Optional[Callable] = None,
    ) -> str:
        """Internal method to launch a wizard."""
        wizard_id = str(uuid4())
        
        # Create wizard state with initial selections
        state = WizardState.create(
            wizard_id=wizard_id,
            wizard_type=wizard_type,
            initial_selections=initial_selections or {},
        )
        
        # Create viewmodel
        viewmodel = WizardViewModel(state)
        
        # Create action executor
        executor = create_wizard_action_executor(viewmodel)
        
        # Create wizard dialog
        dialog = WizardDialog(
            wizard_id=wizard_id,
            wizard_type=wizard_type,
            viewmodel=viewmodel,
            executor=executor,
            parent=parent_widget,
        )
        
        # Connect signals
        dialog.wizard_completed.connect(
            lambda result: self._handle_wizard_completed(wizard_id, result, on_complete)
        )
        dialog.wizard_cancelled.connect(
            lambda: self._handle_wizard_cancelled(wizard_id, on_cancel)
        )
        dialog.wizard_error.connect(
            lambda error: self._handle_wizard_error(wizard_id, error)
        )
        
        # Store references
        self._active_wizards[wizard_id] = viewmodel
        self._active_dialogs[wizard_id] = dialog
        
        # Emit signal
        self.wizard_started.emit(wizard_id, wizard_type)
        
        # Show dialog (non-modal)
        dialog.show()
        
        logger.info(f"Launched {wizard_type.value} wizard: {wizard_id}")
        return wizard_id
    
    def _handle_wizard_completed(
        self,
        wizard_id: str,
        result: WizardResult,
        on_complete: Optional[Callable] = None,
    ) -> None:
        """Handle wizard completion."""
        logger.info(f"Wizard completed: {wizard_id}")
        
        # Emit signal
        self.wizard_completed.emit(wizard_id, result)
        
        # Call user callback if provided
        if on_complete:
            try:
                on_complete(result)
            except Exception as e:
                logger.error(f"Error in wizard completion callback: {e}")
        
        # Clean up
        self._cleanup_wizard(wizard_id)
    
    def _handle_wizard_cancelled(
        self,
        wizard_id: str,
        on_cancel: Optional[Callable] = None,
    ) -> None:
        """Handle wizard cancellation."""
        logger.info(f"Wizard cancelled: {wizard_id}")
        
        # Emit signal
        self.wizard_cancelled.emit(wizard_id)
        
        # Call user callback if provided
        if on_cancel:
            try:
                on_cancel()
            except Exception as e:
                logger.error(f"Error in wizard cancellation callback: {e}")
        
        # Clean up
        self._cleanup_wizard(wizard_id)
    
    def _handle_wizard_error(self, wizard_id: str, error: str) -> None:
        """Handle wizard error."""
        logger.error(f"Wizard error: {wizard_id} - {error}")
        
        # Emit signal
        self.wizard_error.emit(wizard_id, error)
        
        # Clean up
        self._cleanup_wizard(wizard_id)
    
    def _cleanup_wizard(self, wizard_id: str) -> None:
        """Clean up wizard resources."""
        # Close dialog if still open
        dialog = self._active_dialogs.pop(wizard_id, None)
        if dialog:
            dialog.close()
        
        # Remove viewmodel
        self._active_wizards.pop(wizard_id, None)
        
        logger.debug(f"Cleaned up wizard: {wizard_id}")
    
    def get_active_wizard(self, wizard_id: str) -> Optional[WizardViewModel]:
        """Get active wizard viewmodel by ID."""
        return self._active_wizards.get(wizard_id)
    
    def get_active_dialog(self, wizard_id: str) -> Optional[WizardDialog]:
        """Get active wizard dialog by ID."""
        return self._active_dialogs.get(wizard_id)
    
    def close_all_wizards(self) -> None:
        """Close all active wizards."""
        wizard_ids = list(self._active_wizards.keys())
        for wizard_id in wizard_ids:
            self._cleanup_wizard(wizard_id)
        
        logger.info(f"Closed {len(wizard_ids)} active wizards")


# -----------------------------------------------------------------------------
# Singleton pattern
# -----------------------------------------------------------------------------

_WIZARD_LAUNCHER_SERVICE = None


def get_wizard_launcher_service() -> WizardLauncherService:
    """Get singleton instance of wizard launcher service."""
    global _WIZARD_LAUNCHER_SERVICE
    if _WIZARD_LAUNCHER_SERVICE is None:
        _WIZARD_LAUNCHER_SERVICE = WizardLauncherService()
    return _WIZARD_LAUNCHER_SERVICE


def launch_run_job_wizard(
    parent_widget=None,
    initial_selections: Optional[Dict[str, Any]] = None,
    on_complete: Optional[Callable[[WizardJobResult], None]] = None,
    on_cancel: Optional[Callable[[], None]] = None,
) -> str:
    """
    Convenience function to launch Run Job Wizard.
    
    Args:
        parent_widget: Parent widget for the wizard dialog
        initial_selections: Optional initial selections
        on_complete: Optional callback when wizard completes
        on_cancel: Optional callback when wizard is cancelled
        
    Returns:
        wizard_id: Unique identifier for the wizard session
    """
    service = get_wizard_launcher_service()
    return service.launch_run_job_wizard(
        parent_widget=parent_widget,
        initial_selections=initial_selections,
        on_complete=on_complete,
        on_cancel=on_cancel,
    )


def launch_gate_fix_wizard(
    job_id: str,
    parent_widget=None,
    initial_selections: Optional[Dict[str, Any]] = None,
    on_complete: Optional[Callable[[WizardGateFixResult], None]] = None,
    on_cancel: Optional[Callable[[], None]] = None,
) -> str:
    """
    Convenience function to launch Gate Fix Wizard.
    
    Args:
        job_id: ID of the job with gate failures
        parent_widget: Parent widget for the wizard dialog
        initial_selections: Optional initial selections
        on_complete: Optional callback when wizard completes
        on_cancel: Optional callback when wizard is cancelled
        
    Returns:
        wizard_id: Unique identifier for the wizard session
    """
    service = get_wizard_launcher_service()
    return service.launch_gate_fix_wizard(
        job_id=job_id,
        parent_widget=parent_widget,
        initial_selections=initial_selections,
        on_complete=on_complete,
        on_cancel=on_cancel,
    )