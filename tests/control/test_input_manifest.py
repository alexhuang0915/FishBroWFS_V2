"""Tests for input manifest functionality."""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
from datetime import datetime

from FishBroWFS_V2.control.input_manifest import (
    FileManifest,
    DatasetManifest,
    InputManifest,
    create_file_manifest,
    create_dataset_manifest,
    create_input_manifest,
    write_input_manifest,
    read_input_manifest,
    verify_input_manifest
)


def test_file_manifest():
    """Test FileManifest dataclass."""
    manifest = FileManifest(
        path="/test/file.txt",
        exists=True,
        size_bytes=1000,
        mtime_utc="2024-01-01T00:00:00Z",
        signature="sha256:abc123",
        error=None
    )
    
    assert manifest.path == "/test/file.txt"
    assert manifest.exists is True
    assert manifest.size_bytes == 1000
    assert manifest.mtime_utc == "2024-01-01T00:00:00Z"
    assert manifest.signature == "sha256:abc123"
    assert manifest.error is None


def test_dataset_manifest():
    """Test DatasetManifest dataclass."""
    file_manifest = FileManifest(
        path="/test/file.txt",
        exists=True,
        size_bytes=1000
    )
    
    manifest = DatasetManifest(
        dataset_id="test_dataset",
        kind="test_kind",
        txt_root="/data/txt",
        txt_files=[file_manifest],
        txt_present=True,
        txt_total_size_bytes=1000,
        txt_signature_aggregate="txt_sig",
        parquet_root="/data/parquet",
        parquet_files=[file_manifest],
        parquet_present=True,
        parquet_total_size_bytes=5000,
        parquet_signature_aggregate="parquet_sig",
        up_to_date=True,
        bars_count=1000,
        schema_ok=True,
        error=None
    )
    
    assert manifest.dataset_id == "test_dataset"
    assert manifest.kind == "test_kind"
    assert manifest.txt_present is True
    assert manifest.parquet_present is True
    assert manifest.up_to_date is True
    assert manifest.bars_count == 1000
    assert manifest.schema_ok is True


def test_input_manifest():
    """Test InputManifest dataclass."""
    dataset_manifest = DatasetManifest(
        dataset_id="test_dataset",
        kind="test_kind",
        txt_root="/data/txt",
        parquet_root="/data/parquet"
    )
    
    manifest = InputManifest(
        created_at="2024-01-01T00:00:00Z",
        job_id="test_job",
        season="2024Q1",
        config_snapshot={"param": "value"},
        data1_manifest=dataset_manifest,
        data2_manifest=None,
        system_snapshot_summary={"total_datasets": 10},
        manifest_hash="abc123",
        previous_manifest_hash=None
    )
    
    assert manifest.job_id == "test_job"
    assert manifest.season == "2024Q1"
    assert manifest.config_snapshot == {"param": "value"}
    assert manifest.data1_manifest is not None
    assert manifest.data2_manifest is None
    assert manifest.system_snapshot_summary == {"total_datasets": 10}
    assert manifest.manifest_hash == "abc123"


def test_create_file_manifest_exists():
    """Test creating file manifest for existing file."""
    mock_path = Mock(spec=Path)
    mock_path.exists.return_value = True
    mock_path.stat.return_value = Mock(st_size=1000, st_mtime=1234567890)
    
    with patch('FishBroWFS_V2.control.input_manifest.compute_file_signature', return_value="sha256:abc123"):
        with patch('pathlib.Path', return_value=mock_path):
            manifest = create_file_manifest("/test/file.txt")
            
            assert manifest.path == "/test/file.txt"
            assert manifest.exists is True
            assert manifest.size_bytes == 1000
            assert manifest.signature == "sha256:abc123"


def test_create_file_manifest_missing():
    """Test creating file manifest for missing file."""
    mock_path = Mock(spec=Path)
    mock_path.exists.return_value = False
    
    with patch('pathlib.Path', return_value=mock_path):
        manifest = create_file_manifest("/test/file.txt")
        
        assert manifest.path == "/test/file.txt"
        assert manifest.exists is False
        assert "not found" in manifest.error.lower()


