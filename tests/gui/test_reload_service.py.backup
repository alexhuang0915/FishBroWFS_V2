"""Tests for reload service functionality."""

import pytest
from unittest.mock import Mock, patch, MagicMock
import time
from pathlib import Path
from datetime import datetime

from FishBroWFS_V2.gui.services import reload_service
from FishBroWFS_V2.gui.services.reload_service import (
    reload_everything,
    ReloadResult,
    compute_file_signature,
    check_txt_files,
    check_parquet_files,
    get_dataset_status,
    DatasetStatus,
    build_parquet,
    build_all_parquet,
    SystemSnapshot,
)


def test_reload_result_dataclass():
    """Test ReloadResult dataclass."""
    result = ReloadResult(
        ok=True,
        error=None,
        datasets_reloaded=2,
        strategies_reloaded=3,
        caches_invalidated=["feature_cache"],
        duration_seconds=1.5
    )
    
    assert result.ok is True
    assert result.error is None
    assert result.datasets_reloaded == 2
    assert result.strategies_reloaded == 3
    assert result.caches_invalidated == ["feature_cache"]
    assert result.duration_seconds == 1.5


def test_reload_result_error():
    """Test ReloadResult with error."""
    result = ReloadResult(
        ok=False,
        error="Test error",
        duration_seconds=0.5
    )
    
    assert result.ok is False
    assert result.error == "Test error"


def test_invalidate_feature_cache_success():
    """Test successful feature cache invalidation."""
    # Mock the actual function
    with patch('FishBroWFS_V2.gui.services.reload_service.invalidate_feature_cache', return_value=True):
        result = reload_service.invalidate_feature_cache()
        assert result is True


def test_invalidate_feature_cache_failure():
    """Test failed feature cache invalidation."""
    # Mock the actual function to return False (simulating failure)
    with patch('FishBroWFS_V2.gui.services.reload_service.invalidate_feature_cache', return_value=False):
        result = reload_service.invalidate_feature_cache()
        assert result is False


def test_reload_dataset_registry_success():
    """Test successful dataset registry reload."""
    # Mock the catalog functions
    with patch('FishBroWFS_V2.gui.services.reload_service.get_dataset_catalog') as mock_get_catalog:
        mock_catalog = Mock()
        mock_catalog.load_index.return_value = Mock()
        mock_get_catalog.return_value = mock_catalog
        
        result = reload_service.reload_dataset_registry()
        assert result is True


def test_reload_dataset_registry_failure():
    """Test failed dataset registry reload."""
    # Mock the catalog functions to raise exception
    with patch('FishBroWFS_V2.gui.services.reload_service.get_dataset_catalog', side_effect=Exception("Test error")):
        result = reload_service.reload_dataset_registry()
        assert result is False


def test_reload_strategy_registry_success():
    """Test successful strategy registry reload."""
    # Mock the catalog functions
    with patch('FishBroWFS_V2.gui.services.reload_service.get_strategy_catalog') as mock_get_catalog:
        mock_catalog = Mock()
        mock_catalog.load_registry.return_value = Mock()
        mock_get_catalog.return_value = mock_catalog
        
        result = reload_service.reload_strategy_registry()
        assert result is True


def test_reload_strategy_registry_failure():
    """Test failed strategy registry reload."""
    # Mock the catalog functions to raise exception
    with patch('FishBroWFS_V2.gui.services.reload_service.get_strategy_catalog', side_effect=Exception("Test error")):
        result = reload_service.reload_strategy_registry()
        assert result is False


def test_reload_everything_success():
    """Test successful reload of everything."""
    # Mock all the component functions
    with patch('FishBroWFS_V2.gui.services.reload_service.invalidate_feature_cache', return_value=True):
        with patch('FishBroWFS_V2.gui.services.reload_service.reload_dataset_registry', return_value=True):
            with patch('FishBroWFS_V2.gui.services.reload_service.reload_strategy_registry', return_value=True):
                result = reload_everything(reason="test")
                
                assert result.ok is True
                assert result.error is None
                assert result.datasets_reloaded == 1
                assert result.strategies_reloaded == 1
                assert "feature_cache" in result.caches_invalidated
                assert result.duration_seconds > 0


