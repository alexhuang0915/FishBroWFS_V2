"""Tests for worker writing full traceback to log.

Tests that worker writes complete traceback.format_exc() to job_logs table
when job fails, while keeping last_error column short (500 chars).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from FishBroWFS_V2.control.jobs_db import create_job, get_job, get_job_logs, init_db
from FishBroWFS_V2.control.types import JobSpec, JobStatus
from FishBroWFS_V2.control.worker import run_one_job


def test_worker_writes_traceback_to_log(tmp_path: Path) -> None:
    """
    Test that worker writes full traceback to job_logs when job fails.
    
    Verifies:
    - last_error is truncated to 500 chars
    - job_logs contains full traceback with "Traceback (most recent call last):"
    """
    db = tmp_path / "jobs.db"
    init_db(db)
    
    # Create a job
    spec = JobSpec(
        season="2026Q1",
        dataset_id="test_dataset",
        outputs_root=str(tmp_path / "outputs"),
        config_snapshot={"test": "config"},
        config_hash="test_hash",
    )
    job_id = create_job(db, spec)
    
    # Mock run_funnel to raise exception with traceback
    with patch("FishBroWFS_V2.control.worker.run_funnel", side_effect=ValueError("Test error with long message " * 20)):
        # Run job (should catch exception and write traceback)
        run_one_job(db, job_id)
    
    # Verify job is marked as FAILED
    job = get_job(db, job_id)
    assert job.status == JobStatus.FAILED
    assert job.last_error is not None
    assert len(job.last_error) <= 500  # Truncated
    
    # Verify traceback is in job_logs
    logs = get_job_logs(db, job_id)
    assert len(logs) > 0, "Should have at least one log entry"
    
    # Find error log entry
    error_logs = [log for log in logs if "[ERROR]" in log]
    assert len(error_logs) > 0, "Should have error log entry"
    
    # Verify traceback format
    error_log = error_logs[0]
    assert "Traceback (most recent call last):" in error_log, "Should contain full traceback"
    assert "ValueError" in error_log, "Should contain exception type"
    assert "Test error" in error_log, "Should contain error message"
    
    # Verify error message is in last_error (truncated)
    assert "Test error" in job.last_error
