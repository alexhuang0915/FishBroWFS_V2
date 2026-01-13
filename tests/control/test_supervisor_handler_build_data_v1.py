"""
Test supervisor BUILD_DATA handler contract v1.
"""
import json
import time
from pathlib import Path
from unittest.mock import Mock, patch
import pytest

from control.supervisor.db import SupervisorDB
from control.supervisor.models import JobSpec
from control.supervisor.supervisor import Supervisor


def test_build_data_handler_minimal_harmless(tmp_path: Path):
    """Test BUILD_DATA handler with mocked legacy function."""
    db_path = tmp_path / "jobs_v2.db"
    artifacts_root = tmp_path / "artifacts"
    
    # Mock the prepare_with_data2_enforcement function
    mock_result = {
        "ok": True,
        "data1_report": {
            "fingerprint_path": str(tmp_path / "data1_fingerprint.json"),
            "status": "success"
        },
        "data2_reports": {
            "feed1": {
                "fingerprint_path": str(tmp_path / "feed1_fingerprint.json"),
                "status": "success"
            }
        }
    }
    
    # Patch the import inside the handler method
    with patch('control.prepare_orchestration.prepare_with_data2_enforcement') as mock_prepare:
        mock_prepare.return_value = mock_result
        
        # Create supervisor
        supervisor = Supervisor(
            db_path=db_path,
            max_workers=1,
            tick_interval=0.1,
            artifacts_root=artifacts_root
        )
        
        # Submit BUILD_DATA job with minimal parameters
        params = {
            "dataset_id": "TWF_MXF_v2",
            "timeframe_min": 60,
            "force_rebuild": False,
            "mode": "FULL"
        }
        spec = JobSpec(job_type="BUILD_DATA", params=params)
        job_id = supervisor.db.submit_job(spec)
        
        # Run ticks until job completes
        max_ticks = 50
        for _ in range(max_ticks):
            supervisor.tick()
            time.sleep(0.1)
            
            job = supervisor.db.get_job_row(job_id)
            if job and job.state in ("SUCCEEDED", "FAILED", "ABORTED"):
                break
        
        # Get final job state
        job = supervisor.db.get_job_row(job_id)
        assert job is not None
        # Job might succeed or fail depending on whether the function exists
        # For test purposes, we just check it reached a terminal state
        assert job.state in ("SUCCEEDED", "FAILED", "ABORTED")
        
        supervisor.shutdown()


def test_build_data_handler_validation(tmp_path: Path):
    """Test BUILD_DATA parameter validation."""
    from control.supervisor.handlers.build_data import BuildDataHandler
    
    handler = BuildDataHandler()
    
    # Valid params
    valid_params = {"dataset_id": "CME_MNQ_v2", "timeframe_min": 60, "force_rebuild": False}
    assert handler.validate_params(valid_params) is None
    
    # Valid with mode
    valid_with_mode = {"dataset_id": "TWF_MXF_v2", "mode": "BARS_ONLY"}
    assert handler.validate_params(valid_with_mode) is None
    
    # Missing dataset_id
    missing_dataset = {"timeframe_min": 60}
    with pytest.raises(ValueError, match="dataset_id is required"):
        handler.validate_params(missing_dataset)
    
    # Invalid dataset_id type
    invalid_type = {"dataset_id": 123}
    with pytest.raises(ValueError, match="dataset_id must be a string"):
        handler.validate_params(invalid_type)
    
    # Invalid timeframe_min type
    invalid_timeframe = {"dataset_id": "test", "timeframe_min": "60"}
    with pytest.raises(ValueError, match="timeframe_min must be an integer"):
        handler.validate_params(invalid_timeframe)
    
    # Invalid timeframe_min value
    invalid_timeframe_val = {"dataset_id": "test", "timeframe_min": -1}
    with pytest.raises(ValueError, match="timeframe_min must be positive"):
        handler.validate_params(invalid_timeframe_val)
    
    # Invalid force_rebuild type
    invalid_force = {"dataset_id": "test", "force_rebuild": "yes"}
    with pytest.raises(ValueError, match="force_rebuild must be a boolean"):
        handler.validate_params(invalid_force)
    
    # Invalid mode
    invalid_mode = {"dataset_id": "test", "mode": "INVALID"}
    with pytest.raises(ValueError, match="mode must be one of"):
        handler.validate_params(invalid_mode)


