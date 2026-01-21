
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
from control.supervisor.handlers.run_plateau import RunPlateauHandler
from control.supervisor.job_handler import JobContext
from control.control_types import ReasonCode

@pytest.fixture
def mock_job_context(tmp_path):
    context = MagicMock(spec=JobContext)
    context.job_id = "test_plateau_guard"
    context.artifacts_dir = str(tmp_path / "artifacts")
    context.is_abort_requested.return_value = False
    Path(context.artifacts_dir).mkdir(parents=True, exist_ok=True)
    return context

@pytest.fixture
def plateau_handler():
    return RunPlateauHandler()

@patch("control.supervisor.handlers.run_plateau.subprocess.run")
@patch("control.supervisor.handlers.run_plateau.get_outputs_root")
@patch("contracts.artifact_guard.assert_artifacts_present")
def test_plateau_guard_fail_closed(mock_assert, mock_get_outputs_root, mock_subprocess, plateau_handler, mock_job_context, tmp_path):
    """Test plateau run usage of Universal Artifact Guard (Fail-Closed)."""
    # Setup mock subprocess success
    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_subprocess.return_value = mock_process
    
    # Mock assertion failure
    mock_assert.return_value = ["Missing file: plateau_report.json"]
    
    # Mock path resolution
    mock_get_outputs_root.return_value = tmp_path
    
    # Setup required pre-existing directories/files
    # Handler expects: seasons/current/{research_run_id}/winners.json (or candidates)
    research_id = "test_research_run_001"
    research_dir = tmp_path / "seasons" / "current" / research_id
    research_dir.mkdir(parents=True, exist_ok=True)
    (research_dir / "winners.json").write_text('{"winners": []}') # minimal winners
    
    params = {
        "research_run_id": research_id,
        "k_neighbors": 5,
        "score_threshold_rel": 0.95
    }
    
    # Disable test mode detection by ensuring env vars and path don't trigger it
    # We must mock _is_test_mode to return False.
    
    with patch("control.supervisor.handlers.run_plateau._is_test_mode", return_value=False):
        result = plateau_handler.execute(params, mock_job_context)
    
    # Assert Guard Failure
    assert result["ok"] is False
    assert result["error"].startswith(ReasonCode.ERR_PLATEAU_ARTIFACTS_MISSING)
    assert "Missing file: plateau_report.json" in result["error"]
    
    # Verify contract was checked
    mock_assert.assert_called_once()
