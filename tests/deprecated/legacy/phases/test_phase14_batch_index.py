
"""Phase 14: Batch index tests."""

import json
import tempfile
from pathlib import Path

from control.batch_index import build_batch_index
from control.artifacts import canonical_json_bytes, compute_sha256


def test_build_batch_index_deterministic():
    """Batch index is deterministic regardless of job entry order."""
    job_entries = [
        {"job_id": "job1", "score": 0.5, "manifest_hash": "abc123", "manifest_path": "batch-123/job1/manifest.json"},
        {"job_id": "job2", "score": 0.3, "manifest_hash": "def456", "manifest_path": "batch-123/job2/manifest.json"},
        {"job_id": "job3", "score": 0.8, "manifest_hash": "ghi789", "manifest_path": "batch-123/job3/manifest.json"},
    ]
    job_entries_shuffled = [
        {"job_id": "job3", "score": 0.8, "manifest_hash": "ghi789", "manifest_path": "batch-123/job3/manifest.json"},
        {"job_id": "job1", "score": 0.5, "manifest_hash": "abc123", "manifest_path": "batch-123/job1/manifest.json"},
        {"job_id": "job2", "score": 0.3, "manifest_hash": "def456", "manifest_path": "batch-123/job2/manifest.json"},
    ]
    
    with tempfile.TemporaryDirectory() as tmpdir:
        artifacts_root = Path(tmpdir)
        batch_id = "batch-123"
        
        index1 = build_batch_index(artifacts_root, batch_id, job_entries)
        index2 = build_batch_index(artifacts_root, batch_id, job_entries_shuffled)
        
        # Index should be identical (entries sorted by job_id)
        assert index1 == index2
        
        # Verify structure
        assert index1["batch_id"] == batch_id
        assert index1["job_count"] == 3
        assert len(index1["jobs"]) == 3
        # Entries should be sorted by job_id
        assert [e["job_id"] for e in index1["jobs"]] == ["job1", "job2", "job3"]
        
        # Verify index_hash is SHA256 of canonical JSON of index without hash
        import copy
        index_copy = copy.deepcopy(index1)
        expected_hash = index_copy.pop("index_hash")
        computed = compute_sha256(canonical_json_bytes(index_copy))
        assert expected_hash == computed


def test_build_batch_index_without_score():
    """Batch index works when jobs have no score field."""
    job_entries = [
        {"job_id": "jobA", "config": {"x": 1}, "manifest_hash": "hashA", "manifest_path": "batch-no-score/jobA/manifest.json"},
        {"job_id": "jobB", "config": {"x": 2}, "manifest_hash": "hashB", "manifest_path": "batch-no-score/jobB/manifest.json"},
    ]
    
    with tempfile.TemporaryDirectory() as tmpdir:
        artifacts_root = Path(tmpdir)
        batch_id = "batch-no-score"
        
        index = build_batch_index(artifacts_root, batch_id, job_entries)
        
        assert index["batch_id"] == batch_id
        assert index["job_count"] == 2
        # Entries sorted by job_id
        assert [e["job_id"] for e in index["jobs"]] == ["jobA", "jobB"]


def test_build_batch_index_writes_file():
    """Batch index writes index.json to artifacts directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        artifacts_root = Path(tmpdir)
        batch_id = "batch-write"
        job_entries = [{"job_id": "job1", "manifest_hash": "hash1", "manifest_path": "batch-write/job1/manifest.json"}]
        
        index = build_batch_index(artifacts_root, batch_id, job_entries)
        
        # Check file exists
        batch_dir = artifacts_root / batch_id
        index_file = batch_dir / "index.json"
        assert index_file.exists()
        
        # Content matches returned index
        loaded = json.loads(index_file.read_text(encoding="utf-8"))
        assert loaded == index


