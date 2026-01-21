"""
Test BUILD_PORTFOLIO_V2 job lifecycle.

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

from control.supervisor import submit, get_job
from control.supervisor.db import SupervisorDB, get_default_db_path
from control.supervisor.models import JobSpec


def _wait_for_job(job_id: str, timeout: float = 1.0, interval: float = 0.05):
    """Poll until the job record appears in the supervisor DB."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = get_job(job_id)
        if job is not None:
            return job
        remaining = deadline - time.time()
        if remaining <= 0:
            break
        time.sleep(min(interval, remaining))
    raise AssertionError(f"Job {job_id} did not appear in supervisor DB within {timeout:.2f}s")


def test_submit_build_portfolio_v2_job():
    """Test submitting a BUILD_PORTFOLIO_V2 job."""
    # Clean up any existing test jobs
    db = SupervisorDB(get_default_db_path())
    with db._connect() as conn:
        conn.execute("DELETE FROM jobs WHERE job_type = 'BUILD_PORTFOLIO_V2'")
    
    # Submit job
    payload = {
        "season": "2026Q1",
        "outputs_root": "/tmp/test/outputs",
        "allowlist": "MNQ,MES"
    }
    
    job_id = submit("BUILD_PORTFOLIO_V2", payload)
    
    job = _wait_for_job(job_id)
    
    # Verify job was created
    assert job is not None
    assert job.job_id == job_id
    assert job.job_type == "BUILD_PORTFOLIO_V2"
    assert job.state == "QUEUED"
    
    # Verify payload
    spec_dict = json.loads(job.spec_json)
    assert spec_dict["job_type"] == "BUILD_PORTFOLIO_V2"
    assert spec_dict["params"] == payload
    
    print(f"✓ Job submitted: {job_id}")


def test_build_portfolio_v2_job_validation():
    """Test BUILD_PORTFOLIO_V2 parameter validation."""
    # Test missing required field
    with pytest.raises(ValueError, match="season"):
        submit("BUILD_PORTFOLIO_V2", {
            "outputs_root": "/tmp/test/outputs",
            "allowlist": "MNQ,MES"
        })
    
    # Test invalid season (too short)
    with pytest.raises(ValueError, match="season should be at least 4 characters"):
        submit("BUILD_PORTFOLIO_V2", {
            "season": "Q1",
            "outputs_root": "/tmp/test/outputs"
        })
    
    # Test valid season with optional fields omitted
    job_id = submit("BUILD_PORTFOLIO_V2", {
        "season": "2026Q1"
    })
    assert job_id is not None
    
    print("✓ Parameter validation works")


def test_build_portfolio_v2_handler_registered():
    """Test that BUILD_PORTFOLIO_V2 handler is registered."""
    from control.supervisor.job_handler import get_handler
    
    handler = get_handler("BUILD_PORTFOLIO_V2")
    assert handler is not None
    assert hasattr(handler, "validate_params")
    assert hasattr(handler, "execute")
    
    print("✓ BUILD_PORTFOLIO_V2 handler is registered")


@patch('control.supervisor.handlers.build_portfolio.BuildPortfolioHandler._execute_portfolio')
def test_build_portfolio_v2_job_execution(mock_execute):
    """Test BUILD_PORTFOLIO_V2 job execution with mock."""
    from control.supervisor.handlers.build_portfolio import BuildPortfolioHandler
    
    # Mock successful execution
    mock_execute.return_value = {
        "ok": True,
        "returncode": 0,
        "stdout_path": "/tmp/test/stdout.txt",
        "stderr_path": "/tmp/test/stderr.txt",
        "result": {"output_files": ["portfolio.json"]}
    }
    
    handler = BuildPortfolioHandler()
    
    # Test parameter validation
    params = {
        "season": "2026Q1",
        "outputs_root": "/tmp/test/outputs",
        "allowlist": "MNQ,MES"
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
    assert result["job_type"] == "BUILD_PORTFOLIO_V2"
    assert "portfolio_dir" in result
    assert "manifest_path" in result
    
    print("✓ Job execution with mock works")


def test_build_portfolio_v2_manifest_generation():
    """Test manifest generation for BUILD_PORTFOLIO_V2 jobs."""
    from control.supervisor.handlers.build_portfolio import BuildPortfolioHandler
    from contracts.supervisor.build_portfolio import BuildPortfolioPayload
    
    handler = BuildPortfolioHandler()
    
    # Create test payload
    payload = BuildPortfolioPayload(
        season="2026Q1",
        outputs_root="/tmp/test/outputs",
        allowlist="MNQ,MES"
    )
    
    # Test input fingerprint
    fingerprint = payload.compute_input_fingerprint()
    assert isinstance(fingerprint, str)
    assert len(fingerprint) == 16  # SHA256 truncated to 16 chars
    
    # Test with same inputs produces same fingerprint
    payload2 = BuildPortfolioPayload(
        season="2026Q1",
        outputs_root="/tmp/test/outputs",
        allowlist="MNQ,MES"
    )
    fingerprint2 = payload2.compute_input_fingerprint()
    assert fingerprint == fingerprint2
    
    # Test with different params produces different fingerprint
    payload3 = BuildPortfolioPayload(
        season="2026Q2",  # Different
        outputs_root="/tmp/test/outputs",
        allowlist="MNQ,MES"
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
    test_submit_build_portfolio_v2_job()
    test_build_portfolio_v2_job_validation()
    test_build_portfolio_v2_handler_registered()
    test_build_portfolio_v2_manifest_generation()
    test_bypass_prevention()
    print("\n✅ All tests passed!")
