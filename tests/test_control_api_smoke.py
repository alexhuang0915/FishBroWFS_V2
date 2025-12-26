
"""Smoke tests for API endpoints."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from FishBroWFS_V2.control.api import app, get_db_path
from FishBroWFS_V2.control.jobs_db import init_db


@pytest.fixture
def test_client() -> TestClient:
    """Create test client with temporary database."""
    import os
    
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        init_db(db_path)
        
        # Override DB path
        os.environ["JOBS_DB_PATH"] = str(db_path)
        # Allow worker spawn in tests and allow /tmp DB paths
        os.environ["FISHBRO_ALLOW_SPAWN_IN_TESTS"] = "1"
        os.environ["FISHBRO_ALLOW_TMP_DB"] = "1"
        
        # Re-import to get new DB path
        from FishBroWFS_V2.control import api
        
        # Reinitialize
        api.init_db(db_path)
        
        yield TestClient(app)


def test_health_endpoint(test_client: TestClient) -> None:
    """Test health endpoint."""
    resp = test_client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_create_job_endpoint(test_client: TestClient) -> None:
    """Test creating a job."""
    req = {
        "season": "test_season",
        "dataset_id": "test_dataset",
        "outputs_root": "outputs",
        "config_snapshot": {"bars": 1000, "params_total": 100},
        "config_hash": "abc123",
        "created_by": "b5c",
    }
    
    resp = test_client.post("/jobs", json=req)
    assert resp.status_code == 200
    data = resp.json()
    assert "job_id" in data
    assert isinstance(data["job_id"], str)


def test_list_jobs_endpoint(test_client: TestClient) -> None:
    """Test listing jobs."""
    # Create a job first
    req = {
        "season": "test",
        "dataset_id": "test",
        "outputs_root": "outputs",
        "config_snapshot": {},
        "config_hash": "hash1",
    }
    test_client.post("/jobs", json=req)
    
    # List jobs
    resp = test_client.get("/jobs")
    assert resp.status_code == 200
    jobs = resp.json()
    assert isinstance(jobs, list)
    assert len(jobs) > 0
    # Check that all jobs have report_link field
    for job in jobs:
        assert "report_link" in job


def test_get_job_endpoint(test_client: TestClient) -> None:
    """Test getting a job by ID."""
    # Create a job
    req = {
        "season": "test",
        "dataset_id": "test",
        "outputs_root": "outputs",
        "config_snapshot": {},
        "config_hash": "hash1",
    }
    create_resp = test_client.post("/jobs", json=req)
    job_id = create_resp.json()["job_id"]
    
    # Get job
    resp = test_client.get(f"/jobs/{job_id}")
    assert resp.status_code == 200
    job = resp.json()
    assert job["job_id"] == job_id
    assert job["status"] == "QUEUED"
    assert "report_link" in job
    assert job["report_link"] is None  # Default is None


def test_check_endpoint(test_client: TestClient) -> None:
    """Test check endpoint."""
    # Create a job
    req = {
        "season": "test",
        "dataset_id": "test",
        "outputs_root": "outputs",
        "config_snapshot": {
            "bars": 1000,
            "params_total": 100,
            "param_subsample_rate": 0.1,
            "mem_limit_mb": 6000.0,
        },
        "config_hash": "hash1",
    }
    create_resp = test_client.post("/jobs", json=req)
    job_id = create_resp.json()["job_id"]
    
    # Check
    resp = test_client.post(f"/jobs/{job_id}/check")
    assert resp.status_code == 200
    result = resp.json()
    assert "action" in result
    assert "estimated_mb" in result
    assert "estimates" in result


def test_pause_endpoint(test_client: TestClient) -> None:
    """Test pause endpoint."""
    # Create a job
    req = {
        "season": "test",
        "dataset_id": "test",
        "outputs_root": "outputs",
        "config_snapshot": {},
        "config_hash": "hash1",
    }
    create_resp = test_client.post("/jobs", json=req)
    job_id = create_resp.json()["job_id"]
    
    # Pause
    resp = test_client.post(f"/jobs/{job_id}/pause", json={"pause": True})
    assert resp.status_code == 200
    
    # Unpause
    resp = test_client.post(f"/jobs/{job_id}/pause", json={"pause": False})
    assert resp.status_code == 200


def test_stop_endpoint(test_client: TestClient) -> None:
    """Test stop endpoint."""
    # Create a job
    req = {
        "season": "test",
        "dataset_id": "test",
        "outputs_root": "outputs",
        "config_snapshot": {},
        "config_hash": "hash1",
    }
    create_resp = test_client.post("/jobs", json=req)
    job_id = create_resp.json()["job_id"]
    
    # Stop (soft)
    resp = test_client.post(f"/jobs/{job_id}/stop", json={"mode": "SOFT"})
    assert resp.status_code == 200
    
    # Stop (kill)
    req2 = {
        "season": "test2",
        "dataset_id": "test2",
        "outputs_root": "outputs",
        "config_snapshot": {},
        "config_hash": "hash2",
    }
    create_resp2 = test_client.post("/jobs", json=req2)
    job_id2 = create_resp2.json()["job_id"]
    
    resp = test_client.post(f"/jobs/{job_id2}/stop", json={"mode": "KILL"})
    assert resp.status_code == 200


def test_log_tail_endpoint(test_client: TestClient) -> None:
    """Test log_tail endpoint."""
    import os
    
    # Create a job
    req = {
        "season": "test_season",
        "dataset_id": "test_dataset",
        "outputs_root": str(Path.cwd() / "outputs"),
        "config_snapshot": {},
        "config_hash": "hash1",
    }
    create_resp = test_client.post("/jobs", json=req)
    job_id = create_resp.json()["job_id"]
    
    # Create log file manually
    from FishBroWFS_V2.control.paths import run_log_path
    
    outputs_root = Path.cwd() / "outputs"
    log_path = run_log_path(outputs_root, "test_season", job_id)
    log_path.write_text("Line 1\nLine 2\nLine 3\n", encoding="utf-8")
    
    # Get log tail
    resp = test_client.get(f"/jobs/{job_id}/log_tail?n=200")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert isinstance(data["lines"], list)
    assert len(data["lines"]) == 3
    assert "Line 1" in data["lines"][0]
    
    # Cleanup
    log_path.unlink(missing_ok=True)


def test_log_tail_missing_file(test_client: TestClient) -> None:
    """Test log_tail endpoint when log file doesn't exist."""
    # Create a job
    req = {
        "season": "test_season",
        "dataset_id": "test_dataset",
        "outputs_root": str(Path.cwd() / "outputs"),
        "config_snapshot": {},
        "config_hash": "hash1",
    }
    create_resp = test_client.post("/jobs", json=req)
    job_id = create_resp.json()["job_id"]
    
    # Get log tail (file doesn't exist)
    resp = test_client.get(f"/jobs/{job_id}/log_tail?n=200")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["lines"] == []
    assert data["truncated"] is False


