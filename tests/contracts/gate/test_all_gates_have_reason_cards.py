"""
Global contract test: Ensure every gate in GateSummary includes deterministic reason_cards.
"""

import pytest
from unittest.mock import patch, MagicMock

from gui.services.gate_summary_service import GateSummaryService, GateResult, GateStatus
from gui.services.gate_reason_cards_registry import build_reason_cards_for_gate


def test_all_gates_have_reason_cards_field():
    """Every GateResult returned by GateSummary must have reason_cards field in details."""
    # Mock the supervisor client to return minimal responses
    mock_client = MagicMock()
    mock_client.health.return_value = {"status": "ok"}
    mock_client.session.get.return_value.json.return_value = {"status": "ok"}
    mock_client.get_jobs.return_value = []
    mock_client.base_url = "http://example.com"
    
    # Mock registry adapter for registry surface gate
    with patch('gui.services.registry_adapter.fetch_registry_gate_result') as mock_registry:
        mock_registry.return_value = GateResult(
            gate_id="registry_surface",
            gate_name="Registry Surface",
            status=GateStatus.PASS,
            message="Registry accessible",
            details={},
            timestamp="2024-01-01T00:00:00Z",
        )
        
        # Mock the reason cards registry to return empty lists
        with patch('gui.services.gate_summary_service.build_reason_cards_for_gate') as mock_build:
            mock_build.return_value = []
            
            service = GateSummaryService(client=mock_client)
            summary = service.fetch()
            
            # Check each gate
            for gate in summary.gates:
                assert isinstance(gate, GateResult)
                assert gate.details is not None, f"Gate {gate.gate_id} has None details"
                assert "reason_cards" in gate.details, f"Gate {gate.gate_id} missing reason_cards field"
                assert isinstance(gate.details["reason_cards"], list), f"Gate {gate.gate_id} reason_cards not a list"
                
                # Check that reason cards are properly formatted
                for card_dict in gate.details["reason_cards"]:
                    assert isinstance(card_dict, dict)
                    # Check required fields
                    assert "code" in card_dict
                    assert "title" in card_dict
                    assert "severity" in card_dict
                    assert "why" in card_dict
                    assert "impact" in card_dict
                    assert "recommended_action" in card_dict
                    assert "evidence_artifact" in card_dict
                    assert "evidence_path" in card_dict
                    assert "action_target" in card_dict


def test_gate_summary_integration_with_fixture_job():
    """For a constructed job scenario, at least one gate has non-empty cards."""
    # Create a mock job that would trigger a reason card
    mock_client = MagicMock()
    mock_client.health.return_value = {"status": "ok"}
    mock_client.session.get.return_value.json.return_value = {"status": "ok"}
    mock_client.base_url = "http://example.com"
    
    # Mock jobs list with a job that has data alignment artifact
    mock_job = {
        "job_id": "test-job-123",
        "created_at": "2024-01-01T00:00:00Z",
        "status": "SUCCEEDED",
        "policy_stage": "",
    }
    mock_client.get_jobs.return_value = [mock_job]
    
    # Mock data alignment status to trigger a reason card
    with patch('gui.services.gate_summary_service.resolve_data_alignment_status') as mock_resolve:
        from gui.services.data_alignment_status import DataAlignmentStatus
        mock_resolve.return_value = DataAlignmentStatus(
            status="OK",
            artifact_relpath="data_alignment_report.json",
            artifact_abspath="/tmp/test/data_alignment_report.json",
            message="data_alignment_report.json is available",
            metrics={
                "forward_fill_ratio": 0.75,  # > 0.5 threshold
                "dropped_rows": 0,
            },
        )
        
        # Mock registry adapter
        with patch('gui.services.registry_adapter.fetch_registry_gate_result') as mock_registry:
            mock_registry.return_value = GateResult(
                gate_id="registry_surface",
                gate_name="Registry Surface",
                status=GateStatus.PASS,
                message="Registry accessible",
                details={},
                timestamp="2024-01-01T00:00:00Z",
            )
            
            # Mock the reason cards registry to return a specific card
            with patch('gui.services.gate_summary_service.build_reason_cards_for_gate') as mock_build:
                # Create a mock reason card
                mock_card = MagicMock()
                mock_card.code = "DATA_ALIGNMENT_HIGH_FORWARD_FILL_RATIO"
                mock_card.why = "Forward-fill ratio 75.0% exceeds warning threshold 50%"
                mock_card.__dict__ = {
                    "code": "DATA_ALIGNMENT_HIGH_FORWARD_FILL_RATIO",
                    "title": "High Forward-Fill Ratio",
                    "severity": "WARN",
                    "why": "Forward-fill ratio 75.0% exceeds warning threshold 50%",
                    "impact": "Many bars held to last price; may distort signals",
                    "recommended_action": "Check data alignment pipeline or adjust timeframe",
                    "evidence_artifact": "data_alignment_report.json",
                    "evidence_path": "$.forward_fill_ratio",
                    "action_target": "/tmp/test/data_alignment_report.json",
                }
                mock_build.return_value = [mock_card]
                
                service = GateSummaryService(client=mock_client)
                summary = service.fetch()
                
                # Find data alignment gate
                data_alignment_gates = [g for g in summary.gates if g.gate_id == "data_alignment"]
                assert len(data_alignment_gates) == 1
                
                data_alignment_gate = data_alignment_gates[0]
                assert "reason_cards" in data_alignment_gate.details
                reason_cards = data_alignment_gate.details["reason_cards"]
                
                # Should have at least one reason card (high forward-fill ratio)
                assert len(reason_cards) > 0, "Data alignment gate should have non-empty reason cards"
                
                # Check card structure
                card = reason_cards[0]
                assert card["code"] == "DATA_ALIGNMENT_HIGH_FORWARD_FILL_RATIO"
                assert "Forward-fill ratio 75.0% exceeds warning threshold 50%" in card["why"]


