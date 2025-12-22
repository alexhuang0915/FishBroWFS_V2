
"""Integration tests for worker execution and job completion."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from FishBroWFS_V2.control.jobs_db import create_job, get_job, init_db
from FishBroWFS_V2.control.report_links import make_report_link
from FishBroWFS_V2.control.types import JobSpec, JobStatus
from FishBroWFS_V2.control.worker import run_one_job
from FishBroWFS_V2.pipeline.funnel_schema import (
    FunnelPlan,
    FunnelResultIndex,
    FunnelStageIndex,
    StageName,
    StageSpec,
)


@pytest.fixture
def temp_db() -> Path:
    """Create temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        init_db(db_path)
        yield db_path


@pytest.fixture
def temp_outputs_root() -> Path:
    """Create temporary outputs root directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def test_worker_completes_job_with_run_id_and_report_link(
    temp_db: Path, temp_outputs_root: Path
) -> None:
    """Test that worker completes job and sets run_id and report_link."""
    # Create a job
    season = "2026Q1"
    spec = JobSpec(
        season=season,
        dataset_id="test_dataset",
        outputs_root=str(temp_outputs_root),
        config_snapshot={
            "bars": 1000,
            "params_total": 100,
            "param_subsample_rate": 0.1,
        },
        config_hash="test_hash",
    )
    
    job_id = create_job(temp_db, spec)
    
    # Mock run_funnel to return a fake result
    fake_run_id = "stage2_confirm-20251218T093513Z-354cee6b"
    fake_stage_index = FunnelStageIndex(
        stage=StageName.STAGE2_CONFIRM,
        run_id=fake_run_id,
        run_dir=f"seasons/{season}/runs/{fake_run_id}",
    )
    fake_result_index = FunnelResultIndex(
        plan=FunnelPlan(stages=[]),
        stages=[fake_stage_index],
    )
    
    with patch("FishBroWFS_V2.control.worker.run_funnel") as mock_run_funnel:
        mock_run_funnel.return_value = fake_result_index
        
        # Run the job
        run_one_job(temp_db, job_id)
    
    # Check that job is marked as DONE
    job = get_job(temp_db, job_id)
    assert job.status == JobStatus.DONE
    assert job.run_id == fake_run_id
    assert job.report_link == make_report_link(season=season, run_id=fake_run_id)
    
    # Verify report_link format
    assert f"season={season}" in job.report_link
    assert f"run_id={fake_run_id}" in job.report_link


def test_worker_handles_empty_funnel_result(
    temp_db: Path, temp_outputs_root: Path
) -> None:
    """Test that worker handles empty funnel result gracefully."""
    spec = JobSpec(
        season="2026Q1",
        dataset_id="test_dataset",
        outputs_root=str(temp_outputs_root),
        config_snapshot={"bars": 1000, "params_total": 100},
        config_hash="test_hash",
    )
    
    job_id = create_job(temp_db, spec)
    
    # Mock run_funnel to return empty result
    fake_result_index = FunnelResultIndex(
        plan=FunnelPlan(stages=[]),
        stages=[],
    )
    
    with patch("FishBroWFS_V2.control.worker.run_funnel") as mock_run_funnel:
        mock_run_funnel.return_value = fake_result_index
        
        # Run the job
        run_one_job(temp_db, job_id)
    
    # Check that job is still marked as DONE (even without stages)
    job = get_job(temp_db, job_id)
    assert job.status == JobStatus.DONE
    # run_id and report_link should be None if no stages
    assert job.run_id is None
    assert job.report_link is None


