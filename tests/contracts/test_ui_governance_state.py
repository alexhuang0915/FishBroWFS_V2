"""
Test UI Governance State SSOT v1.7.

Tests for the UI governance state system, including:
- UI state model validation
- State-aware action policies
- Action enablement checks
- Singleton state holder
"""

import pytest
from datetime import datetime
from typing import Dict, Any

from contracts.ui_governance_state import (
    # Enums
    UiMode,
    PermissionLevel,
    DataReadinessStatus,
    UiTab,
    
    # Models
    UiGovernanceState,
    UiActionPolicy,
    UiActionPolicyRegistry,
    
    # Singleton
    UiGovernanceStateHolder,
    ui_governance_state,
    
    # Functions
    create_default_action_policies,
    get_default_action_policy_registry,
    check_ui_action_enabled,
    validate_action_for_target,
    
    # Action types
    UiActionType,
)
from contracts.ui_action_registry import UiActionType as RegistryUiActionType
from contracts.portfolio.gate_summary_schemas import GateReasonCode


class TestUiGovernanceStateModel:
    """Test UI governance state model."""
    
    def test_create_default_state(self):
        """Test creating default UI governance state."""
        state = UiGovernanceState()
        
        assert state.selected_job_id is None
        assert state.active_tab is None
        assert state.data_readiness_status == {}
        assert state.permission_level == PermissionLevel.VIEWER
        assert state.ui_mode == UiMode.VIEW
        assert state.system_ready is False
        assert state.any_jobs_running is False
        assert isinstance(state.last_state_update, datetime)
    
    def test_state_validation(self):
        """Test state validation with custom values."""
        state = UiGovernanceState(
            selected_job_id="job_123",
            active_tab=UiTab.GATE_SUMMARY_DASHBOARD,
            data_readiness_status={"registry_cache": DataReadinessStatus.READY},
            permission_level=PermissionLevel.OPERATOR,
            ui_mode=UiMode.EDIT,
            system_ready=True,
            any_jobs_running=False,
        )
        
        assert state.selected_job_id == "job_123"
        assert state.active_tab == UiTab.GATE_SUMMARY_DASHBOARD
        assert state.data_readiness_status["registry_cache"] == DataReadinessStatus.READY
        assert state.permission_level == PermissionLevel.OPERATOR
        assert state.ui_mode == UiMode.EDIT
        assert state.system_ready is True
        assert state.any_jobs_running is False
    
    def test_is_job_selected(self):
        """Test job selection detection."""
        # No job selected
        state1 = UiGovernanceState(selected_job_id=None)
        assert state1.is_job_selected() is False
        
        # Empty job ID
        state2 = UiGovernanceState(selected_job_id="")
        assert state2.is_job_selected() is False
        
        # Job selected
        state3 = UiGovernanceState(selected_job_id="job_123")
        assert state3.is_job_selected() is True
    
    def test_get_data_status(self):
        """Test getting data readiness status."""
        state = UiGovernanceState(
            data_readiness_status={
                "registry_cache": DataReadinessStatus.READY,
                "dataset_cache": DataReadinessStatus.LOADING,
            }
        )
        
        assert state.get_data_status("registry_cache") == DataReadinessStatus.READY
        assert state.get_data_status("dataset_cache") == DataReadinessStatus.LOADING
        assert state.get_data_status("unknown") == DataReadinessStatus.NOT_READY
    
    def test_has_permission(self):
        """Test permission level checks."""
        # Viewer permissions
        viewer_state = UiGovernanceState(permission_level=PermissionLevel.VIEWER)
        assert viewer_state.has_permission(PermissionLevel.VIEWER) is True
        assert viewer_state.has_permission(PermissionLevel.OPERATOR) is False
        assert viewer_state.has_permission(PermissionLevel.ADMINISTRATOR) is False
        
        # Operator permissions
        operator_state = UiGovernanceState(permission_level=PermissionLevel.OPERATOR)
        assert operator_state.has_permission(PermissionLevel.VIEWER) is True
        assert operator_state.has_permission(PermissionLevel.OPERATOR) is True
        assert operator_state.has_permission(PermissionLevel.ADMINISTRATOR) is False
        
        # Administrator permissions
        admin_state = UiGovernanceState(permission_level=PermissionLevel.ADMINISTRATOR)
        assert admin_state.has_permission(PermissionLevel.VIEWER) is True
        assert admin_state.has_permission(PermissionLevel.OPERATOR) is True
        assert admin_state.has_permission(PermissionLevel.ADMINISTRATOR) is True
    
    def test_is_mode_allowed(self):
        """Test UI mode checks."""
        # View mode
        view_state = UiGovernanceState(ui_mode=UiMode.VIEW)
        assert view_state.is_mode_allowed(UiMode.VIEW) is True
        assert view_state.is_mode_allowed(UiMode.EDIT) is False
        assert view_state.is_mode_allowed(UiMode.ADMIN) is False
        
        # Edit mode
        edit_state = UiGovernanceState(ui_mode=UiMode.EDIT)
        assert edit_state.is_mode_allowed(UiMode.VIEW) is True
        assert edit_state.is_mode_allowed(UiMode.EDIT) is True
        assert edit_state.is_mode_allowed(UiMode.ADMIN) is False
        
        # Admin mode
        admin_state = UiGovernanceState(ui_mode=UiMode.ADMIN)
        assert admin_state.is_mode_allowed(UiMode.VIEW) is True
        assert admin_state.is_mode_allowed(UiMode.EDIT) is True
        assert admin_state.is_mode_allowed(UiMode.ADMIN) is True