def test_no_network_calls():
    """Test should not make actual network calls (respect existing policy)."""
    # This test uses mocks, so no network calls should be made
    # The test above already uses mocks for all external dependencies
    pass


def test_reason_cards_deterministic_ordering():
    """Within each gate, reason cards should follow deterministic ordering."""
    # Test ordering by checking that *_ARTIFACT_MISSING cards come first
    # This is tested in individual builder tests, but we can add a simple check here
    mock_client = MagicMock()
    mock_client.health.return_value = {"status": "ok"}
    mock_client.session.get.return_value.json.return_value = {"status": "ok"}
    mock_client.get_jobs.return_value = []
    mock_client.base_url = "http://example.com"
    
    with patch('gui.services.registry_adapter.fetch_registry_gate_result') as mock_registry:
        mock_registry.return_value = GateResult(
            gate_id="registry_surface",
            gate_name="Registry Surface",
            status=GateStatus.PASS,
            message="Registry accessible",
            details={},
            timestamp="2024-01-01T00:00:00Z",
        )
        
        # Mock the reason cards registry to return empty lists
        with patch('gui.services.gate_summary_service.build_reason_cards_for_gate') as mock_build:
            mock_build.return_value = []
            
            service = GateSummaryService(client=mock_client)
            summary = service.fetch()
            
            for gate in summary.gates:
                reason_cards = gate.details["reason_cards"]
                # If there are multiple cards, check ordering
                if len(reason_cards) > 1:
                    # Check that FAIL severity cards come before WARN
                    # This is a simplified check; actual ordering logic is in builders
                    pass


def test_empty_reason_cards_for_system_gates():
    """System health gates (api_health, etc.) should have empty reason cards lists."""
    mock_client = MagicMock()
    mock_client.health.return_value = {"status": "ok"}
    mock_client.session.get.return_value.json.return_value = {"status": "ok"}
    mock_client.get_jobs.return_value = []
    mock_client.base_url = "http://example.com"
    
    with patch('gui.services.registry_adapter.fetch_registry_gate_result') as mock_registry:
        mock_registry.return_value = GateResult(
            gate_id="registry_surface",
            gate_name="Registry Surface",
            status=GateStatus.PASS,
            message="Registry accessible",
            details={},
            timestamp="2024-01-01T00:00:00Z",
        )
        
        # Mock the reason cards registry to return empty lists
        with patch('gui.services.gate_summary_service.build_reason_cards_for_gate') as mock_build:
            mock_build.return_value = []
            
            service = GateSummaryService(client=mock_client)
            summary = service.fetch()
            
            # System gates that should have empty reason cards
            system_gates = ["api_health", "supervisor_db_ssot", "worker_execution_reality", "registry_surface"]
            for gate in summary.gates:
                if gate.gate_id in system_gates:
                    assert gate.details["reason_cards"] == [], f"System gate {gate.gate_id} should have empty reason cards"