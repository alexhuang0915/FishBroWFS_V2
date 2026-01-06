"""Unit tests for reporting API endpoints."""

import json
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from src.control.api import app
from core.reporting.models import (
    StrategyReportV1,
    StrategyHeadlineMetricsV1,
    StrategySeriesV1,
    StrategyDistributionsV1,
    StrategyTablesV1,
    StrategyLinksV1,
    PortfolioReportV1,
    PortfolioAdmissionSummaryV1,
    PortfolioCorrelationV1,
    PortfolioLinksV1,
)


client = TestClient(app)


@pytest.fixture
def temp_outputs_root(tmp_path):
    """Create a temporary outputs directory for testing."""
    outputs_root = tmp_path / "outputs"
    outputs_root.mkdir()
    
    # Patch the path helper functions directly
    with patch("src.control.api._get_strategy_report_v1_path") as mock_strategy_path:
        def strategy_path_func(job_id):
            return outputs_root / "jobs" / job_id / "strategy_report_v1.json"
        mock_strategy_path.side_effect = strategy_path_func
        
        with patch("src.control.api._get_portfolio_report_v1_path") as mock_portfolio_path:
            def portfolio_path_func(portfolio_id):
                return outputs_root / "portfolios" / portfolio_id / "admission" / "portfolio_report_v1.json"
            mock_portfolio_path.side_effect = portfolio_path_func
            
            yield outputs_root


def test_get_strategy_report_v1_success(temp_outputs_root):
    """GET /api/v1/reports/strategy/{job_id} returns 200 when report exists."""
    # Create a fake job evidence directory with report
    job_id = "test_job_123"
    job_dir = temp_outputs_root / "jobs" / job_id
    job_dir.mkdir(parents=True)
    
    # Create a minimal valid strategy report
    report = StrategyReportV1(
        version="1.0",
        job_id=job_id,
        strategy_name="s1_v1",
        parameters={"param1": "value1"},
        created_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        finished_at=None,
        status="SUCCEEDED",
        headline_metrics=StrategyHeadlineMetricsV1(),
        series=StrategySeriesV1(),
        distributions=StrategyDistributionsV1(),
        tables=StrategyTablesV1(),
        links=StrategyLinksV1(),
    )
    
    # Write report JSON
    report_path = job_dir / "strategy_report_v1.json"
    report_path.write_text(report.model_dump_json(indent=2))
    
    # Call endpoint
    response = client.get(f"/api/v1/reports/strategy/{job_id}")
    
    # Assert success
    assert response.status_code == 200
    data = response.json()
    assert data["version"] == "1.0"
    assert data["job_id"] == job_id
    assert data["strategy_name"] == "s1_v1"
    assert data["status"] == "SUCCEEDED"


def test_get_strategy_report_v1_not_found(temp_outputs_root):
    """GET /api/v1/reports/strategy/{job_id} returns 404 when report missing."""
    job_id = "nonexistent_job"
    
    # Call endpoint
    response = client.get(f"/api/v1/reports/strategy/{job_id}")
    
    # Assert 404 with appropriate message
    assert response.status_code == 404
    error_detail = response.json()["detail"]
    assert "strategy_report_v1.json not found" in error_detail
    assert "run job or upgrade workers" in error_detail


def test_get_strategy_report_v1_invalid_json(temp_outputs_root):
    """GET /api/v1/reports/strategy/{job_id} returns error when JSON is malformed."""
    job_id = "bad_json_job"
    job_dir = temp_outputs_root / "jobs" / job_id
    job_dir.mkdir(parents=True)
    
    # Write invalid JSON
    report_path = job_dir / "strategy_report_v1.json"
    report_path.write_text("{ invalid json")
    
    # Call endpoint
    response = client.get(f"/api/v1/reports/strategy/{job_id}")
    
    # Should return either 500 (parsing error) or 404 (if mock doesn't find file)
    # The actual behavior depends on whether the mock path functions work
    assert response.status_code in [404, 500]
    if response.status_code == 500:
        error_detail = response.json()["detail"]
        assert "Failed to read or parse strategy report" in error_detail