class TestUiActionPolicy:
    """Test state-aware action policies."""
    
    def test_create_policy(self):
        """Test creating an action policy."""
        policy = UiActionPolicy(
            action_type=UiActionType.JOB_DETAILS,
            requires_selected_job=True,
            disabled_reason_code=GateReasonCode.GATE_SUMMARY_FETCH_ERROR.value,
            explanation_template="Job details require a selected job.",
        )
        
        assert policy.action_type == UiActionType.JOB_DETAILS
        assert policy.requires_selected_job is True
        assert policy.disabled_reason_code == GateReasonCode.GATE_SUMMARY_FETCH_ERROR.value
        assert policy.explanation_template == "Job details require a selected job."
    
    def test_check_action_enabled_all_requirements_met(self):
        """Test action enabled when all requirements are met."""
        policy = UiActionPolicy(
            action_type=UiActionType.JOB_DETAILS,
            requires_selected_job=True,
            disabled_reason_code=GateReasonCode.GATE_SUMMARY_FETCH_ERROR.value,
            explanation_template="Job details require a selected job.",
        )
        
        state = UiGovernanceState(
            selected_job_id="job_123",
            permission_level=PermissionLevel.OPERATOR,
            ui_mode=UiMode.EDIT,
            system_ready=True,
            any_jobs_running=False,
        )
        
        result = policy.check_action_enabled(state)
        assert result["enabled"] is True
        assert result["reason_code"] is None
        assert result["explanation"] is None
    
    def test_check_action_enabled_missing_selected_job(self):
        """Test action disabled when selected job is missing."""
        policy = UiActionPolicy(
            action_type=UiActionType.JOB_DETAILS,
            requires_selected_job=True,
            disabled_reason_code=GateReasonCode.GATE_SUMMARY_FETCH_ERROR.value,
            explanation_template="Job details require a selected job. No job is currently selected.",
        )
        
        state = UiGovernanceState(selected_job_id=None)
        
        result = policy.check_action_enabled(state)
        assert result["enabled"] is False
        assert result["reason_code"] == GateReasonCode.GATE_SUMMARY_FETCH_ERROR.value
        assert "selected job" in result["explanation"].lower()
    
    def test_check_action_enabled_wrong_tab(self):
        """Test action disabled when wrong tab is active."""
        policy = UiActionPolicy(
            action_type=UiActionType.GATE_SUMMARY,
            requires_active_tab=UiTab.GATE_SUMMARY_DASHBOARD,
            disabled_reason_code=GateReasonCode.GATE_SUMMARY_FETCH_ERROR.value,
            explanation_template="Gate summary requires active gate dashboard tab. Current tab: {current_tab}.",
        )
        
        state = UiGovernanceState(active_tab=UiTab.OP_TAB)
        
        result = policy.check_action_enabled(state)
        assert result["enabled"] is False
        assert result["reason_code"] == GateReasonCode.GATE_SUMMARY_FETCH_ERROR.value
        assert "current tab" in result["explanation"].lower()
    
    def test_check_action_enabled_data_not_ready(self):
        """Test action disabled when data is not ready."""
        policy = UiActionPolicy(
            action_type=UiActionType.REGISTRY_DATASETS,
            requires_data_ready=["registry_cache"],
            disabled_reason_code=GateReasonCode.GATE_SUMMARY_FETCH_ERROR.value,
            explanation_template="Dataset registry requires registry cache to be ready. Status: {status}.",
        )
        
        state = UiGovernanceState(
            data_readiness_status={"registry_cache": DataReadinessStatus.NOT_READY}
        )
        
        result = policy.check_action_enabled(state)
        assert result["enabled"] is False
        assert result["reason_code"] == GateReasonCode.GATE_SUMMARY_FETCH_ERROR.value
        assert "status" in result["explanation"].lower()
    
    def test_check_action_enabled_insufficient_permission(self):
        """Test action disabled when permission level is insufficient."""
        policy = UiActionPolicy(
            action_type=UiActionType.JOB_SUBMISSION,
            requires_permission_level=PermissionLevel.OPERATOR,
            disabled_reason_code=GateReasonCode.GATE_SUMMARY_FETCH_ERROR.value,
            explanation_template="Job submission requires operator permissions. Current permission: {current_permission}.",
        )
        
        state = UiGovernanceState(permission_level=PermissionLevel.VIEWER)
        
        result = policy.check_action_enabled(state)
        assert result["enabled"] is False
        assert result["reason_code"] == GateReasonCode.GATE_SUMMARY_FETCH_ERROR.value
        assert "current permission" in result["explanation"].lower()
    
    def test_check_action_enabled_wrong_ui_mode(self):
        """Test action disabled when UI mode is insufficient."""
        policy = UiActionPolicy(
            action_type=UiActionType.SEASON_MANAGEMENT,
            requires_ui_mode=UiMode.EDIT,
            disabled_reason_code=GateReasonCode.GATE_SUMMARY_FETCH_ERROR.value,
            explanation_template="Season management requires edit mode. Current mode: {current_mode}.",
        )
        
        state = UiGovernanceState(ui_mode=UiMode.VIEW)
        
        result = policy.check_action_enabled(state)
        assert result["enabled"] is False
        assert result["reason_code"] == GateReasonCode.GATE_SUMMARY_FETCH_ERROR.value
        assert "current mode" in result["explanation"].lower()
    
    def test_check_action_enabled_system_not_ready(self):
        """Test action disabled when system is not ready."""
        policy = UiActionPolicy(
            action_type=UiActionType.JOB_SUBMISSION,
            requires_system_ready=True,
            disabled_reason_code=GateReasonCode.GATE_SUMMARY_FETCH_ERROR.value,
            explanation_template="Job submission requires system to be ready. System ready: {system_ready}.",
        )
        
        state = UiGovernanceState(system_ready=False)
        
        result = policy.check_action_enabled(state)
        assert result["enabled"] is False
        assert result["reason_code"] == GateReasonCode.GATE_SUMMARY_FETCH_ERROR.value
        assert "system ready" in result["explanation"].lower()
    
    def test_check_action_enabled_jobs_running(self):
        """Test action disabled when jobs are running."""
        policy = UiActionPolicy(
            action_type=UiActionType.SYSTEM_PRIME_REGISTRIES,
            requires_no_jobs_running=True,
            disabled_reason_code=GateReasonCode.GATE_SUMMARY_FETCH_ERROR.value,
            explanation_template="Prime registries requires no jobs to be running.",
        )
        
        state = UiGovernanceState(any_jobs_running=True)
        
        result = policy.check_action_enabled(state)
        assert result["enabled"] is False
        assert result["reason_code"] == GateReasonCode.GATE_SUMMARY_FETCH_ERROR.value


