
"""Test Manifest Tree Completeness (tamper-proof sealing)."""
import pytest
import tempfile
import json
import hashlib
from pathlib import Path

from FishBroWFS_V2.utils.manifest_verify import (
    compute_files_listing,
    compute_files_sha256,
    verify_manifest,
    verify_manifest_completeness,
)


def test_manifest_tree_completeness_basic():
    """Basic test: valid manifest should pass verification."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        
        # Create some files
        (root / "file1.txt").write_text("content1")
        (root / "file2.json").write_text('{"key": "value"}')
        
        # Compute files listing
        files = compute_files_listing(root)
        files_sha256 = compute_files_sha256(files)
        
        # Build manifest
        manifest = {
            "manifest_type": "test",
            "manifest_version": "1.0",
            "id": "test_id",
            "files": files,
            "files_sha256": files_sha256,
        }
        
        # Compute manifest_sha256 (excluding the hash field)
        manifest_without_hash = dict(manifest)
        # Use canonical JSON from project
        from FishBroWFS_V2.control.artifacts import canonical_json_bytes, compute_sha256
        canonical = canonical_json_bytes(manifest_without_hash)
        manifest_sha256 = compute_sha256(canonical)
        manifest["manifest_sha256"] = manifest_sha256
        
        # Write manifest file
        manifest_path = root / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2))
        
        # Verification should pass
        verify_manifest(root, manifest)
        verify_manifest_completeness(root, manifest)


def test_tamper_extra_file():
    """Tamper test: adding an extra file should cause verification failure."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        
        # Create original files
        (root / "file1.txt").write_text("content1")
        (root / "file2.json").write_text('{"key": "value"}')
        
        # Compute files listing
        files = compute_files_listing(root)
        files_sha256 = compute_files_sha256(files)
        
        # Build manifest
        manifest = {
            "manifest_type": "test",
            "manifest_version": "1.0",
            "id": "test_id",
            "files": files,
            "files_sha256": files_sha256,
        }
        
        # Compute manifest_sha256
        from FishBroWFS_V2.control.artifacts import canonical_json_bytes, compute_sha256
        canonical = canonical_json_bytes(manifest)
        manifest_sha256 = compute_sha256(canonical)
        manifest["manifest_sha256"] = manifest_sha256
        
        # Write manifest file
        manifest_path = root / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2))
        
        # Add an extra file not referenced in manifest
        (root / "extra.txt").write_text("tampered")
        
        # Verification should fail
        with pytest.raises(ValueError, match="Files in directory not in manifest"):
            verify_manifest(root, manifest)


def test_tamper_delete_file():
    """Tamper test: deleting a file should cause verification failure."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        
        # Create original files
        (root / "file1.txt").write_text("content1")
        (root / "file2.json").write_text('{"key": "value"}')
        
        # Compute files listing
        files = compute_files_listing(root)
        files_sha256 = compute_files_sha256(files)
        
        # Build manifest
        manifest = {
            "manifest_type": "test",
            "manifest_version": "1.0",
            "id": "test_id",
            "files": files,
            "files_sha256": files_sha256,
        }
        
        # Compute manifest_sha256
        from FishBroWFS_V2.control.artifacts import canonical_json_bytes, compute_sha256
        canonical = canonical_json_bytes(manifest)
        manifest_sha256 = compute_sha256(canonical)
        manifest["manifest_sha256"] = manifest_sha256
        
        # Write manifest file
        manifest_path = root / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2))
        
        # Delete a file referenced in manifest
        (root / "file1.txt").unlink()
        
        # Verification should fail
        with pytest.raises(ValueError, match="Files in manifest not found in directory"):
            verify_manifest(root, manifest)


def test_tamper_modify_content():
    """Tamper test: modifying file content should cause verification failure."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        
        # Create original files
        (root / "file1.txt").write_text("content1")
        (root / "file2.json").write_text('{"key": "value"}')
        
        # Compute files listing
        files = compute_files_listing(root)
        files_sha256 = compute_files_sha256(files)
        
        # Build manifest
        manifest = {
            "manifest_type": "test",
            "manifest_version": "1.0",
            "id": "test_id",
            "files": files,
            "files_sha256": files_sha256,
        }
        
        # Compute manifest_sha256
        from FishBroWFS_V2.control.artifacts import canonical_json_bytes, compute_sha256
        canonical = canonical_json_bytes(manifest)
        manifest_sha256 = compute_sha256(canonical)
        manifest["manifest_sha256"] = manifest_sha256
        
        # Write manifest file
        manifest_path = root / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2))
        
        # Modify file content
        (root / "file1.txt").write_text("modified content")
        
        # Verification should fail
        with pytest.raises(ValueError, match="SHA256 mismatch"):
            verify_manifest(root, manifest)


