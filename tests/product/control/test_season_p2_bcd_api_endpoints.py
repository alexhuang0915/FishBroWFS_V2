"""
Tests for Season P2-B/C/D API endpoints.
- P2-B: Season Viewer / Analysis Aggregator
- P2-C: Admission Decisions
- P2-D: Export Portfolio Candidate Set
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
    SeasonAnalysisResponse,
    SeasonCandidate,
    CandidateIdentity,
    CandidateSource,
    SeasonAdmissionRequest,
    SeasonAdmissionResponse,
    SeasonExportCandidatesResponse,
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
def mock_season_analysis():
    """Mock the season analysis service."""
    with patch('control.api.analyze_season', new_callable=Mock) as mock_analyze_season:
        yield mock_analyze_season


@pytest.fixture
def mock_season_admission():
    """Mock the season admission service."""
    with patch('control.api.decide_season_admissions', new_callable=Mock) as mock_decide_season_admissions:
        yield mock_decide_season_admissions


@pytest.fixture
def mock_season_export():
    """Mock the season export service."""
    with patch('control.api.export_season_candidates', new_callable=Mock) as mock_export_season_candidates:
        yield mock_export_season_candidates


@pytest.fixture
def mock_evidence_writer():
    """Mock the evidence writer."""
    with patch('control.api.write_admission_evidence', new_callable=Mock) as mock_write_admission_evidence, \
         patch('control.api.write_export_evidence', new_callable=Mock) as mock_write_export_evidence:
        yield {
            'write_admission_evidence': mock_write_admission_evidence,
            'write_export_evidence': mock_write_export_evidence,
        }


def test_analyze_season_ssot_endpoint(client, mock_seasons_repo, mock_season_analysis):
    """Test POST /api/v1/seasons/ssot/{season_id}/analyze endpoint (P2-B)."""
    # Mock season in FROZEN state
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
    mock_seasons_repo['get_season'].return_value = (mock_season, ["job_1", "job_2"])
    
    # Mock analysis response
    mock_analysis_response = SeasonAnalysisResponse(
        season_id="season_2026q1",
        season_state="FROZEN",
        total_jobs=2,
        valid_candidates=5,
        skipped_jobs=[],
        candidates=[
            SeasonCandidate(
                identity=CandidateIdentity(
                    candidate_id="candidate_001",
                    display_name="Candidate 001",
                    rank=1
                ),
                strategy_id="sma_cross_v1",
                param_hash="hash_001",
                research_metrics={"score": 1.5, "sharpe": 2.0},
                source=CandidateSource(
                    job_id="job_1",
                    batch_id="batch_001",
                    artifact_type="winners.json",
                    extracted_at="2026-01-01T00:00:00Z"
                ),
                tags=["high_score"],
                metadata={"param1": "value1"}
            )
        ],
        generated_at="2026-01-01T00:00:00Z",
        deterministic_order="score desc, candidate_id asc"
    )
    mock_season_analysis.return_value = mock_analysis_response
    
    request_data = {
        "season_id": "season_2026q1",
        "actor": "test"
    }
    response = client.post("/api/v1/seasons/ssot/season_2026q1/analyze", json=request_data)
    
    if response.status_code != 200:
        print(f"Response status: {response.status_code}")
        print(f"Response body: {response.text}")
    
    assert response.status_code == 200
    data = response.json()
    assert data["season_id"] == "season_2026q1"
    assert data["season_state"] == "FROZEN"
    assert data["total_jobs"] == 2
    assert data["valid_candidates"] == 5
    assert len(data["candidates"]) == 1
    assert data["candidates"][0]["identity"]["candidate_id"] == "candidate_001"
    
    mock_seasons_repo['get_season'].assert_called_once_with("season_2026q1")
    # The API now passes SeasonAnalysisRequest object, not just season_id
    from contracts.season import SeasonAnalysisRequest
    mock_season_analysis.assert_called_once()
    # Check that it was called with season_id and SeasonAnalysisRequest
    call_args = mock_season_analysis.call_args
    assert call_args[0][0] == "season_2026q1"
    assert isinstance(call_args[0][1], SeasonAnalysisRequest)
    assert call_args[0][1].season_id == "season_2026q1"
    assert call_args[0][1].actor == "test"


def test_analyze_season_ssot_endpoint_season_not_found(client, mock_seasons_repo):
    """Test POST /api/v1/seasons/ssot/{season_id}/analyze when season doesn't exist."""
    mock_seasons_repo['get_season'].return_value = (None, [])
    
    request_data = {
        "season_id": "nonexistent",
        "actor": "test"
    }
    response = client.post("/api/v1/seasons/ssot/nonexistent/analyze", json=request_data)
    
    assert response.status_code == 404
    data = response.json()
    assert "detail" in data
    assert "Season nonexistent not found" in data["detail"]
    
    mock_seasons_repo['get_season'].assert_called_once_with("nonexistent")


