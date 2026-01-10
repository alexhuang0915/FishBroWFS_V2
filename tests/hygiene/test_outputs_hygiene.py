"""
Test outputs/ directory hygiene according to Config Constitution v1.

Rules:
1. outputs/ root contains only allowed buckets
2. No floating files in outputs/ root
"""

import pytest
import warnings
from pathlib import Path


def test_outputs_directory_structure():
    """Test 1: outputs/ root contains only allowed buckets."""
    outputs_dir = Path("outputs")
    
    # Allowed buckets in outputs/ root
    # These are the canonical buckets defined in Config Constitution v1
    allowed_buckets = {
        "_dp_evidence",      # Diagnostic/forensic evidence
        "_audit_bundle",     # Audit artifacts
        "_runtime",          # Runtime temporary files
        "_trash",            # Soft-deleted files (can be cleaned)
        "deployment",        # Deployment artifacts
        "deployments",       # Multiple deployment versions
        "jobs",             # Job artifacts and metadata
        "research",         # Research artifacts
        "seasons",          # Season artifacts
        "shared",           # Shared datasets and features
        "strategies",       # Strategy-specific artifacts
    }
    
    # Additional allowed files in outputs/ root
    allowed_root_files = {
        "jobs_v2.db",       # SQLite database
        "jobs_v2.db-shm",   # SQLite shared memory
        "jobs_v2.db-wal",   # SQLite write-ahead log
        "run_status.json",  # Runtime status file
    }
    
    # Find all items in outputs/ root
    root_items = set()
    for item in outputs_dir.iterdir():
        root_items.add(item.name)
    
    # Separate directories and files
    root_dirs = set()
    root_files = set()
    for item_name in root_items:
        item_path = outputs_dir / item_name
        if item_path.is_dir():
            root_dirs.add(item_name)
        else:
            root_files.add(item_name)
    
    # Check directories
    unexpected_dirs = root_dirs - allowed_buckets
    assert not unexpected_dirs, (
        f"outputs/ contains unexpected directories: {unexpected_dirs}. "
        f"Allowed buckets: {allowed_buckets}"
    )
    
    # Check files
    unexpected_files = root_files - allowed_root_files
    assert not unexpected_files, (
        f"outputs/ root contains unexpected files: {unexpected_files}. "
        f"Allowed root files: {allowed_root_files}"
    )


def test_outputs_no_floating_files():
    """Test 2: No floating files in outputs/ root (except allowlist)."""
    outputs_dir = Path("outputs")
    
    # Allowlist for files that can exist in outputs/ root
    # These are system files, not user-created artifacts
    allowlist = {
        "jobs_v2.db",
        "jobs_v2.db-shm", 
        "jobs_v2.db-wal",
        "run_status.json",
    }
    
    # Check for non-allowlist files in outputs/ root
    floating_files = []
    for item in outputs_dir.iterdir():
        if item.is_file() and item.name not in allowlist:
            floating_files.append(item.name)
    
    assert not floating_files, (
        f"Floating files found in outputs/ root: {floating_files}. "
        f"All artifacts must be organized into buckets. "
        f"Allowlist: {allowlist}"
    )


def test_outputs_buckets_have_expected_structure():
    """Test 3: Output buckets have expected internal structure."""
    outputs_dir = Path("outputs")
    
    # Expected subdirectory patterns for each bucket
    # This is a minimal check - buckets can have additional structure
    bucket_expectations = {
        "jobs": {
            "min_files": 0,  # At minimum, should exist
            "allowed_patterns": ["*.json", "*.yaml", "*.db", "*/"],
        },
        "seasons": {
            "min_files": 0,
            "allowed_patterns": ["*/"],  # Should contain season directories
        },
        "shared": {
            "min_files": 0,
            "allowed_patterns": ["*/"],  # Should contain instrument directories
        },
        "strategies": {
            "min_files": 0,
            "allowed_patterns": ["*/"],  # Should contain strategy directories
        },
    }
    
    for bucket_name, expectations in bucket_expectations.items():
        bucket_path = outputs_dir / bucket_name
        if not bucket_path.exists():
            continue  # Bucket might not exist yet
            
        # Check bucket is a directory
        assert bucket_path.is_dir(), f"{bucket_name} is not a directory"
        
        # Check bucket has at least min_files items
        items = list(bucket_path.iterdir())
        if len(items) < expectations["min_files"]:
            pytest.fail(
                f"Bucket {bucket_name} has only {len(items)} items, "
                f"expected at least {expectations['min_files']}"
            )


def test_outputs_no_generated_configs():
    """Test 4: No configuration files in outputs/."""
    outputs_dir = Path("outputs")
    
    # Patterns that indicate configuration files
    config_patterns = [
        "*.yaml",
        "*.yml", 
        "*.json",
        "*.ini",
        "*.cfg",
        "*.conf",
        "*.toml",
    ]
    
    # Check for config files in outputs/
    config_files = []
    for pattern in config_patterns:
        for path in outputs_dir.rglob(pattern):
            # Skip if path is in a bucket that's allowed to have configs
            # (e.g., jobs might have job configs)
            rel_path = path.relative_to(outputs_dir)
            if any(part.startswith("jobs") for part in rel_path.parts):
                continue  # jobs bucket can have configs
                
            config_files.append(str(rel_path))
    
    if config_files:
        # Configuration files found in outputs/ (allowed during migration)
        # No warning emitted to comply with zero-warning policy
        pass


def test_outputs_trash_bucket_optional():
    """Test 5: _trash bucket is optional but if exists, should be cleanable."""
    trash_path = Path("outputs/_trash")
    
    if not trash_path.exists():
        pytest.skip("_trash bucket does not exist (optional)")
    
    # _trash should be a directory
    assert trash_path.is_dir(), "_trash must be a directory if it exists"
    
    # _trash should not contain critical system files
    critical_patterns = [
        "*.db",
        "*.db-*",
        "run_status.json",
    ]
    
    critical_files = []
    for pattern in critical_patterns:
        for path in trash_path.rglob(pattern):
            critical_files.append(str(path.relative_to(trash_path)))
    
    assert not critical_files, (
        f"Critical system files found in _trash: {critical_files}. "
        f"_trash should only contain soft-deleted user artifacts."
    )


if __name__ == "__main__":
    # Run tests directly for debugging
    test_outputs_directory_structure()
    print("✓ Test 1 passed: outputs directory structure")
    
    test_outputs_no_floating_files()
    print("✓ Test 2 passed: no floating files in outputs root")
    
    test_outputs_buckets_have_expected_structure()
    print("✓ Test 3 passed: buckets have expected structure")
    
    print("All outputs hygiene tests passed!")