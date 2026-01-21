"""
Tests for Action Router Service (DP9).
"""

import pytest
pytest.importorskip("PySide6")

from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from contracts.ui_governance_state import UiTab, ui_governance_state
from gui.services.action_router_service import (
    ActionRouterService,
    get_action_router_service,
)
from gui.services.artifact_navigator_vm import GATE_SUMMARY_TARGET, EXPLAIN_TARGET_PREFIX


@pytest.fixture(autouse=True)
def reset_ui_governance_state():
    """Reset governance state before each test to avoid cross-test interference."""
    ui_governance_state.set_selected_job(None)
    ui_governance_state.set_active_tab(None)
    ui_governance_state.set_system_ready(True)
    yield
    ui_governance_state.set_selected_job(None)
    ui_governance_state.set_active_tab(None)
    ui_governance_state.set_system_ready(False)


class TestActionRouterService:
    """Test ActionRouterService."""
    
    def test_init(self):
        """Test service initialization."""
        service = ActionRouterService()
        assert service is not None
    
    def test_singleton(self):
        """Test singleton pattern."""
        service1 = get_action_router_service()
        service2 = get_action_router_service()
        assert service1 is service2
    
    def test_handle_action_gate_summary(self):
        """Test handling gate summary action."""
        service = ActionRouterService()
        service.open_gate_summary = Mock()
        ui_governance_state.set_active_tab(UiTab.GATE_SUMMARY_DASHBOARD)
        
        result = service.handle_action(
            GATE_SUMMARY_TARGET,
            context={"job_id": "test_job_123"}
        )
        
        assert result is True
        service.open_gate_summary.emit.assert_called_once_with("test_job_123")
    
    def test_handle_action_explain(self):
        """Test handling explain action."""
        service = ActionRouterService()
        service.open_explain = Mock()
        ui_governance_state.set_selected_job("test_job_123")
        
        result = service.handle_action(
            f"{EXPLAIN_TARGET_PREFIX}test_job_123",
            context={"job_id": "test_job_123"}
        )
        
        assert result is True
        service.open_explain.emit.assert_called_once_with("test_job_123")
    
    def test_handle_action_job_admission(self):
        """Test handling job admission action."""
        service = ActionRouterService()
        ui_governance_state.set_selected_job("test_job_123")
        
        with patch.object(service, '_open_job_admission_decision') as mock_open:
            result = service.handle_action(
                "job_admission://test_job_123",
                context={"job_id": "test_job_123"}
            )
            
            assert result is True
            mock_open.assert_called_once_with("test_job_123")
    
    def test_handle_action_gate_dashboard(self):
        """Test handling gate dashboard action."""
        service = ActionRouterService()
        service.open_url = Mock()
        ui_governance_state.set_active_tab(UiTab.GATE_SUMMARY_DASHBOARD)
        
        result = service.handle_action(
            "gate_dashboard",
            context={}
        )
        
        assert result is True
        service.open_url.emit.assert_called_once_with("internal://gate_dashboard")
    
    def test_handle_action_file_url(self):
        """Test handling file:// URL."""
        service = ActionRouterService()
        
        with patch('PySide6.QtGui.QDesktopServices.openUrl') as mock_open_url:
            result = service.handle_action(
                "file:///tmp/test.txt",
                context={}
            )
            
            assert result is True
            mock_open_url.assert_called_once()
    
    def test_handle_action_http_url(self):
        """Test handling http:// URL."""
        service = ActionRouterService()
        
        with patch('PySide6.QtGui.QDesktopServices.openUrl') as mock_open_url:
            result = service.handle_action(
                "http://example.com",
                context={}
            )
            
            assert result is True
            mock_open_url.assert_called_once()
    
    def test_handle_action_artifact_path(self):
        """Test handling job artifact path."""
        service = ActionRouterService()
        service.open_artifact_navigator = Mock()
        
        result = service.handle_action(
            "/jobs/test_job_123/artifacts/gate_summary.json",
            context={}
        )
        
        assert result is True
        service.open_artifact_navigator.emit.assert_called_once_with(
            "test_job_123", "gate_summary.json"
        )
    
    def test_handle_action_unhandled(self):
        """Test handling unhandled action."""
        service = ActionRouterService()
        
        result = service.handle_action(
            "unknown://target",
            context={}
        )
        
        assert result is False
    
    def test_create_gate_dashboard_action(self):
        """Test creating gate dashboard action."""
        service = ActionRouterService()
        
        action = service.create_gate_dashboard_action()
        
        assert action["label"] == "Open Gate Dashboard"
        assert action["target"] == "gate_dashboard"
    
    def test_create_job_admission_action(self):
        """Test creating job admission action."""
        service = ActionRouterService()
        
        action = service.create_job_admission_action("test_job_123")
        
        assert action["label"] == "View Admission Decision"
        assert action["target"] == "job_admission://test_job_123"
    
    def test_create_gate_summary_action(self):
        """Test creating gate summary action."""
        service = ActionRouterService()
        
        action = service.create_gate_summary_action("test_job_123")
        
        assert action["label"] == "View Gate Summary"
        assert action["target"] == GATE_SUMMARY_TARGET
        assert action["context"] == {"job_id": "test_job_123"}
    
    def test_create_explain_action(self):
        """Test creating explain action."""
        service = ActionRouterService()
        
        action = service.create_explain_action("test_job_123")
        
        assert action["label"] == "View Explain"
        assert action["target"] == f"{EXPLAIN_TARGET_PREFIX}test_job_123"
    
    def test_extract_job_id(self):
        """Test extracting job_id from context."""
        service = ActionRouterService()
        
        # With context
        job_id = service._extract_job_id({"job_id": "test_job_123"})
        assert job_id == "test_job_123"
        
        # Without context
        job_id = service._extract_job_id(None)
        assert job_id is None
        
        # With empty context
        job_id = service._extract_job_id({})
        assert job_id is None
    
    @patch('PySide6.QtGui.QDesktopServices.openUrl')
    @patch('gui.services.action_router_service.get_job_artifact_path')
    @patch('gui.services.action_router_service.get_job_evidence_dir')
    def test_open_job_admission_decision_exists(
        self, mock_get_dir, mock_get_path, mock_open_url
    ):
        """Test opening job admission decision when it exists."""
        service = ActionRouterService()
        
        # Mock decision path exists
        mock_decision_path = Mock(spec=Path)
        mock_decision_path.exists.return_value = True
        mock_get_path.return_value = mock_decision_path
        
        # Also mock get_job_evidence_dir to avoid TypeError if get_job_artifact_path
        # is not properly mocked (it calls get_job_evidence_dir internally)
        mock_artifact_dir = Mock(spec=Path)
        mock_get_dir.return_value = mock_artifact_dir
        
        service._open_job_admission_decision("test_job_123")
        
        mock_get_path.assert_called_once()
        mock_open_url.assert_called_once()
    
    @patch('PySide6.QtGui.QDesktopServices.openUrl')
    @patch('gui.services.action_router_service.get_job_artifact_path')
    @patch('gui.services.action_router_service.get_job_evidence_dir')
    def test_open_job_admission_decision_not_exists(
        self, mock_get_dir, mock_get_path, mock_open_url
    ):
        """Test opening job admission decision when it doesn't exist."""
        service = ActionRouterService()
        
        # Mock decision path doesn't exist
        mock_decision_path = Mock(spec=Path)
        mock_decision_path.exists.return_value = False
        mock_get_path.return_value = mock_decision_path
        
        # Mock artifact directory exists
        mock_artifact_dir = Mock(spec=Path)
        mock_artifact_dir.exists.return_value = True
        mock_get_dir.return_value = mock_artifact_dir
        
        service._open_job_admission_decision("test_job_123")
        
        mock_get_path.assert_called_once()
        mock_get_dir.assert_called_once_with("test_job_123")
        mock_open_url.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])