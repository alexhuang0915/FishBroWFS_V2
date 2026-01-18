"""
UI Governance State SSOT (Single Source of Truth) v1.7.

Defines the state model for UI governance and state-aware action policies.
This module provides the authoritative source for:
- UI state definitions (selected job, active tab, data readiness, permissions)
- State-aware action policies (which actions require which UI state)
- Zero-silent UI: All disabled actions must show explanation via reason codes

Governance Rules:
1. Every UI action must have a state-aware policy defined
2. Disabled actions must provide explanation via reason codes (no silent failures)
3. UI state changes must be tracked in the singleton state holder
4. Action enablement must be checked against current UI state
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional, Set, Any, TypedDict
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict

from contracts.ui_action_registry import UiActionType
from contracts.portfolio.gate_summary_schemas import GateReasonCode


class UiMode(str, Enum):
    """UI interaction mode."""
    VIEW = "VIEW"           # Read-only view mode
    EDIT = "EDIT"           # Edit mode (can modify configurations)
    ADMIN = "ADMIN"         # Administrative mode (full control)
    DEBUG = "DEBUG"         # Debug mode (developer tools)


class PermissionLevel(str, Enum):
    """User permission levels for UI actions."""
    VIEWER = "VIEWER"       # Can view but not modify
    OPERATOR = "OPERATOR"   # Can run jobs and modify configurations
    ADMINISTRATOR = "ADMINISTRATOR"  # Full system control
    DEVELOPER = "DEVELOPER" # Developer access (debug tools)


class DataReadinessStatus(str, Enum):
    """Data readiness status for UI components."""
    NOT_READY = "NOT_READY"     # Data not loaded or available
    LOADING = "LOADING"         # Data loading in progress
    READY = "READY"             # Data ready for use
    ERROR = "ERROR"             # Data loading failed
    PARTIAL = "PARTIAL"         # Partial data available


class UiTab(str, Enum):
    """UI tab identifiers."""
    OP_TAB = "OP_TAB"                     # Operation tab (job submission)
    GATE_SUMMARY_DASHBOARD = "GATE_SUMMARY_DASHBOARD"  # Gate summary dashboard
    REPORT_TAB = "REPORT_TAB"             # Report tab
    AUDIT_TAB = "AUDIT_TAB"               # Audit tab
    REGISTRY_TAB = "REGISTRY_TAB"         # Registry tab
    PORTFOLIO_ADMISSION_TAB = "PORTFOLIO_ADMISSION_TAB"  # Portfolio admission
    ALLOCATION_TAB = "ALLOCATION_TAB"     # Allocation tab
    ANALYSIS_DRAWER = "ANALYSIS_DRAWER"   # Analysis drawer widget


class UiGovernanceState(BaseModel):
    """
    Complete UI governance state model.
    
    This model represents the current state of the UI that affects action enablement.
    It's used by state-aware action policies to determine if actions should be enabled.
    """
    
    # Core UI context
    selected_job_id: Optional[str] = Field(
        None,
        description="Currently selected job ID (if any)"
    )
    
    active_tab: Optional[UiTab] = Field(
        None,
        description="Currently active UI tab"
    )
    
    # Data readiness state
    data_readiness_status: Dict[str, DataReadinessStatus] = Field(
        default_factory=dict,
        description="Data readiness status by component/dataset"
    )
    
    # User context
    permission_level: PermissionLevel = Field(
        default=PermissionLevel.VIEWER,
        description="Current user's permission level"
    )
    
    ui_mode: UiMode = Field(
        default=UiMode.VIEW,
        description="Current UI interaction mode"
    )
    
    # System state
    system_ready: bool = Field(
        default=False,
        description="Whether system is ready for operations"
    )
    
    any_jobs_running: bool = Field(
        default=False,
        description="Whether any jobs are currently running"
    )
    
    # Timestamps
    last_state_update: datetime = Field(
        default_factory=datetime.utcnow,
        description="When state was last updated"
    )
    
    model_config = ConfigDict(frozen=True)
    
    def is_job_selected(self) -> bool:
        """Check if a job is currently selected."""
        return self.selected_job_id is not None and self.selected_job_id != ""
    
    def get_data_status(self, component: str) -> DataReadinessStatus:
        """Get data readiness status for a component."""
        return self.data_readiness_status.get(component, DataReadinessStatus.NOT_READY)
    
    def has_permission(self, required_level: PermissionLevel) -> bool:
        """Check if current user has required permission level."""
        permission_order = {
            PermissionLevel.VIEWER: 0,
            PermissionLevel.OPERATOR: 1,
            PermissionLevel.ADMINISTRATOR: 2,
            PermissionLevel.DEVELOPER: 3,
        }
        current_level = permission_order.get(self.permission_level, 0)
        required_level_value = permission_order.get(required_level, 0)
        return current_level >= required_level_value
    
    def is_mode_allowed(self, required_mode: UiMode) -> bool:
        """Check if current UI mode allows the required mode."""
        mode_order = {
            UiMode.VIEW: 0,
            UiMode.EDIT: 1,
            UiMode.ADMIN: 2,
            UiMode.DEBUG: 3,
        }
        current_mode = mode_order.get(self.ui_mode, 0)
        required_mode_value = mode_order.get(required_mode, 0)
        return current_mode >= required_mode_value
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert state to dictionary for serialization."""
        return {
            "selected_job_id": self.selected_job_id,
            "active_tab": self.active_tab.value if self.active_tab else None,
            "data_readiness_status": {
                k: v.value for k, v in self.data_readiness_status.items()
            },
            "permission_level": self.permission_level.value,
            "ui_mode": self.ui_mode.value,
            "system_ready": self.system_ready,
            "any_jobs_running": self.any_jobs_running,
            "last_state_update": self.last_state_update.isoformat(),
        }


