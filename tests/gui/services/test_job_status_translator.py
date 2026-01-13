"""
Unit tests for job_status_translator.
"""

import pytest
from gui.services.job_status_translator import translate_job_status


class TestJobStatusTranslator:
    """Test suite for translate_job_status."""

    def test_success(self):
        """SUCCEEDED status."""
        result = translate_job_status("SUCCEEDED", None)
        assert "completed successfully" in result.lower()

    def test_running(self):
        """RUNNING status."""
        result = translate_job_status("RUNNING", None)
        assert "running" in result.lower()

    def test_pending(self):
        """PENDING status."""
        result = translate_job_status("PENDING", None)
        assert "pending" in result.lower()

    def test_queued(self):
        """QUEUED status."""
        result = translate_job_status("QUEUED", None)
        assert "queued" in result.lower()

    def test_failed_without_details(self):
        """FAILED status without error_details."""
        result = translate_job_status("FAILED", None)
        assert "failed" in result.lower()
        assert "unknown reason" in result.lower()

    def test_failed_with_execution_error(self):
        """FAILED with ExecutionError."""
        error_details = {
            "type": "ExecutionError",
            "msg": "Strategy raised exception",
            "traceback": "Traceback...",
            "phase": "bootstrap"
        }
        result = translate_job_status("FAILED", error_details)
        assert "execution error" in result.lower()
        assert "strategy raised exception" in result.lower()

    def test_failed_with_validation_error(self):
        """FAILED with ValidationError."""
        error_details = {
            "type": "ValidationError",
            "msg": "Invalid parameters",
            "phase": "bootstrap"
        }
        result = translate_job_status("FAILED", error_details)
        assert "job parameters failed validation" in result.lower()
        # translator doesn't include the exact msg

    def test_failed_with_spec_parse_error(self):
        """FAILED with SpecParseError."""
        error_details = {
            "type": "SpecParseError",
            "msg": "Could not parse spec",
            "phase": "bootstrap"
        }
        result = translate_job_status("FAILED", error_details)
        assert "job specification could not be parsed" in result.lower()

    def test_failed_with_unknown_handler(self):
        """FAILED with UnknownHandler."""
        error_details = {
            "type": "UnknownHandler",
            "msg": "Handler not found",
            "phase": "bootstrap"
        }
        result = translate_job_status("FAILED", error_details)
        assert "unknown job handler" in result.lower()

    def test_aborted_without_details(self):
        """ABORTED status without error_details."""
        result = translate_job_status("ABORTED", None)
        assert "aborted" in result.lower()
        assert "unknown reason" in result.lower()

    def test_aborted_with_abort_requested(self):
        """ABORTED with AbortRequested."""
        error_details = {
            "type": "AbortRequested",
            "msg": "user_abort",
            "pid": 12345,
            "phase": "supervisor"
        }
        result = translate_job_status("ABORTED", error_details)
        assert "user manually aborted" in result.lower()
        # pid is not included in the message (translator doesn't include pid)
        # but we can still assert aborted
        assert "aborted" in result.lower()

    def test_heartbeat_timeout(self):
        """FAILED with HeartbeatTimeout."""
        error_details = {
            "type": "HeartbeatTimeout",
            "msg": "Worker stopped responding",
            "phase": "supervisor"
        }
        result = translate_job_status("FAILED", error_details)
        assert "worker heartbeat timeout" in result.lower()
        # translator doesn't include exact msg

    def test_orphaned(self):
        """ABORTED with Orphaned."""
        error_details = {
            "type": "Orphaned",
            "msg": "Worker process orphaned",
            "phase": "supervisor"
        }
        result = translate_job_status("ABORTED", error_details)
        assert "orphaned" in result.lower()
        assert "worker disappeared" in result.lower()

    def test_rejected_without_details(self):
        """REJECTED status."""
        result = translate_job_status("REJECTED", None)
        assert "rejected" in result.lower()
        assert "policy" in result.lower()

    def test_rejected_with_policy_check(self):
        """REJECTED with policy check details."""
        error_details = {
            "type": "ValidationError",
            "msg": "Gate 'risk' failed",
            "phase": "bootstrap"
        }
        result = translate_job_status("REJECTED", error_details)
        assert "parameter validation failure" in result.lower()

    def test_unknown_status(self):
        """Unknown status string."""
        result = translate_job_status("SOME_UNKNOWN_STATUS", None)
        assert "job status:" in result.lower()
        assert "some_unknown_status" in result.lower()

    def test_error_details_not_dict(self):
        """Error details is not a dict (should be ignored)."""
        result = translate_job_status("FAILED", "some string")
        # Should fall back to generic message
        assert "failed" in result.lower()

    def test_error_details_missing_type(self):
        """Error details dict missing 'type'."""
        error_details = {
            "msg": "Something went wrong"
        }
        result = translate_job_status("FAILED", error_details)
        # Should use generic error message
        assert "something went wrong" in result.lower()

    def test_error_details_malformed_json(self):
        """Error details is invalid JSON (should not crash)."""
        # Simulate a non-dict, non-string (like list)
        result = translate_job_status("FAILED", [1, 2, 3])
        assert "failed" in result.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])