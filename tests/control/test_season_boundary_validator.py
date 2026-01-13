"""
Tests for Season SSOT boundary validator (Hard Reject).
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from control.season_boundary_validator import (
    SeasonBoundaryValidator,
    validate_and_attach_job,
)
from contracts.season import (
    SeasonRecord,
    SeasonHardBoundary,
    BoundaryMismatchItem,
)
from control.job_boundary_reader import JobBoundary
from control.seasons_repo import get_season
from control.job_boundary_reader import JobBoundaryExtractionError


def test_season_boundary_validator_validate_match():
    """Test validation passes when all boundaries match."""
    season = SeasonRecord(
        season_id="season_123",
        label="Test Season",
        note="Test note",
        state="OPEN",
        hard_boundary=SeasonHardBoundary(
            universe_fingerprint="universe_fp_123",
            timeframes_fingerprint="timeframes_fp_456",
            dataset_snapshot_id="dataset_snap_789",
            engine_constitution_id="engine_constitution_abc"
        ),
        created_at="2025-01-01T00:00:00Z",
        created_by="test_user",
        updated_at="2025-01-01T00:00:00Z",
    )
    
    job_boundary = JobBoundary(
        universe_fingerprint="universe_fp_123",
        timeframes_fingerprint="timeframes_fp_456",
        dataset_snapshot_id="dataset_snap_789",
        engine_constitution_id="engine_constitution_abc"
    )
    
    is_valid, mismatches = SeasonBoundaryValidator.validate(season, job_boundary)
    
    assert is_valid is True
    assert mismatches == []


def test_season_boundary_validator_validate_mismatch_universe():
    """Test validation fails when universe fingerprint doesn't match."""
    season = SeasonRecord(
        season_id="season_123",
        label="Test Season",
        note="Test note",
        state="OPEN",
        hard_boundary=SeasonHardBoundary(
            universe_fingerprint="universe_fp_123",
            timeframes_fingerprint="timeframes_fp_456",
            dataset_snapshot_id="dataset_snap_789",
            engine_constitution_id="engine_constitution_abc"
        ),
        created_at="2025-01-01T00:00:00Z",
        created_by="test_user",
        updated_at="2025-01-01T00:00:00Z",
    )
    
    job_boundary = JobBoundary(
        universe_fingerprint="universe_fp_DIFFERENT",
        timeframes_fingerprint="timeframes_fp_456",
        dataset_snapshot_id="dataset_snap_789",
        engine_constitution_id="engine_constitution_abc"
    )
    
    is_valid, mismatches = SeasonBoundaryValidator.validate(season, job_boundary)
    
    assert is_valid is False
    assert len(mismatches) == 1
    assert mismatches[0].field == "universe_fingerprint"
    assert mismatches[0].season_value == "universe_fp_123"
    assert mismatches[0].job_value == "universe_fp_DIFFERENT"


def test_season_boundary_validator_validate_mismatch_multiple():
    """Test validation fails when multiple boundaries don't match."""
    season = SeasonRecord(
        season_id="season_123",
        label="Test Season",
        note="Test note",
        state="OPEN",
        hard_boundary=SeasonHardBoundary(
            universe_fingerprint="universe_fp_123",
            timeframes_fingerprint="timeframes_fp_456",
            dataset_snapshot_id="dataset_snap_789",
            engine_constitution_id="engine_constitution_abc"
        ),
        created_at="2025-01-01T00:00:00Z",
        created_by="test_user",
        updated_at="2025-01-01T00:00:00Z",
    )
    
    job_boundary = JobBoundary(
        universe_fingerprint="universe_fp_DIFFERENT",
        timeframes_fingerprint="timeframes_fp_DIFFERENT",
        dataset_snapshot_id="dataset_snap_789",
        engine_constitution_id="engine_constitution_abc"
    )
    
    is_valid, mismatches = SeasonBoundaryValidator.validate(season, job_boundary)
    
    assert is_valid is False
    assert len(mismatches) == 2
    mismatch_fields = [m.field for m in mismatches]
    assert "universe_fingerprint" in mismatch_fields
    assert "timeframes_fingerprint" in mismatch_fields