class UiActionPolicy(BaseModel):
    """
    State-aware action policy.
    
    Defines the UI state requirements for a specific action type.
    If any requirement is not met, the action should be disabled with
    the specified reason code and explanation.
    """
    
    action_type: UiActionType = Field(
        ...,
        description="UI action type this policy applies to"
    )
    
    # State requirements
    requires_selected_job: bool = Field(
        default=False,
        description="Whether action requires a selected job"
    )
    
    requires_active_tab: Optional[UiTab] = Field(
        None,
        description="Required active tab (if any)"
    )
    
    requires_data_ready: List[str] = Field(
        default_factory=list,
        description="List of data components that must be READY"
    )
    
    requires_permission_level: PermissionLevel = Field(
        default=PermissionLevel.VIEWER,
        description="Minimum permission level required"
    )
    
    requires_ui_mode: UiMode = Field(
        default=UiMode.VIEW,
        description="Minimum UI mode required"
    )
    
    requires_system_ready: bool = Field(
        default=True,
        description="Whether system must be ready"
    )
    
    requires_no_jobs_running: bool = Field(
        default=False,
        description="Whether action requires no jobs to be running"
    )
    
    # Disablement information
    disabled_reason_code: str = Field(
        ...,
        description="GateReasonCode to use when action is disabled"
    )
    
    explanation_template: str = Field(
        ...,
        description="Template for explanation message (can include {context_vars})"
    )
    
    model_config = ConfigDict(frozen=True)
    
    def check_action_enabled(self, state: UiGovernanceState) -> Dict[str, Any]:
        """
        Check if action is enabled given current UI state.
        
        Returns:
            Dict with keys:
            - enabled: bool (whether action is enabled)
            - reason_code: str (if disabled, the reason code)
            - explanation: str (if disabled, human-readable explanation)
            - context_vars: Dict (variables for explanation template)
        """
        context_vars = {}
        
        # Check selected job requirement
        if self.requires_selected_job and not state.is_job_selected():
            context_vars["missing_requirement"] = "selected_job"
            return {
                "enabled": False,
                "reason_code": self.disabled_reason_code,
                "explanation": self._format_explanation(context_vars),
                "context_vars": context_vars,
            }
        
        # Check active tab requirement
        if self.requires_active_tab and state.active_tab != self.requires_active_tab:
            context_vars["required_tab"] = self.requires_active_tab.value
            context_vars["current_tab"] = state.active_tab.value if state.active_tab else "None"
            return {
                "enabled": False,
                "reason_code": self.disabled_reason_code,
                "explanation": self._format_explanation(context_vars),
                "context_vars": context_vars,
            }
        
        # Check data readiness requirements
        for component in self.requires_data_ready:
            status = state.get_data_status(component)
            if status != DataReadinessStatus.READY:
                context_vars["component"] = component
                context_vars["status"] = status.value
                return {
                    "enabled": False,
                    "reason_code": self.disabled_reason_code,
                    "explanation": self._format_explanation(context_vars),
                    "context_vars": context_vars,
                }
        
        # Check permission level
        if not state.has_permission(self.requires_permission_level):
            context_vars["required_permission"] = self.requires_permission_level.value
            context_vars["current_permission"] = state.permission_level.value
            return {
                "enabled": False,
                "reason_code": self.disabled_reason_code,
                "explanation": self._format_explanation(context_vars),
                "context_vars": context_vars,
            }
        
        # Check UI mode
        if not state.is_mode_allowed(self.requires_ui_mode):
            context_vars["required_mode"] = self.requires_ui_mode.value
            context_vars["current_mode"] = state.ui_mode.value
            return {
                "enabled": False,
                "reason_code": self.disabled_reason_code,
                "explanation": self._format_explanation(context_vars),
                "context_vars": context_vars,
            }
        
        # Check system readiness
        if self.requires_system_ready and not state.system_ready:
            context_vars["missing_requirement"] = "system_ready"
            return {
                "enabled": False,
                "reason_code": self.disabled_reason_code,
                "explanation": self._format_explanation(context_vars),
                "context_vars": context_vars,
            }
        
        # Check jobs running requirement
        if self.requires_no_jobs_running and state.any_jobs_running:
            context_vars["missing_requirement"] = "no_jobs_running"
            return {
                "enabled": False,
                "reason_code": self.disabled_reason_code,
                "explanation": self._format_explanation(context_vars),
                "context_vars": context_vars,
            }
        
        # All requirements met
        return {
            "enabled": True,
            "reason_code": None,
            "explanation": None,
            "context_vars": {},
        }
    
    def _format_explanation(self, context_vars: Dict[str, str]) -> str:
        """Format explanation message with context variables."""
        explanation = self.explanation_template
        for key, value in context_vars.items():
            placeholder = f"{{{key}}}"
            if placeholder in explanation:
                explanation = explanation.replace(placeholder, str(value))
        return explanation