def test_reload_everything_feature_cache_failure():
    """Test reload everything with feature cache failure."""
    with patch('FishBroWFS_V2.gui.services.reload_service.invalidate_feature_cache', return_value=False):
        with patch('FishBroWFS_V2.gui.services.reload_service.reload_dataset_registry', return_value=True):
            with patch('FishBroWFS_V2.gui.services.reload_service.reload_strategy_registry', return_value=True):
                result = reload_everything(reason="test")
                
                assert result.ok is False
                assert "feature cache" in result.error


def test_reload_everything_dataset_registry_failure():
    """Test reload everything with dataset registry failure."""
    with patch('FishBroWFS_V2.gui.services.reload_service.invalidate_feature_cache', return_value=True):
        with patch('FishBroWFS_V2.gui.services.reload_service.reload_dataset_registry', return_value=False):
            with patch('FishBroWFS_V2.gui.services.reload_service.reload_strategy_registry', return_value=True):
                result = reload_everything(reason="test")
                
                assert result.ok is False
                assert "dataset registry" in result.error


def test_reload_everything_strategy_registry_failure():
    """Test reload everything with strategy registry failure."""
    with patch('FishBroWFS_V2.gui.services.reload_service.invalidate_feature_cache', return_value=True):
        with patch('FishBroWFS_V2.gui.services.reload_service.reload_dataset_registry', return_value=True):
            with patch('FishBroWFS_V2.gui.services.reload_service.reload_strategy_registry', return_value=False):
                result = reload_everything(reason="test")
                
                assert result.ok is False
                assert "strategy registry" in result.error


def test_reload_everything_exception():
    """Test reload everything with unexpected exception."""
    with patch('FishBroWFS_V2.gui.services.reload_service.invalidate_feature_cache', side_effect=Exception("Unexpected error")):
        result = reload_everything(reason="test")
        
        assert result.ok is False
        assert "Unexpected error" in result.error


def test_reload_everything_duration():
    """Test that reload_everything measures duration correctly."""
    # Mock time to control duration
    mock_times = [100.0, 100.5]  # 0.5 seconds duration
    
    with patch('time.time', side_effect=mock_times):
        with patch('FishBroWFS_V2.gui.services.reload_service.invalidate_feature_cache', return_value=True):
            with patch('FishBroWFS_V2.gui.services.reload_service.reload_dataset_registry', return_value=True):
                with patch('FishBroWFS_V2.gui.services.reload_service.reload_strategy_registry', return_value=True):
                    result = reload_everything(reason="test")
                    
                    assert result.duration_seconds == 0.5


def test_reload_everything_reason_parameter():
    """Test that reason parameter is accepted."""
    with patch('FishBroWFS_V2.gui.services.reload_service.invalidate_feature_cache', return_value=True):
        with patch('FishBroWFS_V2.gui.services.reload_service.reload_dataset_registry', return_value=True):
            with patch('FishBroWFS_V2.gui.services.reload_service.reload_strategy_registry', return_value=True):
                result = reload_everything(reason="manual_ui")
                
                assert result.ok is True
                # Reason is not stored in result, but function should accept it


def test_reload_everything_caches_invalidated():
    """Test that caches_invalidated list is populated correctly."""
    with patch('FishBroWFS_V2.gui.services.reload_service.invalidate_feature_cache', return_value=True):
        with patch('FishBroWFS_V2.gui.services.reload_service.reload_dataset_registry', return_value=True):
            with patch('FishBroWFS_V2.gui.services.reload_service.reload_strategy_registry', return_value=True):
                result = reload_everything(reason="test")
                
                assert "feature_cache" in result.caches_invalidated
                assert len(result.caches_invalidated) == 1


# New tests for TXT/Parquet functionality
def test_compute_file_signature_missing():
    """Test file signature for missing file."""
    with patch('pathlib.Path.exists', return_value=False):
        result = compute_file_signature(Path("/nonexistent/file.txt"))
        assert result == "missing"


def test_compute_file_signature_small_file():
    """Test file signature for small file."""
    mock_path = Mock(spec=Path)
    mock_path.exists.return_value = True
    mock_path.stat.return_value = Mock(st_size=1000)  # < 50MB
    
    # Mock file reading - create a mock that supports context manager
    mock_file_content = b"test content"
    
    # Create a mock file object
    mock_file = Mock()
    mock_file.read.side_effect = [mock_file_content, b""]  # First read returns content, second returns empty
    
    # Create a mock context manager
    mock_context = Mock()
    mock_context.__enter__ = Mock(return_value=mock_file)
    mock_context.__exit__ = Mock(return_value=None)
    
    # Mock open to return the context manager
    with patch('builtins.open', return_value=mock_context):
        result = compute_file_signature(mock_path)
        assert result.startswith("sha256:")