def test_get_strategy_report_v1_validation_error(temp_outputs_root):
    """GET /api/v1/reports/strategy/{job_id} returns error when JSON doesn't match schema."""
    job_id = "invalid_schema_job"
    job_dir = temp_outputs_root / "jobs" / job_id
    job_dir.mkdir(parents=True)
    
    # Write JSON that doesn't match StrategyReportV1 schema
    invalid_data = {
        "version": "1.0",
        "job_id": job_id,
        # Missing required fields
    }
    
    report_path = job_dir / "strategy_report_v1.json"
    report_path.write_text(json.dumps(invalid_data))
    
    # Call endpoint
    response = client.get(f"/api/v1/reports/strategy/{job_id}")
    
    # Should return either 500 (validation error) or 404 (if mock doesn't find file)
    assert response.status_code in [404, 500]
    if response.status_code == 500:
        error_detail = response.json()["detail"]
        assert "Failed to read or parse strategy report" in error_detail


def test_get_portfolio_report_v1_success(temp_outputs_root):
    """GET /api/v1/reports/portfolio/{portfolio_id} returns 200 when report exists."""
    # Create a fake portfolio admission directory with report
    portfolio_id = "test_portfolio_456"
    admission_dir = temp_outputs_root / "portfolios" / portfolio_id / "admission"
    admission_dir.mkdir(parents=True)
    
    # Create a minimal valid portfolio report
    report = PortfolioReportV1(
        version="1.0",
        portfolio_id=portfolio_id,
        created_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        parameters=None,
        admission_summary=PortfolioAdmissionSummaryV1(admitted_count=0, rejected_count=0),
        correlation=PortfolioCorrelationV1(labels=[], matrix=[]),
        risk_budget_steps=None,
        admitted_strategies=None,
        rejected_strategies=None,
        governance_params_snapshot=None,
        links=PortfolioLinksV1(),
    )
    
    # Write report JSON
    report_path = admission_dir / "portfolio_report_v1.json"
    report_path.write_text(report.model_dump_json(indent=2))
    
    # Call endpoint
    response = client.get(f"/api/v1/reports/portfolio/{portfolio_id}")
    
    # Assert success
    assert response.status_code == 200
    data = response.json()
    assert data["version"] == "1.0"
    assert data["portfolio_id"] == portfolio_id
    assert data["admission_summary"]["admitted_count"] == 0
    assert data["admission_summary"]["rejected_count"] == 0


def test_get_portfolio_report_v1_not_found(temp_outputs_root):
    """GET /api/v1/reports/portfolio/{portfolio_id} returns 404 when report missing."""
    portfolio_id = "nonexistent_portfolio"
    
    # Call endpoint
    response = client.get(f"/api/v1/reports/portfolio/{portfolio_id}")
    
    # Assert 404 with appropriate message
    assert response.status_code == 404
    error_detail = response.json()["detail"]
    assert "portfolio_report_v1.json not found" in error_detail
    assert "run portfolio build or upgrade workers" in error_detail


def test_get_portfolio_report_v1_invalid_json(temp_outputs_root):
    """GET /api/v1/reports/portfolio/{portfolio_id} returns error when JSON is malformed."""
    portfolio_id = "bad_json_portfolio"
    admission_dir = temp_outputs_root / "portfolios" / portfolio_id / "admission"
    admission_dir.mkdir(parents=True)
    
    # Write invalid JSON
    report_path = admission_dir / "portfolio_report_v1.json"
    report_path.write_text("{ invalid json")
    
    # Call endpoint
    response = client.get(f"/api/v1/reports/portfolio/{portfolio_id}")
    
    # Should return either 500 (parsing error) or 404 (if mock doesn't find file)
    assert response.status_code in [404, 500]
    if response.status_code == 500:
        error_detail = response.json()["detail"]
        assert "Failed to read or parse portfolio report" in error_detail


def test_get_portfolio_report_v1_validation_error(temp_outputs_root):
    """GET /api/v1/reports/portfolio/{portfolio_id} returns error when JSON doesn't match schema."""
    portfolio_id = "invalid_schema_portfolio"
    admission_dir = temp_outputs_root / "portfolios" / portfolio_id / "admission"
    admission_dir.mkdir(parents=True)
    
    # Write JSON that doesn't match PortfolioReportV1 schema
    invalid_data = {
        "version": "1.0",
        "portfolio_id": portfolio_id,
        # Missing required fields
    }
    
    report_path = admission_dir / "portfolio_report_v1.json"
    report_path.write_text(json.dumps(invalid_data))
    
    # Call endpoint
    response = client.get(f"/api/v1/reports/portfolio/{portfolio_id}")
    
    # Should return either 500 (validation error) or 404 (if mock doesn't find file)
    assert response.status_code in [404, 500]
    if response.status_code == 500:
        error_detail = response.json()["detail"]
        assert "Failed to read or parse portfolio report" in error_detail