class UiActionPolicyRegistry(BaseModel):
    """Registry of all state-aware action policies."""
    
    policies: Dict[UiActionType, UiActionPolicy] = Field(
        default_factory=dict,
        description="Mapping from action type to policy"
    )
    
    model_config = ConfigDict(frozen=True)
    
    def get_policy(self, action_type: UiActionType) -> Optional[UiActionPolicy]:
        """Get policy for action type."""
        return self.policies.get(action_type)
    
    def check_action_enabled(
        self, 
        action_type: UiActionType, 
        state: UiGovernanceState
    ) -> Dict[str, Any]:
        """Check if action is enabled given current state."""
        policy = self.get_policy(action_type)
        if not policy:
            # Default policy if none defined
            return {
                "enabled": True,  # Allow by default (backward compatibility)
                "reason_code": None,
                "explanation": None,
                "context_vars": {},
            }
        return policy.check_action_enabled(state)


# -----------------------------------------------------------------------------
# Default UI Governance State (Singleton)
# -----------------------------------------------------------------------------

class UiGovernanceStateHolder:
    """
    Singleton state holder for UI governance state.
    
    Similar to active_run_state.py, provides thread-safe access to current UI state.
    """
    
    _instance: Optional[UiGovernanceStateHolder] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        # Initialize with default state
        self._state = UiGovernanceState()
        self._initialized = True
    
    def get_state(self) -> UiGovernanceState:
        """Get current UI governance state."""
        return self._state
    
    def update_state(self, **kwargs) -> None:
        """Update UI governance state with new values."""
        # Create new state with updated values
        current_dict = self._state.model_dump()
        current_dict.update(kwargs)
        current_dict["last_state_update"] = datetime.utcnow()
        
        # Create new state object
        new_state = UiGovernanceState(**current_dict)
        
        # Update instance
        self._state = new_state
    
    def set_selected_job(self, job_id: Optional[str]) -> None:
        """Set the currently selected job."""
        self.update_state(selected_job_id=job_id)
    
    def set_active_tab(self, tab: Optional[UiTab]) -> None:
        """Set the currently active tab."""
        self.update_state(active_tab=tab)
    
    def set_data_status(self, component: str, status: DataReadinessStatus) -> None:
        """Set data readiness status for a component."""
        current_status = self._state.data_readiness_status.copy()
        current_status[component] = status
        self.update_state(data_readiness_status=current_status)
    
    def set_permission_level(self, level: PermissionLevel) -> None:
        """Set current user's permission level."""
        self.update_state(permission_level=level)
    
    def set_ui_mode(self, mode: UiMode) -> None:
        """Set current UI mode."""
        self.update_state(ui_mode=mode)
    
    def set_system_ready(self, ready: bool) -> None:
        """Set system readiness status."""
        self.update_state(system_ready=ready)
    
    def set_any_jobs_running(self, running: bool) -> None:
        """Set whether any jobs are running."""
        self.update_state(any_jobs_running=running)