def test_create_dataset_manifest():
    """Test creating dataset manifest."""
    dataset_id = "test_dataset"
    
    mock_descriptor = Mock()
    mock_descriptor.dataset_id = dataset_id
    mock_descriptor.kind = "test_kind"
    mock_descriptor.txt_root = "/data/txt"
    mock_descriptor.txt_required_paths = ["/data/txt/file1.txt"]
    mock_descriptor.parquet_root = "/data/parquet"
    mock_descriptor.parquet_expected_paths = ["/data/parquet/file1.parquet"]
    
    with patch('FishBroWFS_V2.control.input_manifest.get_descriptor', return_value=mock_descriptor):
        with patch('FishBroWFS_V2.control.input_manifest.create_file_manifest') as mock_create_file:
            mock_file_manifest = FileManifest(
                path="/test/file.txt",
                exists=True,
                size_bytes=1000,
                signature="sha256:abc123"
            )
            mock_create_file.return_value = mock_file_manifest
            
            with patch('pandas.read_parquet') as mock_read_parquet:
                mock_df = Mock()
                mock_df.__len__.return_value = 1000
                mock_read_parquet.return_value = mock_df
                
                manifest = create_dataset_manifest(dataset_id)
                
                assert manifest.dataset_id == dataset_id
                assert manifest.kind == "test_kind"
                assert manifest.txt_present is True
                assert manifest.parquet_present is True
                assert len(manifest.txt_files) == 1
                assert len(manifest.parquet_files) == 1


def test_create_dataset_manifest_not_found():
    """Test creating dataset manifest for non-existent dataset."""
    dataset_id = "nonexistent"
    
    with patch('FishBroWFS_V2.control.input_manifest.get_descriptor', return_value=None):
        manifest = create_dataset_manifest(dataset_id)
        
        assert manifest.dataset_id == dataset_id
        assert manifest.kind == "unknown"
        assert manifest.error is not None
        assert "not found" in manifest.error.lower()


def test_create_input_manifest():
    """Test creating complete input manifest."""
    job_id = "test_job"
    season = "2024Q1"
    config_snapshot = {"param": "value"}
    data1_dataset_id = "dataset1"
    data2_dataset_id = "dataset2"
    
    with patch('FishBroWFS_V2.control.input_manifest.create_dataset_manifest') as mock_create_dataset:
        mock_dataset_manifest = DatasetManifest(
            dataset_id="test_dataset",
            kind="test_kind",
            txt_root="/data/txt",
            parquet_root="/data/parquet"
        )
        mock_create_dataset.return_value = mock_dataset_manifest
        
        with patch('FishBroWFS_V2.control.input_manifest.get_system_snapshot') as mock_get_snapshot:
            mock_snapshot = Mock()
            mock_snapshot.created_at = datetime(2024, 1, 1, 0, 0, 0)
            mock_snapshot.total_datasets = 10
            mock_snapshot.total_strategies = 5
            mock_snapshot.notes = ["Test note"]
            mock_snapshot.errors = []
            mock_get_snapshot.return_value = mock_snapshot
            
            manifest = create_input_manifest(
                job_id=job_id,
                season=season,
                config_snapshot=config_snapshot,
                data1_dataset_id=data1_dataset_id,
                data2_dataset_id=data2_dataset_id,
                previous_manifest_hash="prev_hash"
            )
            
            assert manifest.job_id == job_id
            assert manifest.season == season
            assert manifest.config_snapshot == config_snapshot
            assert manifest.data1_manifest is not None
            assert manifest.data2_manifest is not None
            assert manifest.previous_manifest_hash == "prev_hash"
            assert manifest.manifest_hash is not None