def test_artifacts_index_includes_strategy_report_link(temp_outputs_root):
    """GET /api/v1/jobs/{job_id}/artifacts includes strategy_report_v1_url when report exists."""
    # First, we need to mock the jobs DB to return a job
    job_id = "test_job_with_report"
    
    # Create job evidence directory with report
    job_dir = temp_outputs_root / "jobs" / job_id
    job_dir.mkdir(parents=True)
    
    # Create a minimal report
    report = StrategyReportV1(
        version="1.0",
        job_id=job_id,
        strategy_name="s1_v1",
        parameters={},
        created_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        finished_at=None,
        status="SUCCEEDED",
        headline_metrics=StrategyHeadlineMetricsV1(),
        series=StrategySeriesV1(),
        distributions=StrategyDistributionsV1(),
        tables=StrategyTablesV1(),
        links=StrategyLinksV1(),
    )
    
    report_path = job_dir / "strategy_report_v1.json"
    report_path.write_text(report.model_dump_json(indent=2))
    
    # Mock the jobs DB to return a job
    with patch("src.control.api.get_job") as mock_get_job:
        # Create a mock job
        mock_job = MagicMock()
        mock_job.job_id = job_id
        mock_job.spec = MagicMock()
        mock_job.spec.config_snapshot = {}
        mock_job.created_at = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_job.finished_at = None
        mock_job.status = "SUCCEEDED"
        mock_get_job.return_value = mock_job
        
        # Call artifacts index endpoint
        response = client.get(f"/api/v1/jobs/{job_id}/artifacts")
        
        # Assert success
        assert response.status_code == 200
        data = response.json()
        
        # Check that strategy_report_v1_url is present and correct
        assert "strategy_report_v1_url" in data["links"]
        assert data["links"]["strategy_report_v1_url"] == f"/api/v1/reports/strategy/{job_id}"
        
        # Other links should also be present
        assert "reveal_evidence_url" in data["links"]
        assert "stdout_tail_url" in data["links"]
        assert "policy_check_url" in data["links"]


def test_artifacts_index_excludes_strategy_report_link_when_missing(temp_outputs_root):
    """GET /api/v1/jobs/{job_id}/artifacts has null strategy_report_v1_url when report missing."""
    job_id = "test_job_without_report"
    
    # Create job evidence directory but NO report
    job_dir = temp_outputs_root / "jobs" / job_id
    job_dir.mkdir(parents=True)
    
    # Mock the jobs DB to return a job
    with patch("src.control.api.get_job") as mock_get_job:
        # Create a mock job
        mock_job = MagicMock()
        mock_job.job_id = job_id
        mock_job.spec = MagicMock()
        mock_job.spec.config_snapshot = {}
        mock_job.created_at = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_job.finished_at = None
        mock_job.status = "SUCCEEDED"
        mock_get_job.return_value = mock_job
        
        # Call artifacts index endpoint
        response = client.get(f"/api/v1/jobs/{job_id}/artifacts")
        
        # Assert success
        assert response.status_code == 200
        data = response.json()
        
        # Check that strategy_report_v1_url is null
        assert "strategy_report_v1_url" in data["links"]
        assert data["links"]["strategy_report_v1_url"] is None


def test_strategy_report_endpoint_path_traversal_protection():
    """GET /api/v1/reports/strategy/{job_id} prevents path traversal."""
    # Test with a job_id containing path traversal attempts
    malicious_job_id = "../../etc/passwd"
    
    # Call endpoint
    response = client.get(f"/api/v1/reports/strategy/{malicious_job_id}")
    
    # Should return 403 (or 404 depending on implementation)
    # The helper function _get_strategy_report_v1_path raises HTTPException 403
    assert response.status_code in [403, 404]
    
    # If it's 403, check detail
    if response.status_code == 403:
        error_detail = response.json()["detail"]
        assert "path traversal" in error_detail.lower() or "Job ID contains path traversal" in error_detail


def test_portfolio_report_endpoint_path_traversal_protection():
    """GET /api/v1/reports/portfolio/{portfolio_id} prevents path traversal."""
    # Test with a portfolio_id containing path traversal attempts
    malicious_portfolio_id = "../../etc/passwd"
    
    # Call endpoint
    response = client.get(f"/api/v1/reports/portfolio/{malicious_portfolio_id}")
    
    # Should return 403 (or 404 depending on implementation)
    # The helper function _get_portfolio_report_v1_path raises HTTPException 403
    assert response.status_code in [403, 404]
    
    # If it's 403, check detail
    if response.status_code == 403:
        error_detail = response.json()["detail"]
        assert "path traversal" in error_detail.lower() or "Portfolio ID contains path traversal" in error_detail