# Global singleton instance
ui_governance_state = UiGovernanceStateHolder()


# -----------------------------------------------------------------------------
# Default Action Policies
# -----------------------------------------------------------------------------

def create_default_action_policies() -> UiActionPolicyRegistry:
    """Create default state-aware action policies."""
    
    policies = {
        # Job operations requiring selected job
        UiActionType.JOB_DETAILS: UiActionPolicy(
            action_type=UiActionType.JOB_DETAILS,
            requires_selected_job=True,
            disabled_reason_code=GateReasonCode.GATE_SUMMARY_FETCH_ERROR.value,
            explanation_template="Job details require a selected job. No job is currently selected.",
        ),
        
        UiActionType.JOB_ABORT: UiActionPolicy(
            action_type=UiActionType.JOB_ABORT,
            requires_selected_job=True,
            requires_permission_level=PermissionLevel.OPERATOR,
            disabled_reason_code=GateReasonCode.GATE_SUMMARY_FETCH_ERROR.value,
            explanation_template="Job abort requires a selected job and operator permissions. Current permission: {current_permission}.",
        ),
        
        UiActionType.JOB_EXPLAIN: UiActionPolicy(
            action_type=UiActionType.JOB_EXPLAIN,
            requires_selected_job=True,
            disabled_reason_code=GateReasonCode.GATE_SUMMARY_FETCH_ERROR.value,
            explanation_template="Job explanation requires a selected job. No job is currently selected.",
        ),
        
        # Navigation operations requiring selected job
        UiActionType.NAVIGATE_JOB_ADMISSION: UiActionPolicy(
            action_type=UiActionType.NAVIGATE_JOB_ADMISSION,
            requires_selected_job=True,
            disabled_reason_code=GateReasonCode.GATE_SUMMARY_FETCH_ERROR.value,
            explanation_template="Job admission navigation requires a selected job. No job is currently selected.",
        ),
        
        UiActionType.NAVIGATE_ARTIFACT: UiActionPolicy(
            action_type=UiActionType.NAVIGATE_ARTIFACT,
            requires_selected_job=True,
            disabled_reason_code=GateReasonCode.GATE_SUMMARY_FETCH_ERROR.value,
            explanation_template="Artifact navigation requires a selected job. No job is currently selected.",
        ),
        
        UiActionType.NAVIGATE_EXPLAIN: UiActionPolicy(
            action_type=UiActionType.NAVIGATE_EXPLAIN,
            requires_selected_job=True,
            disabled_reason_code=GateReasonCode.GATE_SUMMARY_FETCH_ERROR.value,
            explanation_template="Explain navigation requires a selected job. No job is currently selected.",
        ),
        
        # Gate operations
        UiActionType.GATE_SUMMARY: UiActionPolicy(
            action_type=UiActionType.GATE_SUMMARY,
            requires_active_tab=UiTab.GATE_SUMMARY_DASHBOARD,
            disabled_reason_code=GateReasonCode.GATE_SUMMARY_FETCH_ERROR.value,
            explanation_template="Gate summary requires active gate dashboard tab. Current tab: {current_tab}.",
        ),
        
        # Job submission requires system readiness
        UiActionType.JOB_SUBMISSION: UiActionPolicy(
            action_type=UiActionType.JOB_SUBMISSION,
            requires_system_ready=True,
            requires_permission_level=PermissionLevel.OPERATOR,
            disabled_reason_code=GateReasonCode.GATE_SUMMARY_FETCH_ERROR.value,
            explanation_template="Job submission requires system readiness and operator permissions. System ready: {system_ready}, permission: {current_permission}.",
        ),
        
        # Registry operations require data readiness
        UiActionType.REGISTRY_DATASETS: UiActionPolicy(
            action_type=UiActionType.REGISTRY_DATASETS,
            requires_data_ready=["registry_cache"],
            disabled_reason_code=GateReasonCode.GATE_SUMMARY_FETCH_ERROR.value,
            explanation_template="Dataset registry requires registry cache to be ready. Status: {status}.",
        ),
        
        UiActionType.REGISTRY_STRATEGIES: UiActionPolicy(
            action_type=UiActionType.REGISTRY_STRATEGIES,
            requires_data_ready=["registry_cache"],
            disabled_reason_code=GateReasonCode.GATE_SUMMARY_FETCH_ERROR.value,
            explanation_template="Strategy registry requires registry cache to be ready. Status: {status}.",
        ),
        
        # System operations require admin permissions
        UiActionType.SYSTEM_PRIME_REGISTRIES: UiActionPolicy(
            action_type=UiActionType.SYSTEM_PRIME_REGISTRIES,
            requires_permission_level=PermissionLevel.ADMINISTRATOR,
            disabled_reason_code=GateReasonCode.GATE_SUMMARY_FETCH_ERROR.value,
            explanation_template="Prime registries requires administrator permissions. Current permission: {current_permission}.",
        ),
        
        # Season operations require edit mode
        UiActionType.SEASON_MANAGEMENT: UiActionPolicy(
            action_type=UiActionType.SEASON_MANAGEMENT,
            requires_ui_mode=UiMode.EDIT,
            requires_permission_level=PermissionLevel.OPERATOR,
            disabled_reason_code=GateReasonCode.GATE_SUMMARY_FETCH_ERROR.value,
            explanation_template="Season management requires edit mode and operator permissions. Current mode: {current_mode}, permission: {current_permission}.",
        ),
        
        # Job listing - requires system readiness
        UiActionType.JOB_LISTING: UiActionPolicy(
            action_type=UiActionType.JOB_LISTING,
            requires_system_ready=True,
            disabled_reason_code=GateReasonCode.GATE_SUMMARY_FETCH_ERROR.value,
            explanation_template="Job listing requires system to be ready. System ready: {system_ready}.",
        ),
        
        # Registry operations - require data readiness
        UiActionType.REGISTRY_INSTRUMENTS: UiActionPolicy(
            action_type=UiActionType.REGISTRY_INSTRUMENTS,
            requires_data_ready=["registry_cache"],
            disabled_reason_code=GateReasonCode.GATE_SUMMARY_FETCH_ERROR.value,
            explanation_template="Instrument registry requires registry cache to be ready. Status: {status}.",
        ),
        
        UiActionType.REGISTRY_TIMEFRAMES: UiActionPolicy(
            action_type=UiActionType.REGISTRY_TIMEFRAMES,
            requires_data_ready=["registry_cache"],
            disabled_reason_code=GateReasonCode.GATE_SUMMARY_FETCH_ERROR.value,
            explanation_template="Timeframe registry requires registry cache to be ready. Status: {status}.",
        ),
        
        # Data operations - require selected job for context
        UiActionType.DATA_READINESS: UiActionPolicy(
            action_type=UiActionType.DATA_READINESS,
            requires_selected_job=True,
            disabled_reason_code=GateReasonCode.GATE_SUMMARY_FETCH_ERROR.value,
            explanation_template="Data readiness check requires a selected job. No job is currently selected.",
        ),
        
        UiActionType.DATA_PREPARATION: UiActionPolicy(
            action_type=UiActionType.DATA_PREPARATION,
            requires_selected_job=True,
            requires_permission_level=PermissionLevel.OPERATOR,
            disabled_reason_code=GateReasonCode.GATE_SUMMARY_FETCH_ERROR.value,
            explanation_template="Data preparation requires a selected job and operator permissions. Current permission: {current_permission}.",
        ),
        
        # Portfolio operations - require selected job
        UiActionType.PORTFOLIO_BUILD: UiActionPolicy(
            action_type=UiActionType.PORTFOLIO_BUILD,
            requires_selected_job=True,
            requires_permission_level=PermissionLevel.OPERATOR,
            disabled_reason_code=GateReasonCode.GATE_SUMMARY_FETCH_ERROR.value,
            explanation_template="Portfolio build requires a selected job and operator permissions. Current permission: {current_permission}.",
        ),
        
        UiActionType.PORTFOLIO_ARTIFACTS: UiActionPolicy(
            action_type=UiActionType.PORTFOLIO_ARTIFACTS,
            requires_selected_job=True,
            disabled_reason_code=GateReasonCode.GATE_SUMMARY_FETCH_ERROR.value,
            explanation_template="Portfolio artifacts requires a selected job. No job is currently selected.",
        ),
        
        UiActionType.PORTFOLIO_REPORT: UiActionPolicy(
            action_type=UiActionType.PORTFOLIO_REPORT,
            requires_selected_job=True,
            disabled_reason_code=GateReasonCode.GATE_SUMMARY_FETCH_ERROR.value,
            explanation_template="Portfolio report requires a selected job. No job is currently selected.",
        ),
        
        # Gate dashboard navigation
        UiActionType.GATE_DASHBOARD: UiActionPolicy(
            action_type=UiActionType.GATE_DASHBOARD,
            requires_active_tab=UiTab.GATE_SUMMARY_DASHBOARD,
            disabled_reason_code=GateReasonCode.GATE_SUMMARY_FETCH_ERROR.value,
            explanation_template="Gate dashboard requires active gate dashboard tab. Current tab: {current_tab}.",
        ),
        
        UiActionType.NAVIGATE_GATE_DASHBOARD: UiActionPolicy(
            action_type=UiActionType.NAVIGATE_GATE_DASHBOARD,
            requires_system_ready=True,
            disabled_reason_code=GateReasonCode.GATE_SUMMARY_FETCH_ERROR.value,
            explanation_template="Gate dashboard navigation requires system to be ready. System ready: {system_ready}.",
        ),
        
        # System health - always available
        UiActionType.SYSTEM_HEALTH: UiActionPolicy(
            action_type=UiActionType.SYSTEM_HEALTH,
            requires_system_ready=False,  # Can check health even if system not ready
            disabled_reason_code=GateReasonCode.GATE_SUMMARY_FETCH_ERROR.value,
            explanation_template="System health check is always available.",
        ),
        
        # Batch operations - require system readiness
        UiActionType.BATCH_STATUS: UiActionPolicy(
            action_type=UiActionType.BATCH_STATUS,
            requires_system_ready=True,
            disabled_reason_code=GateReasonCode.GATE_SUMMARY_FETCH_ERROR.value,
            explanation_template="Batch status requires system to be ready. System ready: {system_ready}.",
        ),
        
        UiActionType.BATCH_METADATA: UiActionPolicy(
            action_type=UiActionType.BATCH_METADATA,
            requires_system_ready=True,
            requires_permission_level=PermissionLevel.OPERATOR,
            disabled_reason_code=GateReasonCode.GATE_SUMMARY_FETCH_ERROR.value,
            explanation_template="Batch metadata requires system readiness and operator permissions. System ready: {system_ready}, permission: {current_permission}.",
        ),
        
        # Season compare and export - require edit mode
        UiActionType.SEASON_COMPARE: UiActionPolicy(
            action_type=UiActionType.SEASON_COMPARE,
            requires_ui_mode=UiMode.EDIT,
            requires_permission_level=PermissionLevel.OPERATOR,
            disabled_reason_code=GateReasonCode.GATE_SUMMARY_FETCH_ERROR.value,
            explanation_template="Season comparison requires edit mode and operator permissions. Current mode: {current_mode}, permission: {current_permission}.",
        ),
        
        UiActionType.SEASON_EXPORT: UiActionPolicy(
            action_type=UiActionType.SEASON_EXPORT,
            requires_ui_mode=UiMode.EDIT,
            requires_permission_level=PermissionLevel.OPERATOR,
            disabled_reason_code=GateReasonCode.GATE_SUMMARY_FETCH_ERROR.value,
            explanation_template="Season export requires edit mode and operator permissions. Current mode: {current_mode}, permission: {current_permission}.",
        ),
    }
    
    # Create registry
    registry = UiActionPolicyRegistry(policies=policies)
    return registry


