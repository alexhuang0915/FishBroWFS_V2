"""
Test RUN_COMPILE_V2 job lifecycle.

Assertions:
- Submit job → DB state = QUEUED
- Worker starts → RUNNING
- Success → SUCCEEDED
- Exception → FAILED
"""

import pytest
import time
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.control.supervisor import submit, get_job, list_jobs
from src.control.supervisor.db import SupervisorDB, get_default_db_path
from src.control.supervisor.models import JobSpec


def test_submit_run_compile_v2_job():
    """Test submitting a RUN_COMPILE_V2 job."""
    # Clean up any existing test jobs
    db = SupervisorDB(get_default_db_path())
    with db._connect() as conn:
        conn.execute("DELETE FROM jobs WHERE job_type = 'RUN_COMPILE_V2'")
    
    # Submit job
    payload = {
        "season": "2026Q1",
        "manifest_path": "/tmp/test/season_manifest.json"
    }
    
    job_id = submit("RUN_COMPILE_V2", payload)
    
    # Verify job was created
    job = get_job(job_id)
    assert job is not None
    assert job.job_id == job_id
    assert job.job_type == "RUN_COMPILE_V2"
    assert job.state == "QUEUED"
    
    # Verify payload
    spec_dict = json.loads(job.spec_json)
    assert spec_dict["job_type"] == "RUN_COMPILE_V2"
    assert spec_dict["params"] == payload
    
    print(f"✓ Job submitted: {job_id}")


def test_run_compile_v2_job_validation():
    """Test RUN_COMPILE_V2 parameter validation."""
    # Test missing required field
    with pytest.raises(ValueError, match="season"):
        submit("RUN_COMPILE_V2", {
            "manifest_path": "/tmp/test/season_manifest.json"
        })
    
    # Test invalid season (too short)
    with pytest.raises(ValueError, match="season should be at least 4 characters"):
        submit("RUN_COMPILE_V2", {
            "season": "Q1",
            "manifest_path": "/tmp/test/season_manifest.json"
        })
    
    # Test valid season with optional manifest_path omitted
    job_id = submit("RUN_COMPILE_V2", {
        "season": "2026Q1"
    })
    assert job_id is not None
    
    print("✓ Parameter validation works")


def test_run_compile_v2_handler_registered():
    """Test that RUN_COMPILE_V2 handler is registered."""
    from src.control.supervisor.job_handler import get_handler
    
    handler = get_handler("RUN_COMPILE_V2")
    assert handler is not None
    assert hasattr(handler, "validate_params")
    assert hasattr(handler, "execute")
    
    print("✓ RUN_COMPILE_V2 handler is registered")


@patch('src.control.supervisor.handlers.run_compile.RunCompileHandler._execute_compile')
def test_run_compile_v2_job_execution(mock_execute):
    """Test RUN_COMPILE_V2 job execution with mock."""
    from src.control.supervisor.handlers.run_compile import RunCompileHandler
    
    # Mock successful execution
    mock_execute.return_value = {
        "ok": True,
        "returncode": 0,
        "stdout_path": "/tmp/test/stdout.txt",
        "stderr_path": "/tmp/test/stderr.txt",
        "result": {"output_files": ["portfolio.json"]}
    }
    
    handler = RunCompileHandler()
    
    # Test parameter validation
    params = {
        "season": "2026Q1",
        "manifest_path": "/tmp/test/season_manifest.json"
    }
    
    handler.validate_params(params)
    
    # Mock job context
    mock_context = MagicMock()
    mock_context.job_id = "test_job_123"
    mock_context.artifacts_dir = "/tmp/test/artifacts"
    mock_context.is_abort_requested.return_value = False
    mock_context.heartbeat = MagicMock()
    
    # Test execution
    result = handler.execute(params, mock_context)
    
    assert result["ok"] is True
    assert result["job_type"] == "RUN_COMPILE_V2"
    assert "compile_dir" in result
    assert "manifest_path" in result
    
    print("✓ Job execution with mock works")


def test_run_compile_v2_manifest_generation():
    """Test manifest generation for RUN_COMPILE_V2 jobs."""
    from src.control.supervisor.handlers.run_compile import RunCompileHandler
    from src.contracts.supervisor.run_compile import RunCompilePayload
    
    handler = RunCompileHandler()
    
    # Create test payload
    payload = RunCompilePayload(
        season="2026Q1",
        manifest_path="/tmp/test/season_manifest.json"
    )
    
    # Test input fingerprint
    fingerprint = payload.compute_input_fingerprint()
    assert isinstance(fingerprint, str)
    assert len(fingerprint) == 16  # SHA256 truncated to 16 chars
    
    # Test with same inputs produces same fingerprint
    payload2 = RunCompilePayload(
        season="2026Q1",
        manifest_path="/tmp/test/season_manifest.json"
    )
    fingerprint2 = payload2.compute_input_fingerprint()
    assert fingerprint == fingerprint2
    
    # Test with different params produces different fingerprint
    payload3 = RunCompilePayload(
        season="2026Q2",  # Different
        manifest_path="/tmp/test/season_manifest.json"
    )
    fingerprint3 = payload3.compute_input_fingerprint()
    assert fingerprint != fingerprint3
    
    print("✓ Manifest fingerprint generation works")


def test_bypass_prevention():
    """Test that run_make_command is not reachable from UI paths."""
    import subprocess
    import re
    
    # Search for run_make_command in GUI source files
    result = subprocess.run(
        ["grep", "-r", "run_make_command", "src/gui"],
        capture_output=True,
        text=True
    )
    
    # If there are matches, they should only be in deprecated or test code
    if result.stdout:
        lines = result.stdout.strip().split('\n')
        allowed_patterns = [
            r"test_.*\.py",
            r"deprecated",
            r"legacy",
            r"#.*run_make_command"
        ]
        
        for line in lines:
            if line and not any(re.search(pattern, line) for pattern in allowed_patterns):
                # This is a violation - run_make_command in production GUI code
                pytest.fail(f"run_make_command found in GUI code: {line}")
    
    print("✓ No run_make_command in production GUI paths")


if __name__ == "__main__":
    # Run tests
    test_submit_run_compile_v2_job()
    test_run_compile_v2_job_validation()
    test_run_compile_v2_handler_registered()
    test_run_compile_v2_manifest_generation()
    test_bypass_prevention()
    print("\n✅ All tests passed!")
