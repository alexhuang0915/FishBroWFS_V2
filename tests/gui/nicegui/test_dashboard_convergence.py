"""Unit tests for dashboard convergence (no infinite Checking)."""
import pytest
from unittest.mock import patch, MagicMock, call
from gui.nicegui.pages.dashboard import update_dashboard


@pytest.fixture
def mock_services():
    """Mock all external services used by dashboard."""
    with patch("gui.nicegui.pages.dashboard.get_backend_status_dict") as mock_status, \
         patch("gui.nicegui.pages.dashboard.list_local_runs") as mock_list_runs, \
         patch("gui.nicegui.pages.dashboard.get_run_count_by_status") as mock_run_counts, \
         patch("gui.nicegui.pages.dashboard.get_recent_logs") as mock_logs, \
         patch("gui.nicegui.pages.dashboard.render_simple_table") as mock_table, \
         patch("gui.nicegui.pages.dashboard.show_toast") as mock_toast:
        yield {
            "status": mock_status,
            "list_runs": mock_list_runs,
            "run_counts": mock_run_counts,
            "logs": mock_logs,
            "table": mock_table,
            "toast": mock_toast,
        }


def test_dashboard_update_all_systems_online(mock_services):
    """Dashboard cards updated when system is online."""
    mock_services["status"].return_value = {
        "backend": {"online": True},
        "worker": {"alive": True},
        "overall": True,
        "state": "ONLINE",
        "summary": "System fully operational",
    }
    mock_services["list_runs"].return_value = [
        {"run_id": "run1", "season": "2026Q1", "status": "RUNNING", "progress": "50%"},
        {"run_id": "run2", "season": "2026Q1", "status": "COMPLETED", "progress": "100%"},
    ]
    mock_services["run_counts"].return_value = {"COMPLETED": 5, "RUNNING": 1, "FAILED": 0}
    mock_services["logs"].return_value = ["log line 1", "log line 2"]
    
    # Mock card objects with update methods
    status_card = MagicMock()
    active_runs_card = MagicMock()
    candidates_card = MagicMock()
    storage_card = MagicMock()
    runs_container = MagicMock()
    log_terminal = MagicMock()
    
    update_dashboard(
        status_card, active_runs_card, candidates_card, storage_card,
        runs_container, log_terminal
    )
    
    # Verify status card updates
    status_card.update_content.assert_called_once_with("All systems operational")
    status_card.update_color.assert_called_once_with("success")
    
    # Verify active runs count
    active_runs_card.update_content.assert_called_once_with("1")  # only RUNNING
    
    # Verify candidates card uses completed runs count
    candidates_card.update_content.assert_called_once_with("5")
    
    # Verify storage card gets N/A
    storage_card.update_content.assert_called_once_with("N/A")
    
    # Verify runs table cleared and re-rendered
    runs_container.clear.assert_called_once()
    mock_services["table"].assert_called_once()
    
    # Verify log terminal updated
    log_terminal.set_value.assert_called_once_with("log line 1\nlog line 2")


def test_dashboard_update_worker_down(mock_services):
    """Dashboard shows degraded when worker down."""
    mock_services["status"].return_value = {
        "backend": {"online": True},
        "worker": {"alive": False},
        "overall": False,
        "state": "DEGRADED",
        "summary": "Backend up, worker down",
    }
    mock_services["list_runs"].return_value = []
    mock_services["run_counts"].return_value = {"COMPLETED": 0, "RUNNING": 0, "FAILED": 0}
    mock_services["logs"].return_value = []
    
    status_card = MagicMock()
    active_runs_card = MagicMock()
    candidates_card = MagicMock()
    storage_card = MagicMock()
    runs_container = MagicMock()
    log_terminal = MagicMock()
    
    update_dashboard(
        status_card, active_runs_card, candidates_card, storage_card,
        runs_container, log_terminal
    )
    
    status_card.update_content.assert_called_once_with("Worker down")
    status_card.update_color.assert_called_once_with("warning")
    active_runs_card.update_content.assert_called_once_with("0")
    candidates_card.update_content.assert_called_once_with("0")
    log_terminal.set_value.assert_called_once_with("No logs available")


def test_dashboard_update_backend_offline(mock_services):
    """Dashboard shows offline when backend unreachable."""
    mock_services["status"].return_value = {
        "backend": {"online": False},
        "worker": {"alive": False},
        "overall": False,
        "state": "OFFLINE",
        "summary": "Backend unreachable",
    }
    mock_services["list_runs"].return_value = []
    mock_services["run_counts"].return_value = {"COMPLETED": 0, "RUNNING": 0, "FAILED": 0}
    mock_services["logs"].return_value = []
    
    status_card = MagicMock()
    active_runs_card = MagicMock()
    candidates_card = MagicMock()
    storage_card = MagicMock()
    runs_container = MagicMock()
    log_terminal = MagicMock()
    
    update_dashboard(
        status_card, active_runs_card, candidates_card, storage_card,
        runs_container, log_terminal
    )
    
    status_card.update_content.assert_called_once_with("Backend unreachable")
    status_card.update_color.assert_called_once_with("danger")
    active_runs_card.update_content.assert_called_once_with("0")
    candidates_card.update_content.assert_called_once_with("0")


def test_dashboard_update_exception_shows_toast(mock_services):
    """Dashboard error handling shows toast."""
    mock_services["status"].side_effect = Exception("Network error")
    
    status_card = MagicMock()
    active_runs_card = MagicMock()
    candidates_card = MagicMock()
    storage_card = MagicMock()
    runs_container = MagicMock()
    log_terminal = MagicMock()
    
    update_dashboard(
        status_card, active_runs_card, candidates_card, storage_card,
        runs_container, log_terminal
    )
    
    # Toast should be shown
    mock_services["toast"].assert_called_once()
    assert "Network error" in mock_services["toast"].call_args[0][0]
    # No card updates should happen (since exception)
    assert status_card.update_content.call_count == 0


if __name__ == "__main__":
    pytest.main([__file__])