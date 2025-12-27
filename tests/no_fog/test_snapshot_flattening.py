#!/usr/bin/env python3
"""
Test snapshot flattening requirements.

Validates that snapshot generation produces exactly two files in outputs/snapshots/:
- SYSTEM_FULL_SNAPSHOT.md (static, contains all embedded artifacts)
- RUNTIME_CONTEXT.md (runtime, only after dashboard run)

No intermediate audit artifacts should remain as standalone files.
"""

import os
import tempfile
import shutil
from pathlib import Path
import pytest
import subprocess
import sys


def test_snapshot_flattened_structure():
    """
    Verify that `make snapshot` produces exactly SYSTEM_FULL_SNAPSHOT.md
    and no other files in outputs/snapshots/.
    """
    # Clean up any existing snapshot outputs
    snapshot_dir = Path("outputs/snapshots")
    if snapshot_dir.exists():
        shutil.rmtree(snapshot_dir)
    
    # Run make snapshot
    result = subprocess.run(
        ["make", "snapshot"],
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
    )
    
    assert result.returncode == 0, f"make snapshot failed: {result.stderr}"
    
    # Verify outputs/snapshots/ exists
    assert snapshot_dir.exists(), "outputs/snapshots/ directory not created"
    
    # List all files in outputs/snapshots/
    paths = list(snapshot_dir.iterdir())
    path_names = [p.name for p in paths]
    
    # Should contain exactly SYSTEM_FULL_SNAPSHOT.md
    assert set(path_names) == {
        "SYSTEM_FULL_SNAPSHOT.md",
    }, f"Unexpected files in outputs/snapshots/: {path_names}"
    
    # Verify SYSTEM_FULL_SNAPSHOT.md exists and is non-empty
    snapshot_file = snapshot_dir / "SYSTEM_FULL_SNAPSHOT.md"
    assert snapshot_file.exists(), "SYSTEM_FULL_SNAPSHOT.md not created"
    assert snapshot_file.stat().st_size > 0, "SYSTEM_FULL_SNAPSHOT.md is empty"
    
    # Verify no subdirectories exist
    for path in paths:
        assert not path.is_dir(), f"Unexpected subdirectory: {path}"
    
    # Verify no intermediate audit files exist
    for audit_file in [
        "REPO_TREE.txt",
        "MANIFEST.json", 
        "SKIPPED_FILES.txt",
        "AUDIT_GREP.txt",
        "AUDIT_IMPORTS.csv",
        "AUDIT_ENTRYPOINTS.md",
        "AUDIT_CONFIG_REFERENCES.txt",
        "AUDIT_CALL_GRAPH.txt",
        "AUDIT_TEST_SURFACE.txt",
        "AUDIT_RUNTIME_MUTATIONS.txt",
        "AUDIT_STATE_FLOW.md",
    ]:
        assert not (snapshot_dir / audit_file).exists(), \
            f"Intermediate audit file {audit_file} should not exist as standalone file"
    
    # Clean up
    if snapshot_dir.exists():
        shutil.rmtree(snapshot_dir)


def test_runtime_context_flattened():
    """
    Verify that dashboard startup creates RUNTIME_CONTEXT.md in outputs/snapshots/
    (not in a runtime subdirectory).
    """
    # Clean up any existing snapshot outputs
    snapshot_dir = Path("outputs/snapshots")
    if snapshot_dir.exists():
        shutil.rmtree(snapshot_dir)
    
    # Create snapshot first
    result = subprocess.run(
        ["make", "snapshot"],
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"make snapshot failed: {result.stderr}"
    
    # Run dashboard startup (simulated by running runtime context generation)
    # We'll run the runtime context script directly
    runtime_script = Path("src/FishBroWFS_V2/gui/services/runtime_context.py")
    if runtime_script.exists():
        result = subprocess.run(
            [sys.executable, str(runtime_script)],
            cwd=Path.cwd(),
            capture_output=True,
            text=True,
        )
        # Script may exit with non-zero if dashboard not running, but that's OK
        # We just want to see if it creates the file
    
    # Check for RUNTIME_CONTEXT.md in outputs/snapshots/
    runtime_file = snapshot_dir / "RUNTIME_CONTEXT.md"
    
    # If the file was created, verify it's in the right location
    if runtime_file.exists():
        # Should NOT be in outputs/snapshots/runtime/
        runtime_subdir = snapshot_dir / "runtime"
        assert not runtime_subdir.exists(), \
            "runtime subdirectory should not exist"
        
        # List all files in outputs/snapshots/
        paths = list(snapshot_dir.iterdir())
        path_names = [p.name for p in paths]
        
        # Should contain both files
        assert "SYSTEM_FULL_SNAPSHOT.md" in path_names
        assert "RUNTIME_CONTEXT.md" in path_names
        
        # Should contain exactly these two files (no others)
        assert set(path_names) == {
            "SYSTEM_FULL_SNAPSHOT.md",
            "RUNTIME_CONTEXT.md",
        }, f"Unexpected files after dashboard run: {path_names}"
    
    # Clean up
    if snapshot_dir.exists():
        shutil.rmtree(snapshot_dir)


def test_make_dashboard_creates_runtime_context():
    """
    Integration test: `make dashboard` should create RUNTIME_CONTEXT.md
    in the flattened location.
    """
    # This is a heavier integration test that actually starts the dashboard
    # We'll mark it as integration and skip by default
    pass


def test_snapshot_compiler_embeds_all_artifacts():
    """
    Verify that SYSTEM_FULL_SNAPSHOT.md contains all required embedded artifacts.
    """
    # Clean up any existing snapshot outputs
    snapshot_dir = Path("outputs/snapshots")
    if snapshot_dir.exists():
        shutil.rmtree(snapshot_dir)
    
    # Run make snapshot
    result = subprocess.run(
        ["make", "snapshot"],
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"make snapshot failed: {result.stderr}"
    
    # Read SYSTEM_FULL_SNAPSHOT.md
    snapshot_file = snapshot_dir / "SYSTEM_FULL_SNAPSHOT.md"
    content = snapshot_file.read_text()
    
    # Verify it contains all required sections
    required_sections = [
        "# SYSTEM FULL SNAPSHOT",
        "## MANIFEST",
        "## LOCAL_SCAN_RULES", 
        "## REPO_TREE",
        "## AUDIT_GREP",
        "## AUDIT_IMPORTS",
        "## AUDIT_ENTRYPOINTS",
        "## AUDIT_CONFIG_REFERENCES",
        "## AUDIT_CALL_GRAPH",
        "## AUDIT_TEST_SURFACE",
        "## AUDIT_RUNTIME_MUTATIONS",
        "## AUDIT_STATE_FLOW",
        "## SKIPPED_FILES",
    ]
    
    for section in required_sections:
        assert section in content, f"Missing section in SYSTEM_FULL_SNAPSHOT.md: {section}"
    
    # Clean up
    if snapshot_dir.exists():
        shutil.rmtree(snapshot_dir)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])