def test_write_and_read_input_manifest(tmp_path):
    """Test writing and reading input manifest."""
    # Create a test manifest
    dataset_manifest = DatasetManifest(
        dataset_id="test_dataset",
        kind="test_kind",
        txt_root="/data/txt",
        parquet_root="/data/parquet"
    )
    
    manifest = InputManifest(
        created_at="2024-01-01T00:00:00Z",
        job_id="test_job",
        season="2024Q1",
        config_snapshot={"param": "value"},
        data1_manifest=dataset_manifest,
        data2_manifest=None,
        system_snapshot_summary={"total_datasets": 10},
        manifest_hash="test_hash"
    )
    
    # Write manifest
    output_path = tmp_path / "manifest.json"
    success = write_input_manifest(manifest, output_path)
    
    assert success is True
    assert output_path.exists()
    
    # Read manifest back
    read_manifest = read_input_manifest(output_path)
    
    assert read_manifest is not None
    assert read_manifest.job_id == manifest.job_id
    assert read_manifest.season == manifest.season
    assert read_manifest.manifest_hash == manifest.manifest_hash


def test_verify_input_manifest_valid():
    """Test verifying a valid input manifest."""
    dataset_manifest = DatasetManifest(
        dataset_id="test_dataset",
        kind="test_kind",
        txt_root="/data/txt",
        txt_files=[],
        txt_present=True,
        parquet_root="/data/parquet",
        parquet_files=[],
        parquet_present=True,
        up_to_date=True
    )
    
    manifest = InputManifest(
        created_at=datetime.utcnow().isoformat() + "Z",
        job_id="test_job",
        season="2024Q1",
        config_snapshot={"param": "value"},
        data1_manifest=dataset_manifest,
        system_snapshot_summary={"total_datasets": 10},
        manifest_hash="abc123"
    )
    
    # Manually set hash for test
    import hashlib
    import json
    from dataclasses import asdict
    
    manifest_dict = asdict(manifest)
    manifest_dict.pop("manifest_hash", None)
    manifest_json = json.dumps(manifest_dict, sort_keys=True, separators=(',', ':'))
    computed_hash = hashlib.sha256(manifest_json.encode('utf-8')).hexdigest()[:32]
    manifest.manifest_hash = computed_hash
    
    results = verify_input_manifest(manifest)
    
    assert results["valid"] is True
    assert len(results["errors"]) == 0


def test_verify_input_manifest_invalid_hash():
    """Test verifying input manifest with invalid hash."""
    dataset_manifest = DatasetManifest(
        dataset_id="test_dataset",
        kind="test_kind",
        txt_root="/data/txt",
        parquet_root="/data/parquet"
    )
    
    manifest = InputManifest(
        created_at="2024-01-01T00:00:00Z",
        job_id="test_job",
        season="2024Q1",
        config_snapshot={"param": "value"},
        data1_manifest=dataset_manifest,
        system_snapshot_summary={"total_datasets": 10},
        manifest_hash="wrong_hash"  # Intentionally wrong
    )
    
    results = verify_input_manifest(manifest)
    
    assert results["valid"] is False
    assert len(results["errors"]) > 0
    assert "hash mismatch" in results["errors"][0].lower()


def test_verify_input_manifest_missing_data1():
    """Test verifying input manifest with missing DATA1."""
    manifest = InputManifest(
        created_at="2024-01-01T00:00:00Z",
        job_id="test_job",
        season="2024Q1",
        config_snapshot={"param": "value"},
        data1_manifest=None,  # Missing DATA1
        system_snapshot_summary={"total_datasets": 10},
        manifest_hash="abc123"
    )
    
    results = verify_input_manifest(manifest)
    
    assert results["valid"] is False
    assert len(results["errors"]) > 0
    assert "missing data1" in results["errors"][0].lower()


def test_verify_input_manifest_old_timestamp():
    """Test verifying input manifest with old timestamp."""
    dataset_manifest = DatasetManifest(
        dataset_id="test_dataset",
        kind="test_kind",
        txt_root="/data/txt",
        parquet_root="/data/parquet"
    )
    
    manifest = InputManifest(
        created_at="2020-01-01T00:00:00Z",  # Very old
        job_id="test_job",
        season="2024Q1",
        config_snapshot={"param": "value"},
        data1_manifest=dataset_manifest,
        system_snapshot_summary={"total_datasets": 10},
        manifest_hash="abc123"
    )
    
    results = verify_input_manifest(manifest)
    
    # Should have warning about age
    assert len(results["warnings"]) > 0
    assert "hours old" in results["warnings"][0].lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])