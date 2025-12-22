
"""Phase 14: Artifacts module tests."""

import json
import tempfile
from pathlib import Path

from FishBroWFS_V2.control.artifacts import (
    canonical_json_bytes,
    compute_sha256,
    write_atomic_json,
    build_job_manifest,
)


def test_canonical_json_bytes_deterministic():
    """Canonical JSON must be deterministic regardless of dict order."""
    obj1 = {"a": 1, "b": 2, "c": [3, 4]}
    obj2 = {"c": [3, 4], "b": 2, "a": 1}
    
    bytes1 = canonical_json_bytes(obj1)
    bytes2 = canonical_json_bytes(obj2)
    
    assert bytes1 == bytes2
    # Ensure no extra whitespace
    decoded = json.loads(bytes1.decode("utf-8"))
    assert decoded == obj1


def test_canonical_json_bytes_unicode():
    """Canonical JSON handles Unicode characters."""
    obj = {"name": "測試", "value": "🎯"}
    bytes_out = canonical_json_bytes(obj)
    decoded = json.loads(bytes_out.decode("utf-8"))
    assert decoded == obj


def test_compute_sha256():
    """SHA256 hash matches known value."""
    data = b"hello world"
    hash_hex = compute_sha256(data)
    # Expected SHA256 of "hello world"
    expected = "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"
    assert hash_hex == expected


def test_write_atomic_json():
    """Atomic write creates file with correct content."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "test.json"
        obj = {"x": 42, "y": "text"}
        
        write_atomic_json(path, obj)
        
        assert path.exists()
        content = json.loads(path.read_text(encoding="utf-8"))
        assert content == obj


def test_build_job_manifest():
    """Job manifest includes required fields."""
    job_spec = {
        "season": "2026Q1",
        "dataset_id": "CME_MNQ_v2",
        "outputs_root": "/tmp/outputs",
        "config_snapshot": {"param": 1.0},
        "config_hash": "abc123",
        "created_by": "test",
    }
    job_id = "job-123"
    
    manifest = build_job_manifest(job_spec, job_id)
    
    assert manifest["job_id"] == job_id
    assert manifest["season"] == job_spec["season"]
    assert manifest["dataset_id"] == job_spec["dataset_id"]
    assert manifest["config_hash"] == job_spec["config_hash"]
    assert "created_at" in manifest
    assert "manifest_hash" in manifest
    
    # Verify manifest_hash is SHA256 of canonical JSON
    import copy
    manifest_copy = copy.deepcopy(manifest)
    expected_hash = manifest_copy.pop("manifest_hash")
    computed = compute_sha256(canonical_json_bytes(manifest_copy))
    assert expected_hash == computed