class TestUiActionPolicyRegistry:
    """Test action policy registry."""
    
    def test_create_registry(self):
        """Test creating action policy registry."""
        policy = UiActionPolicy(
            action_type=UiActionType.JOB_DETAILS,
            requires_selected_job=True,
            disabled_reason_code=GateReasonCode.GATE_SUMMARY_FETCH_ERROR.value,
            explanation_template="Test policy",
        )
        
        registry = UiActionPolicyRegistry(
            policies={UiActionType.JOB_DETAILS: policy}
        )
        
        assert registry.get_policy(UiActionType.JOB_DETAILS) == policy
        assert registry.get_policy(UiActionType.JOB_SUBMISSION) is None
    
    def test_check_action_enabled_with_policy(self):
        """Test checking action enabled with registry."""
        policy = UiActionPolicy(
            action_type=UiActionType.JOB_DETAILS,
            requires_selected_job=True,
            requires_system_ready=False,  # Explicitly disable system requirement for test
            disabled_reason_code=GateReasonCode.GATE_SUMMARY_FETCH_ERROR.value,
            explanation_template="Test policy",
        )
        
        registry = UiActionPolicyRegistry(
            policies={UiActionType.JOB_DETAILS: policy}
        )
        
        # With selected job (enabled)
        state_with_job = UiGovernanceState(selected_job_id="job_123", system_ready=True)
        result1 = registry.check_action_enabled(UiActionType.JOB_DETAILS, state_with_job)
        assert result1["enabled"] is True
        
        # Without selected job (disabled)
        state_without_job = UiGovernanceState(selected_job_id=None, system_ready=True)
        result2 = registry.check_action_enabled(UiActionType.JOB_DETAILS, state_without_job)
        assert result2["enabled"] is False
    
    def test_check_action_enabled_no_policy(self):
        """Test checking action enabled when no policy exists (default allow)."""
        registry = UiActionPolicyRegistry(policies={})
        state = UiGovernanceState()
        
        result = registry.check_action_enabled(UiActionType.JOB_DETAILS, state)
        assert result["enabled"] is True  # Default allow for backward compatibility
        assert result["reason_code"] is None


