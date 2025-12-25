"""Tests for system status snapshot functionality."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
from pathlib import Path

from FishBroWFS_V2.gui.services.reload_service import (
    get_system_snapshot,
    SystemSnapshot,
    DatasetStatus,
    StrategyStatus,
    FileStatus,
    compute_file_signature,
    check_dataset_files,
    get_dataset_status,
    get_strategy_status,
)


def test_compute_file_signature_missing():
    """Test signature computation for missing file."""
    result = compute_file_signature(Path("/nonexistent/file.txt"))
    assert result == "missing"


def test_compute_file_signature_small_file(tmp_path):
    """Test signature computation for small file."""
    test_file = tmp_path / "test.txt"
    test_file.write_text("Hello, World!")
    
    result = compute_file_signature(test_file)
    assert result.startswith("sha256:")
    assert len(result) > 10


def test_compute_file_signature_error():
    """Test signature computation with error."""
    # Mock a file that exists but causes error on read
    with patch('pathlib.Path.exists', return_value=True):
        with patch('pathlib.Path.stat', side_effect=OSError("Permission denied")):
            result = compute_file_signature(Path("/bad/file.txt"))
            assert result.startswith("error:")


def test_check_dataset_files():
    """Test checking dataset files."""
    # Mock dataset record
    dataset = Mock()
    dataset.root = "/test/root"
    dataset.required_paths = ["/test/root/file1.txt", "/test/root/file2.txt"]
    
    # Mock Path operations
    with patch('pathlib.Path.exists') as mock_exists:
        mock_exists.return_value = True
        with patch('pathlib.Path.stat') as mock_stat:
            mock_stat.return_value = Mock(st_size=100, st_mtime=1234567890)
            with patch('FishBroWFS_V2.gui.services.reload_service.compute_file_signature') as mock_sig:
                mock_sig.return_value = "sha256:abc123"
                
                files, missing_count = check_dataset_files(dataset)
                
                assert len(files) == 3  # root + 2 required paths
                assert missing_count == 0
                assert all(f.exists for f in files)


def test_get_dataset_status():
    """Test getting dataset status."""
    # Mock dataset record
    dataset = Mock()
    dataset.id = "test_dataset"
    dataset.kind = "test_kind"
    dataset.root = "/test/root"
    
    # Mock check_dataset_files
    with patch('FishBroWFS_V2.gui.services.reload_service.check_dataset_files') as mock_check:
        mock_check.return_value = ([], 0)  # No files missing
        
        status = get_dataset_status(dataset)
        
        assert status.id == "test_dataset"
        assert status.kind == "test_kind"
        assert status.present is True
        assert status.missing_count == 0


def test_get_dataset_status_error():
    """Test getting dataset status with error."""
    dataset = Mock()
    dataset.id = "test_dataset"
    
    # Make check_dataset_files raise an exception
    with patch('FishBroWFS_V2.gui.services.reload_service.check_dataset_files', side_effect=Exception("Test error")):
        status = get_dataset_status(dataset)
        
        assert status.id == "test_dataset"
        assert status.error == "Test error"
        assert status.present is False


def test_get_strategy_status():
    """Test getting strategy status."""
    # Mock strategy spec
    strategy = Mock()
    strategy.strategy_id = "test_strategy"
    strategy.file_path = "/test/strategy.py"
    strategy.feature_requirements = []
    
    # Mock file operations
    with patch('pathlib.Path.exists', return_value=True):
        with patch('pathlib.Path.stat') as mock_stat:
            mock_stat.return_value = Mock(st_mtime=1234567890)
            with patch('FishBroWFS_V2.gui.services.reload_service.compute_file_signature') as mock_sig:
                mock_sig.return_value = "sha256:def456"
                
                status = get_strategy_status(strategy)
                
                assert status.id == "test_strategy"
                assert status.can_import is True
                assert status.can_build_spec is True
                assert status.signature == "sha256:def456"


def test_get_system_snapshot_with_mocks():
    """Test getting system snapshot with mocked registries."""
    # Mock dataset catalog
    mock_dataset = Mock()
    mock_dataset.id = "test_dataset"
    mock_dataset.kind = "test_kind"
    mock_dataset.root = "/test/root"
    
    # Mock strategy catalog
    mock_strategy = Mock()
    mock_strategy.strategy_id = "test_strategy"
    mock_strategy.file_path = "/test/strategy.py"
    mock_strategy.feature_requirements = []
    
    with patch('FishBroWFS_V2.gui.services.reload_service.get_dataset_catalog') as mock_get_ds_catalog:
        mock_catalog = Mock()
        mock_catalog.list_datasets.return_value = [mock_dataset]
        mock_get_ds_catalog.return_value = mock_catalog
        
        with patch('FishBroWFS_V2.gui.services.reload_service.get_strategy_catalog') as mock_get_st_catalog:
            mock_strategy_catalog = Mock()
            mock_strategy_catalog.list_strategies.return_value = [mock_strategy]
            mock_get_st_catalog.return_value = mock_strategy_catalog
            
            # Mock file operations
            with patch('pathlib.Path.exists', return_value=True):
                with patch('pathlib.Path.stat') as mock_stat:
                    mock_stat.return_value = Mock(st_size=100, st_mtime=1234567890)
                    with patch('FishBroWFS_V2.gui.services.reload_service.compute_file_signature') as mock_sig:
                        mock_sig.return_value = "sha256:abc123"
                        
                        snapshot = get_system_snapshot()
                        
                        assert isinstance(snapshot, SystemSnapshot)
                        assert snapshot.total_datasets == 1
                        assert snapshot.total_strategies == 1
                        assert len(snapshot.dataset_statuses) == 1
                        assert len(snapshot.strategy_statuses) == 1
                        assert snapshot.dataset_statuses[0].id == "test_dataset"
                        assert snapshot.strategy_statuses[0].id == "test_strategy"


def test_get_system_snapshot_error():
    """Test getting system snapshot when catalog fails."""
    with patch('FishBroWFS_V2.gui.services.reload_service.get_dataset_catalog', side_effect=Exception("Catalog error")):
        snapshot = get_system_snapshot()
        
        assert isinstance(snapshot, SystemSnapshot)
        assert len(snapshot.errors) > 0
        assert "Catalog error" in snapshot.errors[0]


def test_system_snapshot_dataclass():
    """Test SystemSnapshot dataclass."""
    snapshot = SystemSnapshot(
        created_at=datetime(2024, 1, 1, 12, 0, 0),
        total_datasets=5,
        total_strategies=3,
        dataset_statuses=[],
        strategy_statuses=[],
        notes=["Test note"],
        errors=[]
    )
    
    assert snapshot.total_datasets == 5
    assert snapshot.total_strategies == 3
    assert snapshot.notes == ["Test note"]


def test_dataset_status_dataclass():
    """Test DatasetStatus dataclass."""
    status = DatasetStatus(
        id="test_dataset",
        kind="test_kind",
        present=True,
        missing_count=0,
        bars_count=1000,
        schema_ok=True,
        error=None
    )
    
    assert status.id == "test_dataset"
    assert status.present is True
    assert status.schema_ok is True


def test_strategy_status_dataclass():
    """Test StrategyStatus dataclass."""
    status = StrategyStatus(
        id="test_strategy",
        can_import=True,
        can_build_spec=True,
        mtime=1234567890.0,
        signature="sha256:abc123",
        feature_requirements_count=5,
        error=None
    )
    
    assert status.id == "test_strategy"
    assert status.can_import is True
    assert status.feature_requirements_count == 5


def test_file_status_dataclass():
    """Test FileStatus dataclass."""
    status = FileStatus(
        path="/test/file.txt",
        exists=True,
        size=1024,
        mtime=1234567890.0,
        signature="sha256:abc123",
        error=None
    )
    
    assert status.path == "/test/file.txt"
    assert status.exists is True
    assert status.size == 1024