
import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from pathlib import Path
from control.supervisor.handlers.build_data import BuildDataHandler
from control.supervisor.job_handler import JobContext
from control.control_types import ReasonCode

@pytest.fixture
def mock_job_context(tmp_path):
    context = MagicMock(spec=JobContext)
    context.job_id = "test_feature_guard"
    context.artifacts_dir = str(tmp_path / "artifacts")
    Path(context.artifacts_dir).mkdir(parents=True, exist_ok=True)
    return context

@pytest.fixture
def build_data_handler():
    return BuildDataHandler()

@patch("control.supervisor.handlers.build_data.subprocess.run")
@patch("control.supervisor.handlers.build_data.resampled_bars_path")
@patch("control.supervisor.handlers.build_data.get_outputs_root")
@patch("contracts.artifact_guard.assert_artifacts_present")
def test_feature_guard_fail_closed(mock_assert, mock_get_outputs_root, mock_resampled_path, mock_subprocess, build_data_handler, mock_job_context):
    """Test feature build usage of Universal Artifact Guard (Fail-Closed)."""
    # Setup mock subprocess success
    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_subprocess.return_value = mock_process
    
    # Mock assertion failure (Missing artifacts)
    mock_assert.return_value = ["Missing file: features/features_manifest.json"]
    
    # Mock path resolution
    mock_root = MagicMock()
    mock_get_outputs_root.return_value = mock_root
    
    # We need to ensure resampled_bars_path is mocked such that .parent.parent logic works
    # resampled_path -> .../bars/file.npz
    # .parent -> .../bars
    # .parent.parent -> .../dataset_root (Target logic)
    mock_bar_file = MagicMock()
    mock_bar_dir = MagicMock()
    mock_dataset_root = MagicMock()
    
    mock_bar_file.parent = mock_bar_dir
    mock_bar_dir.parent = mock_dataset_root
    mock_resampled_path.return_value = mock_bar_file

    params = {
        "dataset_id": "TEST.DATA",
        "timeframe_min": 60,
        "mode": "FULL", # Triggers Feature check
        "build_features": True
    }
    
    result = build_data_handler._execute_via_cli(params, mock_job_context)
    
    # Assert Guard Failure
    assert result["ok"] is False
    assert result["error"].startswith(ReasonCode.ERR_FEATURE_ARTIFACTS_MISSING)
    assert "features/features_manifest.json" in result["error"]
    
    # Verify contract was checked
    mock_assert.assert_called_once()
