"""
Tests for job boundary extraction functions.
"""
import pytest
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from control.job_boundary_reader import (
    JobBoundary,
    extract_job_boundary,
    JobBoundaryExtractionError,
    _extract_from_spec,
    _extract_from_research_artifacts,
    _extract_from_job_dir,
    _extract_from_portfolio_artifacts,
)


def test_job_boundary_model():
    """Test JobBoundary model creation."""
    boundary = JobBoundary(
        universe_fingerprint="universe_fp_123",
        timeframes_fingerprint="timeframes_fp_456",
        dataset_snapshot_id="dataset_snap_789",
        engine_constitution_id="engine_constitution_abc"
    )
    
    assert boundary.universe_fingerprint == "universe_fp_123"
    assert boundary.timeframes_fingerprint == "timeframes_fp_456"
    assert boundary.dataset_snapshot_id == "dataset_snap_789"
    assert boundary.engine_constitution_id == "engine_constitution_abc"


def test_extract_from_spec_complete():
    """Test extraction from complete spec."""
    spec = {
        "params": {
            "universe_fingerprint": "universe_fp_123",
            "timeframes_fingerprint": "timeframes_fp_456",
            "dataset_snapshot_id": "dataset_snap_789",
            "engine_constitution_id": "engine_constitution_abc"
        }
    }
    
    boundary = _extract_from_spec(spec)
    
    assert isinstance(boundary, JobBoundary)
    assert boundary.universe_fingerprint == "universe_fp_123"
    assert boundary.timeframes_fingerprint == "timeframes_fp_456"
    assert boundary.dataset_snapshot_id == "dataset_snap_789"
    assert boundary.engine_constitution_id == "engine_constitution_abc"


def test_extract_from_spec_from_metadata():
    """Test extraction from spec metadata."""
    spec = {
        "metadata": {
            "universe_fingerprint": "universe_fp_123",
            "timeframes_fingerprint": "timeframes_fp_456",
            "dataset_snapshot_id": "dataset_snap_789",
            "engine_constitution_id": "engine_constitution_abc"
        }
    }
    
    boundary = _extract_from_spec(spec)
    
    assert isinstance(boundary, JobBoundary)
    assert boundary.universe_fingerprint == "universe_fp_123"
    assert boundary.timeframes_fingerprint == "timeframes_fp_456"
    assert boundary.dataset_snapshot_id == "dataset_snap_789"
    assert boundary.engine_constitution_id == "engine_constitution_abc"


def test_extract_from_spec_mixed():
    """Test extraction from spec with mixed params and metadata."""
    spec = {
        "params": {
            "universe_fingerprint": "universe_fp_123",
            "timeframes_fingerprint": "timeframes_fp_456",
        },
        "metadata": {
            "dataset_snapshot_id": "dataset_snap_789",
            "engine_constitution_id": "engine_constitution_abc"
        }
    }
    
    boundary = _extract_from_spec(spec)
    
    assert isinstance(boundary, JobBoundary)
    assert boundary.universe_fingerprint == "universe_fp_123"
    assert boundary.timeframes_fingerprint == "timeframes_fp_456"
    assert boundary.dataset_snapshot_id == "dataset_snap_789"
    assert boundary.engine_constitution_id == "engine_constitution_abc"


def test_extract_from_spec_incomplete():
    """Test extraction from incomplete spec (should return None)."""
    spec = {
        "params": {
            "universe_fingerprint": "universe_fp_123",
            # Missing other fields
        }
    }
    
    boundary = _extract_from_spec(spec)
    
    assert boundary is None


def test_extract_from_research_artifacts():
    """Test extraction from research artifacts."""
    mock_research_dir = Mock(spec=Path)
    mock_manifest = Mock(spec=Path)
    mock_manifest.exists.return_value = True
    
    manifest_data = {
        "universe_fingerprint": "universe_fp_123",
        "timeframes_fingerprint": "timeframes_fp_456",
        "dataset_snapshot_id": "dataset_snap_789",
        "engine_constitution_id": "engine_constitution_abc"
    }
    
    # Use __truediv__ as a method that returns a Mock
    mock_research_dir.__truediv__ = Mock(return_value=mock_manifest)
    
    # Mock the built-in open function (not manifest_path.open)
    mock_file = MagicMock()
    mock_file.__enter__.return_value = mock_file
    mock_file.__exit__.return_value = None
    mock_file.read.return_value = json.dumps(manifest_data)
    
    with patch('builtins.open', return_value=mock_file):
        boundary = _extract_from_research_artifacts(mock_research_dir)
    
    assert isinstance(boundary, JobBoundary)
    assert boundary.universe_fingerprint == "universe_fp_123"
    assert boundary.timeframes_fingerprint == "timeframes_fp_456"
    assert boundary.dataset_snapshot_id == "dataset_snap_789"
    assert boundary.engine_constitution_id == "engine_constitution_abc"


