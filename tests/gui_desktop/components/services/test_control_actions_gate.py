"""
Unit tests for control_actions_gate module.
"""

import os
import pytest
from unittest.mock import patch

from gui.services.control_actions_gate import (
    is_control_actions_enabled,
    get_control_actions_block_reason,
    is_job_abortable,
    is_abort_allowed,
    get_control_actions_indicator_text,
    get_control_actions_indicator_tooltip,
    get_abort_button_tooltip,
    get_abort_attribution_summary,
)


class TestControlActionsGate:
    """Test suite for control actions gate functions."""
    
    def test_is_control_actions_enabled_default(self):
        """By default, control actions should be disabled (safe)."""
        # Clear the environment variable
        with patch.dict(os.environ, {}, clear=True):
            assert is_control_actions_enabled() is False
    
    def test_is_control_actions_enabled_when_set_to_1(self):
        """Control actions enabled when FISHBRO_ENABLE_CONTROL_ACTIONS=1."""
        with patch.dict(os.environ, {"FISHBRO_ENABLE_CONTROL_ACTIONS": "1"}):
            assert is_control_actions_enabled() is True
    
    def test_is_control_actions_enabled_when_set_to_other(self):
        """Control actions disabled when FISHBRO_ENABLE_CONTROL_ACTIONS is not '1'."""
        test_cases = [
            ("0", False),
            ("true", False),
            ("TRUE", False),
            ("yes", False),
            ("", False),
            (" ", False),  # whitespace
        ]
        
        for env_value, expected in test_cases:
            with patch.dict(os.environ, {"FISHBRO_ENABLE_CONTROL_ACTIONS": env_value}):
                assert is_control_actions_enabled() == expected, f"Failed for value '{env_value}'"
    
    def test_get_control_actions_block_reason_when_enabled(self):
        """Block reason should be None when control actions are enabled."""
        with patch.dict(os.environ, {"FISHBRO_ENABLE_CONTROL_ACTIONS": "1"}):
            assert get_control_actions_block_reason() is None
    
    def test_get_control_actions_block_reason_when_not_set(self):
        """Block reason should mention variable not set."""
        with patch.dict(os.environ, {}, clear=True):
            reason = get_control_actions_block_reason()
            assert reason is not None
            assert "FISHBRO_ENABLE_CONTROL_ACTIONS not set" in reason
    
    def test_get_control_actions_block_reason_when_empty(self):
        """Block reason should mention variable is empty."""
        with patch.dict(os.environ, {"FISHBRO_ENABLE_CONTROL_ACTIONS": ""}):
            reason = get_control_actions_block_reason()
            assert reason is not None
            assert "empty" in reason.lower() or "FISHBRO_ENABLE_CONTROL_ACTIONS is empty" in reason
    
    def test_get_control_actions_block_reason_when_other_value(self):
        """Block reason should mention the actual value."""
        with patch.dict(os.environ, {"FISHBRO_ENABLE_CONTROL_ACTIONS": "0"}):
            reason = get_control_actions_block_reason()
            assert reason is not None
            assert "0" in reason
            assert "expected '1'" in reason
    
    def test_is_job_abortable(self):
        """Test job abortable status detection."""
        # Abortable statuses
        abortable_statuses = {"QUEUED", "RUNNING", "PENDING", "STARTED"}
        for status in abortable_statuses:
            assert is_job_abortable(status) is True, f"Status {status} should be abortable"
        
        # Non-abortable statuses
        non_abortable_statuses = {"SUCCEEDED", "FAILED", "ABORTED", "REJECTED", "UNKNOWN", ""}
        for status in non_abortable_statuses:
            assert is_job_abortable(status) is False, f"Status {status} should not be abortable"
    
    def test_is_abort_allowed_combined(self):
        """Test combined check of gate and job status."""
        test_cases = [
            # (env_value, job_status, expected_result)
            ("1", "RUNNING", True),   # Enabled + abortable = allowed
            ("1", "QUEUED", True),    # Enabled + abortable = allowed
            ("1", "SUCCEEDED", False), # Enabled but not abortable = not allowed
            ("0", "RUNNING", False),  # Disabled but abortable = not allowed
            ("", "RUNNING", False),   # Disabled but abortable = not allowed
            (None, "RUNNING", False), # Disabled but abortable = not allowed
            ("1", "UNKNOWN", False),  # Enabled but not abortable = not allowed
        ]
        
        for env_value, job_status, expected in test_cases:
            env_dict = {}
            if env_value is not None:
                env_dict["FISHBRO_ENABLE_CONTROL_ACTIONS"] = env_value
            
            with patch.dict(os.environ, env_dict, clear=True):
                result = is_abort_allowed(job_status)
                assert result == expected, (
                    f"Failed for env={env_value}, status={job_status}: "
                    f"expected {expected}, got {result}"
                )
    
    def test_deterministic_strings(self):
        """Block reason strings should be deterministic and stable."""
        # Test that the same input produces the same output
        with patch.dict(os.environ, {}, clear=True):
            reason1 = get_control_actions_block_reason()
            reason2 = get_control_actions_block_reason()
            assert reason1 == reason2, "Block reason should be deterministic"
        
        with patch.dict(os.environ, {"FISHBRO_ENABLE_CONTROL_ACTIONS": "1"}):
            reason1 = get_control_actions_block_reason()
            reason2 = get_control_actions_block_reason()
            assert reason1 == reason2 == None, "Enabled should always return None"
    
    def test_get_control_actions_indicator_text(self):
        """Test indicator text generation."""
        # When disabled
        with patch.dict(os.environ, {}, clear=True):
            primary, secondary = get_control_actions_indicator_text()
            assert "DISABLED" in primary
            assert "Disabled (safe default)" in secondary
        
        # When enabled
        with patch.dict(os.environ, {"FISHBRO_ENABLE_CONTROL_ACTIONS": "1"}):
            primary, secondary = get_control_actions_indicator_text()
            assert "ENABLED" in primary
            assert "Enabled by: ENV (FISHBRO_ENABLE_CONTROL_ACTIONS=1)" in secondary
    
    def test_get_control_actions_indicator_tooltip(self):
        """Test indicator tooltip generation."""
        # When disabled
        with patch.dict(os.environ, {}, clear=True):
            tooltip = get_control_actions_indicator_tooltip()
            assert "disabled by default" in tooltip.lower()
            assert "FISHBRO_ENABLE_CONTROL_ACTIONS=1" in tooltip
        
        # When enabled
        with patch.dict(os.environ, {"FISHBRO_ENABLE_CONTROL_ACTIONS": "1"}):
            tooltip = get_control_actions_indicator_tooltip()
            assert "enabled via environment variable" in tooltip.lower()
    
    def test_get_abort_button_tooltip(self):
        """Test abort button tooltip generation."""
        # Enabled case
        tooltip_enabled = get_abort_button_tooltip(is_enabled=True)
        assert "Requests job abort" in tooltip_enabled
        assert "Requires confirmation" in tooltip_enabled
        assert "Writes an audit record" in tooltip_enabled
        assert "Job may take time to stop" in tooltip_enabled
        
        # Disabled case
        tooltip_disabled = get_abort_button_tooltip(is_enabled=False)
        assert "Control actions are disabled" in tooltip_disabled
        assert "Enable via ENV FISHBRO_ENABLE_CONTROL_ACTIONS=1" in tooltip_disabled
        
        # Job status parameter is optional and currently unused, but ensure it doesn't break
        tooltip_with_status = get_abort_button_tooltip(is_enabled=True, job_status="RUNNING")
        assert "Requests job abort" in tooltip_with_status
    
    def test_get_abort_attribution_summary(self):
        """Test abort attribution summary generation."""
        # Non-ABORTED status returns empty string
        assert get_abort_attribution_summary("RUNNING", {}) == ""
        assert get_abort_attribution_summary("SUCCEEDED", None) == ""
        
        # ABORTED with no error_details
        assert get_abort_attribution_summary("ABORTED", None) == "Abort reason unknown."
        assert get_abort_attribution_summary("ABORTED", {}) == "Abort reason unknown."
        
        # ABORTED with error_details
        # User abort
        user_abort_details = {"type": "AbortRequested", "msg": "user_abort"}
        assert "User manually aborted" in get_abort_attribution_summary("ABORTED", user_abort_details)
        
        # Supervisor abort
        supervisor_abort_details = {"type": "AbortRequested", "msg": "some other reason"}
        assert "aborted by supervisor" in get_abort_attribution_summary("ABORTED", supervisor_abort_details).lower()
        
        # Heartbeat timeout
        timeout_details = {"type": "HeartbeatTimeout", "msg": "worker timed out"}
        assert "heartbeat lost" in get_abort_attribution_summary("ABORTED", timeout_details).lower()
        
        # Orphaned
        orphaned_details = {"type": "Orphaned", "msg": "worker disappeared"}
        assert "orphaned" in get_abort_attribution_summary("ABORTED", orphaned_details).lower()
        
        # Unknown type
        unknown_details = {"type": "UnknownType", "msg": "something"}
        assert get_abort_attribution_summary("ABORTED", unknown_details) == "Job was aborted."


if __name__ == "__main__":
    pytest.main([__file__, "-v"])