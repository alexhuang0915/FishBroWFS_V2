"""
Tests for Season SSOT API endpoints.
"""
import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from control.api import app
from contracts.season import (
    SeasonRecord,
    SeasonHardBoundary,
    SeasonState,
    SeasonCreateRequest,
    SeasonCreateResponse,
    SeasonListResponse,
    SeasonDetailResponse,
    SeasonAttachRequest,
    SeasonAttachResponse,
    SeasonFreezeResponse,
    SeasonArchiveResponse,
    BoundaryMismatchErrorPayload,
    BoundaryMismatchItem,
)


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def mock_seasons_repo():
    """Mock the seasons repository functions imported in api.py."""
    with patch('control.api.create_season', new_callable=Mock) as mock_create_season, \
         patch('control.api.list_seasons', new_callable=Mock) as mock_list_seasons, \
         patch('control.api.get_season', new_callable=Mock) as mock_get_season, \
         patch('control.api.freeze_season', new_callable=Mock) as mock_freeze_season, \
         patch('control.api.archive_season', new_callable=Mock) as mock_archive_season, \
         patch('control.api.attach_job_to_season', new_callable=Mock) as mock_attach_job_to_season, \
         patch('control.api.get_season_jobs', new_callable=Mock) as mock_get_season_jobs:
        
        yield {
            'create_season': mock_create_season,
            'list_seasons': mock_list_seasons,
            'get_season': mock_get_season,
            'freeze_season': mock_freeze_season,
            'archive_season': mock_archive_season,
            'attach_job_to_season': mock_attach_job_to_season,
            'get_season_jobs': mock_get_season_jobs,
        }


@pytest.fixture
def mock_boundary_validator():
    """Mock the boundary validator."""
    with patch('control.api.SeasonBoundaryValidator') as mock_validator_class:
        mock_validator = Mock()
        mock_validator_class.validate.return_value = (True, [])
        yield mock_validator_class


@pytest.fixture
def mock_job_boundary_reader():
    """Mock the job boundary reader."""
    with patch('control.api.extract_job_boundary') as mock_extract_job_boundary:
        yield mock_extract_job_boundary


@pytest.fixture
def mock_evidence_writer():
    """Mock the evidence writer."""
    with patch('control.api.write_attach_evidence') as mock_write_attach_evidence:
        yield mock_write_attach_evidence


def test_list_seasons_ssot_endpoint(client, mock_seasons_repo):
    """Test GET /api/v1/seasons/ssot endpoint."""
    # Mock seasons data
    mock_season = SeasonRecord(
        season_id="season_2026q1",
        label="2026Q1 Trading Season",
        note="First quarter trading season for 2026",
        state="DRAFT",
        hard_boundary=SeasonHardBoundary(
            universe_fingerprint="universe_fp_123",
            timeframes_fingerprint="timeframes_fp_456",
            dataset_snapshot_id="dataset_snap_789",
            engine_constitution_id="engine_constitution_abc"
        ),
        created_at="2026-01-01T00:00:00Z",
        created_by="api",
        updated_at="2026-01-01T00:00:00Z"
    )
    # Return the SeasonRecord object (not dictionary)
    mock_seasons_repo['list_seasons'].return_value = [mock_season]
    
    response = client.get("/api/v1/seasons/ssot")
    
    if response.status_code != 200:
        print(f"Response status: {response.status_code}")
        print(f"Response body: {response.text}")
    
    assert response.status_code == 200
    data = response.json()
    assert "seasons" in data
    assert len(data["seasons"]) == 1
    assert data["seasons"][0]["season_id"] == "season_2026q1"
    assert data["seasons"][0]["label"] == "2026Q1 Trading Season"
    assert data["seasons"][0]["state"] == "DRAFT"
    
    mock_seasons_repo['list_seasons'].assert_called_once()


def test_get_season_ssot_endpoint(client, mock_seasons_repo):
    """Test GET /api/v1/seasons/ssot/{season_id} endpoint."""
    mock_season = SeasonRecord(
        season_id="season_2026q1",
        label="2026Q1 Trading Season",
        note="First quarter trading season for 2026",
        state="DRAFT",
        hard_boundary=SeasonHardBoundary(
            universe_fingerprint="universe_fp_123",
            timeframes_fingerprint="timeframes_fp_456",
            dataset_snapshot_id="dataset_snap_789",
            engine_constitution_id="engine_constitution_abc"
        ),
        created_at="2026-01-01T00:00:00Z",
        created_by="api",
        updated_at="2026-01-01T00:00:00Z"
    )
    mock_seasons_repo['get_season'].return_value = (mock_season, [])
    
    response = client.get("/api/v1/seasons/ssot/season_2026q1")
    
    assert response.status_code == 200
    data = response.json()
    assert "season" in data
    assert data["season"]["season_id"] == "season_2026q1"
    assert data["season"]["label"] == "2026Q1 Trading Season"
    assert "job_ids" in data
    
    mock_seasons_repo['get_season'].assert_called_once_with("season_2026q1")


