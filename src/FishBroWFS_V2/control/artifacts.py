"""Artifact storage, hashing, and manifest generation for Phase 14.

Deterministic canonical JSON, SHA256 hashing, atomic writes, and immutable artifact manifests.
"""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any


def canonical_json_bytes(obj: object) -> bytes:
    """Serialize object to canonical JSON bytes.
    
    Uses sort_keys=True, ensure_ascii=False, separators=(',', ':') for deterministic ordering.
    
    Args:
        obj: JSON-serializable object (dict, list, str, int, float, bool, None)
    
    Returns:
        UTF-8 encoded bytes of canonical JSON representation.
    
    Raises:
        TypeError: If obj is not JSON serializable.
    """
    return json.dumps(
        obj,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    """Compute SHA256 hash of bytes.
    
    Args:
        data: Input bytes.
    
    Returns:
        Lowercase hex digest string.
    """
    return hashlib.sha256(data).hexdigest()


# Alias for compatibility with existing code
compute_sha256 = sha256_bytes


def write_json_atomic(path: Path, data: dict) -> None:
    """Atomically write JSON dict to file.
    
    Writes to a temporary file in the same directory, then renames to target.
    Ensures no partial writes are visible.
    
    Args:
        path: Target file path.
        data: JSON-serializable dict.
    
    Raises:
        OSError: If file cannot be written.
    """
    # Ensure parent directory exists
    path.parent.mkdir(parents=True, exist_ok=True)
    
    # Write to temporary file
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.tmp.",
        delete=False,
    ) as f:
        json.dump(
            data,
            f,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
        tmp_path = Path(f.name)
    
    # Atomic rename (POSIX guarantees atomicity)
    try:
        tmp_path.replace(path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def compute_job_artifacts_root(artifacts_root: Path, batch_id: str, job_id: str) -> Path:
    """Compute job artifacts root directory.
    
    Path pattern: artifacts/{batch_id}/{job_id}/
    
    Args:
        artifacts_root: Base artifacts directory (e.g., outputs/artifacts).
        batch_id: Batch identifier.
        job_id: Job identifier.
    
    Returns:
        Path to job artifacts directory.
    """
    return artifacts_root / batch_id / job_id


def build_job_manifest(job_spec: dict, job_id: str) -> dict:
    """Build job manifest dict with hash, without writing to disk.
    
    The manifest includes:
      - job_id
      - season, dataset_id, config_hash, created_by (from job_spec)
      - created_at (ISO 8601 timestamp)
      - manifest_hash (SHA256 of canonical JSON excluding this field)
    
    Args:
        job_spec: Job specification dict (must contain season, dataset_id,
                  config_hash, created_by, config_snapshot, outputs_root).
        job_id: Job identifier.
    
    Returns:
        Manifest dict with manifest_hash.
    
    Raises:
        KeyError: If required fields missing.
    """
    import datetime
    
    # Required fields
    required = ["season", "dataset_id", "config_hash", "created_by", "config_snapshot", "outputs_root"]
    for field in required:
        if field not in job_spec:
            raise KeyError(f"job_spec missing required field: {field}")
    
    # Build base manifest (without hash)
    manifest = {
        "job_id": job_id,
        "season": job_spec["season"],
        "dataset_id": job_spec["dataset_id"],
        "config_hash": job_spec["config_hash"],
        "created_by": job_spec["created_by"],
        "config_snapshot": job_spec["config_snapshot"],
        "outputs_root": job_spec["outputs_root"],
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    
    # Compute hash of canonical JSON (without hash field)
    canonical = canonical_json_bytes(manifest)
    manifest_hash = sha256_bytes(canonical)
    
    # Add hash field
    manifest_with_hash = {**manifest, "manifest_hash": manifest_hash}
    return manifest_with_hash


def write_job_manifest(job_root: Path, manifest: dict) -> dict:
    """Write job manifest.json and compute its hash.

    The manifest must be a JSON-serializable dict. The function adds a
    'manifest_hash' field containing the SHA256 of the canonical JSON bytes
    (excluding the hash field itself). The manifest is then written to
    job_root / "manifest.json".

    Args:
        job_root: Job artifacts directory (must exist).
        manifest: Manifest dict (must not contain 'manifest_hash' key).

    Returns:
        Updated manifest dict with 'manifest_hash' field.

    Raises:
        ValueError: If manifest already contains 'manifest_hash'.
        OSError: If directory does not exist or cannot write.
    """
    if "manifest_hash" in manifest:
        raise ValueError("manifest must not contain 'manifest_hash' key")
    
    # Ensure directory exists
    job_root.mkdir(parents=True, exist_ok=True)
    
    # Compute hash of canonical JSON (without hash field)
    canonical = canonical_json_bytes(manifest)
    manifest_hash = sha256_bytes(canonical)
    
    # Add hash field
    manifest_with_hash = {**manifest, "manifest_hash": manifest_hash}
    
    # Write manifest.json
    manifest_path = job_root / "manifest.json"
    write_json_atomic(manifest_path, manifest_with_hash)
    
    return manifest_with_hash


# Aliases for compatibility
compute_sha256 = sha256_bytes
write_atomic_json = write_json_atomic
# build_job_manifest is now the function above, not an alias