
"""Manifest Tree Completeness verification tool.

This module provides functions to verify the integrity and completeness
of manifest trees for tamper-proof sealing.
"""

from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional, Any
from dataclasses import dataclass

from FishBroWFS_V2.control.artifacts import compute_sha256, canonical_json_bytes
from FishBroWFS_V2.core.schemas.manifest import UnifiedManifest


@dataclass
class VerificationResult:
    """Result of manifest verification."""
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    manifest_type: str
    manifest_id: str


class ManifestVerifier:
    """Verifies manifest tree completeness and integrity."""
    
    def __init__(self, root_dir: Path):
        """
        Initialize verifier with root directory.
        
        Args:
            root_dir: Root directory containing manifests to verify
        """
        self.root_dir = root_dir.resolve()
        self.allowed_extensions = {'.json', '.txt', '.csv', '.parquet', '.feather', '.png', '.jpg', '.jpeg'}
    
    def verify_manifest_file(self, manifest_path: Path) -> VerificationResult:
        """
        Verify a single manifest file.
        
        Args:
            manifest_path: Path to manifest file
            
        Returns:
            VerificationResult with validation status
        """
        errors = []
        warnings = []
        
        try:
            # Read and parse manifest
            manifest_bytes = manifest_path.read_bytes()
            manifest_dict = json.loads(manifest_bytes.decode('utf-8'))
            
            # Validate against unified schema
            try:
                manifest = UnifiedManifest(**manifest_dict)
            except Exception as e:
                errors.append(f"Schema validation failed: {e}")
                return VerificationResult(
                    is_valid=False,
                    errors=errors,
                    warnings=warnings,
                    manifest_type="unknown",
                    manifest_id="unknown"
                )
            
            # Verify manifest self-hash
            if not self._verify_self_hash(manifest_dict, manifest_bytes):
                errors.append("Manifest self-hash verification failed")
            
            # Verify referenced files exist and match checksums
            file_errors = self._verify_referenced_files(manifest_path.parent, manifest_dict)
            errors.extend(file_errors)
            
            # Check for completeness (all files in directory are accounted for)
            completeness_errors = self._verify_directory_completeness(manifest_path.parent, manifest_dict)
            errors.extend(completeness_errors)
            
            return VerificationResult(
                is_valid=len(errors) == 0,
                errors=errors,
                warnings=warnings,
                manifest_type=manifest.manifest_type,
                manifest_id=manifest.id
            )
            
        except Exception as e:
            errors.append(f"Failed to read/parse manifest: {e}")
            return VerificationResult(
                is_valid=False,
                errors=errors,
                warnings=warnings,
                manifest_type="unknown",
                manifest_id="unknown"
            )
    
    def _verify_self_hash(self, manifest_dict: Dict[str, Any], manifest_bytes: bytes) -> bool:
        """Verify manifest's self-hash (manifest_sha256 field)."""
        if 'manifest_sha256' not in manifest_dict:
            return False
        
        # Remove the hash field before computing
        manifest_without_hash = dict(manifest_dict)
        manifest_without_hash.pop('manifest_sha256', None)
        
        # Compute canonical JSON
        canonical_bytes = canonical_json_bytes(manifest_without_hash)
        computed_hash = compute_sha256(canonical_bytes)
        
        return computed_hash == manifest_dict['manifest_sha256']
    
    def _verify_referenced_files(self, base_dir: Path, manifest_dict: Dict[str, Any]) -> List[str]:
        """Verify that all referenced files exist and match their checksums."""
        errors = []
        
        # Check files in checksums fields
        checksum_fields = ['checksums', 'export_checksums', 'plan_checksums', 
                          'view_checksums', 'quality_checksums']
        
        for field in checksum_fields:
            if field in manifest_dict and isinstance(manifest_dict[field], dict):
                checksums = manifest_dict[field]
                for filename, expected_hash in checksums.items():
                    file_path = base_dir / filename
                    if not file_path.exists():
                        errors.append(f"Referenced file not found: {filename}")
                        continue
                    
                    # Compute file hash
                    try:
                        file_hash = compute_sha256(file_path.read_bytes())
                        if file_hash != expected_hash:
                            errors.append(f"Hash mismatch for {filename}: expected {expected_hash}, got {file_hash}")
                    except Exception as e:
                        errors.append(f"Failed to compute hash for {filename}: {e}")
        
        return errors
    
    def _verify_directory_completeness(self, dir_path: Path, manifest_dict: Dict[str, Any]) -> List[str]:
        """
        Verify that all files in the directory are accounted for in the manifest.
        
        This ensures tamper-proof sealing: any file added, removed, or modified
        without updating the manifest will cause verification to fail.
        """
        errors = []
        
        # Get all files in directory (excluding temporary files and manifests)
        all_files = set()
        for file_path in dir_path.iterdir():
            if file_path.is_file():
                # Skip temporary files and .tmp files
                if file_path.suffix == '.tmp' or file_path.name.startswith('.'):
                    continue
                # Skip manifest files themselves (they're verified separately)
                if 'manifest' in file_path.name.lower():
                    continue
                all_files.add(file_path.name)
        
        # Get files referenced in manifest
        referenced_files = set()
        
        # Add files from checksums fields
        checksum_fields = ['checksums', 'export_checksums', 'plan_checksums', 
                          'view_checksums', 'quality_checksums']
        
        for field in checksum_fields:
            if field in manifest_dict and isinstance(manifest_dict[field], dict):
                referenced_files.update(manifest_dict[field].keys())
        
        # Check for files in directory not referenced in manifest
        unreferenced = all_files - referenced_files
        if unreferenced:
            errors.append(f"Files in directory not referenced in manifest: {sorted(unreferenced)}")
        
        # Check for files referenced in manifest but not in directory
        missing = referenced_files - all_files
        if missing:
            errors.append(f"Files referenced in manifest but not found in directory: {sorted(missing)}")
        
        return errors
    
    def verify_manifest_tree(self, start_path: Optional[Path] = None) -> List[VerificationResult]:
        """
        Recursively verify all manifests in a directory tree.
        
        Args:
            start_path: Starting directory (defaults to root_dir)
            
        Returns:
            List of verification results for all manifests found
        """
        if start_path is None:
            start_path = self.root_dir
        
        results = []
        
        # Look for manifest files
        manifest_patterns = ['*manifest*.json', 'manifest*.json', '*_manifest.json']
        
        for pattern in manifest_patterns:
            for manifest_path in start_path.rglob(pattern):
                # Skip if not a file or in excluded directories
                if not manifest_path.is_file():
                    continue
                
                # Skip temporary files
                if manifest_path.suffix == '.tmp' or manifest_path.name.startswith('.'):
                    continue
                
                result = self.verify_manifest_file(manifest_path)
                results.append(result)
        
        return results


