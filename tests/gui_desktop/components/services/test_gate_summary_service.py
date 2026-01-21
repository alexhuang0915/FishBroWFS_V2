"""
Unit tests for GateSummaryService.

Tests the mapping of supervisor API responses to gate statuses.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone
from gui.services.explain_adapter import JobReason
from gui.services.supervisor_client import SupervisorClientError
from gui.services.gate_summary_service import (
    GateSummaryService,
    GateStatus,
    GateResult,
    GateSummary,
    get_gate_summary_service,
    fetch_gate_summary,
)


@pytest.fixture(autouse=True)
def default_explain_payload(monkeypatch):
    def _payload(job_id: str) -> dict[str, str]:
        return {
            "summary": f"Policy summary for {job_id}",
            "action_hint": "Adjust parameters and resubmit.",
            "evidence": {
                "policy_check_url": f"/api/v1/jobs/{job_id}/artifacts/policy_check.json"
            },
            "decision_layer": "POLICY",
            "human_tag": "VIOLATION",
            "final_status": "SUCCEEDED",
        }

    def reason(job_id: str) -> JobReason:
        payload = _payload(job_id)
        return JobReason(
            job_id=job_id,
            summary=payload["summary"],
            action_hint=payload["action_hint"],
            decision_layer=payload["decision_layer"],
            human_tag=payload["human_tag"],
            recoverable=False,
            evidence_urls={
                "policy_check_url": payload["evidence"]["policy_check_url"],
                "manifest_url": None,
                "inputs_fingerprint_url": None,
            },
            fallback=False,
        )

    monkeypatch.setattr(
        "gui.services.gate_summary_service._explain_adapter.get_job_reason",
        reason,
    )


class TestGateSummaryService:
    """Test suite for GateSummaryService."""

    def test_fetch_all_gates_pass(self, monkeypatch):
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
        mock_client.get_artifact_file.return_value = b'{"overall_status": "PASS"}'
        mock_client.base_url = "http://testserver"

        monkeypatch.setattr(
            "gui.services.gate_summary_service.GateSummaryService._fetch_data_alignment_gate",
            lambda self: GateResult(
                gate_id="data_alignment",
                gate_name="Data Alignment",
                status=GateStatus.PASS,
                message="Data alignment gate stubbed for tests.",
                details={},
                timestamp=datetime.now(timezone.utc).isoformat(),
            ),
        )
        monkeypatch.setattr(
            "gui.services.gate_summary_service.GateSummaryService._fetch_resource_gate",
            lambda self: GateResult(
                gate_id="resource",
                gate_name="Resource / OOM",
                status=GateStatus.PASS,
                message="Resource gate stubbed for tests.",
                details={},
                timestamp=datetime.now(timezone.utc).isoformat(),
            ),
        )
        monkeypatch.setattr(
            "gui.services.gate_summary_service.GateSummaryService._fetch_portfolio_admission_gate",
            lambda self: GateResult(
                gate_id="portfolio_admission",
                gate_name="Portfolio Admission",
                status=GateStatus.PASS,
                message="Portfolio admission gate stubbed for tests.",
                details={},
                timestamp=datetime.now(timezone.utc).isoformat(),
            ),
        )

        service = GateSummaryService(client=mock_client)
        summary = service.fetch()

        # Verify overall status
        assert summary.overall_status == GateStatus.PASS
        assert "All gates PASS" in summary.overall_message
        assert len(summary.gates) == 9
        # Check each gate status
        gate_ids = [g.gate_id for g in summary.gates]
        assert "api_health" in gate_ids
        assert "api_readiness" in gate_ids
        assert "supervisor_db_ssot" in gate_ids
        assert "worker_execution_reality" in gate_ids
        assert "registry_surface" in gate_ids
        assert "policy_enforcement" in gate_ids
        assert "data_alignment" in gate_ids
        assert "resource" in gate_ids
        assert "portfolio_admission" in gate_ids
        policy_gate = next(g for g in summary.gates if g.gate_id == "policy_enforcement")
        assert policy_gate.status == GateStatus.PASS
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
        mock_client.get_artifact_file.return_value = b'{"overall_status": "PASS"}'
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
        mock_client.get_artifact_file.return_value = b'{"overall_status": "PASS"}'
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
        mock_client.get_artifact_file.return_value = b'{"overall_status": "PASS"}'
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
        mock_client.get_artifact_file.return_value = b'{"overall_status": "PASS"}'
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
        mock_client.get_artifact_file.return_value = b'{"overall_status": "PASS"}'
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
        mock_client.get_artifact_file.return_value = b'{"overall_status": "PASS"}'
        mock_client.base_url = "http://testserver"

        service = GateSummaryService(client=mock_client)
        summary = service.fetch()

        worker_gate = next(g for g in summary.gates if g.gate_id == "worker_execution_reality")
        assert worker_gate.status == GateStatus.PASS
        assert "idle" in worker_gate.message.lower()
        assert worker_gate.details["running_count"] == 0
        assert worker_gate.details["queued_count"] == 0

    def test_policy_gate_reports_preflight_rejection(self):
        """Policy gate FAIL when preflight policy rejects a job."""
        mock_client = Mock()
        mock_client.health.return_value = {"status": "ok"}
        mock_client.get_jobs.return_value = [
            {
                "job_id": "policy-1",
                "status": "REJECTED",
                "policy_stage": "preflight",
                "failure_code": "POLICY_REJECT_MISSING_SEASON",
                "created_at": "2026-01-01T00:00:00Z",
            }
        ]
        mock_session = Mock()
        mock_response = Mock()
        mock_response.json.return_value = {"status": "ok"}
        mock_response.raise_for_status.return_value = None
        mock_session.get.return_value = mock_response
        mock_client.session = mock_session
        mock_client.get_artifact_file.return_value = b'{"overall_status": "PASS"}'
        mock_client.base_url = "http://testserver"

        service = GateSummaryService(client=mock_client)
        summary = service.fetch()

        policy_gate = next(g for g in summary.gates if g.gate_id == "policy_enforcement")
        assert policy_gate.status == GateStatus.FAIL
        assert policy_gate.details["policy_stage"] == "preflight"
        assert "policy summary for policy-1" in policy_gate.message.lower()
        assert "next: adjust parameters and resubmit." in policy_gate.message.lower()
        assert policy_gate.actions and policy_gate.actions[0]["url"] == "/api/v1/jobs/policy-1/artifacts/policy_check.json"

    def test_policy_gate_warns_when_policy_evidence_missing(self, monkeypatch):
        """Policy gate WARN when succeeded job lacks policy_check artifact."""
        mock_client = Mock()
        mock_client.health.return_value = {"status": "ok"}
        mock_client.get_jobs.return_value = [
            {
                "job_id": "policy-2",
                "status": "SUCCEEDED",
                "created_at": "2026-01-02T00:00:00Z",
            }
        ]
        mock_client.get_artifact_file.side_effect = SupervisorClientError(
            status_code=404, message="Not found", error_type="validation"
        )
        mock_session = Mock()
        mock_response = Mock()
        mock_response.json.return_value = {"status": "ok"}
        mock_response.raise_for_status.return_value = None
        mock_session.get.return_value = mock_response
        mock_client.session = mock_session
        mock_client.get_artifact_file.return_value = b'{"overall_status": "PASS"}'
        mock_client.base_url = "http://testserver"

        monkeypatch.setattr(
            "gui.services.gate_summary_service._explain_adapter.get_job_reason",
            lambda _: (_ for _ in ()).throw(
                SupervisorClientError(status_code=404, message="Explain missing", error_type="validation")
            ),
        )

        service = GateSummaryService(client=mock_client)
        summary = service.fetch()

        policy_gate = next(g for g in summary.gates if g.gate_id == "policy_enforcement")
        assert policy_gate.status == GateStatus.WARN
        assert "explain unavailable" in policy_gate.message.lower()

    @patch('gui.services.registry_adapter.fetch_registry_gate_result')
    def test_fetch_registry_surface_empty(self, mock_fetch):
        """Test registry surface gate with empty list (WARN)."""
        mock_client = Mock()
        mock_client.health.return_value = {"status": "ok"}
        mock_client.get_jobs.return_value = []
        
        # Mock the registry adapter to return WARN for empty registry
        from gui.services.gate_summary_service import GateResult, GateStatus
        from datetime import datetime, timezone
        mock_fetch.return_value = GateResult(
            gate_id="registry_surface",
            gate_name="Registry Surface",
            status=GateStatus.WARN,
            message="Registry surface accessible but empty (no timeframes).",
            details={"timeframes_count": 0, "datasets_count": 0, "strategies_count": 0, "instruments_count": 0, "status": "PARTIAL"},
            timestamp=datetime.now(timezone.utc).isoformat()
        )

        service = GateSummaryService(client=mock_client)
        summary = service.fetch()

        registry_gate = next(g for g in summary.gates if g.gate_id == "registry_surface")
        assert registry_gate.status == GateStatus.WARN
        assert "empty" in registry_gate.message.lower()

    @patch('gui.services.registry_adapter.fetch_registry_gate_result')
    def test_fetch_registry_surface_fail(self, mock_fetch):
        """Test registry surface gate with network error (FAIL)."""
        mock_client = Mock()
        mock_client.health.return_value = {"status": "ok"}
        mock_client.get_jobs.return_value = []
        
        # Mock the registry adapter to return FAIL for network error
        from gui.services.gate_summary_service import GateResult, GateStatus
        from datetime import datetime, timezone
        mock_fetch.return_value = GateResult(
            gate_id="registry_surface",
            gate_name="Registry Surface",
            status=GateStatus.FAIL,
            message="Registry surface unavailable: Connection refused",
            details={"missing_methods": ["get_registry_timeframes"], "error": "Connection refused", "status": "UNAVAILABLE"},
            timestamp=datetime.now(timezone.utc).isoformat()
        )

        service = GateSummaryService(client=mock_client)
        summary = service.fetch()

        registry_gate = next(g for g in summary.gates if g.gate_id == "registry_surface")
        assert registry_gate.status == GateStatus.FAIL
        assert "unavailable" in registry_gate.message.lower()

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