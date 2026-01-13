"""
Tests for SeasonAttachEvidence writer.
"""
import pytest
import json
import tempfile
import os
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
from control.season_attach_evidence import write_attach_evidence
from contracts.season import (
    SeasonHardBoundary,
    BoundaryMismatchItem,
    SeasonRecord,
    SeasonAttachResponse,
)
from control.job_boundary_reader import JobBoundary


def test_write_season_attach_evidence_accepted(tmp_path):
    """Test writing evidence for accepted attach attempt."""
    season_id = "season_123"
    job_id = "job_456"
    season = SeasonRecord(
        season_id=season_id,
        label="Test Season",
        note="Test note",
        state="OPEN",
        hard_boundary=SeasonHardBoundary(
            universe_fingerprint="universe_fp_123",
            timeframes_fingerprint="timeframes_fp_456",
            dataset_snapshot_id="dataset_snap_789",
            engine_constitution_id="engine_constitution_abc"
        ),
        created_at="2026-01-01T00:00:00Z",
        created_by="test",
        updated_at="2026-01-01T00:00:00Z"
    )
    job_boundary = JobBoundary(
        universe_fingerprint="universe_fp_123",
        timeframes_fingerprint="timeframes_fp_456",
        dataset_snapshot_id="dataset_snap_789",
        engine_constitution_id="engine_constitution_abc"
    )
    attach_response = SeasonAttachResponse(
        season_id=season_id,
        job_id=job_id,
        result="ACCEPTED",
        mismatches=[]
    )
    
    # Create evidence directory
    evidence_dir = tmp_path / "_dp_evidence" / "phase_p2a_season_ssot_validator" / "attach_attempts"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    
    # Call the function
    evidence_path = write_attach_evidence(
        season=season,
        job_boundary=job_boundary,
        job_id=job_id,
        actor="test",
        is_accepted=True,
        attach_response=attach_response,
        outputs_root=tmp_path,
    )
    
    # Check that a file was created
    assert evidence_path.exists()
    
    # Read and verify content
    with open(evidence_path, 'r', encoding='utf-8') as f:
        evidence_data = json.load(f)
    
    assert evidence_data["season_id"] == season_id
    assert evidence_data["job_id"] == job_id
    assert evidence_data["result"] == "ACCEPTED"
    assert evidence_data["season_boundary"]["universe_fingerprint"] == "universe_fp_123"
    assert evidence_data["job_boundary"]["universe_fingerprint"] == "universe_fp_123"
    assert "timestamp" in evidence_data
    assert "evidence_id" in evidence_data


def test_write_season_attach_evidence_rejected(tmp_path):
    """Test writing evidence for rejected attach attempt."""
    season_id = "season_123"
    job_id = "job_456"
    season = SeasonRecord(
        season_id=season_id,
        label="Test Season",
        note="Test note",
        state="OPEN",
        hard_boundary=SeasonHardBoundary(
            universe_fingerprint="universe_fp_123",
            timeframes_fingerprint="timeframes_fp_456",
            dataset_snapshot_id="dataset_snap_789",
            engine_constitution_id="engine_constitution_abc"
        ),
        created_at="2026-01-01T00:00:00Z",
        created_by="test",
        updated_at="2026-01-01T00:00:00Z"
    )
    job_boundary = JobBoundary(
        universe_fingerprint="universe_fp_DIFFERENT",  # Mismatch
        timeframes_fingerprint="timeframes_fp_456",
        dataset_snapshot_id="dataset_snap_789",
        engine_constitution_id="engine_constitution_abc"
    )
    
    mismatches = [
        BoundaryMismatchItem(
            field="universe_fingerprint",
            season_value="universe_fp_123",
            job_value="universe_fp_DIFFERENT",
        )
    ]
    
    # Create evidence directory
    evidence_dir = tmp_path / "_dp_evidence" / "phase_p2a_season_ssot_validator" / "attach_attempts"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    
    # Call the function
    evidence_path = write_attach_evidence(
        season=season,
        job_boundary=job_boundary,
        job_id=job_id,
        actor="test",
        is_accepted=False,
        mismatches=mismatches,
        outputs_root=tmp_path,
    )
    
    # Check that a file was created
    assert evidence_path.exists()
    
    # Read and verify content
    with open(evidence_path, 'r', encoding='utf-8') as f:
        evidence_data = json.load(f)
    
    assert evidence_data["season_id"] == season_id
    assert evidence_data["job_id"] == job_id
    assert evidence_data["result"] == "REJECTED"
    assert "mismatches" in evidence_data
    assert len(evidence_data["mismatches"]) == 1
    assert evidence_data["mismatches"][0]["field"] == "universe_fingerprint"


