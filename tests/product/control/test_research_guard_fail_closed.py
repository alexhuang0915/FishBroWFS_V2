
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
from control.supervisor.handlers.run_research import RunResearchHandler
from control.supervisor.job_handler import JobContext
from control.control_types import ReasonCode

@pytest.fixture
def mock_job_context(tmp_path):
    context = MagicMock(spec=JobContext)
    context.job_id = "test_research_guard"
    context.artifacts_dir = str(tmp_path / "artifacts")
    context.is_abort_requested.return_value = False
    Path(context.artifacts_dir).mkdir(parents=True, exist_ok=True)
    return context

@pytest.fixture
def research_handler():
    return RunResearchHandler()

@patch("control.supervisor.handlers.run_research.subprocess.run")
@patch("control.supervisor.handlers.run_research.get_outputs_root")
@patch("contracts.artifact_guard.assert_artifacts_present")
def test_research_guard_fail_closed(mock_assert, mock_get_outputs_root, mock_subprocess, research_handler, mock_job_context, tmp_path):
    """Test research run usage of Universal Artifact Guard (Fail-Closed)."""
    # Setup mock subprocess success
    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_subprocess.return_value = mock_process
    
    # Mock assertion failure
    mock_assert.return_value = ["Missing directory: research"]
    
    # Mock path resolution to tmp_path
    mock_get_outputs_root.return_value = tmp_path
    
    # Create fake payload params
    params = {
        "strategy_id": "TEST_STRAT",
        "start_date": "2024-01-01",
        "end_date": "2024-01-31",
        "params_override": {"instrument": "CME.ES"} # Required for manifest logic
    }
    
    # Determine expected run dir based on logic: outputs_root / "seasons" / "current" / context.job_id
    # We must ensure this directory exists so the handler doesn't fail before subprocess
    expected_run_dir = tmp_path / "seasons" / "current" / "test_research_guard"
    expected_run_dir.mkdir(parents=True, exist_ok=True)

    # Execute
    result = research_handler.execute(params, mock_job_context)
    
    # Verify contract was checked
    mock_assert.assert_called_once()
    
    # Assert Guard Failure
    assert result["ok"] is False
    assert result["error"].startswith(ReasonCode.ERR_RESEARCH_ARTIFACTS_MISSING)
    assert "Missing directory: research" in result["error"]
