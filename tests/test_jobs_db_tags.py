
"""Tests for jobs_db tags functionality.

Tests:
1. Create job with tags
2. Read job with tags
3. Old rows without tags fallback to []
4. search_by_tag query helper
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from control.jobs_db import (
    create_job,
    get_job,
    init_db,
    list_jobs,
    search_by_tag,
)
from control.types import DBJobSpec


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    """Create temporary database for testing."""
    db_path = tmp_path / "test_jobs.db"
    init_db(db_path)
    return db_path


def test_create_job_with_tags(temp_db: Path) -> None:
    """Test creating a job with tags."""
    spec = DBJobSpec(
        season="2026Q1",
        dataset_id="test_dataset",
        outputs_root="/tmp/outputs",
        config_snapshot={"test": "config"},
        config_hash="abc123",
    )
    
    job_id = create_job(temp_db, spec, tags=["production", "high-priority"])
    
    # Read back and verify tags
    record = get_job(temp_db, job_id)
    assert record.tags == ["production", "high-priority"]


def test_create_job_without_tags(temp_db: Path) -> None:
    """Test creating a job without tags (defaults to empty list)."""
    spec = DBJobSpec(
        season="2026Q1",
        dataset_id="test_dataset",
        outputs_root="/tmp/outputs",
        config_snapshot={"test": "config"},
        config_hash="abc123",
    )
    
    job_id = create_job(temp_db, spec)
    
    # Read back and verify tags is empty list
    record = get_job(temp_db, job_id)
    assert record.tags == []


def test_read_job_with_tags(temp_db: Path) -> None:
    """Test reading a job with tags."""
    spec = DBJobSpec(
        season="2026Q1",
        dataset_id="test_dataset",
        outputs_root="/tmp/outputs",
        config_snapshot={"test": "config"},
        config_hash="abc123",
    )
    
    job_id = create_job(temp_db, spec, tags=["test", "debug"])
    
    # Read back
    record = get_job(temp_db, job_id)
    assert isinstance(record.tags, list)
    assert "test" in record.tags
    assert "debug" in record.tags
    assert len(record.tags) == 2


def test_old_rows_fallback_to_empty_tags(temp_db: Path) -> None:
    """
    Test that old rows without tags_json fallback to empty list.
    
    This tests backward compatibility: existing jobs without tags_json
    should be readable and have tags=[].
    """
    import sqlite3
    import json
    
    # Manually insert a job without tags_json (simulating old schema)
    conn = sqlite3.connect(str(temp_db))
    try:
        # Insert job with old schema (no tags_json)
        conn.execute("""
            INSERT INTO jobs (
                job_id, status, created_at, updated_at,
                season, dataset_id, outputs_root, config_hash,
                config_snapshot_json, requested_pause
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "old-job-123",
            "QUEUED",
            "2026-01-01T00:00:00Z",
            "2026-01-01T00:00:00Z",
            "2026Q1",
            "test_dataset",
            "/tmp/outputs",
            "abc123",
            json.dumps({"test": "config"}),
            0,
        ))
        conn.commit()
    finally:
        conn.close()
    
    # Read back - should have tags=[]
    record = get_job(temp_db, "old-job-123")
    assert record.tags == []


def test_search_by_tag(temp_db: Path) -> None:
    """Test search_by_tag query helper."""
    spec1 = DBJobSpec(
        season="2026Q1",
        dataset_id="test_dataset",
        outputs_root="/tmp/outputs",
        config_snapshot={"test": "config1"},
        config_hash="abc123",
    )
    spec2 = DBJobSpec(
        season="2026Q1",
        dataset_id="test_dataset",
        outputs_root="/tmp/outputs",
        config_snapshot={"test": "config2"},
        config_hash="def456",
    )
    spec3 = DBJobSpec(
        season="2026Q1",
        dataset_id="test_dataset",
        outputs_root="/tmp/outputs",
        config_snapshot={"test": "config3"},
        config_hash="ghi789",
    )
    
    # Create jobs with different tags
    job1 = create_job(temp_db, spec1, tags=["production", "high-priority"])
    job2 = create_job(temp_db, spec2, tags=["staging", "low-priority"])
    job3 = create_job(temp_db, spec3, tags=["production", "medium-priority"])
    
    # Search for "production" tag
    results = search_by_tag(temp_db, "production")
    assert len(results) == 2
    job_ids = {r.job_id for r in results}
    assert job1 in job_ids
    assert job3 in job_ids
    assert job2 not in job_ids
    
    # Search for "staging" tag
    results = search_by_tag(temp_db, "staging")
    assert len(results) == 1
    assert results[0].job_id == job2
    
    # Search for non-existent tag
    results = search_by_tag(temp_db, "non-existent")
    assert len(results) == 0


def test_list_jobs_includes_tags(temp_db: Path) -> None:
    """Test that list_jobs includes tags in records."""
    spec = DBJobSpec(
        season="2026Q1",
        dataset_id="test_dataset",
        outputs_root="/tmp/outputs",
        config_snapshot={"test": "config"},
        config_hash="abc123",
    )
    
    job_id = create_job(temp_db, spec, tags=["test", "debug"])
    
    # List jobs
    jobs = list_jobs(temp_db, limit=10)
    assert len(jobs) >= 1
    
    # Find our job
    our_job = next((j for j in jobs if j.job_id == job_id), None)
    assert our_job is not None
    assert our_job.tags == ["test", "debug"]


