"""
Unit tests for GET /api/v1/outputs/summary endpoint.
"""
import json
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.control.api import app


@pytest.fixture
def client():
    """Test client for FastAPI app."""
    return TestClient(app)


def test_outputs_summary_endpoint_exists(client):
    """Test that the endpoint exists and returns version 1.0."""
    response = client.get("/api/v1/outputs/summary")
    assert response.status_code == 200
    
    data = response.json()
    assert "version" in data
    assert data["version"] == "1.0"
    assert "generated_at" in data
    assert "jobs" in data
    assert "portfolios" in data
    assert "informational" in data


def test_outputs_summary_schema(client):
    """Test that the response schema matches the required structure."""
    response = client.get("/api/v1/outputs/summary")
    data = response.json()
    
    # Check top-level structure
    assert isinstance(data["version"], str)
    assert isinstance(data["generated_at"], str)
    assert isinstance(data["jobs"], dict)
    assert isinstance(data["portfolios"], dict)
    assert isinstance(data["informational"], dict)
    
    # Check jobs structure
    jobs = data["jobs"]
    assert "recent" in jobs
    assert "counts_by_status" in jobs
    assert isinstance(jobs["recent"], list)
    assert isinstance(jobs["counts_by_status"], dict)
    
    # Check portfolios structure
    portfolios = data["portfolios"]
    assert "recent" in portfolios
    assert isinstance(portfolios["recent"], list)
    
    # Check informational structure
    informational = data["informational"]
    assert "orphaned_artifact_dirs_count" in informational
    assert "notes" in informational
    assert isinstance(informational["orphaned_artifact_dirs_count"], int)
    assert isinstance(informational["notes"], list)


def test_outputs_summary_job_items(client):
    """Test that job items have expected fields."""
    response = client.get("/api/v1/outputs/summary")
    data = response.json()
    
    for job in data["jobs"]["recent"]:
        assert "job_id" in job
        assert "status" in job
        assert "strategy_name" in job
        assert "instrument" in job
        assert "timeframe" in job
        assert "season" in job
        assert "run_mode" in job
        assert "created_at" in job
        assert "finished_at" in job  # can be null
        assert "links" in job
        
        links = job["links"]
        assert "artifacts_url" in links
        assert "report_url" in links  # can be null
        
        # Check URLs are strings
        assert isinstance(links["artifacts_url"], str)
        if links["report_url"] is not None:
            assert isinstance(links["report_url"], str)


def test_outputs_summary_portfolio_items(client):
    """Test that portfolio items have expected fields."""
    response = client.get("/api/v1/outputs/summary")
    data = response.json()
    
    for portfolio in data["portfolios"]["recent"]:
        assert "portfolio_id" in portfolio
        assert "created_at" in portfolio
        assert "season" in portfolio
        assert "timeframe" in portfolio
        assert "admitted_count" in portfolio
        assert "rejected_count" in portfolio
        assert "links" in portfolio
        
        links = portfolio["links"]
        assert "artifacts_url" in links
        assert "report_url" in links  # can be null
        
        # Check counts are integers
        assert isinstance(portfolio["admitted_count"], int)
        assert isinstance(portfolio["rejected_count"], int)


def test_outputs_summary_json_serializable(client):
    """Test that the response is JSON serializable (no complex objects)."""
    response = client.get("/api/v1/outputs/summary")
    data = response.json()
    
    # This should not raise any exceptions
    json_str = json.dumps(data)
    assert isinstance(json_str, str)
    assert len(json_str) > 0


def test_outputs_summary_no_filesystem_paths(client):
    """Test that no filesystem paths are returned in the response."""
    response = client.get("/api/v1/outputs/summary")
    data = response.json()
    
    # Check that no field contains absolute paths or "outputs/" patterns
    def check_no_paths(obj, path=""):
        if isinstance(obj, dict):
            for key, value in obj.items():
                check_no_paths(value, f"{path}.{key}")
        elif isinstance(obj, list):
            for i, value in enumerate(obj):
                check_no_paths(value, f"{path}[{i}]")
        elif isinstance(obj, str):
            # Check for filesystem path patterns
            assert "\\" not in obj, f"Path found at {path}: {obj}"
            # Allow relative URLs like /api/v1/jobs/...
            if obj.startswith("/"):
                assert obj.startswith("/api/"), f"Non-API path at {path}: {obj}"
    
    check_no_paths(data)