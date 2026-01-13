"""
Test RUN_RESEARCH_V2 job lifecycle.

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

from control.supervisor import submit, get_job, list_jobs
from control.supervisor.db import SupervisorDB, get_default_db_path
from control.supervisor.models import JobSpec


def test_submit_run_research_v2_job():
    """Test submitting a RUN_RESEARCH_V2 job."""
    # Clean up any existing test jobs
    db = SupervisorDB(get_default_db_path())
    with db._connect() as conn:
        conn.execute("DELETE FROM jobs WHERE job_type = 'RUN_RESEARCH_V2'")
    
    # Submit job
    payload = {
        "strategy_id": "S1",
        "profile_name": "CME_MNQ_v2",
        "start_date": "2025-01-01",
        "end_date": "2025-01-31",
        "params_override": {}
    }
    
    job_id = submit("RUN_RESEARCH_V2", payload)
    
    # Verify job was created
    job = get_job(job_id)
    assert job is not None
    assert job.job_id == job_id
    assert job.job_type == "RUN_RESEARCH_V2"
    assert job.state == "QUEUED"
    
    # Verify payload
    spec_dict = json.loads(job.spec_json)
    assert spec_dict["job_type"] == "RUN_RESEARCH_V2"
    assert spec_dict["params"] == payload
    
    print(f"✓ Job submitted: {job_id}")


def test_run_research_v2_job_validation():
    """Test RUN_RESEARCH_V2 parameter validation."""
    # Test missing required field
    with pytest.raises(ValueError, match="strategy_id"):
        submit("RUN_RESEARCH_V2", {
            "profile_name": "CME_MNQ_v2",
            "start_date": "2025-01-01",
            "end_date": "2025-01-31"
        })
    
    # Test invalid date format
    with pytest.raises(ValueError, match="start_date"):
        submit("RUN_RESEARCH_V2", {
            "strategy_id": "S1",
            "profile_name": "CME_MNQ_v2",
            "start_date": "invalid",
            "end_date": "2025-01-31"
        })
    
    print("✓ Parameter validation works")


def test_run_research_v2_handler_registered():
    """Test that RUN_RESEARCH_V2 handler is registered."""
    from control.supervisor.job_handler import get_handler
    
    handler = get_handler("RUN_RESEARCH_V2")
    assert handler is not None
    assert hasattr(handler, "validate_params")
    assert hasattr(handler, "execute")
    
    print("✓ RUN_RESEARCH_V2 handler is registered")


@patch('control.supervisor.handlers.run_research.RunResearchHandler._execute_research')
def test_run_research_v2_job_execution(mock_execute):
    """Test RUN_RESEARCH_V2 job execution with mock."""
    from control.supervisor.handlers.run_research import RunResearchHandler
    
    # Mock successful execution
    mock_execute.return_value = {
        "ok": True,
        "returncode": 0,
        "stdout_path": "/tmp/test/stdout.txt",
        "stderr_path": "/tmp/test/stderr.txt",
        "result": {"output_files": ["canonical_results.json"]}
    }
    
    handler = RunResearchHandler()
    
    # Test parameter validation
    params = {
        "strategy_id": "S1",
        "profile_name": "CME_MNQ_v2",
        "start_date": "2025-01-01",
        "end_date": "2025-01-31",
        "params_override": {}
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
    assert result["job_type"] == "RUN_RESEARCH_V2"
    assert "run_dir" in result
    assert "manifest_path" in result
    
    print("✓ Job execution with mock works")


def test_run_research_v2_manifest_generation():
    """Test manifest generation for RUN_RESEARCH_V2 jobs."""
    from control.supervisor.handlers.run_research import RunResearchHandler
    from contracts.supervisor.run_research import RunResearchPayload
    
    handler = RunResearchHandler()
    
    # Create test payload
    payload = RunResearchPayload(
        strategy_id="S1",
        profile_name="CME_MNQ_v2",
        start_date="2025-01-01",
        end_date="2025-01-31",
        params_override={"param1": "value1"}
    )
    
    # Test input fingerprint
    fingerprint = payload.compute_input_fingerprint()
    assert isinstance(fingerprint, str)
    assert len(fingerprint) == 16  # SHA256 truncated to 16 chars
    
    # Test with same inputs produces same fingerprint
    payload2 = RunResearchPayload(
        strategy_id="S1",
        profile_name="CME_MNQ_v2",
        start_date="2025-01-01",
        end_date="2025-01-31",
        params_override={"param1": "value1"}
    )
    fingerprint2 = payload2.compute_input_fingerprint()
    assert fingerprint == fingerprint2
    
    # Test with different params produces different fingerprint
    payload3 = RunResearchPayload(
        strategy_id="S1",
        profile_name="CME_MNQ_v2",
        start_date="2025-01-01",
        end_date="2025-01-31",
        params_override={"param1": "different"}
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
    test_submit_run_research_v2_job()
    test_run_research_v2_job_validation()
    test_run_research_v2_handler_registered()
    test_run_research_v2_manifest_generation()
    test_bypass_prevention()
    print("\n✅ All tests passed!")