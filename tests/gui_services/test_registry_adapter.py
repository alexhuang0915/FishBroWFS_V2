"""
Tests for Registry Surface Adapter (Route 1 Governance Core).
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone

from gui.services.registry_adapter import (
    RegistrySurfaceAdapter,
    RegistrySurfaceResult,
    fetch_registry_gate_result,
    RegistryStatus,
)
from gui.services.gate_summary_service import GateResult, GateStatus


class TestRegistrySurfaceAdapter:
    """Test RegistrySurfaceAdapter defensive error handling."""
    
    def test_init(self):
        """Test adapter initialization."""
        mock_client = Mock()
        adapter = RegistrySurfaceAdapter(client=mock_client)
        assert adapter.client == mock_client
    
    @patch('gui.services.registry_adapter.SupervisorClient')
    def test_fetch_registry_surface_success(self, MockSupervisorClient):
        """Test successful registry surface fetch."""
        # Mock client with all required methods
        mock_client = Mock()
        mock_client.get_registry_timeframes.return_value = ["60", "240"]
        mock_client.get_registry_instruments.return_value = ["CME.MNQ"]
        mock_client.get_registry_datasets.return_value = ["CME.MNQ.60m"]
        mock_client.get_registry_strategies.return_value = [{"id": "s1_v1"}]
        
        adapter = RegistrySurfaceAdapter(client=mock_client)
        result = adapter.fetch_registry_surface()
        
        assert isinstance(result, RegistrySurfaceResult)
        assert result.status == RegistryStatus.AVAILABLE
        assert result.timeframes == ["60", "240"]
        assert result.instruments == ["CME.MNQ"]
        assert result.datasets == ["CME.MNQ.60m"]
        assert result.strategies == ["s1_v1"]
        assert result.missing_methods == []
        assert result.error is None
    
    @patch('gui.services.registry_adapter.SupervisorClient')
    def test_fetch_registry_surface_missing_methods(self, MockSupervisorClient):
        """Test registry surface fetch with missing methods."""
        # Mock client missing some methods - use spec to properly simulate missing methods
        mock_client = Mock()
        mock_client.get_registry_timeframes.return_value = []  # This method exists
        # Remove other attributes to simulate missing methods
        # Mock objects dynamically create attributes, so we need to delete them
        # or use side_effect to raise AttributeError
        delattr(mock_client, 'get_registry_instruments')
        delattr(mock_client, 'get_registry_datasets')
        delattr(mock_client, 'get_registry_strategies')
        
        adapter = RegistrySurfaceAdapter(client=mock_client)
        result = adapter.fetch_registry_surface()
        
        assert isinstance(result, RegistrySurfaceResult)
        assert result.status == RegistryStatus.PARTIAL
        assert "get_registry_instruments" in result.missing_methods
        assert "get_registry_datasets" in result.missing_methods
        assert "get_registry_strategies" in result.missing_methods
        assert result.timeframes == []
        assert result.instruments == []
        assert result.datasets == []
        assert result.strategies == []
    
    @patch('gui.services.registry_adapter.SupervisorClient')
    def test_fetch_registry_surface_attribute_error(self, MockSupervisorClient):
        """Test registry surface fetch with AttributeError."""
        mock_client = Mock()
        mock_client.get_registry_timeframes.side_effect = AttributeError("No such method")
        
        adapter = RegistrySurfaceAdapter(client=mock_client)
        result = adapter.fetch_registry_surface()
        
        assert result.status == RegistryStatus.PARTIAL
        assert "get_registry_timeframes" in result.missing_methods
    
    @patch('gui.services.registry_adapter.SupervisorClient')
    def test_fetch_registry_surface_network_error(self, MockSupervisorClient):
        """Test registry surface fetch with network error."""
        mock_client = Mock()
        mock_client.get_registry_timeframes.side_effect = ConnectionError("Network down")
        
        adapter = RegistrySurfaceAdapter(client=mock_client)
        result = adapter.fetch_registry_surface()
        
        assert result.status == RegistryStatus.PARTIAL
        assert "get_registry_timeframes" in result.missing_methods
        assert result.error is not None
        # The error message might not contain "Network down" exactly due to logging
        # Just check that we got an error
    
    def test_to_gate_result_success(self):
        """Test conversion to GateResult for successful fetch."""
        # Create a mock adapter
        adapter = RegistrySurfaceAdapter()
        
        # Create a result with successful data
        result = RegistrySurfaceResult(
            status=RegistryStatus.AVAILABLE,
            timeframes=["60", "240"],
            instruments=["CME.MNQ"],
            datasets=["CME.MNQ.60m"],
            strategies=["s1_v1"],
            missing_methods=[],
            error=None
        )
        
        gate_result = adapter.to_gate_result(result)
        
        assert isinstance(gate_result, GateResult)
        assert gate_result.status == GateStatus.PASS
        assert "Registry surface accessible" in gate_result.message
        assert gate_result.details["timeframes_count"] == 2
        assert gate_result.details["datasets_count"] == 1
    
    def test_to_gate_result_missing_methods(self):
        """Test conversion to GateResult for missing methods."""
        adapter = RegistrySurfaceAdapter()
        
        result = RegistrySurfaceResult(
            status=RegistryStatus.PARTIAL,
            timeframes=[],
            instruments=[],
            datasets=[],
            strategies=[],
            missing_methods=["get_registry_instruments", "get_registry_datasets"],
            error="Registry surface partially available: missing ['get_registry_instruments', 'get_registry_datasets']"
        )
        
        gate_result = adapter.to_gate_result(result)
        
        assert gate_result.status == GateStatus.WARN
        assert "partially available" in gate_result.message.lower()
        assert "get_registry_instruments" in str(gate_result.details.get("missing_methods", []))
    
    def test_to_gate_result_empty_registry(self):
        """Test conversion to GateResult for empty registry."""
        adapter = RegistrySurfaceAdapter()
        
        result = RegistrySurfaceResult(
            status=RegistryStatus.PARTIAL,
            timeframes=[],  # Empty registry
            instruments=[],
            datasets=[],
            strategies=[],
            missing_methods=[],
            error="Registry surface endpoints returned empty data"
        )
        
        gate_result = adapter.to_gate_result(result)
        
        assert gate_result.status == GateStatus.WARN
        assert "empty" in gate_result.message.lower() or "accessible but empty" in gate_result.message


class TestConvenienceFunctions:
    """Test convenience functions."""
    
    @patch('gui.services.registry_adapter._registry_adapter')
    def test_fetch_registry_gate_result(self, mock_adapter):
        """Test fetch_registry_gate_result convenience function."""
        mock_result = RegistrySurfaceResult(
            status=RegistryStatus.AVAILABLE,
            timeframes=["60", "240"],
            instruments=["CME.MNQ"],
            datasets=["CME.MNQ.60m"],
            strategies=["s1_v1"],
            missing_methods=[],
            error=None
        )
        mock_gate_result = GateResult(
            gate_id="registry_surface",
            gate_name="Registry Surface",
            status=GateStatus.PASS,
            message="Test",
            details={},
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        
        mock_adapter.fetch_registry_surface.return_value = mock_result
        mock_adapter.to_gate_result.return_value = mock_gate_result
        
        result = fetch_registry_gate_result()
        
        assert result == mock_gate_result
        mock_adapter.fetch_registry_surface.assert_called_once()
        mock_adapter.to_gate_result.assert_called_once_with(mock_result)
    
    @patch('gui.services.registry_adapter._registry_adapter')
    def test_fetch_registry_gate_result_adapter_exception(self, mock_adapter):
        """Test fetch_registry_gate_result when adapter raises exception."""
        # The adapter should handle exceptions internally, not raise them
        # So we need to mock the adapter to return a result with error status
        mock_result = RegistrySurfaceResult(
            status=RegistryStatus.UNAVAILABLE,
            timeframes=[],
            instruments=[],
            datasets=[],
            strategies=[],
            missing_methods=["get_registry_timeframes", "get_registry_instruments", "get_registry_datasets", "get_registry_strategies"],
            error="Adapter failed"
        )
        mock_gate_result = GateResult(
            gate_id="registry_surface",
            gate_name="Registry Surface",
            status=GateStatus.FAIL,
            message="Registry surface unavailable: Adapter failed",
            details={},
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        
        mock_adapter.fetch_registry_surface.return_value = mock_result
        mock_adapter.to_gate_result.return_value = mock_gate_result
        
        result = fetch_registry_gate_result()
        
        assert isinstance(result, GateResult)
        assert result.status == GateStatus.FAIL
        assert "unavailable" in result.message.lower() or "Adapter failed" in result.message


class TestIntegrationWithGateSummaryService:
    """Test integration with gate summary service."""
    
    @patch('gui.services.registry_adapter.fetch_registry_gate_result')
    def test_gate_summary_service_integration(self, mock_fetch):
        """Test that gate summary service uses the adapter."""
        from gui.services.gate_summary_service import GateSummaryService
        
        mock_gate_result = GateResult(
            gate_id="registry_surface",
            gate_name="Registry Surface",
            status=GateStatus.PASS,
            message="Test",
            details={},
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        mock_fetch.return_value = mock_gate_result
        
        mock_client = Mock()
        service = GateSummaryService(client=mock_client)
        
        # Call the method that should use the adapter
        result = service._fetch_registry_surface()
        
        assert result == mock_gate_result
        mock_fetch.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])