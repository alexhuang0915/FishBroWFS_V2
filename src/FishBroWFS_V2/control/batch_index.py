
"""Batch-level index generation for Phase 14.

Deterministic batch index that references job manifests and provides immutable artifact references.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from FishBroWFS_V2.control.artifacts import canonical_json_bytes, sha256_bytes, write_json_atomic


def build_batch_index(
    artifacts_root: Path,
    batch_id: str,
    job_entries: list[dict],
    *,
    write: bool = True,
) -> dict:
    """Build batch index dict from job entries and optionally write to disk.
    
    The index contains:
      - batch_id
      - job_count
      - jobs: sorted list of job entries (by job_id)
      - index_hash: SHA256 of canonical JSON (excluding this field)
    
    Each job entry must contain at least:
      - job_id
      - manifest_hash (SHA256 of job manifest)
      - manifest_path: relative path from artifacts_root to manifest.json
    
    Args:
        artifacts_root: Base artifacts directory (e.g., outputs/artifacts).
        batch_id: Batch identifier.
        job_entries: List of job entry dicts (must contain job_id).
        write: If True (default), write index.json to artifacts_root / batch_id.
    
    Returns:
        Batch index dict with index_hash.
    
    Raises:
        ValueError: If duplicate job_id or missing required fields.
        OSError: If write fails.
    """
    # Validate job entries
    seen = set()
    for entry in job_entries:
        job_id = entry.get("job_id")
        if job_id is None:
            raise ValueError("job entry missing 'job_id'")
        if job_id in seen:
            raise ValueError(f"duplicate job_id in batch: {job_id}")
        seen.add(job_id)
        
        if "manifest_hash" not in entry:
            raise ValueError(f"job entry {job_id} missing 'manifest_hash'")
        if "manifest_path" not in entry:
            raise ValueError(f"job entry {job_id} missing 'manifest_path'")
    
    # Sort entries by job_id for deterministic ordering
    sorted_entries = sorted(job_entries, key=lambda e: e["job_id"])
    
    # Build index dict (without hash)
    index_without_hash = {
        "batch_id": batch_id,
        "job_count": len(sorted_entries),
        "jobs": sorted_entries,
        "schema_version": "1.0",
    }
    
    # Compute hash of canonical JSON (without hash field)
    canonical = canonical_json_bytes(index_without_hash)
    index_hash = sha256_bytes(canonical)
    
    # Add hash field
    index = {**index_without_hash, "index_hash": index_hash}
    
    # Write to disk if requested
    if write:
        batch_root = artifacts_root / batch_id
        write_batch_index(batch_root, index)
    
    return index


def write_batch_index(batch_root: Path, index: dict) -> dict:
    """Write batch index.json, ensuring it has a valid index_hash.

    If the index already contains an 'index_hash' field, it is kept (but validated).
    Otherwise, the function computes the SHA256 of the canonical JSON bytes
    (excluding the hash field itself) and adds it. The index is then written to
    batch_root / "index.json".

    Args:
        batch_root: Batch artifacts directory (must exist).
        index: Batch index dict (may contain 'index_hash').

    Returns:
        Updated index dict with 'index_hash' field.

    Raises:
        ValueError: If existing index_hash does not match computed hash.
        OSError: If directory does not exist or cannot write.
    """
    # Ensure directory exists
    batch_root.mkdir(parents=True, exist_ok=True)
    
    # Compute hash of canonical JSON (without hash field)
    index_without_hash = {k: v for k, v in index.items() if k != "index_hash"}
    canonical = canonical_json_bytes(index_without_hash)
    computed_hash = sha256_bytes(canonical)
    
    # Determine final hash
    if "index_hash" in index:
        if index["index_hash"] != computed_hash:
            raise ValueError("existing index_hash does not match computed hash")
        index_hash = index["index_hash"]
    else:
        index_hash = computed_hash
    
    # Ensure index contains hash
    index_with_hash = {**index_without_hash, "index_hash": index_hash}
    
    # Write index.json
    index_path = batch_root / "index.json"
    write_json_atomic(index_path, index_with_hash)
    
    return index_with_hash


def read_batch_index(batch_root: Path) -> dict:
    """Read batch index.json.
    
    Args:
        batch_root: Batch artifacts directory.
    
    Returns:
        Parsed index dict (including index_hash).
    
    Raises:
        FileNotFoundError: If index.json does not exist.
        json.JSONDecodeError: If file is malformed.
    """
    index_path = batch_root / "index.json"
    if not index_path.exists():
        raise FileNotFoundError(f"batch index not found: {index_path}")
    
    data = json.loads(index_path.read_text(encoding="utf-8"))
    return data


def validate_batch_index(index: dict) -> bool:
    """Validate batch index integrity.
    
    Checks that index_hash matches the SHA256 of the rest of the index.
    
    Args:
        index: Batch index dict (must contain 'index_hash').
    
    Returns:
        True if hash matches, False otherwise.
    """
    if "index_hash" not in index:
        return False
    
    # Extract hash and compute from rest
    provided_hash = index["index_hash"]
    index_without_hash = {k: v for k, v in index.items() if k != "index_hash"}
    
    canonical = canonical_json_bytes(index_without_hash)
    computed_hash = sha256_bytes(canonical)
    
    return provided_hash == computed_hash


