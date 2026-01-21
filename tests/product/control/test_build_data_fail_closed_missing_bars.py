
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
from control.supervisor.handlers.build_data import BuildDataHandler
from control.supervisor.job_handler import JobContext

@pytest.fixture
def mock_job_context(tmp_path):
    context = MagicMock(spec=JobContext)
    context.job_id = "test_job_id"
    context.artifacts_dir = str(tmp_path / "artifacts")
    Path(context.artifacts_dir).mkdir(parents=True, exist_ok=True)
    return context

@pytest.fixture
def build_data_handler():
    return BuildDataHandler()

@patch("control.supervisor.handlers.build_data.subprocess.run")
@patch("control.supervisor.handlers.build_data.resampled_bars_path")
def test_execute_via_cli_success(mock_resampled_path, mock_subprocess, build_data_handler, mock_job_context):
    """Test successful CLI execution with artifact verification."""
    # Setup mock subprocess success
    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_subprocess.return_value = mock_process
    
    # Setup mock artifact existence
    mock_path = MagicMock()
    mock_path.exists.return_value = True
    mock_resampled_path.return_value = mock_path
    
    params = {
        "dataset_id": "TEST.DATA",
        "timeframe_min": 60,
        "mode": "BARS_ONLY"
    }
    
    result = build_data_handler._execute_via_cli(params, mock_job_context)
    
    assert result["ok"] is True
    assert result["job_type"] == "BUILD_DATA"
    assert "error" not in result

@patch("control.supervisor.handlers.build_data.subprocess.run")
@patch("control.supervisor.handlers.build_data.resampled_bars_path")
@patch("control.supervisor.handlers.build_data.get_outputs_root")
def test_execute_via_cli_fail_closed_missing_artifacts(mock_get_outputs_root, mock_resampled_path, mock_subprocess, build_data_handler, mock_job_context):
    """Test fail-closed behavior when CLI succeeds but artifacts are missing."""
    # Setup mock subprocess success
    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_subprocess.return_value = mock_process
    
    # Setup mock artifact MISSING
    mock_path = MagicMock()
    mock_path.exists.return_value = False
    mock_path.__str__.return_value = "/mock/path/to/bars"
    mock_resampled_path.return_value = mock_path
    
    params = {
        "dataset_id": "TEST.DATA",
        "timeframe_min": 60,
        "mode": "BARS_ONLY"
    }
    
    result = build_data_handler._execute_via_cli(params, mock_job_context)
    
    # Assert FAIL CLOSED
    assert result["ok"] is False
    assert "ERR_BUILD_ARTIFACTS_MISSING" in result["error"]
    assert "Bars missing" in result["error"]

@patch("control.supervisor.handlers.build_data.subprocess.run")
def test_execute_via_cli_subprocess_failure(mock_subprocess, build_data_handler, mock_job_context):
    """Test behavior when CLI itself fails."""
    # Setup mock subprocess failure
    mock_process = MagicMock()
    mock_process.returncode = 1
    mock_subprocess.return_value = mock_process
    
    params = {
        "dataset_id": "TEST.DATA",
        "timeframe_min": 60,
        "mode": "BARS_ONLY"
    }
    
    result = build_data_handler._execute_via_cli(params, mock_job_context)
    
    assert result["ok"] is False
    assert "CLI failed with return code 1" in result["error"]