def test_get_season_ssot_endpoint_not_found(client, mock_seasons_repo):
    """Test GET /api/v1/seasons/ssot/{season_id} when season doesn't exist."""
    mock_seasons_repo['get_season'].return_value = (None, [])
    
    response = client.get("/api/v1/seasons/ssot/nonexistent")
    
    assert response.status_code == 404
    data = response.json()
    assert "detail" in data
    assert "Season nonexistent not found" in data["detail"]
    
    mock_seasons_repo['get_season'].assert_called_once_with("nonexistent")


def test_create_season_ssot_endpoint(client, mock_seasons_repo):
    """Test POST /api/v1/seasons/ssot/create endpoint."""
    # Mock the created season
    mock_season = SeasonRecord(
        season_id="season_2026q1",
        label="2026Q1 Trading Season",
        note="First quarter trading season for 2026",
        state="DRAFT",
        hard_boundary=SeasonHardBoundary(
            universe_fingerprint="universe_fp_123",
            timeframes_fingerprint="timeframes_fp_456",
            dataset_snapshot_id="dataset_snap_789",
            engine_constitution_id="engine_constitution_abc"
        ),
        created_at="2026-01-01T00:00:00Z",
        created_by="api",
        updated_at="2026-01-01T00:00:00Z"
    )
    mock_seasons_repo['create_season'].return_value = mock_season
    
    request_data = {
        "label": "2026Q1 Trading Season",
        "note": "First quarter trading season for 2026",
        "hard_boundary": {
            "universe_fingerprint": "universe_fp_123",
            "timeframes_fingerprint": "timeframes_fp_456",
            "dataset_snapshot_id": "dataset_snap_789",
            "engine_constitution_id": "engine_constitution_abc"
        }
    }
    
    response = client.post("/api/v1/seasons/ssot/create", json=request_data)
    
    assert response.status_code == 200
    data = response.json()
    assert "season" in data
    assert data["season"]["season_id"] == "season_2026q1"
    assert data["season"]["label"] == "2026Q1 Trading Season"
    
    # Verify the create_season was called with a SeasonCreateRequest and actor
    mock_seasons_repo['create_season'].assert_called_once()
    call_args = mock_seasons_repo['create_season'].call_args
    # The API passes a SeasonCreateRequest object (parsed from JSON) and actor="api" as keyword argument
    # Check that the first positional argument has the right attributes
    assert call_args[0][0].label == "2026Q1 Trading Season"
    assert call_args[0][0].note == "First quarter trading season for 2026"
    # Check keyword argument
    assert call_args.kwargs.get("actor") == "api"


def test_attach_job_to_season_ssot_endpoint(
    client,
    mock_seasons_repo,
    mock_boundary_validator,
    mock_job_boundary_reader,
    mock_evidence_writer
):
    """Test POST /api/v1/seasons/ssot/{season_id}/attach endpoint."""
    # Mock season
    mock_season = SeasonRecord(
        season_id="season_2026q1",
        label="2026Q1 Trading Season",
        note="First quarter trading season for 2026",
        state="OPEN",
        hard_boundary=SeasonHardBoundary(
            universe_fingerprint="universe_fp_123",
            timeframes_fingerprint="timeframes_fp_456",
            dataset_snapshot_id="dataset_snap_789",
            engine_constitution_id="engine_constitution_abc"
        ),
        created_at="2026-01-01T00:00:00Z",
        created_by="api",
        updated_at="2026-01-01T00:00:00Z"
    )
    mock_seasons_repo['get_season'].return_value = (mock_season, [])
    
    # Mock job boundary
    job_boundary = SeasonHardBoundary(
        universe_fingerprint="universe_fp_123",
        timeframes_fingerprint="timeframes_fp_456",
        dataset_snapshot_id="dataset_snap_789",
        engine_constitution_id="engine_constitution_abc"
    )
    mock_job_boundary_reader.return_value = job_boundary
    
    # Mock validation result
    mock_boundary_validator.validate.return_value = (True, [])
    
    # Mock attachment
    mock_seasons_repo['attach_job_to_season'].return_value = None  # Success
    
    request_data = {"job_id": "job_123", "actor": "ui"}
    
    response = client.post("/api/v1/seasons/ssot/season_2026q1/attach", json=request_data)
    
    if response.status_code != 200:
        print(f"Response status: {response.status_code}")
        print(f"Response body: {response.text}")
    
    assert response.status_code == 200
    data = response.json()
    assert data["season_id"] == "season_2026q1"
    assert data["job_id"] == "job_123"
    assert data["result"] == "ACCEPTED"
    
    # Verify calls
    mock_seasons_repo['get_season'].assert_called_once_with("season_2026q1")
    mock_job_boundary_reader.assert_called_once_with("job_123")
    mock_boundary_validator.validate.assert_called_once_with(mock_season, job_boundary)
    mock_seasons_repo['attach_job_to_season'].assert_called_once()
    mock_evidence_writer.assert_called_once()