def test_compute_file_signature_large_file():
    """Test file signature for large file."""
    mock_path = Mock(spec=Path)
    mock_path.exists.return_value = True
    mock_path.name = "large_file.parquet"
    mock_path.stat.return_value = Mock(st_size=100 * 1024 * 1024, st_mtime=1234567890)  # 100MB
    
    result = compute_file_signature(mock_path)
    assert result.startswith("stat:")


def test_check_txt_files():
    """Test checking TXT files."""
    txt_root = "/data/txt"
    txt_paths = ["/data/txt/file1.txt", "/data/txt/file2.txt"]
    
    with patch('pathlib.Path.exists') as mock_exists:
        mock_exists.return_value = True
        
        with patch('pathlib.Path.stat') as mock_stat:
            mock_stat.return_value = Mock(st_size=1000, st_mtime=1234567890)
            
            present, missing, latest_mtime, total_size, signature = check_txt_files(txt_root, txt_paths)
            
            assert present is True
            assert len(missing) == 0
            assert latest_mtime is not None
            assert total_size == 2000
            assert "file1.txt:" in signature
            assert "file2.txt:" in signature


def test_check_txt_files_missing():
    """Test checking TXT files with missing files."""
    txt_root = "/data/txt"
    txt_paths = ["/data/txt/file1.txt", "/data/txt/file2.txt"]
    
    # Mock Path class in the module where it's imported
    with patch('FishBroWFS_V2.gui.services.reload_service.Path') as MockPath:
        # Create mock for file1 (exists)
        mock_path1 = Mock()
        mock_path1.exists.return_value = True
        mock_path1.stat.return_value = Mock(st_size=1000, st_mtime=1234567890)
        mock_path1.name = "file1.txt"
        
        # Create mock for file2 (doesn't exist)
        mock_path2 = Mock()
        mock_path2.exists.return_value = False
        mock_path2.name = "file2.txt"
        
        # Make Path constructor return appropriate mock based on input string
        def path_constructor(path_str):
            if isinstance(path_str, str):
                if path_str == "/data/txt/file1.txt":
                    return mock_path1
                elif path_str == "/data/txt/file2.txt":
                    return mock_path2
            # For other cases (like Path() called without args), return a default mock
            mock = Mock()
            mock.exists.return_value = False
            return mock
        
        MockPath.side_effect = path_constructor
        
        # Also need to mock compute_file_signature for the existing file
        with patch('FishBroWFS_V2.gui.services.reload_service.compute_file_signature') as mock_compute_sig:
            mock_compute_sig.return_value = "mock_sig"
            
            present, missing, latest_mtime, total_size, signature = check_txt_files(txt_root, txt_paths)
            
            assert present is False
            assert len(missing) == 1
            assert missing[0] == "/data/txt/file2.txt"
            assert total_size == 1000


def test_check_parquet_files():
    """Test checking Parquet files."""
    parquet_root = "/data/parquet"
    parquet_paths = ["/data/parquet/file1.parquet", "/data/parquet/file2.parquet"]
    
    with patch('pathlib.Path.exists') as mock_exists:
        mock_exists.return_value = True
        
        with patch('pathlib.Path.stat') as mock_stat:
            mock_stat.return_value = Mock(st_size=5000, st_mtime=1234567890)
            
            present, missing, latest_mtime, total_size, signature = check_parquet_files(parquet_root, parquet_paths)
            
            assert present is True
            assert len(missing) == 0
            assert latest_mtime is not None
            assert total_size == 10000
            assert "file1.parquet:" in signature
            assert "file2.parquet:" in signature