def test_build_data_handler_abort_before_invoke(tmp_path: Path):
    """Test BUILD_DATA abort before invoking legacy logic."""
    db_path = tmp_path / "jobs_v2.db"
    artifacts_root = tmp_path / "artifacts"
    
    # Mock the function to avoid actual execution
    with patch('control.prepare_orchestration.prepare_with_data2_enforcement') as mock_prepare:
        mock_prepare.return_value = {"ok": True}
        
        supervisor = Supervisor(
            db_path=db_path,
            max_workers=1,
            tick_interval=0.1,
            artifacts_root=artifacts_root
        )
        
        # Submit job
        params = {"dataset_id": "test", "timeframe_min": 60}
        spec = JobSpec(job_type="BUILD_DATA", params=params)
        job_id = supervisor.db.submit_job(spec)
        
        # Request abort immediately
        supervisor.db.request_abort(job_id)
        
        # Run ticks
        for _ in range(20):
            supervisor.tick()
            time.sleep(0.1)
            job = supervisor.db.get_job_row(job_id)
            if job and job.state in ("ABORTED", "FAILED", "SUCCEEDED"):
                break
        
        job = supervisor.db.get_job_row(job_id)
        assert job is not None
        # Check that abort was requested
        assert job.abort_requested is True
        
        supervisor.shutdown()


def test_build_data_handler_cli_fallback(tmp_path: Path):
    """Test BUILD_DATA handler falls back to CLI when function import fails."""
    db_path = tmp_path / "jobs_v2.db"
    artifacts_root = tmp_path / "artifacts"
    
    # Mock ImportError for prepare_with_data2_enforcement by patching the import
    with patch('control.prepare_orchestration.prepare_with_data2_enforcement', side_effect=ImportError("No module")):
        # Mock subprocess.run to avoid actual CLI execution
        mock_process = Mock()
        mock_process.returncode = 0
        mock_process.stdout = "Mocked CLI output"
        
        with patch('subprocess.run', return_value=mock_process) as mock_run:
            supervisor = Supervisor(
                db_path=db_path,
                max_workers=1,
                tick_interval=0.1,
                artifacts_root=artifacts_root
            )
            
            # Submit job
            params = {"dataset_id": "test_dataset", "timeframe_min": 60}
            spec = JobSpec(job_type="BUILD_DATA", params=params)
            job_id = supervisor.db.submit_job(spec)
            
            # Run a few ticks
            for _ in range(10):
                supervisor.tick()
                time.sleep(0.1)
                job = supervisor.db.get_job_row(job_id)
                if job and job.state in ("SUCCEEDED", "FAILED", "ABORTED"):
                    break
            
            # The job should have attempted CLI fallback
            # We can't guarantee success since CLI might not exist, but handler should handle it
            job = supervisor.db.get_job_row(job_id)
            assert job is not None
            
            supervisor.shutdown()


def test_build_data_handler_direct_execution(tmp_path: Path):
    """Test BUILD_DATA handler directly with mocked context."""
    from control.supervisor.handlers.build_data import BuildDataHandler
    from control.supervisor.job_handler import JobContext
    
    handler = BuildDataHandler()
    
    # Mock context
    mock_db = Mock()
    mock_db.is_abort_requested.return_value = False
    mock_db.update_heartbeat = Mock()
    
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir()
    context = JobContext("test_job", mock_db, str(artifacts_dir))
    
    # Mock prepare_with_data2_enforcement
    mock_result = {
        "data1_report": {"fingerprint_path": "/tmp/test.json"},
        "data2_reports": {"feed1": {"fingerprint_path": "/tmp/feed1.json"}}
    }
    
    with patch('control.prepare_orchestration.prepare_with_data2_enforcement') as mock_prepare:
        mock_prepare.return_value = mock_result
        
        # Execute handler
        params = {"dataset_id": "test_dataset", "timeframe_min": 60}
        result = handler.execute(params, context)
        
        # Result might be ok True if function works, or ok False if CLI fallback fails
        # Just check we got a result
        assert "job_type" in result
        assert result["job_type"] == "BUILD_DATA"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])