def test_attach_job_to_season_ssot_endpoint_season_not_found(client, mock_seasons_repo):
    """Test POST /api/v1/seasons/ssot/{season_id}/attach when season doesn't exist."""
    mock_seasons_repo['get_season'].return_value = (None, [])
    
    request_data = {"job_id": "job_123", "actor": "ui"}
    
    response = client.post("/api/v1/seasons/ssot/nonexistent/attach", json=request_data)
    
    assert response.status_code == 404
    data = response.json()
    assert "detail" in data
    assert "Season nonexistent not found" in data["detail"]
    
    mock_seasons_repo['get_season'].assert_called_once_with("nonexistent")


def test_attach_job_to_season_ssot_endpoint_boundary_mismatch(
    client,
    mock_seasons_repo,
    mock_boundary_validator,
    mock_job_boundary_reader,
    mock_evidence_writer
):
    """Test POST /api/v1/seasons/ssot/{season_id}/attach when boundaries don't match."""
    # Mock season
    mock_season = SeasonRecord(
        season_id="season_2026q1",
        label="2026Q1 Trading Season",
        note="First quarter trading season for 2026",
        state="OPEN",
        hard_boundary=SeasonHardBoundary(
            universe_fingerprint="universe_fp_123",
            timeframes_fingerprint="timeframes_fp_456",
            dataset_snapshot_id="dataset_snap_789",
            engine_constitution_id="engine_constitution_abc"
        ),
        created_at="2026-01-01T00:00:00Z",
        created_by="api",
        updated_at="2026-01-01T00:00:00Z"
    )
    mock_seasons_repo['get_season'].return_value = (mock_season, [])
    
    # Mock job boundary with mismatch
    job_boundary = SeasonHardBoundary(
        universe_fingerprint="universe_fp_DIFFERENT",  # Mismatch
        timeframes_fingerprint="timeframes_fp_456",
        dataset_snapshot_id="dataset_snap_789",
        engine_constitution_id="engine_constitution_abc"
    )
    mock_job_boundary_reader.return_value = job_boundary
    
    # Mock validation result (rejected)
    mismatches = [
        BoundaryMismatchItem(
            field="universe_fingerprint",
            season_value="universe_fp_123",
            job_value="universe_fp_DIFFERENT"
        )
    ]
    mock_boundary_validator.validate.return_value = (False, mismatches)
    
    request_data = {"job_id": "job_123", "actor": "ui"}
    
    response = client.post("/api/v1/seasons/ssot/season_2026q1/attach", json=request_data)
    
    if response.status_code != 422:
        print(f"Response status: {response.status_code}")
        print(f"Response body: {response.text}")
    
    assert response.status_code == 422  # Unprocessable Entity
    data = response.json()
    assert "detail" in data
    detail_data = data["detail"]
    assert detail_data["error_type"] == "SeasonBoundaryMismatch"
    assert detail_data["season_id"] == "season_2026q1"
    assert detail_data["job_id"] == "job_123"
    assert len(detail_data["mismatches"]) == 1
    
    # Verify attachment was NOT called
    mock_seasons_repo['attach_job_to_season'].assert_not_called()
    
    # Verify evidence was written
    mock_evidence_writer.assert_called_once()


