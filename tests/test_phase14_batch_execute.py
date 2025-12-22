
"""Phase 14: Batch execution tests."""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

from FishBroWFS_V2.control.batch_execute import (
    BatchExecutor,
    BatchExecutionState,
    JobExecutionState,
    run_batch,
    retry_failed,
)


def test_batch_execution_state_enum():
    """Batch execution state enum values."""
    assert BatchExecutionState.PENDING.value == "PENDING"
    assert BatchExecutionState.RUNNING.value == "RUNNING"
    assert BatchExecutionState.DONE.value == "DONE"
    assert BatchExecutionState.FAILED.value == "FAILED"
    assert BatchExecutionState.PARTIAL_FAILED.value == "PARTIAL_FAILED"


def test_job_execution_state_enum():
    """Job execution state enum values."""
    assert JobExecutionState.PENDING.value == "PENDING"
    assert JobExecutionState.RUNNING.value == "RUNNING"
    assert JobExecutionState.SUCCESS.value == "SUCCESS"
    assert JobExecutionState.FAILED.value == "FAILED"
    assert JobExecutionState.SKIPPED.value == "SKIPPED"


def test_batch_executor_initial_state():
    """BatchExecutor initializes with correct state."""
    batch_id = "batch-123"
    job_ids = ["job1", "job2", "job3"]
    
    executor = BatchExecutor(batch_id, job_ids)
    
    assert executor.batch_id == batch_id
    assert executor.job_ids == job_ids
    assert executor.state == BatchExecutionState.PENDING
    assert executor.job_states == {
        "job1": JobExecutionState.PENDING,
        "job2": JobExecutionState.PENDING,
        "job3": JobExecutionState.PENDING,
    }
    assert executor.created_at is not None
    assert executor.updated_at is not None


def test_batch_executor_transition():
    """BatchExecutor transitions state based on job states."""
    executor = BatchExecutor("batch", ["job1", "job2"])
    
    # Initially PENDING
    assert executor.state == BatchExecutionState.PENDING
    
    # Start first job -> RUNNING
    executor._set_job_state("job1", JobExecutionState.RUNNING)
    assert executor.state == BatchExecutionState.RUNNING
    
    # Finish first job successfully, second still pending -> RUNNING
    executor._set_job_state("job1", JobExecutionState.SUCCESS)
    assert executor.state == BatchExecutionState.RUNNING
    
    # Start second job -> RUNNING
    executor._set_job_state("job2", JobExecutionState.RUNNING)
    assert executor.state == BatchExecutionState.RUNNING
    
    # Finish second job successfully -> DONE
    executor._set_job_state("job2", JobExecutionState.SUCCESS)
    assert executor.state == BatchExecutionState.DONE
    
    # If one job fails -> PARTIAL_FAILED
    executor._set_job_state("job1", JobExecutionState.FAILED)
    executor._set_job_state("job2", JobExecutionState.SUCCESS)
    executor._recompute_state()
    assert executor.state == BatchExecutionState.PARTIAL_FAILED
    
    # If all jobs fail -> FAILED
    executor._set_job_state("job2", JobExecutionState.FAILED)
    executor._recompute_state()
    assert executor.state == BatchExecutionState.FAILED


def test_batch_executor_skipped_jobs():
    """SKIPPED jobs count as completed for state computation."""
    executor = BatchExecutor("batch", ["job1", "job2"])
    
    executor._set_job_state("job1", JobExecutionState.SUCCESS)
    executor._set_job_state("job2", JobExecutionState.SKIPPED)
    
    # Both jobs are completed (SUCCESS + SKIPPED) -> DONE
    assert executor.state == BatchExecutionState.DONE


@patch("FishBroWFS_V2.control.batch_execute.BatchExecutor")
def test_run_batch_mock(mock_executor_cls):
    """run_batch creates executor and runs jobs."""
    mock_executor = Mock()
    mock_executor_cls.return_value = mock_executor
    
    batch_id = "batch-test"
    job_ids = ["job1", "job2"]
    artifacts_root = Path("/tmp/artifacts")
    
    result = run_batch(batch_id, job_ids, artifacts_root)
    
    mock_executor_cls.assert_called_once_with(batch_id, job_ids)
    mock_executor.run.assert_called_once_with(artifacts_root)
    assert result == mock_executor


@patch("FishBroWFS_V2.control.batch_execute.BatchExecutor")
def test_retry_failed_mock(mock_executor_cls):
    """retry_failed creates executor and retries failed jobs."""
    mock_executor = Mock()
    mock_executor_cls.return_value = mock_executor
    
    batch_id = "batch-retry"
    artifacts_root = Path("/tmp/artifacts")
    
    result = retry_failed(batch_id, artifacts_root)
    
    mock_executor_cls.assert_called_once_with(batch_id, [])
    mock_executor.retry_failed.assert_called_once_with(artifacts_root)
    assert result == mock_executor