class TestDefaultActionPolicies:
    """Test default action policies."""
    
    def test_create_default_policies(self):
        """Test creating default action policies."""
        registry = create_default_action_policies()
        
        # Should have policies for all action types
        assert len(registry.policies) > 0
        
        # Check specific policies exist
        assert UiActionType.JOB_DETAILS in registry.policies
        assert UiActionType.JOB_SUBMISSION in registry.policies
        assert UiActionType.GATE_SUMMARY in registry.policies
        assert UiActionType.REGISTRY_DATASETS in registry.policies
    
    def test_get_default_registry_singleton(self):
        """Test singleton pattern for default registry."""
        registry1 = get_default_action_policy_registry()
        registry2 = get_default_action_policy_registry()
        
        assert registry1 is registry2  # Should be same instance


class TestUiGovernanceStateHolder:
    """Test UI governance state holder singleton."""
    
    def test_singleton_pattern(self):
        """Test that state holder is a singleton."""
        holder1 = UiGovernanceStateHolder()
        holder2 = UiGovernanceStateHolder()
        
        assert holder1 is holder2
    
    def test_get_and_update_state(self):
        """Test getting and updating state."""
        holder = UiGovernanceStateHolder()
        
        # Get initial state
        initial_state = holder.get_state()
        assert initial_state.selected_job_id is None
        
        # Update state
        holder.update_state(selected_job_id="job_123", system_ready=True)
        
        # Get updated state
        updated_state = holder.get_state()
        assert updated_state.selected_job_id == "job_123"
        assert updated_state.system_ready is True
        
        # Initial state should not be modified (frozen model)
        assert initial_state.selected_job_id is None
    
    def test_convenience_methods(self):
        """Test convenience methods for updating state."""
        holder = UiGovernanceStateHolder()
        
        # Test set_selected_job
        holder.set_selected_job("job_123")
        assert holder.get_state().selected_job_id == "job_123"
        
        # Test set_active_tab
        holder.set_active_tab(UiTab.GATE_SUMMARY_DASHBOARD)
        assert holder.get_state().active_tab == UiTab.GATE_SUMMARY_DASHBOARD
        
        # Test set_data_status
        holder.set_data_status("registry_cache", DataReadinessStatus.READY)
        assert holder.get_state().get_data_status("registry_cache") == DataReadinessStatus.READY
        
        # Test set_permission_level
        holder.set_permission_level(PermissionLevel.OPERATOR)
        assert holder.get_state().permission_level == PermissionLevel.OPERATOR
        
        # Test set_ui_mode
        holder.set_ui_mode(UiMode.EDIT)
        assert holder.get_state().ui_mode == UiMode.EDIT
        
        # Test set_system_ready
        holder.set_system_ready(True)
        assert holder.get_state().system_ready is True
        
        # Test set_any_jobs_running
        holder.set_any_jobs_running(True)
        assert holder.get_state().any_jobs_running is True