# -----------------------------------------------------------------------------
# Singleton Action Policy Registry
# -----------------------------------------------------------------------------

_DEFAULT_ACTION_POLICY_REGISTRY: Optional[UiActionPolicyRegistry] = None


def get_default_action_policy_registry() -> UiActionPolicyRegistry:
    """Get singleton instance of default action policy registry."""
    global _DEFAULT_ACTION_POLICY_REGISTRY
    if _DEFAULT_ACTION_POLICY_REGISTRY is None:
        _DEFAULT_ACTION_POLICY_REGISTRY = create_default_action_policies()
    return _DEFAULT_ACTION_POLICY_REGISTRY


def reload_action_policy_registry() -> UiActionPolicyRegistry:
    """Reload the action policy registry (for testing)."""
    global _DEFAULT_ACTION_POLICY_REGISTRY
    _DEFAULT_ACTION_POLICY_REGISTRY = create_default_action_policies()
    return _DEFAULT_ACTION_POLICY_REGISTRY


# -----------------------------------------------------------------------------
# Integration Helpers
# -----------------------------------------------------------------------------

def check_ui_action_enabled(
    action_type: UiActionType,
    state: Optional[UiGovernanceState] = None
) -> Dict[str, Any]:
    """
    Check if a UI action is enabled given current UI state.
    
    Args:
        action_type: UI action type to check
        state: Optional UI governance state (uses current singleton if None)
        
    Returns:
        Dict with enabled status, reason code, and explanation
    """
    if state is None:
        state = ui_governance_state.get_state()
    
    registry = get_default_action_policy_registry()
    return registry.check_action_enabled(action_type, state)


