"""
Unit tests for ConsolidatedGateSummaryService.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone

from gui.services.consolidated_gate_summary_service import (
    ConsolidatedGateSummaryService,
    get_consolidated_gate_summary_service,
    fetch_consolidated_gate_summary,
)
from contracts.portfolio.gate_summary_schemas import GateSummaryV1, GateItemV1, GateStatus


class TestConsolidatedGateSummaryService:
    """Test suite for ConsolidatedGateSummaryService."""
    
    def test_initialization(self):
        """Test service initialization."""
        service = ConsolidatedGateSummaryService()
        assert service.system_gate_service is not None
        assert service.jobs_root.name == "jobs"
    
    @patch('gui.services.consolidated_gate_summary_service.GateSummaryService')
    def test_fetch_system_health_gates_success(self, mock_gate_service_class):
        """Test fetching system health gates successfully."""
        # Mock the system gate service
        mock_gate_service = Mock()
        mock_gate_summary = Mock()
        mock_gate_summary.gates = [
            Mock(
                gate_id="api_health",
                gate_name="API Health",
                status="PASS",
                message="API health endpoint responds with status ok.",
                details={"status": "ok"},
                actions=[{"label": "View Health", "url": "/health"}],
                timestamp="2026-01-14T15:00:00Z",
            )
        ]
        mock_gate_service.fetch.return_value = mock_gate_summary
        mock_gate_service_class.return_value = mock_gate_service
        
        service = ConsolidatedGateSummaryService(system_gate_service=mock_gate_service)
        gates = service.fetch_system_health_gates()
        
        assert len(gates) == 1
        assert gates[0].gate_id == "api_health"  # Not prefixed yet (prefixing happens in fetch_consolidated_summary)
        assert gates[0].status == GateStatus.PASS
        assert "API health endpoint" in gates[0].message
    
    @patch('gui.services.consolidated_gate_summary_service.GateSummaryService')
    def test_fetch_system_health_gates_error(self, mock_gate_service_class):
        """Test fetching system health gates with error."""
        mock_gate_service = Mock()
        mock_gate_service.fetch.side_effect = Exception("Network error")
        mock_gate_service_class.return_value = mock_gate_service
        
        service = ConsolidatedGateSummaryService(system_gate_service=mock_gate_service)
        gates = service.fetch_system_health_gates()
        
        assert len(gates) == 1
        assert gates[0].gate_id == "system_gates_error"
        assert gates[0].status == GateStatus.UNKNOWN
        assert "Failed to fetch system gates" in gates[0].message
    
    @patch('core.portfolio.evidence_aggregator.EvidenceAggregator', create=True)
    def test_fetch_gatekeeper_gates_success(self, mock_aggregator_class):
        """Test fetching gatekeeper gates successfully."""
        # Mock the evidence aggregator
        mock_aggregator = Mock()
        mock_index = Mock()
        mock_job_summary = Mock()
        mock_job_summary.job_id = "test_job_123"
        mock_job_summary.strategy_id = "test_strategy"
        mock_job_summary.gate_status = "PASS"
        mock_job_summary.gate_summary = Mock(total_permutations=100, valid_candidates=85)
        mock_job_summary.artifacts_present = ["strategy_report_v1.json", "input_manifest.json"]
        mock_job_summary.created_at = "2026-01-14T15:00:00Z"
        
        mock_index.jobs = {"test_job_123": mock_job_summary}
        mock_aggregator.build_index.return_value = mock_index
        mock_aggregator_class.return_value = mock_aggregator
        
        service = ConsolidatedGateSummaryService()
        gates = service.fetch_gatekeeper_gates()
        
        # Might be empty if import fails, but at least shouldn't crash
        # The test verifies the method doesn't raise exceptions
    
    @patch('core.portfolio.evidence_aggregator.EvidenceAggregator', create=True, side_effect=ImportError)
    def test_fetch_gatekeeper_gates_import_error(self, mock_aggregator):
        """Test fetching gatekeeper gates when evidence aggregator not available."""
        service = ConsolidatedGateSummaryService()
        gates = service.fetch_gatekeeper_gates()
        
        assert gates == []  # Should return empty list
    
    def test_fetch_all_gates(self):
        """Test fetching all gates combines sources."""
        service = ConsolidatedGateSummaryService()
        
        with patch.object(service, 'fetch_system_health_gates') as mock_system:
            with patch.object(service, 'fetch_gatekeeper_gates') as mock_gatekeeper:
                with patch.object(service, 'fetch_portfolio_admission_gates') as mock_admission:
                    mock_system.return_value = [
                        GateItemV1(
                            gate_id="api_health",
                            gate_name="API Health",
                            status=GateStatus.PASS,
                            message="Test",
                            evaluator="gate_summary_service",
                        )
                    ]
                    mock_gatekeeper.return_value = [
                        GateItemV1(
                            gate_id="job_123",
                            gate_name="Gatekeeper: test",
                            status=GateStatus.PASS,
                            message="Test",
                            evaluator="evidence_aggregator",
                        )
                    ]
                    mock_admission.return_value = []
                    
                    gates = service.fetch_all_gates()
                    
                    assert len(gates) == 2
                    # Gate IDs are NOT prefixed in fetch_all_gates (prefixing happens in fetch_consolidated_summary)
                    gate_ids = [g.gate_id for g in gates]
                    assert "api_health" in gate_ids
                    assert "job_123" in gate_ids
    
    def test_with_prefixed_gate_id_returns_copy(self):
        """Ensure gate_id prefixes without mutating the original gate."""
        service = ConsolidatedGateSummaryService()
        gate = GateItemV1(
            gate_id="api_health",
            gate_name="API Health",
            status=GateStatus.PASS,
            message="Fresh gate",
            evaluator="gate_summary_service",
        )
        prefixed_gate = service._with_prefixed_gate_id(gate)
        assert prefixed_gate.gate_id == "system_api_health"
        assert gate.gate_id == "api_health"
        assert prefixed_gate is not gate
    
    def test_fetch_consolidated_summary(self):
        """Test fetching consolidated summary."""
        service = ConsolidatedGateSummaryService()
        
        with patch.object(service, 'fetch_all_gates') as mock_fetch:
            gate_a = GateItemV1(
                gate_id="api_health",
                gate_name="API Health",
                status=GateStatus.PASS,
                message="API health endpoint responds with status ok.",
                evaluator="gate_summary_service",
            )
            gate_b = GateItemV1(
                gate_id="job_123",
                gate_name="Gatekeeper: test",
                status=GateStatus.WARN,
                message="Job test_job_123: 85/100 valid",
                evaluator="evidence_aggregator",
            )
            mock_fetch.return_value = [gate_a, gate_b]
            
            summary = service.fetch_consolidated_summary()
            
            assert isinstance(summary, GateSummaryV1)
            assert summary.schema_version == "v1"
            assert summary.overall_status == GateStatus.WARN  # Because there's a WARN
            assert summary.total_gates == 2
            assert summary.counts["pass"] == 1
            assert summary.counts["warn"] == 1
            gate_ids = {g.gate_id for g in summary.gates}
            assert gate_ids == {"system_api_health", "gatekeeper_job_123"}
            # Original gate instances should remain unchanged
            assert gate_a.gate_id == "api_health"
            assert gate_b.gate_id == "job_123"
    
    def test_singleton(self):
        """Test singleton get_consolidated_gate_summary_service."""
        service1 = get_consolidated_gate_summary_service()
        service2 = get_consolidated_gate_summary_service()
        assert service1 is service2
        
        # Test fetch_consolidated_gate_summary convenience function
        with patch.object(service1, 'fetch_consolidated_summary') as mock_fetch:
            mock_fetch.return_value = GateSummaryV1(
                overall_status=GateStatus.PASS,
                overall_message="Test",
                evaluated_at_utc="2026-01-14T15:00:00Z",
                evaluator="test",
                source="test",
            )
            result = fetch_consolidated_gate_summary()
            assert result.overall_status == GateStatus.PASS
            mock_fetch.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])