def test_freeze_season_ssot_endpoint(client, mock_seasons_repo):
    """Test POST /api/v1/seasons/ssot/{season_id}/freeze endpoint."""
    # Mock the frozen season
    mock_season = SeasonRecord(
        season_id="season_2026q1",
        label="2026Q1 Trading Season",
        note="First quarter trading season for 2026",
        state="FROZEN",
        hard_boundary=SeasonHardBoundary(
            universe_fingerprint="universe_fp_123",
            timeframes_fingerprint="timeframes_fp_456",
            dataset_snapshot_id="dataset_snap_789",
            engine_constitution_id="engine_constitution_abc"
        ),
        created_at="2026-01-01T00:00:00Z",
        created_by="api",
        updated_at="2026-01-02T00:00:00Z"
    )
    mock_seasons_repo['freeze_season'].return_value = mock_season
    
    response = client.post("/api/v1/seasons/ssot/season_2026q1/freeze")
    
    if response.status_code != 200:
        print(f"Response status: {response.status_code}")
        print(f"Response body: {response.text}")
    
    assert response.status_code == 200
    data = response.json()
    assert data["season_id"] == "season_2026q1"
    assert data["previous_state"] == "OPEN"
    assert data["new_state"] == "FROZEN"
    
    mock_seasons_repo['freeze_season'].assert_called_once_with("season_2026q1", actor="api")


def test_freeze_season_ssot_endpoint_not_found(client, mock_seasons_repo):
    """Test POST /api/v1/seasons/ssot/{season_id}/freeze when season doesn't exist."""
    mock_seasons_repo['freeze_season'].return_value = None
    
    response = client.post("/api/v1/seasons/ssot/nonexistent/freeze")
    
    assert response.status_code == 404
    data = response.json()
    assert "detail" in data
    assert "Season nonexistent not found" in data["detail"]
    
    mock_seasons_repo['freeze_season'].assert_called_once_with("nonexistent", actor="api")


def test_archive_season_ssot_endpoint(client, mock_seasons_repo):
    """Test POST /api/v1/seasons/ssot/{season_id}/archive endpoint."""
    # Mock the season before archiving (should be FROZEN)
    mock_season_before = SeasonRecord(
        season_id="season_2026q1",
        label="2026Q1 Trading Season",
        note="First quarter trading season for 2026",
        state="FROZEN",
        hard_boundary=SeasonHardBoundary(
            universe_fingerprint="universe_fp_123",
            timeframes_fingerprint="timeframes_fp_456",
            dataset_snapshot_id="dataset_snap_789",
            engine_constitution_id="engine_constitution_abc"
        ),
        created_at="2026-01-01T00:00:00Z",
        created_by="api",
        updated_at="2026-01-02T00:00:00Z"
    )
    
    # Mock the season after archiving (should be ARCHIVED)
    mock_season_after = SeasonRecord(
        season_id="season_2026q1",
        label="2026Q1 Trading Season",
        note="First quarter trading season for 2026",
        state="ARCHIVED",
        hard_boundary=SeasonHardBoundary(
            universe_fingerprint="universe_fp_123",
            timeframes_fingerprint="timeframes_fp_456",
            dataset_snapshot_id="dataset_snap_789",
            engine_constitution_id="engine_constitution_abc"
        ),
        created_at="2026-01-01T00:00:00Z",
        created_by="api",
        updated_at="2026-01-02T00:00:00Z"
    )
    
    # Set up mocks
    mock_seasons_repo['get_season'].return_value = (mock_season_before, [])
    mock_seasons_repo['archive_season'].return_value = mock_season_after
    
    response = client.post("/api/v1/seasons/ssot/season_2026q1/archive")
    
    if response.status_code != 200:
        print(f"Response status: {response.status_code}")
        print(f"Response body: {response.text}")
    
    assert response.status_code == 200
    data = response.json()
    assert data["season_id"] == "season_2026q1"
    assert data["previous_state"] == "FROZEN"
    assert data["new_state"] == "ARCHIVED"
    
    mock_seasons_repo['get_season'].assert_called_once_with("season_2026q1")
    mock_seasons_repo['archive_season'].assert_called_once_with("season_2026q1", actor="api")


def test_archive_season_ssot_endpoint_not_found(client, mock_seasons_repo):
    """Test POST /api/v1/seasons/ssot/{season_id}/archive when season doesn't exist."""
    mock_seasons_repo['get_season'].return_value = (None, [])
    
    response = client.post("/api/v1/seasons/ssot/nonexistent/archive")
    
    assert response.status_code == 404
    data = response.json()
    assert "detail" in data
    assert "Season nonexistent not found" in data["detail"]
    
    mock_seasons_repo['get_season'].assert_called_once_with("nonexistent")


