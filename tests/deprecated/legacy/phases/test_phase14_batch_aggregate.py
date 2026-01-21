
"""Phase 14: Batch aggregation tests."""

import tempfile
from pathlib import Path

from control.batch_aggregate import compute_batch_summary
from control.artifacts import canonical_json_bytes, compute_sha256


def test_compute_batch_summary_topk():
    """Batch summary selects top K jobs by score."""
    job_entries = [
        {"job_id": "job1", "score": 0.1},
        {"job_id": "job2", "score": 0.9},
        {"job_id": "job3", "score": 0.5},
        {"job_id": "job4", "score": 0.7},
        {"job_id": "job5", "score": 0.3},
    ]
    
    summary = compute_batch_summary(job_entries, top_k=3)
    
    assert summary["total_jobs"] == 5
    assert len(summary["top_k"]) == 3
    # Should be sorted descending by score
    assert [e["job_id"] for e in summary["top_k"]] == ["job2", "job4", "job3"]
    assert [e["score"] for e in summary["top_k"]] == [0.9, 0.7, 0.5]
    
    # Stats should contain counts
    stats = summary["stats"]
    assert stats["count"] == 5
    assert "mean_score" in stats
    assert "median_score" in stats
    assert "std_score" in stats
    
    # summary_hash should be SHA256 of canonical JSON of summary without hash
    import copy
    summary_copy = copy.deepcopy(summary)
    expected_hash = summary_copy.pop("summary_hash")
    computed = compute_sha256(canonical_json_bytes(summary_copy))
    assert expected_hash == computed


def test_compute_batch_summary_no_score():
    """Batch summary uses job_id ordering when score missing."""
    job_entries = [
        {"job_id": "jobC", "config": {"x": 1}},
        {"job_id": "jobA", "config": {"x": 2}},
        {"job_id": "jobB", "config": {"x": 3}},
    ]
    
    summary = compute_batch_summary(job_entries, top_k=2)
    
    # Top K by job_id alphabetical
    assert [e["job_id"] for e in summary["top_k"]] == ["jobA", "jobB"]
    
    # Stats should not contain score statistics
    stats = summary["stats"]
    assert stats["count"] == 3
    assert "mean_score" not in stats
    assert "median_score" not in stats
    assert "std_score" not in stats


def test_compute_batch_summary_empty():
    """Batch summary handles empty job list."""
    summary = compute_batch_summary([], top_k=5)
    
    assert summary["total_jobs"] == 0
    assert summary["top_k"] == []
    stats = summary["stats"]
    assert stats["count"] == 0
    assert "mean_score" not in stats


def test_compute_batch_summary_k_larger_than_total():
    """Top K larger than total jobs returns all jobs."""
    job_entries = [
        {"job_id": "job1", "score": 0.5},
        {"job_id": "job2", "score": 0.8},
    ]
    
    summary = compute_batch_summary(job_entries, top_k=10)
    
    assert len(summary["top_k"]) == 2
    assert [e["job_id"] for e in summary["top_k"]] == ["job2", "job1"]


def test_compute_batch_summary_deterministic():
    """Summary is deterministic regardless of input order."""
    job_entries1 = [
        {"job_id": "job1", "score": 0.5},
        {"job_id": "job2", "score": 0.8},
    ]
    job_entries2 = [
        {"job_id": "job2", "score": 0.8},
        {"job_id": "job1", "score": 0.5},
    ]
    
    summary1 = compute_batch_summary(job_entries1, top_k=5)
    summary2 = compute_batch_summary(job_entries2, top_k=5)
    
    # Top K order should be same (descending score)
    assert summary1["top_k"] == summary2["top_k"]
    # Stats should be identical
    assert summary1["stats"] == summary2["stats"]
    # Hash should match
    assert summary1["summary_hash"] == summary2["summary_hash"]


