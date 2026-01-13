"""
Unit tests for GateSummaryService.

Tests the mapping of supervisor API responses to gate statuses.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone

from gui.services.supervisor_client import SupervisorClientError
from gui.services.gate_summary_service import (
    GateSummaryService,
    GateStatus,
    GateResult,
    GateSummary,
    get_gate_summary_service,
    fetch_gate_summary,
)


class TestGateSummaryService:
    """Test suite for GateSummaryService."""

    def test_fetch_all_gates_pass(self):
        """Test fetch when all gates return PASS."""
        mock_client = Mock()
        mock_client.health.return_value = {"status": "ok"}
        mock_client.get_jobs.return_value = [
            {"job_id": "1", "status": "RUNNING"},
            {"job_id": "2", "status": "QUEUED"},
        ]
        # Mock session for readiness and registry endpoints
        mock_session = Mock()
        # Create two mock responses
        readiness_response = Mock()
        readiness_response.json.return_value = {"status": "ok"}
        readiness_response.raise_for_status.return_value = None
        registry_response = Mock()
        registry_response.json.return_value = ["15m", "30m", "60m"]
        registry_response.raise_for_status.return_value = None
        
        def side_effect(url, **kwargs):
            if url.endswith("/api/v1/readiness"):
                return readiness_response
            elif url.endswith("/api/v1/registry/timeframes"):
                return registry_response
            else:
                raise ValueError(f"Unexpected URL: {url}")
        mock_session.get.side_effect = side_effect
        mock_client.session = mock_session
        mock_client.base_url = "http://testserver"

        service = GateSummaryService(client=mock_client)
        summary = service.fetch()

        # Verify overall status
        assert summary.overall_status == GateStatus.PASS
        assert "All gates PASS" in summary.overall_message
        assert len(summary.gates) == 5
        # Check each gate status
        gate_ids = [g.gate_id for g in summary.gates]
        assert "api_health" in gate_ids
        assert "api_readiness" in gate_ids
        assert "supervisor_db_ssot" in gate_ids
        assert "worker_execution_reality" in gate_ids
        assert "registry_surface" in gate_ids
        for gate in summary.gates:
            assert gate.status == GateStatus.PASS

    def test_fetch_api_health_fail(self):
        """Test when API health endpoint fails."""
        mock_client = Mock()
        mock_client.health.side_effect = SupervisorClientError(
            status_code=503, message="Connection refused", error_type="network"
        )
        mock_client.get_jobs.return_value = []
        mock_session = Mock()
        mock_response = Mock()
        mock_response.json.return_value = {"status": "ok"}
        mock_response.raise_for_status.return_value = None
        mock_session.get.return_value = mock_response
        mock_client.session = mock_session
        mock_client.base_url = "http://testserver"

        service = GateSummaryService(client=mock_client)
        summary = service.fetch()

        # Health gate should be FAIL
        health_gate = next(g for g in summary.gates if g.gate_id == "api_health")
        assert health_gate.status == GateStatus.FAIL
        # Overall status should be FAIL
        assert summary.overall_status == GateStatus.FAIL
        assert "Gates with FAIL" in summary.overall_message

    def test_fetch_api_readiness_warn(self):
        """Test when readiness returns unexpected response."""
        mock_client = Mock()
        mock_client.health.return_value = {"status": "ok"}
        mock_client.get_jobs.return_value = []
        mock_session = Mock()
        mock_response = Mock()
        mock_response.json.return_value = {"status": "not ok"}
        mock_response.raise_for_status.return_value = None
        mock_session.get.return_value = mock_response
        mock_client.session = mock_session
        mock_client.base_url = "http://testserver"

        service = GateSummaryService(client=mock_client)
        summary = service.fetch()

        readiness_gate = next(g for g in summary.gates if g.gate_id == "api_readiness")
        assert readiness_gate.status == GateStatus.WARN
        # Overall status should be WARN
        assert summary.overall_status == GateStatus.WARN
        assert "Gates with WARN" in summary.overall_message

    def test_fetch_supervisor_db_ssot_fail(self):
        """Test when supervisor DB is unreachable."""
        mock_client = Mock()
        mock_client.health.return_value = {"status": "ok"}
        mock_client.get_jobs.side_effect = SupervisorClientError(
            status_code=500, message="DB connection failed", error_type="server"
        )
        mock_session = Mock()
        mock_response = Mock()
        mock_response.json.return_value = {"status": "ok"}
        mock_response.raise_for_status.return_value = None
        mock_session.get.return_value = mock_response
        mock_client.session = mock_session
        mock_client.base_url = "http://testserver"

        service = GateSummaryService(client=mock_client)
        summary = service.fetch()

        db_gate = next(g for g in summary.gates if g.gate_id == "supervisor_db_ssot")
        assert db_gate.status == GateStatus.FAIL
        # Overall status should be FAIL (since one FAIL)
        assert summary.overall_status == GateStatus.FAIL

    def test_fetch_worker_execution_reality_running(self):
        """Test worker reality gate with RUNNING jobs."""
        mock_client = Mock()
        mock_client.health.return_value = {"status": "ok"}
        mock_client.get_jobs.return_value = [
            {"job_id": "1", "status": "RUNNING"},
            {"job_id": "2", "status": "QUEUED"},
            {"job_id": "3", "status": "SUCCEEDED"},
        ]
        mock_session = Mock()
        mock_response = Mock()
        mock_response.json.return_value = {"status": "ok"}
        mock_response.raise_for_status.return_value = None
        mock_session.get.return_value = mock_response
        mock_client.session = mock_session
        mock_client.base_url = "http://testserver"

        service = GateSummaryService(client=mock_client)
        summary = service.fetch()

        worker_gate = next(g for g in summary.gates if g.gate_id == "worker_execution_reality")
        assert worker_gate.status == GateStatus.PASS
        assert "RUNNING" in worker_gate.message
        assert worker_gate.details["running_count"] == 1
        assert worker_gate.details["queued_count"] == 1

    def test_fetch_worker_execution_reality_only_queued(self):
        """Test worker reality gate with only QUEUED jobs (WARN)."""
        mock_client = Mock()
        mock_client.health.return_value = {"status": "ok"}
        mock_client.get_jobs.return_value = [
            {"job_id": "1", "status": "QUEUED"},
            {"job_id": "2", "status": "QUEUED"},
        ]
        mock_session = Mock()
        mock_response = Mock()
        mock_response.json.return_value = {"status": "ok"}
        mock_response.raise_for_status.return_value = None
        mock_session.get.return_value = mock_response
        mock_client.session = mock_session
        mock_client.base_url = "http://testserver"

        service = GateSummaryService(client=mock_client)
        summary = service.fetch()

        worker_gate = next(g for g in summary.gates if g.gate_id == "worker_execution_reality")
        assert worker_gate.status == GateStatus.WARN
        assert "QUEUED" in worker_gate.message
        assert worker_gate.details["running_count"] == 0
        assert worker_gate.details["queued_count"] == 2

    def test_fetch_worker_execution_reality_idle(self):
        """Test worker reality gate with no RUNNING or QUEUED jobs (PASS)."""
        mock_client = Mock()
        mock_client.health.return_value = {"status": "ok"}
        mock_client.get_jobs.return_value = [
            {"job_id": "1", "status": "SUCCEEDED"},
            {"job_id": "2", "status": "FAILED"},
        ]
        mock_session = Mock()
        mock_response = Mock()
        mock_response.json.return_value = {"status": "ok"}
        mock_response.raise_for_status.return_value = None
        mock_session.get.return_value = mock_response
        mock_client.session = mock_session
        mock_client.base_url = "http://testserver"

        service = GateSummaryService(client=mock_client)
        summary = service.fetch()

        worker_gate = next(g for g in summary.gates if g.gate_id == "worker_execution_reality")
        assert worker_gate.status == GateStatus.PASS
        assert "idle" in worker_gate.message.lower()
        assert worker_gate.details["running_count"] == 0
        assert worker_gate.details["queued_count"] == 0

    def test_fetch_registry_surface_empty(self):
        """Test registry surface gate with empty list (WARN)."""
        mock_client = Mock()
        mock_client.health.return_value = {"status": "ok"}
        mock_client.get_jobs.return_value = []
        mock_session = Mock()
        mock_response = Mock()
        mock_response.json.return_value = []  # empty list
        mock_response.raise_for_status.return_value = None
        mock_session.get.return_value = mock_response
        mock_client.session = mock_session
        mock_client.base_url = "http://testserver"

        service = GateSummaryService(client=mock_client)
        summary = service.fetch()

        registry_gate = next(g for g in summary.gates if g.gate_id == "registry_surface")
        assert registry_gate.status == GateStatus.WARN
        assert "empty" in registry_gate.message.lower()

    def test_fetch_registry_surface_fail(self):
        """Test registry surface gate with network error (FAIL)."""
        mock_client = Mock()
        mock_client.health.return_value = {"status": "ok"}
        mock_client.get_jobs.return_value = []
        mock_session = Mock()
        mock_session.get.side_effect = Exception("Connection refused")
        mock_client.session = mock_session
        mock_client.base_url = "http://testserver"

        service = GateSummaryService(client=mock_client)
        summary = service.fetch()

        registry_gate = next(g for g in summary.gates if g.gate_id == "registry_surface")
        assert registry_gate.status == GateStatus.FAIL
        assert "unreachable" in registry_gate.message.lower()

    def test_compute_overall_status(self):
        """Test _compute_overall_status logic."""
        service = GateSummaryService()
        # All PASS -> PASS
        gates = [
            GateResult("1", "Test", GateStatus.PASS, ""),
            GateResult("2", "Test", GateStatus.PASS, ""),
        ]
        assert service._compute_overall_status(gates) == GateStatus.PASS
        # One WARN -> WARN
        gates.append(GateResult("3", "Test", GateStatus.WARN, ""))
        assert service._compute_overall_status(gates) == GateStatus.WARN
        # One FAIL -> FAIL (even if others PASS/WARN)
        gates.append(GateResult("4", "Test", GateStatus.FAIL, ""))
        assert service._compute_overall_status(gates) == GateStatus.FAIL
        # No PASS, only UNKNOWN -> UNKNOWN
        gates = [GateResult("1", "Test", GateStatus.UNKNOWN, "")]
        assert service._compute_overall_status(gates) == GateStatus.UNKNOWN

    def test_compute_overall_message(self):
        """Test _compute_overall_message generation."""
        service = GateSummaryService()
        gates = [
            GateResult("1", "Health", GateStatus.PASS, ""),
            GateResult("2", "Readiness", GateStatus.WARN, ""),
            GateResult("3", "DB", GateStatus.FAIL, ""),
        ]
        # FAIL case
        msg = service._compute_overall_message(GateStatus.FAIL, gates)
        assert "Gates with FAIL" in msg
        assert "DB" in msg
        # WARN case
        msg = service._compute_overall_message(GateStatus.WARN, gates)
        assert "Gates with WARN" in msg
        assert "Readiness" in msg
        # PASS case
        msg = service._compute_overall_message(GateStatus.PASS, gates)
        assert "All gates PASS" in msg
        # UNKNOWN case
        msg = service._compute_overall_message(GateStatus.UNKNOWN, gates)
        assert "unknown" in msg.lower()

    def test_singleton(self):
        """Test singleton get_gate_summary_service and fetch_gate_summary."""
        service1 = get_gate_summary_service()
        service2 = get_gate_summary_service()
        assert service1 is service2
        # Ensure fetch_gate_summary works (will raise due to missing client, but we can mock)
        with patch.object(service1, 'fetch') as mock_fetch:
            mock_fetch.return_value = GateSummary([], "2026-01-01T00:00:00Z", GateStatus.PASS, "test")
            result = fetch_gate_summary()
            assert result.overall_status == GateStatus.PASS
            mock_fetch.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])