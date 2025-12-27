"""Test that job submission returns HTTP 503 when worker is unavailable.

EOOR500 → HTTP 503 (WORKER-AWARE) requirement:
- All job submission endpoints must return HTTP 503 Service Unavailable when worker is unavailable
- Never return HTTP 500 for worker unavailability
- Error message must mention worker explicitly
- JSON response must include diagnostic details
"""

from __future__ import annotations

import tempfile
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from FishBroWFS_V2.control.api import app, get_db_path
from FishBroWFS_V2.control.jobs_db import init_db


@pytest.fixture
def test_client_no_worker() -> TestClient:
    """Create test client with temporary database and no worker."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        init_db(db_path)
        
        # Save original environment variables
        original_jobs_db_path = os.environ.get("JOBS_DB_PATH")
        original_allow_tmp_db = os.environ.get("FISHBRO_ALLOW_TMP_DB")
        original_allow_spawn = os.environ.get("FISHBRO_ALLOW_SPAWN_IN_TESTS")
        
        # Override DB path
        os.environ["JOBS_DB_PATH"] = str(db_path)
        # Allow /tmp DB paths (required for temporary DB)
        os.environ["FISHBRO_ALLOW_TMP_DB"] = "1"
        # DO NOT allow worker spawn in tests for this fixture (we want to test 503)
        os.environ["FISHBRO_ALLOW_SPAWN_IN_TESTS"] = "0"
        
        # Re-import to get new DB path
        from FishBroWFS_V2.control import api
        
        # Reinitialize
        api.init_db(db_path)
        
        # Mock worker status to simulate no worker
        with patch('FishBroWFS_V2.control.api._check_worker_status') as mock_check, \
             patch('FishBroWFS_V2.control.api.load_dataset_index') as mock_load_dataset:
            mock_check.return_value = {
                "alive": False,
                "pid": None,
                "last_heartbeat_age_sec": None,
                "reason": "pidfile missing",
                "expected_db": str(db_path),
            }
            # Mock dataset index to avoid FileNotFoundError
            from FishBroWFS_V2.data.dataset_registry import DatasetIndex, DatasetRecord
            from datetime import date
            mock_index = DatasetIndex(
                generated_at="2024-01-01T00:00:00Z",
                datasets=[
                    DatasetRecord(
                        id="test_dataset",
                        symbol="TEST",
                        exchange="TEST",
                        timeframe="60m",
                        path="TEST/60m/2020-2024.parquet",
                        start_date=date(2020, 1, 1),
                        end_date=date(2024, 12, 31),
                        fingerprint_sha256_40="d" * 40,
                        tz_provider="IANA",
                        tz_version="unknown",
                    )
                ]
            )
            mock_load_dataset.return_value = mock_index
            try:
                yield TestClient(app)
            finally:
                # Restore original environment variables
                if original_jobs_db_path is not None:
                    os.environ["JOBS_DB_PATH"] = original_jobs_db_path
                else:
                    os.environ.pop("JOBS_DB_PATH", None)
                if original_allow_tmp_db is not None:
                    os.environ["FISHBRO_ALLOW_TMP_DB"] = original_allow_tmp_db
                else:
                    os.environ.pop("FISHBRO_ALLOW_TMP_DB", None)
                if original_allow_spawn is not None:
                    os.environ["FISHBRO_ALLOW_SPAWN_IN_TESTS"] = original_allow_spawn
                else:
                    os.environ.pop("FISHBRO_ALLOW_SPAWN_IN_TESTS", None)


@pytest.fixture
def test_client_with_worker() -> TestClient:
    """Create test client with temporary database and worker running."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        init_db(db_path)
        
        # Save original environment variables
        original_jobs_db_path = os.environ.get("JOBS_DB_PATH")
        original_allow_tmp_db = os.environ.get("FISHBRO_ALLOW_TMP_DB")
        original_allow_spawn = os.environ.get("FISHBRO_ALLOW_SPAWN_IN_TESTS")
        
        # Override DB path
        os.environ["JOBS_DB_PATH"] = str(db_path)
        os.environ["FISHBRO_ALLOW_SPAWN_IN_TESTS"] = "1"
        os.environ["FISHBRO_ALLOW_TMP_DB"] = "1"
        
        # Re-import to get new DB path
        from FishBroWFS_V2.control import api
        
        # Reinitialize
        api.init_db(db_path)
        
        # Mock worker status to simulate worker running
        with patch('FishBroWFS_V2.control.api._check_worker_status') as mock_check, \
             patch('FishBroWFS_V2.control.api.load_dataset_index') as mock_load_dataset:
            mock_check.return_value = {
                "alive": True,
                "pid": 12345,
                "last_heartbeat_age_sec": 1.0,
                "reason": "worker alive",
                "expected_db": str(db_path),
            }
            # Mock dataset index to avoid FileNotFoundError
            from FishBroWFS_V2.data.dataset_registry import DatasetIndex, DatasetRecord
            from datetime import date
            mock_index = DatasetIndex(
                generated_at="2024-01-01T00:00:00Z",
                datasets=[
                    DatasetRecord(
                        id="test_dataset",
                        symbol="TEST",
                        exchange="TEST",
                        timeframe="60m",
                        path="TEST/60m/2020-2024.parquet",
                        start_date=date(2020, 1, 1),
                        end_date=date(2024, 12, 31),
                        fingerprint_sha256_40="d" * 40,
                        tz_provider="IANA",
                        tz_version="unknown",
                    )
                ]
            )
            mock_load_dataset.return_value = mock_index
            try:
                yield TestClient(app)
            finally:
                # Restore original environment variables
                if original_jobs_db_path is not None:
                    os.environ["JOBS_DB_PATH"] = original_jobs_db_path
                else:
                    os.environ.pop("JOBS_DB_PATH", None)
                if original_allow_tmp_db is not None:
                    os.environ["FISHBRO_ALLOW_TMP_DB"] = original_allow_tmp_db
                else:
                    os.environ.pop("FISHBRO_ALLOW_TMP_DB", None)
                if original_allow_spawn is not None:
                    os.environ["FISHBRO_ALLOW_SPAWN_IN_TESTS"] = original_allow_spawn
                else:
                    os.environ.pop("FISHBRO_ALLOW_SPAWN_IN_TESTS", None)