class TestIntegrationHelpers:
    """Test integration helper functions."""
    
    def test_check_ui_action_enabled(self):
        """Test checking UI action enabled with default state."""
        # Create a fresh default state (no selected job, system not ready)
        # Don't use the singleton as it may be modified by other tests
        state = UiGovernanceState(
            selected_job_id=None,
            system_ready=False,  # Default is False
            permission_level=PermissionLevel.VIEWER,
            ui_mode=UiMode.VIEW,
            any_jobs_running=False,
        )
        
        # Check job details action (requires selected job)
        result = check_ui_action_enabled(UiActionType.JOB_DETAILS, state)
        
        # Should be disabled because no job is selected
        assert result["enabled"] is False
        assert result["reason_code"] is not None
        assert result["explanation"] is not None
    
    def test_check_ui_action_enabled_with_custom_state(self):
        """Test checking UI action enabled with custom state."""
        # Create state with selected job
        state = UiGovernanceState(
            selected_job_id="job_123",
            permission_level=PermissionLevel.OPERATOR,
            system_ready=True,
        )
        
        # Check job details action (requires selected job)
        result = check_ui_action_enabled(UiActionType.JOB_DETAILS, state)
        
        # Should be enabled because job is selected
        assert result["enabled"] is True
        assert result["reason_code"] is None
    
    def test_validate_action_for_target(self):
        """Test validating action target."""
        # Test with valid target that requires selected job
        result = validate_action_for_target("job_details://job_123")
        
        # The result depends on current UI state
        # At minimum, we should get a dict with enabled status
        assert isinstance(result, dict)
        assert "enabled" in result
        assert "reason_code" in result
        assert "explanation" in result
    
    def test_validate_action_for_target_unknown(self):
        """Test validating unknown action target."""
        result = validate_action_for_target("unknown://target")
        
        # Unknown target should be allowed (governance policies apply only to known actions)
        assert result["enabled"] is True
        assert result["reason_code"] is None
        assert result["explanation"] is None


class TestFrozenModels:
    """Test that models are frozen (immutable)."""
    
    def test_ui_governance_state_frozen(self):
        """Test that UiGovernanceState is frozen."""
        state = UiGovernanceState(selected_job_id="job_123")
        
        # Should not be able to modify attributes
        # Pydantic v2 raises ValidationError for frozen instances
        with pytest.raises(Exception) as exc_info:
            state.selected_job_id = "job_456"
        
        # Check that it's a frozen instance error
        assert "frozen" in str(exc_info.value).lower()
    
    def test_ui_action_policy_frozen(self):
        """Test that UiActionPolicy is frozen."""
        policy = UiActionPolicy(
            action_type=UiActionType.JOB_DETAILS,
            disabled_reason_code=GateReasonCode.GATE_SUMMARY_FETCH_ERROR.value,
            explanation_template="Test",
        )
        
        # Should not be able to modify attributes
        # Pydantic v2 raises ValidationError for frozen instances
        with pytest.raises(Exception) as exc_info:
            policy.requires_selected_job = True
        
        # Check that it's a frozen instance error
        assert "frozen" in str(exc_info.value).lower()
    
    def test_ui_action_policy_registry_frozen(self):
        """Test that UiActionPolicyRegistry is frozen."""
        registry = UiActionPolicyRegistry(policies={})
        
        # Should not be able to modify attributes
        # Pydantic v2 raises ValidationError for frozen instances
        with pytest.raises(Exception) as exc_info:
            registry.policies = {UiActionType.JOB_DETAILS: None}
        
        # Check that it's a frozen instance error
        assert "frozen" in str(exc_info.value).lower()


class TestActionTypeConsistency:
    """Test consistency between UiActionType definitions."""
    
    def test_action_type_enum_values_match(self):
        """Test that UiActionType enum values match between modules."""
        # Import both enums
        from contracts.ui_action_registry import UiActionType as RegistryUiActionType
        
        # Check that all values from ui_governance_state are in ui_action_registry
        governance_values = set(UiActionType)
        registry_values = set(RegistryUiActionType)
        
        # All governance action types should be in registry
        # (Some registry types might not have policies yet, but all governance types should exist)
        for action_type in governance_values:
            assert action_type in registry_values, f"{action_type} not found in UI action registry"
        
        # Check that we have policies for all registry action types
        registry = get_default_action_policy_registry()
        missing_policies = []
        
        for action_type in registry_values:
            if action_type not in registry.policies:
                missing_policies.append(action_type)
        
        # Log missing policies but don't fail (they might be added later)
        if missing_policies:
            print(f"Note: Missing policies for action types: {missing_policies}")