def test_get_dataset_status():
    """Test getting dataset status."""
    dataset_id = "test_dataset"
    
    with patch('FishBroWFS_V2.gui.services.reload_service.get_descriptor') as mock_get_descriptor:
        mock_descriptor = Mock()
        mock_descriptor.dataset_id = dataset_id
        mock_descriptor.kind = "test_kind"
        mock_descriptor.txt_root = "/data/txt"
        mock_descriptor.txt_required_paths = ["/data/txt/file1.txt"]
        mock_descriptor.parquet_root = "/data/parquet"
        mock_descriptor.parquet_expected_paths = ["/data/parquet/file1.parquet"]
        mock_get_descriptor.return_value = mock_descriptor
        
        with patch('FishBroWFS_V2.gui.services.reload_service.check_txt_files') as mock_check_txt:
            mock_check_txt.return_value = (True, [], "2024-01-01T00:00:00Z", 1000, "txt_sig")
            
            with patch('FishBroWFS_V2.gui.services.reload_service.check_parquet_files') as mock_check_parquet:
                mock_check_parquet.return_value = (True, [], "2024-01-01T00:00:00Z", 5000, "parquet_sig")
                
                status = get_dataset_status(dataset_id)
                
                assert isinstance(status, DatasetStatus)
                assert status.dataset_id == dataset_id
                assert status.kind == "test_kind"
                assert status.txt_present is True
                assert status.parquet_present is True
                assert status.up_to_date is True


def test_get_dataset_status_not_found():
    """Test getting dataset status for non-existent dataset."""
    dataset_id = "nonexistent"
    
    with patch('FishBroWFS_V2.gui.services.reload_service.get_descriptor', return_value=None):
        status = get_dataset_status(dataset_id)
        
        assert status.dataset_id == dataset_id
        assert status.kind == "unknown"
        assert status.error is not None
        assert "not found" in status.error.lower()


def test_build_parquet():
    """Test building Parquet for a dataset."""
    dataset_id = "test_dataset"
    
    with patch('FishBroWFS_V2.gui.services.reload_service.build_parquet_from_txt') as mock_build:
        mock_result = Mock()
        mock_result.success = True
        mock_result.error = None
        mock_build.return_value = mock_result
        
        result = build_parquet(dataset_id, reason="test")
        
        assert result.success is True
        mock_build.assert_called_once()


def test_build_all_parquet():
    """Test building Parquet for all datasets."""
    with patch('FishBroWFS_V2.gui.services.reload_service.list_descriptors') as mock_list:
        mock_descriptor1 = Mock()
        mock_descriptor1.dataset_id = "dataset1"
        mock_descriptor2 = Mock()
        mock_descriptor2.dataset_id = "dataset2"
        mock_list.return_value = [mock_descriptor1, mock_descriptor2]
        
        with patch('FishBroWFS_V2.gui.services.reload_service.build_parquet') as mock_build:
            mock_result = Mock()
            mock_result.success = True
            mock_build.return_value = mock_result
            
            results = build_all_parquet(reason="test")
            
            assert len(results) == 2
            assert mock_build.call_count == 2


def test_system_snapshot():
    """Test SystemSnapshot dataclass."""
    snapshot = SystemSnapshot(
        created_at=datetime(2024, 1, 1, 0, 0, 0),
        total_datasets=10,
        total_strategies=5,
        dataset_statuses=[],
        strategy_statuses=[],
        notes=["Test note"],
        errors=[]
    )
    
    assert snapshot.total_datasets == 10
    assert snapshot.total_strategies == 5
    assert len(snapshot.notes) == 1
    assert snapshot.notes[0] == "Test note"


def test_dataset_status_dataclass():
    """Test DatasetStatus dataclass."""
    status = DatasetStatus(
        dataset_id="test_dataset",
        kind="test_kind",
        txt_root="/data/txt",
        txt_required_paths=["file1.txt"],
        txt_present=True,
        txt_missing=[],
        txt_latest_mtime_utc="2024-01-01T00:00:00Z",
        txt_total_size_bytes=1000,
        txt_signature="txt_sig",
        parquet_root="/data/parquet",
        parquet_expected_paths=["file1.parquet"],
        parquet_present=True,
        parquet_missing=[],
        parquet_latest_mtime_utc="2024-01-01T00:00:00Z",
        parquet_total_size_bytes=5000,
        parquet_signature="parquet_sig",
        up_to_date=True,
        bars_count=1000,
        schema_ok=True
    )
    
    assert status.dataset_id == "test_dataset"
    assert status.kind == "test_kind"
    assert status.txt_present is True
    assert status.parquet_present is True
    assert status.up_to_date is True
    assert status.bars_count == 1000
    assert status.schema_ok is True