def test_write_season_attach_evidence_creates_directory(tmp_path):
    """Test that evidence writer creates directory if it doesn't exist."""
    season_id = "season_123"
    job_id = "job_456"
    season = SeasonRecord(
        season_id=season_id,
        label="Test Season",
        note="Test note",
        state="OPEN",
        hard_boundary=SeasonHardBoundary(
            universe_fingerprint="ufp",
            timeframes_fingerprint="tfp",
            dataset_snapshot_id="dsid",
            engine_constitution_id="ecid"
        ),
        created_at="2026-01-01T00:00:00Z",
        created_by="test",
        updated_at="2026-01-01T00:00:00Z"
    )
    job_boundary = JobBoundary(
        universe_fingerprint="ufp",
        timeframes_fingerprint="tfp",
        dataset_snapshot_id="dsid",
        engine_constitution_id="ecid"
    )
    attach_response = SeasonAttachResponse(
        season_id=season_id,
        job_id=job_id,
        result="ACCEPTED",
        mismatches=[]
    )
    
    # Directory doesn't exist yet
    evidence_dir = tmp_path / "_dp_evidence" / "phase_p2a_season_ssot_validator" / "attach_attempts"
    
    # Call the function
    evidence_path = write_attach_evidence(
        season=season,
        job_boundary=job_boundary,
        job_id=job_id,
        actor="test",
        is_accepted=True,
        attach_response=attach_response,
        outputs_root=tmp_path,
    )
    
    # Directory should have been created
    assert evidence_dir.exists()
    assert evidence_dir.is_dir()
    
    # File should exist
    assert evidence_path.exists()


def test_write_season_attach_evidence_json_serialization(tmp_path):
    """Test that complex objects are properly JSON serialized."""
    season_id = "season_123"
    job_id = "job_456"
    season = SeasonRecord(
        season_id=season_id,
        label="Test Season",
        note="Test note",
        state="OPEN",
        hard_boundary=SeasonHardBoundary(
            universe_fingerprint="universe_fp_123",
            timeframes_fingerprint="timeframes_fp_456",
            dataset_snapshot_id="dataset_snap_789",
            engine_constitution_id="engine_constitution_abc"
        ),
        created_at="2026-01-01T00:00:00Z",
        created_by="test",
        updated_at="2026-01-01T00:00:00Z"
    )
    job_boundary = JobBoundary(
        universe_fingerprint="universe_fp_123",
        timeframes_fingerprint="timeframes_fp_456",
        dataset_snapshot_id="dataset_snap_789",
        engine_constitution_id="engine_constitution_abc"
    )
    attach_response = SeasonAttachResponse(
        season_id=season_id,
        job_id=job_id,
        result="ACCEPTED",
        mismatches=[]
    )
    
    # Create evidence directory
    evidence_dir = tmp_path / "_dp_evidence" / "phase_p2a_season_ssot_validator" / "attach_attempts"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    
    # This should not raise JSON serialization errors
    evidence_path = write_attach_evidence(
        season=season,
        job_boundary=job_boundary,
        job_id=job_id,
        actor="test",
        is_accepted=True,
        attach_response=attach_response,
        outputs_root=tmp_path,
    )
    
    # Verify file can be read back
    with open(evidence_path, 'r', encoding='utf-8') as f:
        evidence_data = json.load(f)
    
    # Check that Pydantic models were converted to dict
    assert isinstance(evidence_data["season_boundary"], dict)
    assert isinstance(evidence_data["job_boundary"], dict)


def test_write_season_attach_evidence_with_multiple_mismatches(tmp_path):
    """Test writing evidence with multiple mismatch details."""
    season_id = "season_123"
    job_id = "job_456"
    season = SeasonRecord(
        season_id=season_id,
        label="Test Season",
        note="Test note",
        state="OPEN",
        hard_boundary=SeasonHardBoundary(
            universe_fingerprint="universe_fp_123",
            timeframes_fingerprint="timeframes_fp_456",
            dataset_snapshot_id="dataset_snap_789",
            engine_constitution_id="engine_constitution_abc"
        ),
        created_at="2026-01-01T00:00:00Z",
        created_by="test",
        updated_at="2026-01-01T00:00:00Z"
    )
    job_boundary = JobBoundary(
        universe_fingerprint="universe_fp_DIFFERENT",
        timeframes_fingerprint="timeframes_fp_DIFFERENT_TOO",
        dataset_snapshot_id="dataset_snap_789",
        engine_constitution_id="engine_constitution_abc"
    )
    
    mismatches = [
        BoundaryMismatchItem(
            field="universe_fingerprint",
            season_value="universe_fp_123",
            job_value="universe_fp_DIFFERENT",
        ),
        BoundaryMismatchItem(
            field="timeframes_fingerprint",
            season_value="timeframes_fp_456",
            job_value="timeframes_fp_DIFFERENT_TOO",
        )
    ]
    
    # Create evidence directory
    evidence_dir = tmp_path / "_dp_evidence" / "phase_p2a_season_ssot_validator" / "attach_attempts"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    
    evidence_path = write_attach_evidence(
        season=season,
        job_boundary=job_boundary,
        job_id=job_id,
        actor="test",
        is_accepted=False,
        mismatches=mismatches,
        outputs_root=tmp_path,
    )
    
    # Read and verify content
    with open(evidence_path, 'r', encoding='utf-8') as f:
        evidence_data = json.load(f)
    
    assert evidence_data["result"] == "REJECTED"
    assert "mismatches" in evidence_data
    assert len(evidence_data["mismatches"]) == 2
    mismatch_fields = [m["field"] for m in evidence_data["mismatches"]]
    assert "universe_fingerprint" in mismatch_fields
    assert "timeframes_fingerprint" in mismatch_fields