def test_analyze_season_ssot_endpoint_wrong_state(client, mock_seasons_repo):
    """Test POST /api/v1/seasons/ssot/{season_id}/analyze when season is not FROZEN or DECIDING."""
    # Mock season in OPEN state (not allowed for analysis)
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
        updated_at="2026-01-02T00:00:00Z"
    )
    mock_seasons_repo['get_season'].return_value = (mock_season, [])
    
    request_data = {
        "season_id": "season_2026q1",
        "actor": "test"
    }
    response = client.post("/api/v1/seasons/ssot/season_2026q1/analyze", json=request_data)
    
    assert response.status_code == 403
    data = response.json()
    assert "detail" in data
    # The actual error message is different
    assert "Cannot analyze season in OPEN state (must be FROZEN)" in data["detail"]
    
    mock_seasons_repo['get_season'].assert_called_once_with("season_2026q1")


def test_admit_candidates_to_season_ssot_endpoint(client, mock_seasons_repo, mock_season_admission, mock_evidence_writer):
    """Test POST /api/v1/seasons/ssot/{season_id}/admit endpoint (P2-C)."""
    # Mock season in FROZEN state
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
    mock_seasons_repo['get_season'].return_value = (mock_season, [])
    
    # Mock admission response - using the actual SeasonAdmissionResponse model
    from contracts.season import AdmissionDecision, DecisionOutcome, AdmissionEvidence
    mock_admission_response = SeasonAdmissionResponse(
        season_id="season_2026q1",
        total_candidates=3,
        admitted_count=2,
        rejected_count=1,
        held_count=0,
        decisions=[
            AdmissionDecision(
                candidate_identity="candidate_001",
                outcome=DecisionOutcome.ADMIT,
                decision_reason="Score 1.5 >= minimum threshold 1.0",
                evidence=AdmissionEvidence(
                    evidence_id="admission_season_2026q1_candidate_001_2026-01-01T00:00:00Z",
                    generated_at="2026-01-01T00:00:00Z",
                    decision_outcome=DecisionOutcome.ADMIT,
                    decision_reason="Score 1.5 >= minimum threshold 1.0",
                    decision_criteria={"min_score": 1.0, "candidate_score": 1.5},
                    actor="test",
                    evidence_data={}
                ),
                decided_at="2026-01-01T00:00:00Z",
                decided_by="test"
            ),
            AdmissionDecision(
                candidate_identity="candidate_002",
                outcome=DecisionOutcome.ADMIT,
                decision_reason="Score 1.2 >= minimum threshold 1.0",
                evidence=AdmissionEvidence(
                    evidence_id="admission_season_2026q1_candidate_002_2026-01-01T00:00:00Z",
                    generated_at="2026-01-01T00:00:00Z",
                    decision_outcome=DecisionOutcome.ADMIT,
                    decision_reason="Score 1.2 >= minimum threshold 1.0",
                    decision_criteria={"min_score": 1.0, "candidate_score": 1.2},
                    actor="test",
                    evidence_data={}
                ),
                decided_at="2026-01-01T00:00:00Z",
                decided_by="test"
            ),
            AdmissionDecision(
                candidate_identity="candidate_003",
                outcome=DecisionOutcome.REJECT,
                decision_reason="Score 0.8 < minimum threshold 1.0",
                evidence=AdmissionEvidence(
                    evidence_id="admission_season_2026q1_candidate_003_2026-01-01T00:00:00Z",
                    generated_at="2026-01-01T00:00:00Z",
                    decision_outcome=DecisionOutcome.REJECT,
                    decision_reason="Score 0.8 < minimum threshold 1.0",
                    decision_criteria={"min_score": 1.0, "candidate_score": 0.8},
                    actor="test",
                    evidence_data={}
                ),
                decided_at="2026-01-01T00:00:00Z",
                decided_by="test"
            )
        ],
        generated_at="2026-01-01T00:00:00Z"
    )
    mock_season_admission.return_value = mock_admission_response
    
    request_data = {
        "season_id": "season_2026q1",
        "actor": "test",
        "candidate_refs": [
            {
                "season_id": "season_2026q1",
                "job_id": "job_1",
                "candidate_key": "candidate_001",
                "candidate_id": "candidate_001"
            },
            {
                "season_id": "season_2026q1",
                "job_id": "job_1",
                "candidate_key": "candidate_002",
                "candidate_id": "candidate_002"
            },
            {
                "season_id": "season_2026q1",
                "job_id": "job_1",
                "candidate_key": "candidate_003",
                "candidate_id": "candidate_003"
            }
        ]
    }
    
    response = client.post("/api/v1/seasons/ssot/season_2026q1/admit", json=request_data)
    
    if response.status_code != 200:
        print(f"Response status: {response.status_code}")
        print(f"Response body: {response.text}")
    
    assert response.status_code == 200
    data = response.json()
    assert data["season_id"] == "season_2026q1"
    assert data["total_candidates"] == 3
    assert data["admitted_count"] == 2
    assert data["rejected_count"] == 1
    assert data["held_count"] == 0
    assert len(data["decisions"]) == 3
    assert data["decisions"][0]["candidate_identity"] == "candidate_001"
    assert data["decisions"][0]["outcome"] == "ADMIT"
    assert data["decisions"][2]["outcome"] == "REJECT"
    
    mock_seasons_repo['get_season'].assert_called_once_with("season_2026q1")
    mock_season_admission.assert_called_once()
    mock_evidence_writer['write_admission_evidence'].assert_called_once()