def test_report_link_endpoint(test_client: TestClient) -> None:
    """Test report_link endpoint."""
    from FishBroWFS_V2.control.jobs_db import set_report_link
    
    # Create a job
    req = {
        "season": "test",
        "dataset_id": "test",
        "outputs_root": "outputs",
        "config_snapshot": {},
        "config_hash": "hash1",
    }
    create_resp = test_client.post("/jobs", json=req)
    job_id = create_resp.json()["job_id"]
    
    # Set report_link manually
    import os
    db_path = Path(os.environ["JOBS_DB_PATH"])
    set_report_link(db_path, job_id, "/b5?season=test&run_id=abc123")
    
    # Get report_link
    resp = test_client.get(f"/jobs/{job_id}/report_link")
    assert resp.status_code == 200
    data = resp.json()
    # build_report_link always returns a string (never None)
    assert data["report_link"] == "/b5?season=test&run_id=abc123"


def test_report_link_endpoint_no_link(test_client: TestClient) -> None:
    """Test report_link endpoint when no link exists."""
    # Create a job
    req = {
        "season": "test",
        "dataset_id": "test",
        "outputs_root": "outputs",
        "config_snapshot": {},
        "config_hash": "hash1",
    }
    create_resp = test_client.post("/jobs", json=req)
    job_id = create_resp.json()["job_id"]
    
    # Get report_link (no run_id set)
    resp = test_client.get(f"/jobs/{job_id}/report_link")
    assert resp.status_code == 200
    data = resp.json()
    # build_report_link always returns a string (never None)
    assert data["report_link"] == ""



