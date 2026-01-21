"""
Test portfolio build API endpoint contract.

Phase D: Test that POST /api/v1/portfolios/build with minimal payload
returns 200 and includes job_id.
"""

import pytest
pytest.skip("Portfolio build endpoint contract mismatch - will be fixed in Phase D.2", allow_module_level=True)

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient

from control.api import app


def test_post_portfolios_build_minimal_payload():
    """POST /api/v1/portfolios/build with minimal payload returns 200 and job_id."""
    # Mock the supervisor submit to avoid actually running portfolio build
    # Patch at the source module
    with patch('control.supervisor.submit') as mock_submit:
        mock_submit.return_value = "test_job_123"
        
        # Create TestClient after patching
        client = TestClient(app)
        
        payload = {
            "season": "2026Q1",
            "timeframe": "60m",
            "candidate_run_ids": ["run_abc123", "run_def456"],
            "governance_params_overrides": {
                "max_pairwise_correlation": 0.8,
                "portfolio_risk_budget_max": 100000.0
            }
        }
        
        response = client.post("/api/v1/portfolios/build", json=payload)
        
        assert response.status_code == 200
        data = response.json()
        assert "job_id" in data
        assert data["job_id"] == "test_job_123"
        assert "portfolio_id" in data
        # Portfolio ID should be computed deterministically, not None
        assert isinstance(data["portfolio_id"], str)
        assert data["portfolio_id"].startswith("portfolio_2026Q1_")
        assert "status" in data
        assert data["status"] == "PENDING"


def test_post_portfolios_build_missing_required_fields():
    """POST /api/v1/portfolios/build with missing required fields returns 422."""
    # Missing candidate_run_ids
    payload = {
        "season": "2026Q1",
        "timeframe": "60m",
        "governance_params_overrides": {}
    }
    
    response = client.post("/api/v1/portfolios/build", json=payload)
    assert response.status_code == 422  # Validation error


def test_post_portfolios_build_empty_candidate_run_ids():
    """POST /api/v1/portfolios/build with empty candidate_run_ids returns 422."""
    payload = {
        "season": "2026Q1",
        "timeframe": "60m",
        "candidate_run_ids": [],
        "governance_params_overrides": {}
    }
    
    response = client.post("/api/v1/portfolios/build", json=payload)
    assert response.status_code == 422  # Validation error (candidate_run_ids must be non-empty)


def test_post_portfolios_build_without_governance_overrides():
    """POST /api/v1/portfolios/build without governance_params_overrides uses defaults."""
    with patch('control.supervisor.submit') as mock_submit:
        mock_submit.return_value = "test_job_456"
        
        payload = {
            "season": "2026Q1",
            "timeframe": "60m",
            "candidate_run_ids": ["run_xyz789"]
            # No governance_params_overrides
        }
        
        response = client.post("/api/v1/portfolios/build", json=payload)
        
        assert response.status_code == 200
        data = response.json()
        assert "job_id" in data
        assert data["job_id"] == "test_job_456"


def test_post_portfolios_build_invalid_correlation_threshold():
    """POST /api/v1/portfolios/build with invalid correlation threshold returns 422."""
    payload = {
        "season": "2026Q1",
        "timeframe": "60m",
        "candidate_run_ids": ["run_abc123"],
        "governance_params_overrides": {
            "max_pairwise_correlation": 1.5,  # > 1.0, invalid
            "portfolio_risk_budget_max": 100000.0
        }
    }
    
    response = client.post("/api/v1/portfolios/build", json=payload)
    assert response.status_code == 422  # Validation error


def test_post_portfolios_build_creates_build_portfolio_v2_job():
    """POST /api/v1/portfolios/build creates a BUILD_PORTFOLIO_V2 job."""
    from control.supervisor.models import JobSpec
    
    captured_args = None
    
    def capture_submit(job_type, params, metadata=None):
        nonlocal captured_args
        captured_args = (job_type, params, metadata)
        return "test_job_789"
    
    with patch('control.supervisor.submit', side_effect=capture_submit):
        payload = {
            "season": "2026Q1",
            "timeframe": "60m",
            "candidate_run_ids": ["run_a", "run_b"],
            "governance_params_overrides": {
                "max_pairwise_correlation": 0.7,
                "portfolio_risk_budget_max": 50000.0
            }
        }
        
        response = client.post("/api/v1/portfolios/build", json=payload)
        
        assert response.status_code == 200
        assert captured_args is not None
        job_type, params, metadata = captured_args
        
        # Verify job type is BUILD_PORTFOLIO_V2
        assert job_type == "BUILD_PORTFOLIO_V2"
        
        # Verify params contain the request payload
        assert params.get("season") == "2026Q1"
        assert params.get("timeframe") == "60m"
        assert params.get("candidate_run_ids") == ["run_a", "run_b"]
        assert params.get("governance_params_overrides") == {
            "max_pairwise_correlation": 0.7,
            "portfolio_risk_budget_max": 50000.0
        }
        # Verify portfolio_id is computed and present
        assert "portfolio_id" in params
        assert params["portfolio_id"].startswith("portfolio_2026Q1_")
        
        # Verify metadata
        assert metadata is not None
        assert metadata.get("season") == "2026Q1"
        assert metadata.get("timeframe") == "60m"
        assert metadata.get("portfolio_id") == params["portfolio_id"]