def test_admit_candidates_to_season_ssot_endpoint_season_not_found(client, mock_seasons_repo):
    """Test POST /api/v1/seasons/ssot/{season_id}/admit when season doesn't exist."""
    mock_seasons_repo['get_season'].return_value = (None, [])
    
    request_data = {
        "season_id": "nonexistent",
        "actor": "test",
        "candidate_refs": [
            {
                "season_id": "nonexistent",
                "job_id": "job_1",
                "candidate_key": "candidate_001",
                "candidate_id": "candidate_001"
            }
        ]
    }
    
    response = client.post("/api/v1/seasons/ssot/nonexistent/admit", json=request_data)
    
    assert response.status_code == 404
    data = response.json()
    assert "detail" in data
    assert "Season nonexistent not found" in data["detail"]
    
    mock_seasons_repo['get_season'].assert_called_once_with("nonexistent")


def test_admit_candidates_to_season_ssot_endpoint_wrong_state(client, mock_seasons_repo):
    """Test POST /api/v1/seasons/ssot/{season_id}/admit when season is not FROZEN."""
    # Mock season in OPEN state (not allowed for admission)
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
        updated_at="2026-01-02T00:00:00Z"
    )
    mock_seasons_repo['get_season'].return_value = (mock_season, [])
    
    request_data = {
        "season_id": "season_2026q1",
        "actor": "test",
        "candidate_refs": [
            {
                "season_id": "season_2026q1",
                "job_id": "job_1",
                "candidate_key": "candidate_001",
                "candidate_id": "candidate_001"
            }
        ]
    }
    
    response = client.post("/api/v1/seasons/ssot/season_2026q1/admit", json=request_data)
    
    assert response.status_code == 403
    data = response.json()
    assert "detail" in data
    # The actual error message is different
    assert "Cannot make admission decisions for season in OPEN state (must be FROZEN)" in data["detail"]
    
    mock_seasons_repo['get_season'].assert_called_once_with("season_2026q1")


