"""Tests for jobs database."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from FishBroWFS_V2.control.jobs_db import (
    create_job,
    get_job,
    get_requested_pause,
    get_requested_stop,
    init_db,
    list_jobs,
    mark_done,
    mark_failed,
    mark_killed,
    request_pause,
    request_stop,
    update_running,
)
from FishBroWFS_V2.control.types import JobSpec, JobStatus, StopMode


@pytest.fixture
def temp_db() -> Path:
    """Create temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        init_db(db_path)
        yield db_path


def test_init_db_creates_table(temp_db: Path) -> None:
    """Test that init_db creates the jobs table."""
    assert temp_db.exists()
    
    import sqlite3
    
    conn = sqlite3.connect(str(temp_db))
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='jobs'")
    assert cursor.fetchone() is not None
    conn.close()


def test_create_job_and_get(temp_db: Path) -> None:
    """Test creating and retrieving a job."""
    spec = JobSpec(
        season="test_season",
        dataset_id="test_dataset",
        outputs_root="outputs",
        config_snapshot={"bars": 1000, "params_total": 100},
        config_hash="abc123",
    )
    
    job_id = create_job(temp_db, spec)
    assert job_id
    
    job = get_job(temp_db, job_id)
    assert job.job_id == job_id
    assert job.status == JobStatus.QUEUED
    assert job.spec.season == "test_season"
    assert job.spec.dataset_id == "test_dataset"
    assert job.report_link is None  # Default is None


def test_list_jobs(temp_db: Path) -> None:
    """Test listing jobs."""
    spec = JobSpec(
        season="test",
        dataset_id="test",
        outputs_root="outputs",
        config_snapshot={},
        config_hash="hash1",
    )
    
    job_id1 = create_job(temp_db, spec)
    job_id2 = create_job(temp_db, spec)
    
    jobs = list_jobs(temp_db, limit=10)
    assert len(jobs) == 2
    assert {j.job_id for j in jobs} == {job_id1, job_id2}
    # Check that all jobs have report_link field
    for job in jobs:
        assert hasattr(job, "report_link")
        assert job.report_link is None  # Default is None


def test_request_pause(temp_db: Path) -> None:
    """Test pause request."""
    spec = JobSpec(
        season="test",
        dataset_id="test",
        outputs_root="outputs",
        config_snapshot={},
        config_hash="hash1",
    )
    job_id = create_job(temp_db, spec)
    
    request_pause(temp_db, job_id, pause=True)
    assert get_requested_pause(temp_db, job_id) is True
    
    request_pause(temp_db, job_id, pause=False)
    assert get_requested_pause(temp_db, job_id) is False


def test_request_stop(temp_db: Path) -> None:
    """Test stop request."""
    spec = JobSpec(
        season="test",
        dataset_id="test",
        outputs_root="outputs",
        config_snapshot={},
        config_hash="hash1",
    )
    job_id = create_job(temp_db, spec)
    
    request_stop(temp_db, job_id, StopMode.SOFT)
    assert get_requested_stop(temp_db, job_id) == "SOFT"
    
    request_stop(temp_db, job_id, StopMode.KILL)
    assert get_requested_stop(temp_db, job_id) == "KILL"
    
    # QUEUED job should be immediately KILLED
    job = get_job(temp_db, job_id)
    assert job.status == JobStatus.KILLED


def test_status_transitions(temp_db: Path) -> None:
    """Test status transitions."""
    spec = JobSpec(
        season="test",
        dataset_id="test",
        outputs_root="outputs",
        config_snapshot={},
        config_hash="hash1",
    )
    job_id = create_job(temp_db, spec)
    
    # QUEUED -> RUNNING
    update_running(temp_db, job_id, pid=12345)
    job = get_job(temp_db, job_id)
    assert job.status == JobStatus.RUNNING
    assert job.pid == 12345
    
    # RUNNING -> DONE
    mark_done(temp_db, job_id)
    job = get_job(temp_db, job_id)
    assert job.status == JobStatus.DONE
    
    # Cannot transition from DONE
    with pytest.raises(ValueError, match="Cannot transition from terminal status"):
        update_running(temp_db, job_id, pid=12345)


def test_mark_failed(temp_db: Path) -> None:
    """Test marking job as failed."""
    spec = JobSpec(
        season="test",
        dataset_id="test",
        outputs_root="outputs",
        config_snapshot={},
        config_hash="hash1",
    )
    job_id = create_job(temp_db, spec)
    update_running(temp_db, job_id, pid=12345)
    
    mark_failed(temp_db, job_id, error="Test error")
    job = get_job(temp_db, job_id)
    assert job.status == JobStatus.FAILED
    assert job.last_error == "Test error"


def test_mark_killed(temp_db: Path) -> None:
    """Test marking job as killed."""
    spec = JobSpec(
        season="test",
        dataset_id="test",
        outputs_root="outputs",
        config_snapshot={},
        config_hash="hash1",
    )
    job_id = create_job(temp_db, spec)
    
    mark_killed(temp_db, job_id, error="Killed by user")
    job = get_job(temp_db, job_id)
    assert job.status == JobStatus.KILLED
    assert job.last_error == "Killed by user"