def test_tamper_manifest_sha256():
    """Tamper test: modifying manifest_sha256 should cause verification failure."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        
        # Create original files
        (root / "file1.txt").write_text("content1")
        
        # Compute files listing
        files = compute_files_listing(root)
        files_sha256 = compute_files_sha256(files)
        
        # Build manifest
        manifest = {
            "manifest_type": "test",
            "manifest_version": "1.0",
            "id": "test_id",
            "files": files,
            "files_sha256": files_sha256,
        }
        
        # Compute manifest_sha256
        from FishBroWFS_V2.control.artifacts import canonical_json_bytes, compute_sha256
        canonical = canonical_json_bytes(manifest)
        manifest_sha256 = compute_sha256(canonical)
        manifest["manifest_sha256"] = manifest_sha256
        
        # Write manifest file
        manifest_path = root / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2))
        
        # Tamper with manifest_sha256 field
        manifest["manifest_sha256"] = "0" * 64
        
        # Verification should fail
        with pytest.raises(ValueError, match="manifest_sha256 mismatch"):
            verify_manifest(root, manifest)


def test_tamper_files_sha256():
    """Tamper test: modifying files_sha256 should cause verification failure."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        
        # Create original files
        (root / "file1.txt").write_text("content1")
        
        # Compute files listing
        files = compute_files_listing(root)
        files_sha256 = compute_files_sha256(files)
        
        # Build manifest
        manifest = {
            "manifest_type": "test",
            "manifest_version": "1.0",
            "id": "test_id",
            "files": files,
            "files_sha256": files_sha256,
        }
        
        # Compute manifest_sha256
        from FishBroWFS_V2.control.artifacts import canonical_json_bytes, compute_sha256
        canonical = canonical_json_bytes(manifest)
        manifest_sha256 = compute_sha256(canonical)
        manifest["manifest_sha256"] = manifest_sha256
        
        # Write manifest file
        manifest_path = root / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2))
        
        # Tamper with files_sha256 field
        manifest["files_sha256"] = "0" * 64
        
        # Verification should fail
        with pytest.raises(ValueError, match="files_sha256 mismatch"):
            verify_manifest(root, manifest)


def test_real_plan_manifest_tamper():
    """Test with a real plan manifest structure."""
    with tempfile.TemporaryDirectory() as tmpdir:
        plan_dir = Path(tmpdir) / "plan"
        plan_dir.mkdir()
        
        # Create minimal plan package files
        (plan_dir / "portfolio_plan.json").write_text('{"plan_id": "test"}')
        (plan_dir / "plan_metadata.json").write_text('{"meta": "data"}')
        (plan_dir / "plan_checksums.json").write_text('{"portfolio_plan.json": "hash1", "plan_metadata.json": "hash2"}')
        
        # Compute SHA256 for each file
        from FishBroWFS_V2.control.artifacts import compute_sha256
        files = []
        for rel_path in ["portfolio_plan.json", "plan_metadata.json", "plan_checksums.json"]:
            file_path = plan_dir / rel_path
            files.append({
                "rel_path": rel_path,
                "sha256": compute_sha256(file_path.read_bytes())
            })
        
        # Sort by rel_path
        files.sort(key=lambda x: x["rel_path"])
        
        # Compute files_sha256
        concatenated = "".join(f["sha256"] for f in files)
        files_sha256 = hashlib.sha256(concatenated.encode("utf-8")).hexdigest()
        
        # Build manifest
        manifest = {
            "manifest_type": "plan",
            "manifest_version": "1.0",
            "id": "test_plan",
            "plan_id": "test_plan",
            "generated_at_utc": "2025-01-01T00:00:00Z",
            "source": {"season": "test"},
            "checksums": {"portfolio_plan.json": files[0]["sha256"], "plan_metadata.json": files[1]["sha256"]},
            "files": files,
            "files_sha256": files_sha256,
        }
        
        # Compute manifest_sha256
        from FishBroWFS_V2.control.artifacts import canonical_json_bytes
        canonical = canonical_json_bytes(manifest)
        manifest_sha256 = compute_sha256(canonical)
        manifest["manifest_sha256"] = manifest_sha256
        
        # Write manifest file
        manifest_path = plan_dir / "plan_manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2))
        
        # Verification should pass
        verify_manifest(plan_dir, manifest)
        
        # Tamper: add extra file
        (plan_dir / "extra.txt").write_text("tampered")
        
        # Verification should fail
        with pytest.raises(ValueError, match="Files in directory not in manifest"):
            verify_manifest(plan_dir, manifest)