def validate_action_for_target(
    target: str,
    state: Optional[UiGovernanceState] = None
) -> Dict[str, Any]:
    """
    Validate if an action target is enabled given current UI state.
    
    Args:
        target: Action target string (e.g., "gate_summary", "job_admission://job123")
        state: Optional UI governance state
        
    Returns:
        Dict with enabled status, reason code, and explanation
    """
    from contracts.ui_action_registry import get_action_metadata_for_target
    
    # Get action metadata for target
    metadata = get_action_metadata_for_target(target)
    if not metadata:
        return {
            "enabled": True,
            "reason_code": None,
            "explanation": None,
            "context_vars": {},
        }
    
    # Check if action is enabled
    return check_ui_action_enabled(metadata.action_type, state)


# -----------------------------------------------------------------------------
# Export
# -----------------------------------------------------------------------------

__all__ = [
    # Enums
    "UiMode",
    "PermissionLevel",
    "DataReadinessStatus",
    "UiTab",
    
    # Models
    "UiGovernanceState",
    "UiActionPolicy",
    "UiActionPolicyRegistry",
    
    # Singleton
    "UiGovernanceStateHolder",
    "ui_governance_state",
    
    # Registry functions
    "create_default_action_policies",
    "get_default_action_policy_registry",
    "reload_action_policy_registry",
    
    # Integration helpers
    "check_ui_action_enabled",
    "validate_action_for_target",
]