def test_extract_from_job_dir():
    """Test extraction from job directory with boundary.json."""
    mock_job_dir = Mock(spec=Path)
    mock_boundary_file = Mock(spec=Path)
    mock_boundary_file.exists.return_value = True
    
    boundary_data = {
        "universe_fingerprint": "universe_fp_123",
        "timeframes_fingerprint": "timeframes_fp_456",
        "dataset_snapshot_id": "dataset_snap_789",
        "engine_constitution_id": "engine_constitution_abc"
    }
    
    # Use __truediv__ as a method that returns a Mock
    mock_job_dir.__truediv__ = Mock(return_value=mock_boundary_file)
    
    # Mock glob to return empty list (so it doesn't try to iterate over other JSON files)
    mock_job_dir.glob.return_value = []
    
    # Mock the built-in open function
    mock_file = MagicMock()
    mock_file.__enter__.return_value = mock_file
    mock_file.__exit__.return_value = None
    mock_file.read.return_value = json.dumps(boundary_data)
    
    with patch('builtins.open', return_value=mock_file):
        boundary = _extract_from_job_dir(mock_job_dir)
    
    assert isinstance(boundary, JobBoundary)
    assert boundary.universe_fingerprint == "universe_fp_123"
    assert boundary.timeframes_fingerprint == "timeframes_fp_456"
    assert boundary.dataset_snapshot_id == "dataset_snap_789"
    assert boundary.engine_constitution_id == "engine_constitution_abc"


def test_extract_from_portfolio_artifacts():
    """Test extraction from portfolio artifacts."""
    mock_portfolio_dir = Mock(spec=Path)
    mock_manifest = Mock(spec=Path)
    mock_manifest.exists.return_value = True
    
    manifest_data = {
        "universe_fingerprint": "universe_fp_123",
        "timeframes_fingerprint": "timeframes_fp_456",
        "dataset_snapshot_id": "dataset_snap_789",
        "engine_constitution_id": "engine_constitution_abc"
    }
    
    # Use __truediv__ as a method that returns a Mock
    mock_portfolio_dir.__truediv__ = Mock(return_value=mock_manifest)
    
    # Mock the built-in open function
    mock_file = MagicMock()
    mock_file.__enter__.return_value = mock_file
    mock_file.__exit__.return_value = None
    mock_file.read.return_value = json.dumps(manifest_data)
    
    with patch('builtins.open', return_value=mock_file):
        boundary = _extract_from_portfolio_artifacts(mock_portfolio_dir)
    
    assert isinstance(boundary, JobBoundary)
    assert boundary.universe_fingerprint == "universe_fp_123"
    assert boundary.timeframes_fingerprint == "timeframes_fp_456"
    assert boundary.dataset_snapshot_id == "dataset_snap_789"
    assert boundary.engine_constitution_id == "engine_constitution_abc"


def test_extract_job_boundary_from_spec():
    """Test extract_job_boundary using job spec."""
    mock_job_row = Mock()
    mock_job_row.spec_json = json.dumps({
        "params": {
            "universe_fingerprint": "universe_fp_123",
            "timeframes_fingerprint": "timeframes_fp_456",
            "dataset_snapshot_id": "dataset_snap_789",
            "engine_constitution_id": "engine_constitution_abc"
        }
    })
    
    with patch('control.supervisor.get_job') as mock_get_job:
        mock_get_job.return_value = mock_job_row
        
        outputs_root = Path("/tmp/outputs")
        boundary = extract_job_boundary("test_job_123", outputs_root)
        
        assert isinstance(boundary, JobBoundary)
        assert boundary.universe_fingerprint == "universe_fp_123"
        assert boundary.timeframes_fingerprint == "timeframes_fp_456"
        assert boundary.dataset_snapshot_id == "dataset_snap_789"
        assert boundary.engine_constitution_id == "engine_constitution_abc"


def test_extract_job_boundary_no_sources():
    """Test extract_job_boundary when no sources are available."""
    with patch('control.supervisor.get_job') as mock_get_job:
        mock_get_job.return_value = None
        
        outputs_root = Path("/tmp/outputs")
        
        # Mock job directory doesn't exist
        with patch.object(Path, 'exists', return_value=False):
            with pytest.raises(JobBoundaryExtractionError):
                extract_job_boundary("test_job_123", outputs_root)


def test_get_job_artifact_dir():
    """Test get_job_artifact_dir helper."""
    from control.job_boundary_reader import get_job_artifact_dir
    
    outputs_root = Path("/tmp/outputs")
    job_dir = get_job_artifact_dir("test_job_123", outputs_root)
    
    assert job_dir == Path("/tmp/outputs/jobs/test_job_123")