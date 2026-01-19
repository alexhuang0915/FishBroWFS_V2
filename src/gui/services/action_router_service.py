"""
Action Router Service (DP9).

Handles navigation actions for UI components, particularly for DP7 dashboard
and DP8 admission decisions. Provides consistent navigation patterns for
opening artifacts, gate summaries, and admission decisions.

Integrated with UI Governance State v1.7 for state-aware action enablement.
"""

import logging
from typing import Optional, Dict, Any
from pathlib import Path

from PySide6.QtCore import QObject, Signal  # type: ignore
from PySide6.QtGui import QDesktopServices  # type: ignore
from PySide6.QtCore import QUrl  # type: ignore

from control.job_artifacts import get_job_evidence_dir, get_job_artifact_path
from contracts.job_admission_schemas import JOB_ADMISSION_DECISION_FILE
from contracts.ui_governance_state import validate_action_for_target, ui_governance_state
from gui.services.artifact_navigator_vm import GATE_SUMMARY_TARGET, EXPLAIN_TARGET_PREFIX

logger = logging.getLogger(__name__)


class ActionRouterService(QObject):
    """Service for routing UI actions to appropriate handlers."""
    
    # Signals
    open_artifact_navigator = Signal(str, str)  # job_id, artifact_path
    open_gate_summary = Signal(str)  # job_id
    open_explain = Signal(str)  # job_id
    open_evidence_browser = Signal(str)  # job_id
    open_url = Signal(str)  # url
    
    def __init__(self):
        super().__init__()
    
    def handle_action(self, target: str, context: Optional[Dict[str, Any]] = None) -> bool:
        """
        Handle a navigation action.
        
        Args:
            target: Action target (URL, path, or special target)
            context: Optional context dictionary (e.g., job_id, artifact_type)
            
        Returns:
            True if action was handled, False otherwise
        """
        logger.debug(f"Handling action: {target}")
        
        # Check if action is enabled based on UI governance state
        validation_result = validate_action_for_target(target)
        if not validation_result.get("enabled", True):
            reason_code = validation_result.get("reason_code")
            explanation = validation_result.get("explanation")
            logger.warning(
                f"Action disabled by UI governance state: {target}. "
                f"Reason: {reason_code}, Explanation: {explanation}"
            )
            # TODO: Emit signal or show notification to user about disabled action
            return False
        
        # Internal UI targets (handled by main window/router)
        if target.startswith("internal://"):
            self.open_url.emit(target)
            return True

        # Special targets
        if target == GATE_SUMMARY_TARGET:
            job_id = self._extract_job_id(context)
            if job_id:
                self.open_gate_summary.emit(job_id)
                return True
        
        elif target.startswith(EXPLAIN_TARGET_PREFIX):
            job_id = target[len(EXPLAIN_TARGET_PREFIX):]
            self.open_explain.emit(job_id)
            return True
        
        # Job admission decision target
        elif target.startswith("job_admission://"):
            job_id = target[len("job_admission://"):]
            self._open_job_admission_decision(job_id)
            return True

        # Artifact navigator target
        elif target.startswith("artifact://"):
            job_id = target[len("artifact://"):]
            if job_id:
                self.open_artifact_navigator.emit(job_id, "")
                return True

        # Evidence browser target
        elif target.startswith("evidence://"):
            job_id = target[len("evidence://"):]
            if job_id:
                if context and context.get("local_only"):
                    return False
                self.open_evidence_browser.emit(job_id)
                return True
        
        # Gate summary dashboard target
        elif target == "gate_dashboard":
            # Switch to gate dashboard tab (handled by main window)
            self.open_url.emit("internal://gate_dashboard")
            return True
        
        # File paths
        elif target.startswith("file://"):
            url = QUrl.fromLocalFile(target[7:])
            QDesktopServices.openUrl(url)
            return True
        
        # HTTP/HTTPS URLs
        elif target.startswith(("http://", "https://")):
            url = QUrl(target)
            QDesktopServices.openUrl(url)
            return True
        
        # Local file paths
        elif Path(target).exists():
            url = QUrl.fromLocalFile(target)
            QDesktopServices.openUrl(url)
            return True
        
        # Job artifact paths
        elif "/jobs/" in target and "/artifacts/" in target:
            # Extract job_id and artifact name from path
            parts = target.split("/jobs/")
            if len(parts) > 1:
                job_artifact_part = parts[1]
                job_parts = job_artifact_part.split("/artifacts/")
                if len(job_parts) == 2:
                    job_id = job_parts[0]
                    artifact_name = job_parts[1]
                    self.open_artifact_navigator.emit(job_id, artifact_name)
                    return True
        
        logger.warning(f"Unhandled action target: {target}")
        return False
    
    def _extract_job_id(self, context: Optional[Dict[str, Any]]) -> Optional[str]:
        """Extract job_id from context."""
        if not context:
            return None
        return context.get("job_id")
    
    def _open_job_admission_decision(self, job_id: str) -> None:
        """Open job admission decision artifact."""
        decision_path = get_job_artifact_path(job_id, JOB_ADMISSION_DECISION_FILE)
        if decision_path and decision_path.exists():
            url = QUrl.fromLocalFile(str(decision_path))
            QDesktopServices.openUrl(url)
        else:
            logger.warning(f"Job admission decision not found for {job_id}")
            # Fallback: open job artifact directory
            artifact_dir = get_job_evidence_dir(job_id)
            if artifact_dir.exists():
                url = QUrl.fromLocalFile(str(artifact_dir))
                QDesktopServices.openUrl(url)
    
    def create_gate_dashboard_action(self) -> Dict[str, str]:
        """Create action for opening gate dashboard."""
        return {
            "label": "Open Gate Dashboard",
            "target": "gate_dashboard",
        }
    
    def create_job_admission_action(self, job_id: str) -> Dict[str, str]:
        """Create action for opening job admission decision."""
        return {
            "label": "View Admission Decision",
            "target": f"job_admission://{job_id}",
        }
    
    def create_gate_summary_action(self, job_id: str) -> Dict[str, str]:
        """Create action for opening gate summary."""
        return {
            "label": "View Gate Summary",
            "target": GATE_SUMMARY_TARGET,
            "context": {"job_id": job_id},
        }
    
    def create_explain_action(self, job_id: str) -> Dict[str, str]:
        """Create action for opening explain."""
        return {
            "label": "View Explain",
            "target": f"{EXPLAIN_TARGET_PREFIX}{job_id}",
        }


# -----------------------------------------------------------------------------
# Singleton pattern
# -----------------------------------------------------------------------------

_ACTION_ROUTER_SERVICE = None


def get_action_router_service() -> ActionRouterService:
    """Get singleton instance of action router service."""
    global _ACTION_ROUTER_SERVICE
    if _ACTION_ROUTER_SERVICE is None:
        _ACTION_ROUTER_SERVICE = ActionRouterService()
    return _ACTION_ROUTER_SERVICE