def test_season_boundary_validator_validate_season_job():
    """Test validate_season_job method."""
    season_id = "season_123"
    job_id = "job_456"
    
    mock_season = SeasonRecord(
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
        created_at="2025-01-01T00:00:00Z",
        created_by="test_user",
        updated_at="2025-01-01T00:00:00Z",
    )
    
    mock_job_boundary = JobBoundary(
        universe_fingerprint="universe_fp_123",
        timeframes_fingerprint="timeframes_fp_456",
        dataset_snapshot_id="dataset_snap_789",
        engine_constitution_id="engine_constitution_abc"
    )
    
    with patch('control.season_boundary_validator.get_season') as mock_get_season:
        mock_get_season.return_value = (mock_season, [])
        
        with patch('control.season_boundary_validator.extract_job_boundary') as mock_extract:
            mock_extract.return_value = mock_job_boundary
            
            is_valid, mismatches, error_msg = SeasonBoundaryValidator.validate_season_job(
                season_id=season_id,
                job_id=job_id,
                outputs_root=None,
            )
            
            assert is_valid is True
            assert mismatches == []
            assert error_msg is None


def test_season_boundary_validator_validate_season_job_not_open():
    """Test validate_season_job when season is not OPEN."""
    season_id = "season_123"
    job_id = "job_456"
    
    mock_season = SeasonRecord(
        season_id=season_id,
        label="Test Season",
        note="Test note",
        state="FROZEN",  # Not OPEN
        hard_boundary=SeasonHardBoundary(
            universe_fingerprint="universe_fp_123",
            timeframes_fingerprint="timeframes_fp_456",
            dataset_snapshot_id="dataset_snap_789",
            engine_constitution_id="engine_constitution_abc"
        ),
        created_at="2025-01-01T00:00:00Z",
        created_by="test_user",
        updated_at="2025-01-01T00:00:00Z",
    )
    
    with patch('control.season_boundary_validator.get_season') as mock_get_season:
        mock_get_season.return_value = (mock_season, [])
        
        is_valid, mismatches, error_msg = SeasonBoundaryValidator.validate_season_job(
            season_id=season_id,
            job_id=job_id,
            outputs_root=None,
        )
        
        assert is_valid is False
        assert mismatches == []
        assert "must be OPEN" in error_msg


def test_season_boundary_validator_validate_season_job_extraction_error():
    """Test validate_season_job when job boundary extraction fails."""
    season_id = "season_123"
    job_id = "job_456"
    
    mock_season = SeasonRecord(
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
        created_at="2025-01-01T00:00:00Z",
        created_by="test_user",
        updated_at="2025-01-01T00:00:00Z",
    )
    
    with patch('control.season_boundary_validator.get_season') as mock_get_season:
        mock_get_season.return_value = (mock_season, [])
        
        with patch('control.season_boundary_validator.extract_job_boundary') as mock_extract:
            mock_extract.side_effect = JobBoundaryExtractionError("Failed to extract")
            
            is_valid, mismatches, error_msg = SeasonBoundaryValidator.validate_season_job(
                season_id=season_id,
                job_id=job_id,
                outputs_root=None,
            )
            
            assert is_valid is False
            assert mismatches == []
            assert "Failed to extract" in error_msg


def test_create_mismatch_payload():
    """Test create_mismatch_payload method."""
    season_id = "season_123"
    job_id = "job_456"
    
    mismatches = [
        BoundaryMismatchItem(
            field="universe_fingerprint",
            season_value="season_val",
            job_value="job_val",
        )
    ]
    
    payload = SeasonBoundaryValidator.create_mismatch_payload(
        season_id=season_id,
        job_id=job_id,
        mismatches=mismatches,
    )
    
    assert payload.season_id == season_id
    assert payload.job_id == job_id
    assert payload.mismatches == mismatches


def test_validate_and_attach_job():
    """Test validate_and_attach_job function."""
    season_id = "season_123"
    job_id = "job_456"
    actor = "test_user"
    
    with patch('control.season_boundary_validator.SeasonBoundaryValidator.validate_season_job') as mock_validate:
        mock_validate.return_value = (True, [], None)
        
        is_valid, mismatches, error_msg = validate_and_attach_job(
            season_id=season_id,
            job_id=job_id,
            actor=actor,
            outputs_root=None,
        )
        
        assert is_valid is True
        assert mismatches == []
        assert error_msg is None
        mock_validate.assert_called_once_with(
            season_id=season_id,
            job_id=job_id,
            outputs_root=None,
        )