def test_admit_candidates_to_season_ssot_endpoint_invalid_decisions(client, mock_seasons_repo):
    """Test POST /api/v1/seasons/ssot/{season_id}/admit with invalid decisions."""
    # Mock season in FROZEN state
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
    mock_seasons_repo['get_season'].return_value = (mock_season, [])
    
    # Invalid request - missing required fields
    request_data = {
        "season_id": "season_2026q1",
        "actor": "test"
        # Missing candidate_refs field
    }
    
    response = client.post("/api/v1/seasons/ssot/season_2026q1/admit", json=request_data)
    
    assert response.status_code == 400  # The API returns 400 for validation errors
    data = response.json()
    assert "detail" in data
    
    mock_seasons_repo['get_season'].assert_called_once_with("season_2026q1")


def test_export_candidates_from_season_ssot_endpoint(client, mock_seasons_repo, mock_season_export, mock_evidence_writer):
    """Test POST /api/v1/seasons/ssot/{season_id}/export_candidates endpoint (P2-D)."""
    # Mock season in DECIDING state
    mock_season = SeasonRecord(
        season_id="season_2026q1",
        label="2026Q1 Trading Season",
        note="First quarter trading season for 2026",
        state="DECIDING",
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
    mock_seasons_repo['get_season'].return_value = (mock_season, [])
    
    # Mock export response
    mock_export_response = SeasonExportCandidatesResponse(
        season_id="season_2026q1",
        export_id="export_2026q1_001",
        candidate_count=5,
        artifact_path="/path/to/export/portfolio_candidates.json",
        generated_at="2026-01-01T00:00:00Z"
    )
    mock_season_export.return_value = mock_export_response
    
    request_data = {
        "season_id": "season_2026q1",
        "actor": "test"
    }
    response = client.post("/api/v1/seasons/ssot/season_2026q1/export_candidates", json=request_data)
    
    if response.status_code != 200:
        print(f"Response status: {response.status_code}")
        print(f"Response body: {response.text}")
    
    assert response.status_code == 200
    data = response.json()
    assert data["season_id"] == "season_2026q1"
    assert data["export_id"] == "export_2026q1_001"
    assert data["candidate_count"] == 5
    assert data["artifact_path"] == "/path/to/export/portfolio_candidates.json"
    
    mock_seasons_repo['get_season'].assert_called_once_with("season_2026q1")
    # The API now passes SeasonExportCandidatesRequest object, not just season_id
    from contracts.season import SeasonExportCandidatesRequest
    mock_season_export.assert_called_once()
    # Check that it was called with season_id and SeasonExportCandidatesRequest
    call_args = mock_season_export.call_args
    assert call_args[0][0] == "season_2026q1"
    assert isinstance(call_args[0][1], SeasonExportCandidatesRequest)
    assert call_args[0][1].season_id == "season_2026q1"
    assert call_args[0][1].actor == "test"
    mock_evidence_writer['write_export_evidence'].assert_called_once()


def test_export_candidates_from_season_ssot_endpoint_season_not_found(client, mock_seasons_repo):
    """Test POST /api/v1/seasons/ssot/{season_id}/export_candidates when season doesn't exist."""
    mock_seasons_repo['get_season'].return_value = (None, [])
    
    request_data = {
        "season_id": "nonexistent",
        "actor": "test"
    }
    response = client.post("/api/v1/seasons/ssot/nonexistent/export_candidates", json=request_data)
    
    assert response.status_code == 404
    data = response.json()
    assert "detail" in data
    assert "Season nonexistent not found" in data["detail"]
    
    mock_seasons_repo['get_season'].assert_called_once_with("nonexistent")


def test_export_candidates_from_season_ssot_endpoint_wrong_state(client, mock_seasons_repo):
    """Test POST /api/v1/seasons/ssot/{season_id}/export_candidates when season is not DECIDING."""
    # Mock season in FROZEN state (not allowed for export)
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
    mock_seasons_repo['get_season'].return_value = (mock_season, [])
    
    request_data = {
        "season_id": "season_2026q1",
        "actor": "test"
    }
    response = client.post("/api/v1/seasons/ssot/season_2026q1/export_candidates", json=request_data)
    
    assert response.status_code == 403
    data = response.json()
    assert "detail" in data
    # The actual error message is different
    assert "Cannot export candidates for season in FROZEN state (must be DECIDING)" in data["detail"]
    
    mock_seasons_repo['get_season'].assert_called_once_with("season_2026q1")


def test_analyze_season_ssot_endpoint_analysis_error(client, mock_seasons_repo, mock_season_analysis):
    """Test POST /api/v1/seasons/ssot/{season_id}/analyze when analysis service raises an error."""
    # Mock season in FROZEN state
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
    mock_seasons_repo['get_season'].return_value = (mock_season, [])
    
    # Mock analysis service raising an error
    mock_season_analysis.side_effect = ValueError("Analysis failed: no job artifacts found")
    
    request_data = {
        "season_id": "season_2026q1",
        "actor": "test"
    }
    response = client.post("/api/v1/seasons/ssot/season_2026q1/analyze", json=request_data)
    
    assert response.status_code == 400  # The API returns 400 for ValueError
    data = response.json()
    assert "detail" in data
    assert "Analysis failed" in data["detail"]
    
    mock_seasons_repo['get_season'].assert_called_once_with("season_2026q1")
    # The API now passes SeasonAnalysisRequest object, not just season_id
    from contracts.season import SeasonAnalysisRequest
    mock_season_analysis.assert_called_once()
    # Check that it was called with season_id and SeasonAnalysisRequest
    call_args = mock_season_analysis.call_args
    assert call_args[0][0] == "season_2026q1"
    assert isinstance(call_args[0][1], SeasonAnalysisRequest)
    assert call_args[0][1].season_id == "season_2026q1"
    assert call_args[0][1].actor == "test"


def test_admit_candidates_to_season_ssot_endpoint_admission_error(client, mock_seasons_repo, mock_season_admission):
    """Test POST /api/v1/seasons/ssot/{season_id}/admit when admission service raises an error."""
    # Mock season in FROZEN state
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
    mock_seasons_repo['get_season'].return_value = (mock_season, [])
    
    # Mock admission service raising an error
    mock_season_admission.side_effect = ValueError("Admission failed: invalid candidate")
    
    request_data = {
        "season_id": "season_2026q1",
        "actor": "test",
        "candidate_refs": [
            {
                "season_id": "season_2026q1",
                "job_id": "job_1",
                "candidate_key": "candidate_001",
                "candidate_id": "candidate_001"
            }
        ]
    }
    
    response = client.post("/api/v1/seasons/ssot/season_2026q1/admit", json=request_data)
    
    assert response.status_code == 400  # The API returns 400 for ValueError
    data = response.json()
    assert "detail" in data
    assert "Admission failed" in data["detail"]
    
    mock_seasons_repo['get_season'].assert_called_once_with("season_2026q1")
    mock_season_admission.assert_called_once()


def test_export_candidates_from_season_ssot_endpoint_export_error(client, mock_seasons_repo, mock_season_export):
    """Test POST /api/v1/seasons/ssot/{season_id}/export_candidates when export service raises an error."""
    # Mock season in DECIDING state
    mock_season = SeasonRecord(
        season_id="season_2026q1",
        label="2026Q1 Trading Season",
        note="First quarter trading season for 2026",
        state="DECIDING",
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
    mock_seasons_repo['get_season'].return_value = (mock_season, [])
    
    # Mock export service raising an error
    mock_season_export.side_effect = ValueError("Export failed: no candidates found")
    
    request_data = {
        "season_id": "season_2026q1",
        "actor": "test"
    }
    response = client.post("/api/v1/seasons/ssot/season_2026q1/export_candidates", json=request_data)
    
    assert response.status_code == 400  # The API returns 400 for ValueError
    data = response.json()
    assert "detail" in data
    assert "Export failed" in data["detail"]
    
    mock_seasons_repo['get_season'].assert_called_once_with("season_2026q1")
    # The API now passes SeasonExportCandidatesRequest object, not just season_id
    from contracts.season import SeasonExportCandidatesRequest
    mock_season_export.assert_called_once()
    # Check that it was called with season_id and SeasonExportCandidatesRequest
    call_args = mock_season_export.call_args
    assert call_args[0][0] == "season_2026q1"
    assert isinstance(call_args[0][1], SeasonExportCandidatesRequest)
    assert call_args[0][1].season_id == "season_2026q1"
    assert call_args[0][1].actor == "test"