#!/usr/bin/env python3
"""
Test the full snapshot forensic kit artifacts (dump_context.py).

Validates that `make snapshot` generates 10 JSONL parts, a manifest,
and no truncation.
"""

import json
import os
import tempfile
from pathlib import Path
import pytest
import subprocess
import sys


# ------------------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------------------

@pytest.fixture
def snapshot_output_dir(tmp_path):
    """Create a temporary output directory for snapshot generation."""
    output_dir = tmp_path / "SNAPSHOT"
    output_dir.mkdir(parents=True)
    return output_dir


@pytest.fixture
def run_snapshot_script(snapshot_output_dir, monkeypatch):
    """Run dump_context.py with monkeypatched output directory."""
    # Use subprocess to run the script, avoiding sys.path hacks
    script_path = Path.cwd() / "scripts" / "dump_context.py"
    
    # Set environment variable to override output directory? Not needed; we can pass --snapshot-root
    # We'll just run with --snapshot-root pointing to a temporary subdirectory under snapshot_output_dir
    # But the script expects a subdirectory inside SNAPSHOT. We'll let it create its own run_id directory.
    # We'll pass --snapshot-root as the parent directory.
    snapshot_root = snapshot_output_dir
    
    # Run the script
    result = subprocess.run(
        [sys.executable, str(script_path), "--snapshot-root", str(snapshot_root), "--repo-root", str(Path.cwd())],
        capture_output=True,
        text=True,
        cwd=Path.cwd(),
    )
    
    if result.returncode != 0:
        raise RuntimeError(
            f"Snapshot script failed with code {result.returncode}\n"
            f"stderr: {result.stderr}\n"
            f"stdout: {result.stdout}"
        )
    
    # Find the generated run directory (most recent)
    run_dirs = list(snapshot_root.glob("20*"))
    if not run_dirs:
        raise RuntimeError("No snapshot run directory created")
    latest_run = max(run_dirs, key=lambda p: p.name)
    return latest_run


# ------------------------------------------------------------------------------
# Core validation tests
# ------------------------------------------------------------------------------

def test_ten_parts_exist(run_snapshot_script):
    """Verify exactly 10 JSONL parts exist."""
    run_dir = run_snapshot_script
    parts = list(run_dir.glob("part_*.jsonl"))
    assert len(parts) == 10, f"Expected 10 parts, got {len(parts)}"
    # Ensure they are named part_00.jsonl through part_09.jsonl
    part_names = {p.name for p in parts}
    expected = {f"part_{i:02d}.jsonl" for i in range(10)}
    assert part_names == expected, f"Missing parts: {expected - part_names}"
    # Ensure each part has non-zero size (except maybe part_08, part_09 small)
    for p in parts:
        if p.name not in ("part_08.jsonl", "part_09.jsonl"):
            assert p.stat().st_size > 0, f"Part {p.name} is empty"


def test_manifest_in_last_part(run_snapshot_script):
    """Verify the last part contains a manifest entry."""
    run_dir = run_snapshot_script
    part_09 = run_dir / "part_09.jsonl"
    assert part_09.exists()
    with open(part_09, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    # Find line with type "manifest"
    manifest_lines = []
    for line in lines:
        try:
            obj = json.loads(line)
            if obj.get("type") == "manifest":
                manifest_lines.append(line)
        except json.JSONDecodeError:
            continue
    assert len(manifest_lines) == 1, f"Expected exactly one manifest line, got {len(manifest_lines)}"
    manifest = json.loads(manifest_lines[0])
    assert manifest.get("type") == "manifest"
    assert "files_total" in manifest
    assert "files_complete" in manifest
    assert "files_skipped" in manifest
    # Ensure no truncation flag
    assert '"file_truncated"' not in part_09.read_text()


def test_no_file_truncated(run_snapshot_script):
    """Verify none of the parts contain 'file_truncated'."""
    run_dir = run_snapshot_script
    for part in run_dir.glob("part_*.jsonl"):
        content = part.read_text(encoding='utf-8')
        assert '"file_truncated"' not in content, f"Found file_truncated in {part.name}"


def test_manifest_json_exists(run_snapshot_script):
    """Verify MANIFEST.json exists in snapshot root (written by dump_context.py)."""
    # The dump_context.py writes MANIFEST.json in snapshot_root (parent of run_dir)
    snapshot_root = run_snapshot_script.parent
    manifest_file = snapshot_root / "MANIFEST.json"
    assert manifest_file.exists(), "MANIFEST.json not created"
    manifest = json.loads(manifest_file.read_text(encoding='utf-8'))
    assert manifest.get("type") == "manifest"
    assert "run_id" in manifest
    # Ensure consistency with run directory name
    assert manifest["run_id"] == run_snapshot_script.name


def test_outputs_evidence_included(run_snapshot_script):
    """Verify outputs/ files are referenced in snapshot (metadata-only for large files)."""
    # This test is a placeholder; actual outputs evidence validation is part of Phase 3.
    pass


# ------------------------------------------------------------------------------
# Deterministic test (optional)
# ------------------------------------------------------------------------------

def test_deterministic_output(run_snapshot_script):
    """
    Verify that running the snapshot twice produces identical part files
    (except for run_id).
    """
    run_dir1 = run_snapshot_script
    snapshot_root = run_dir1.parent
    
    # Run a second time, but we need to ensure we don't overwrite the first run.
    # Use a temporary directory for second run.
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_root = Path(tmpdir) / "SNAPSHOT"
        tmp_root.mkdir(parents=True)
        script_path = Path.cwd() / "scripts" / "dump_context.py"
        result = subprocess.run(
            [sys.executable, str(script_path), "--snapshot-root", str(tmp_root), "--repo-root", str(Path.cwd())],
            capture_output=True,
            text=True,
            cwd=Path.cwd(),
        )
        assert result.returncode == 0, f"Second run failed: {result.stderr}"
        run_dirs2 = list(tmp_root.glob("20*"))
        assert run_dirs2, "Second run produced no directory"
        run_dir2 = max(run_dirs2, key=lambda p: p.name)
        
        # Compare part files (excluding run_id in meta lines)
        for i in range(10):
            p1 = run_dir1 / f"part_{i:02d}.jsonl"
            p2 = run_dir2 / f"part_{i:02d}.jsonl"
            # Read lines, filter out meta lines that contain run_id
            lines1 = p1.read_text(encoding='utf-8').splitlines()
            lines2 = p2.read_text(encoding='utf-8').splitlines()
            # Remove lines with "run_id" (meta lines) for comparison
            filtered1 = [line for line in lines1 if '"run_id"' not in line]
            filtered2 = [line for line in lines2 if '"run_id"' not in line]
            assert filtered1 == filtered2, f"Part {i} content differs (excluding run_id)"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])