def verify_manifest(manifest_path: str | Path) -> VerificationResult:
    """
    Convenience function to verify a single manifest file.
    
    Args:
        manifest_path: Path to manifest file
        
    Returns:
        VerificationResult
    """
    verifier = ManifestVerifier(Path(manifest_path).parent)
    return verifier.verify_manifest_file(Path(manifest_path))


def verify_directory(dir_path: str | Path) -> List[VerificationResult]:
    """
    Convenience function to verify all manifests in a directory.
    
    Args:
        dir_path: Directory to scan for manifests
        
    Returns:
        List of VerificationResult objects
    """
    verifier = ManifestVerifier(Path(dir_path))
    return verifier.verify_manifest_tree()


def print_verification_results(results: List[VerificationResult]) -> None:
    """Print verification results in a readable format."""
    total = len(results)
    valid = sum(1 for r in results if r.is_valid)
    
    print(f"=== Manifest Verification Results ===")
    print(f"Total manifests: {total}")
    print(f"Valid: {valid}")
    print(f"Invalid: {total - valid}")
    print()
    
    for i, result in enumerate(results, 1):
        status = "✓ PASS" if result.is_valid else "✗ FAIL"
        print(f"{i}. {status} - {result.manifest_type} ({result.manifest_id})")
        
        if result.errors:
            print(f"   Errors:")
            for error in result.errors:
                print(f"     - {error}")
        
        if result.warnings:
            print(f"   Warnings:")
            for warning in result.warnings:
                print(f"     - {warning}")
        
        print()


def compute_files_listing(root_dir: Path, allowed_scope: Optional[List[str]] = None) -> List[Dict[str, str]]:
    """
    Compute listing of all files in directory with SHA256 checksums.
    
    Args:
        root_dir: Root directory to scan
        allowed_scope: Optional list of relative paths to include. If None, include all files.
        
    Returns:
        List of dicts with keys "rel_path" and "sha256", sorted by rel_path asc.
    """
    files = []
    
    for file_path in root_dir.iterdir():
        if not file_path.is_file():
            continue
        
        # Skip temporary files and hidden files
        if file_path.suffix == '.tmp' or file_path.name.startswith('.'):
            continue
        
        # Skip manifest files themselves (they are the metadata, not part of the content)
        if 'manifest' in file_path.name.lower() and file_path.suffix in ('.json', '.yaml', '.yml'):
            continue
        
        rel_path = file_path.name
        
        # If allowed_scope is provided, filter by it
        if allowed_scope is not None and rel_path not in allowed_scope:
            continue
        
        # Compute SHA256
        try:
            file_hash = compute_sha256(file_path.read_bytes())
        except Exception:
            # Skip files that cannot be read
            continue
        
        files.append({
            "rel_path": rel_path,
            "sha256": file_hash
        })
    
    # Sort by rel_path ascending
    files.sort(key=lambda x: x["rel_path"])
    return files