def test_attach_job_to_season_ssot_endpoint_season_not_open(
    client,
    mock_seasons_repo,
    mock_boundary_validator,
    mock_job_boundary_reader,
    mock_evidence_writer
):
    """Test POST /api/v1/seasons/ssot/{season_id}/attach when season is not OPEN."""
    # Mock season in DRAFT state
    mock_season = SeasonRecord(
        season_id="season_2026q1",
        label="2026Q1 Trading Season",
        note="First quarter trading season for 2026",
        state="DRAFT",  # Not OPEN
        hard_boundary=SeasonHardBoundary(
            universe_fingerprint="universe_fp_123",
            timeframes_fingerprint="timeframes_fp_456",
            dataset_snapshot_id="dataset_snap_789",
            engine_constitution_id="engine_constitution_abc"
        ),
        created_at="2026-01-01T00:00:00Z",
        created_by="api",
        updated_at="2026-01-01T00:00:00Z"
    )
    mock_seasons_repo['get_season'].return_value = (mock_season, [])
    
    # Mock job boundary (won't be used due to early exit, but need to mock to avoid 500)
    job_boundary = SeasonHardBoundary(
        universe_fingerprint="universe_fp_123",
        timeframes_fingerprint="timeframes_fp_456",
        dataset_snapshot_id="dataset_snap_789",
        engine_constitution_id="engine_constitution_abc"
    )
    mock_job_boundary_reader.return_value = job_boundary
    
    request_data = {"job_id": "job_123", "actor": "ui"}
    
    response = client.post("/api/v1/seasons/ssot/season_2026q1/attach", json=request_data)
    
    if response.status_code != 403:
        print(f"Response status: {response.status_code}")
        print(f"Response body: {response.text}")
    
    assert response.status_code == 403
    data = response.json()
    assert "detail" in data
    assert "Cannot attach jobs to season in DRAFT state" in data["detail"]
    
    mock_seasons_repo['get_season'].assert_called_once_with("season_2026q1")
    # The boundary validator and evidence writer should NOT be called due to early exit
    mock_boundary_validator.validate.assert_not_called()
    mock_evidence_writer.assert_not_called()


def test_attach_job_to_season_ssot_endpoint_job_already_attached(
    client,
    mock_seasons_repo,
    mock_boundary_validator,
    mock_job_boundary_reader,
    mock_evidence_writer
):
    """Test POST /api/v1/seasons/ssot/{season_id}/attach when job is already attached."""
    # Mock season
    mock_season = SeasonRecord(
        season_id="season_2026q1",
        label="2026Q1 Trading Season",
        note="First quarter trading season for 2026",
        state="OPEN",
        hard_boundary=SeasonHardBoundary(
            universe_fingerprint="universe_fp_123",
            timeframes_fingerprint="timeframes_fp_456",
            dataset_snapshot_id="dataset_snap_789",
            engine_constitution_id="engine_constitution_abc"
        ),
        created_at="2026-01-01T00:00:00Z",
        created_by="api",
        updated_at="2026-01-01T00:00:00Z"
    )
    mock_seasons_repo['get_season'].return_value = (mock_season, [])
    
    # Mock job boundary
    job_boundary = SeasonHardBoundary(
        universe_fingerprint="universe_fp_123",
        timeframes_fingerprint="timeframes_fp_456",
        dataset_snapshot_id="dataset_snap_789",
        engine_constitution_id="engine_constitution_abc"
    )
    mock_job_boundary_reader.return_value = job_boundary
    
    # Mock validation result
    mock_boundary_validator.validate.return_value = (True, [])
    
    # Mock that attach_job_to_season raises ValueError for already attached
    mock_seasons_repo['attach_job_to_season'].side_effect = ValueError("Job already attached to season")
    
    request_data = {"job_id": "job_123", "actor": "ui"}
    
    response = client.post("/api/v1/seasons/ssot/season_2026q1/attach", json=request_data)
    
    # Should still return 200 because idempotent (already attached is OK)
    assert response.status_code == 200
    data = response.json()
    assert data["season_id"] == "season_2026q1"
    assert data["job_id"] == "job_123"
    assert data["result"] == "ACCEPTED"
    
    # Verify attachment was called
    mock_seasons_repo['attach_job_to_season'].assert_called_once()
    mock_evidence_writer.assert_called_once()