def test_submit_job_returns_503_when_worker_missing(test_client_no_worker: TestClient) -> None:
    """Test POST /jobs returns 503 when worker is unavailable."""
    req = {
        "season": "test_season",
        "dataset_id": "test_dataset",
        "outputs_root": "outputs",
        "config_snapshot": {"bars": 1000, "params_total": 100},
        "config_hash": "abc123",
        "created_by": "b5c",
    }
    
    resp = test_client_no_worker.post("/jobs", json=req)
    
    # Must return HTTP 503, not 500
    assert resp.status_code == 503, f"Expected 503, got {resp.status_code}"
    
    # Must have proper JSON structure
    data = resp.json()
    assert "detail" in data
    detail = data["detail"]
    
    # Error message must mention worker (detail is a dict with "message" field)
    assert isinstance(detail, dict)
    assert "message" in detail
    assert "worker" in detail["message"].lower(), f"Error message should mention worker: {detail['message']}"
    
    # Should not be generic 500 error
    assert "internal server error" not in detail["message"].lower()
    
    # Check response structure matches our error format
    assert "error" in detail
    assert detail["error"] == "WORKER_UNAVAILABLE"
    assert "worker" in detail
    assert "action" in detail


def test_batch_submit_returns_503_when_worker_missing(test_client_no_worker: TestClient) -> None:
    """Test POST /jobs/batch returns 503 when worker is unavailable."""
    from datetime import date
    
    req = {
        "jobs": [
            {
                "season": "test_season",
                "data1": {
                    "dataset_id": "test_dataset",
                    "start_date": "2020-01-01",
                    "end_date": "2024-12-31"
                },
                "data2": None,
                "strategy_id": "test_strategy",
                "params": {},
                "wfs": {
                    "stage0_subsample": 1.0,
                    "top_k": 100,
                    "mem_limit_mb": 4096,
                    "allow_auto_downsample": True
                }
            }
        ]
    }
    
    resp = test_client_no_worker.post("/jobs/batch", json=req)
    
    # Must return HTTP 503, not 500
    assert resp.status_code == 503, f"Expected 503, got {resp.status_code}"
    
    # Must have proper JSON structure
    data = resp.json()
    assert "detail" in data
    detail = data["detail"]
    
    # Error message must mention worker (detail is a dict with "message" field)
    assert isinstance(detail, dict)
    assert "message" in detail
    assert "worker" in detail["message"].lower(), f"Error message should mention worker: {detail['message']}"
    
    # Should not be generic 500 error
    assert "internal server error" not in detail["message"].lower()
    
    # Check response structure matches our error format
    assert "error" in detail
    assert detail["error"] == "WORKER_UNAVAILABLE"


def test_submit_job_succeeds_when_worker_running(test_client_with_worker: TestClient) -> None:
    """Test POST /jobs succeeds when worker is available."""
    req = {
        "season": "test_season",
        "dataset_id": "test_dataset",
        "outputs_root": "outputs",
        "config_snapshot": {"bars": 1000, "params_total": 100},
        "config_hash": "abc123",
        "created_by": "b5c",
    }
    
    resp = test_client_with_worker.post("/jobs", json=req)
    
    # Should succeed (200 or 201)
    assert resp.status_code in (200, 201), f"Expected success, got {resp.status_code}"
    
    data = resp.json()
    assert "job_id" in data
    assert isinstance(data["job_id"], str)