def compute_files_sha256(files_listing: List[Dict[str, str]]) -> str:
    """
    Compute combined SHA256 of all files by concatenating their individual hashes.
    
    Args:
        files_listing: List of dicts with "rel_path" and "sha256"
        
    Returns:
        SHA256 hex string of concatenated hashes (sorted by rel_path)
    """
    # Ensure sorted by rel_path
    sorted_files = sorted(files_listing, key=lambda x: x["rel_path"])
    
    # Concatenate all SHA256 strings
    concatenated = "".join(f["sha256"] for f in sorted_files)
    
    # Compute SHA256 of the concatenated string (as UTF-8 bytes)
    return hashlib.sha256(concatenated.encode("utf-8")).hexdigest()


def verify_manifest_completeness(root_dir: Path, manifest_dict: Dict[str, Any]) -> None:
    """
    Verify manifest completeness and integrity.
    
    Validates:
    1. Files listing matches exactly (no extra/missing files)
    2. Each file's SHA256 matches
    3. files_sha256 field is correct
    4. manifest_sha256 field is correct
    
    Args:
        root_dir: Directory containing the files
        manifest_dict: Parsed manifest JSON as dict
        
    Raises:
        ValueError: If any verification fails
    """
    errors = []
    
    # 1. Verify files listing exists
    if "files" not in manifest_dict:
        raise ValueError("Manifest missing 'files' field")
    
    manifest_files = manifest_dict.get("files", [])
    if not isinstance(manifest_files, list):
        raise ValueError("Manifest 'files' must be a list")
    
    # Convert to dict for easier lookup
    manifest_file_map = {f["rel_path"]: f["sha256"] for f in manifest_files if isinstance(f, dict) and "rel_path" in f and "sha256" in f}
    
    # 2. Compute actual files listing (include all files, not just those in manifest)
    # This ensures we detect extra files added to the directory
    actual_files = compute_files_listing(root_dir, allowed_scope=None)
    actual_file_map = {f["rel_path"]: f["sha256"] for f in actual_files}
    
    # Check for missing files in manifest
    missing_in_manifest = set(actual_file_map.keys()) - set(manifest_file_map.keys())
    if missing_in_manifest:
        errors.append(f"Files in directory not in manifest: {sorted(missing_in_manifest)}")
    
    # Check for extra files in manifest not in directory
    extra_in_manifest = set(manifest_file_map.keys()) - set(actual_file_map.keys())
    if extra_in_manifest:
        errors.append(f"Files in manifest not found in directory: {sorted(extra_in_manifest)}")
    
    # 3. Verify SHA256 matches for common files
    common = set(manifest_file_map.keys()) & set(actual_file_map.keys())
    for rel_path in common:
        if manifest_file_map[rel_path] != actual_file_map[rel_path]:
            errors.append(f"SHA256 mismatch for {rel_path}: manifest={manifest_file_map[rel_path]}, actual={actual_file_map[rel_path]}")
    
    # 4. Verify files_sha256 if present
    if "files_sha256" in manifest_dict:
        expected_files_sha256 = manifest_dict["files_sha256"]
        computed_files_sha256 = compute_files_sha256(actual_files)
        if expected_files_sha256 != computed_files_sha256:
            errors.append(f"files_sha256 mismatch: expected {expected_files_sha256}, computed {computed_files_sha256}")
    
    # 5. Verify manifest_sha256 if present
    if "manifest_sha256" in manifest_dict:
        # Create copy without manifest_sha256 field
        manifest_without_hash = dict(manifest_dict)
        manifest_without_hash.pop("manifest_sha256", None)
        
        # Compute canonical JSON hash
        canonical_bytes = canonical_json_bytes(manifest_without_hash)
        computed_hash = compute_sha256(canonical_bytes)
        
        if manifest_dict["manifest_sha256"] != computed_hash:
            errors.append(f"manifest_sha256 mismatch: expected {manifest_dict['manifest_sha256']}, computed {computed_hash}")
    
    if errors:
        raise ValueError("Manifest verification failed:\n" + "\n".join(f"  - {e}" for e in errors))


def verify_manifest(root_dir: str | Path, manifest_json: dict | str | Path) -> None:
    """
    Verify manifest completeness and integrity (task‑required signature).
    
    Args:
        root_dir: Directory containing the files
        manifest_json: Either a dict of parsed manifest, or a path to manifest file,
                      or a string of JSON content.
    
    Raises:
        ValueError: If verification fails
    """
    root_dir = Path(root_dir)
    
    # Parse manifest_json based on its type
    if isinstance(manifest_json, dict):
        manifest_dict = manifest_json
    elif isinstance(manifest_json, (str, Path)):
        path = Path(manifest_json)
        if path.exists():
            manifest_dict = json.loads(path.read_text(encoding="utf-8"))
        else:
            # Try to parse as JSON string
            try:
                manifest_dict = json.loads(manifest_json)
            except json.JSONDecodeError:
                raise ValueError(f"manifest_json is not a valid file path or JSON string: {manifest_json}")
    else:
        raise TypeError(f"manifest_json must be dict, str, or Path, got {type(manifest_json)}")
    
    # Delegate to verify_manifest_completeness
    verify_manifest_completeness(root_dir, manifest_dict)


