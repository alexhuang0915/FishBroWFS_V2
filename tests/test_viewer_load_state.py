"""Tests for Viewer load state computation.

Tests compute_load_state() mapping contract.
Uses try_read_artifact() to create SafeReadResult instances.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from FishBroWFS_V2.core.artifact_reader import SafeReadResult, try_read_artifact
from FishBroWFS_V2.core.artifact_status import ValidationResult, ArtifactStatus

from FishBroWFS_V2.gui.viewer.load_state import (
    ArtifactLoadStatus,
    ArtifactLoadState,
    compute_load_state,
)


def test_compute_load_state_ok() -> None:
    """Test OK status mapping."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "manifest.json"
        path.write_text(json.dumps({"run_id": "test"}), encoding="utf-8")
        
        read_result = try_read_artifact(path)
        assert isinstance(read_result, SafeReadResult)
        assert read_result.is_ok
        
        validation_result = ValidationResult(
            status=ArtifactStatus.OK,
            message="manifest.json 驗證通過",
        )
        
        state = compute_load_state("manifest", path, read_result, validation_result)
        
        assert state.status == ArtifactLoadStatus.OK
        assert state.artifact_name == "manifest"
        assert state.path == path
        assert state.error is None
        assert state.dirty_reasons == []
        assert state.last_modified_ts is not None


def test_compute_load_state_missing() -> None:
    """Test MISSING status mapping."""
    path = Path("/nonexistent/manifest.json")
    
    read_result = try_read_artifact(path)
    assert isinstance(read_result, SafeReadResult)
    assert read_result.is_error
    
    state = compute_load_state("manifest", path, read_result)
    
    assert state.status == ArtifactLoadStatus.MISSING
    assert state.artifact_name == "manifest"
    assert state.path == path
    assert state.error is None
    assert state.dirty_reasons == []
    assert state.last_modified_ts is None


def test_compute_load_state_invalid_from_read_error() -> None:
    """Test INVALID status from read error (non-FILE_NOT_FOUND)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "invalid.json"
        # Write invalid JSON
        path.write_text("{invalid json}", encoding="utf-8")
        
        read_result = try_read_artifact(path)
        assert isinstance(read_result, SafeReadResult)
        assert read_result.is_error
        
        state = compute_load_state("manifest", path, read_result)
        
        assert state.status == ArtifactLoadStatus.INVALID
        assert state.artifact_name == "manifest"
        assert state.path == path
        assert state.error is not None
        assert "JSON" in state.error or "decode" in state.error.lower()
        assert state.dirty_reasons == []
        assert state.last_modified_ts is None


def test_compute_load_state_invalid_from_validation() -> None:
    """Test INVALID status from validation result."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "manifest.json"
        path.write_text(json.dumps({"invalid": "data"}), encoding="utf-8")
        
        read_result = try_read_artifact(path)
        assert isinstance(read_result, SafeReadResult)
        assert read_result.is_ok
        
        validation_result = ValidationResult(
            status=ArtifactStatus.INVALID,
            message="manifest.json 缺少欄位: run_id",
            error_details="Field required: run_id",
        )
        
        state = compute_load_state("manifest", path, read_result, validation_result)
        
        assert state.status == ArtifactLoadStatus.INVALID
        assert state.artifact_name == "manifest"
        assert state.path == path
        assert state.error == "Field required: run_id"  # Prefers error_details
        assert state.dirty_reasons == []
        assert state.last_modified_ts is not None


def test_compute_load_state_dirty() -> None:
    """Test DIRTY status mapping."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "manifest.json"
        path.write_text(json.dumps({"run_id": "test", "config_hash": "abc123"}), encoding="utf-8")
        
        read_result = try_read_artifact(path)
        assert isinstance(read_result, SafeReadResult)
        assert read_result.is_ok
        
        validation_result = ValidationResult(
            status=ArtifactStatus.DIRTY,
            message="manifest.config_hash=abc123 但預期值為 def456",
        )
        
        state = compute_load_state("manifest", path, read_result, validation_result)
        
        assert state.status == ArtifactLoadStatus.DIRTY
        assert state.artifact_name == "manifest"
        assert state.path == path
        assert state.error is None
        assert state.dirty_reasons == ["manifest.config_hash=abc123 但預期值為 def456"]
        assert state.last_modified_ts is not None


def test_compute_load_state_dirty_empty_reasons() -> None:
    """Test DIRTY status with empty dirty_reasons."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "manifest.json"
        path.write_text(json.dumps({"run_id": "test"}), encoding="utf-8")
        
        read_result = try_read_artifact(path)
        assert isinstance(read_result, SafeReadResult)
        assert read_result.is_ok
        
        validation_result = ValidationResult(
            status=ArtifactStatus.DIRTY,
            message="",  # Empty message
        )
        
        state = compute_load_state("manifest", path, read_result, validation_result)
        
        assert state.status == ArtifactLoadStatus.DIRTY
        assert state.dirty_reasons == []  # Empty list when message is empty


def test_compute_load_state_no_validation_result() -> None:
    """Test compute_load_state without validation_result (assumes OK)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "manifest.json"
        path.write_text(json.dumps({"run_id": "test"}), encoding="utf-8")
        
        read_result = try_read_artifact(path)
        assert isinstance(read_result, SafeReadResult)
        assert read_result.is_ok
        
        state = compute_load_state("manifest", path, read_result)
        
        assert state.status == ArtifactLoadStatus.OK
        assert state.error is None
        assert state.dirty_reasons == []
        assert state.last_modified_ts is not None


def test_compute_load_state_never_raises() -> None:
    """Test that compute_load_state never raises exceptions."""
    path = Path("/test/manifest.json")
    
    # Test with empty SafeReadResult (both result and error are None)
    read_result = SafeReadResult()
    
    # Should not raise
    state = compute_load_state("manifest", path, read_result)
    
    # Should map to some status (likely INVALID)
    assert state.status in [
        ArtifactLoadStatus.OK,
        ArtifactLoadStatus.MISSING,
        ArtifactLoadStatus.INVALID,
        ArtifactLoadStatus.DIRTY,
    ]


def test_dirty_reasons_preserved() -> None:
    """Test that dirty_reasons are preserved in DIRTY state."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "winners_v2.json"
        path.write_text(json.dumps({"config_hash": "abc123"}), encoding="utf-8")
        
        read_result = try_read_artifact(path)
        assert isinstance(read_result, SafeReadResult)
        assert read_result.is_ok
        
        validation_result = ValidationResult(
            status=ArtifactStatus.DIRTY,
            message="winners_v2.config_hash=abc123 但 manifest.config_hash=def456",
        )
        
        state = compute_load_state("winners_v2", path, read_result, validation_result)
        
        assert state.status == ArtifactLoadStatus.DIRTY
        assert len(state.dirty_reasons) == 1
        assert "config_hash" in state.dirty_reasons[0]
        # Ensure dirty_reasons is not swallowed
        assert state.dirty_reasons[0] == "winners_v2.config_hash=abc123 但 manifest.config_hash=def456"