def test_batch_submit_succeeds_when_worker_running(test_client_with_worker: TestClient) -> None:
    """Test POST /jobs/batch succeeds when worker is available."""
    from datetime import date
    
    req = {
        "jobs": [
            {
                "season": "test_season",
                "data1": {
                    "dataset_id": "test_dataset",
                    "start_date": "2020-01-01",
                    "end_date": "2024-12-31"
                },
                "data2": None,
                "strategy_id": "test_strategy",
                "params": {},
                "wfs": {
                    "stage0_subsample": 1.0,
                    "top_k": 100,
                    "mem_limit_mb": 4096,
                    "allow_auto_downsample": True
                }
            }
        ]
    }
    
    resp = test_client_with_worker.post("/jobs/batch", json=req)
    
    # Should succeed (200 or 201)
    assert resp.status_code in (200, 201), f"Expected success, got {resp.status_code}"
    
    data = resp.json()
    assert "batch_id" in data
    assert isinstance(data["batch_id"], str)


def test_worker_status_check_integration() -> None:
    """Test that _check_worker_status function works correctly."""
    from FishBroWFS_V2.control.api import _check_worker_status
    from pathlib import Path
    
    # Create a temporary DB path for testing
    db_path = Path("/tmp/test.db")
    
    # Mock the dependencies
    with patch('FishBroWFS_V2.control.api.validate_pidfile') as mock_validate, \
         patch('FishBroWFS_V2.control.api.time.time') as mock_time, \
         patch('FishBroWFS_V2.control.api.Path.exists') as mock_exists, \
         patch('FishBroWFS_V2.control.api.Path.read_text') as mock_read_text, \
         patch('FishBroWFS_V2.control.api.Path.stat') as mock_stat:
        
        # Test case 1: pidfile doesn't exist
        mock_exists.return_value = False
        result = _check_worker_status(db_path)
        assert not result["alive"]
        assert result["reason"] == "pidfile missing"
        
        # Test case 2: pidfile exists but corrupted (read_text raises ValueError)
        mock_exists.return_value = True
        mock_validate.return_value = (True, "")  # pidfile is valid
        mock_read_text.side_effect = ValueError("invalid literal")
        result = _check_worker_status(db_path)
        assert not result["alive"]
        assert "corrupted" in result["reason"]
        
        # Test case 3: pidfile exists, validate_pidfile returns invalid
        mock_exists.return_value = True
        mock_validate.return_value = (False, "pidfile stale")
        # Clear any side effect from previous test
        mock_read_text.side_effect = None
        # read_text won't be called because validate_pidfile returns invalid
        result = _check_worker_status(db_path)
        assert not result["alive"]
        assert result["reason"] == "pidfile stale"
        
        # Test case 4: pidfile exists, process alive, heartbeat stale
        mock_exists.return_value = True
        mock_read_text.side_effect = None  # Clear side effect
        mock_read_text.return_value = "12345"
        mock_validate.return_value = (True, "")
        # Mock stat for heartbeat file
        mock_stat_obj = MagicMock()
        mock_stat_obj.st_mtime = 1000.0
        mock_stat.return_value = mock_stat_obj
        mock_time.return_value = 2000.0  # Current time (1000 seconds later)
        result = _check_worker_status(db_path)
        assert result["alive"]  # Process is alive
        assert result["last_heartbeat_age_sec"] == 1000.0
        
        # Test case 5: pidfile exists, process alive, heartbeat fresh
        mock_stat_obj = MagicMock()
        mock_stat_obj.st_mtime = 1995.0  # 5 seconds ago
        mock_stat.return_value = mock_stat_obj
        mock_time.return_value = 2000.0  # Current time
        result = _check_worker_status(db_path)
        assert result["alive"]
        assert result["last_heartbeat_age_sec"] == 5.0


def test_error_message_includes_diagnostics() -> None:
    """Test that 503 error message includes diagnostic details."""
    from FishBroWFS_V2.control.api import require_worker_or_503
    from pathlib import Path
    import os
    
    # Create a temporary DB path for testing
    db_path = Path("/tmp/test.db")
    
    # Mock _check_worker_status to return False with specific reason
    with patch('FishBroWFS_V2.control.api._check_worker_status') as mock_check:
        mock_check.return_value = {
            "alive": False,
            "pid": None,
            "last_heartbeat_age_sec": None,
            "reason": "pidfile missing",
            "expected_db": str(db_path),
        }
        
        # Ensure the environment variable does NOT allow spawn in tests
        original = os.environ.get("FISHBRO_ALLOW_SPAWN_IN_TESTS")
        os.environ["FISHBRO_ALLOW_SPAWN_IN_TESTS"] = "0"
        try:
            # Should raise HTTPException with 503
            import fastapi
            try:
                require_worker_or_503(db_path)
                assert False, "Should have raised HTTPException"
            except fastapi.HTTPException as e:
                assert e.status_code == 503
                detail = e.detail
                # Check structure
                assert isinstance(detail, dict)
                assert "error" in detail
                assert detail["error"] == "WORKER_UNAVAILABLE"
                assert "worker" in detail
                assert "action" in detail
                assert "message" in detail
                assert "worker" in detail["message"].lower()
        finally:
            if original is not None:
                os.environ["FISHBRO_ALLOW_SPAWN_IN_TESTS"] = original
            else:
                os.environ.pop("FISHBRO_ALLOW_SPAWN_IN_TESTS", None)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])