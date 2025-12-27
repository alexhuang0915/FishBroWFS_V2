#!/usr/bin/env python3
"""
Test snapshot compiler deterministic compilation.

Contract:
- Temp snapshots/full/ with known content files including LOCAL_SCAN_RULES.json
- Run compile_full_snapshot(snapshots_root=tmp_path/...)
- Assert output exists.
- Assert section order includes LOCAL_SCAN_RULES.json after MANIFEST.json.
- Assert raw content substrings match verbatim.
- Determinism: run twice; assert output bytes identical.
"""

import tempfile
import json
import hashlib
from pathlib import Path
import pytest

from control.snapshot_compiler import (
    compile_full_snapshot,
    verify_deterministic,
)


def test_compile_full_snapshot_basic(tmp_path: Path):
    """Test basic compilation with minimal artifacts."""
    snapshots_root = tmp_path / "snapshots"
    full_dir = snapshots_root / "full"
    full_dir.mkdir(parents=True)
    
    # Create required files (some may be missing, that's OK)
    (full_dir / "MANIFEST.json").write_text(json.dumps({
        "generated_at_utc": "2025-12-26T11:00:00Z",
        "git_head": "abc123",
        "scan_mode": "local-strict",
        "file_count": 1,
        "files": [],
    }))
    
    (full_dir / "LOCAL_SCAN_RULES.json").write_text(json.dumps({
        "mode": "local-strict",
        "allowed_roots": ["src", "tests"],
        "max_files": 20000,
    }))
    
    (full_dir / "REPO_TREE.txt").write_text("src/a.py\ntests/test.py\n")
    (full_dir / "SKIPPED_FILES.txt").write_text("TOO_LARGE\tbig.bin\n")
    (full_dir / "AUDIT_IMPORTS.csv").write_text("file,lineno,kind,module,name\n")
    (full_dir / "AUDIT_ENTRYPOINTS.md").write_text("# Entrypoints\n")
    (full_dir / "AUDIT_CALL_GRAPH.txt").write_text("call graph\n")
    (full_dir / "AUDIT_RUNTIME_MUTATIONS.txt").write_text("mutations\n")
    (full_dir / "AUDIT_STATE_FLOW.md").write_text("# State Flow\n")
    (full_dir / "AUDIT_CONFIG_REFERENCES.txt").write_text("config refs\n")
    (full_dir / "AUDIT_TEST_SURFACE.txt").write_text("test surface\n")
    
    # Run compiler
    out_path = compile_full_snapshot(
        snapshots_root=str(snapshots_root),
        full_dir_name="full",
        out_name="SYSTEM_FULL_SNAPSHOT.md",
    )
    
    assert out_path.exists()
    assert out_path.name == "SYSTEM_FULL_SNAPSHOT.md"
    assert out_path.parent == snapshots_root
    
    content = out_path.read_text(encoding="utf-8")
    
    # Check section order
    lines = content.splitlines()
    section_titles = []
    for line in lines:
        if line.startswith("## "):
            section_titles.append(line)
    
    # Should have sections in order
    assert any("MANIFEST.json" in title for title in section_titles)
    assert any("LOCAL_SCAN_RULES.json" in title for title in section_titles)
    assert any("REPO_TREE.txt" in title for title in section_titles)
    
    # Check that LOCAL_SCAN_RULES.json appears after MANIFEST.json
    manifest_idx = next(i for i, t in enumerate(section_titles) if "MANIFEST.json" in t)
    local_scan_idx = next(i for i, t in enumerate(section_titles) if "LOCAL_SCAN_RULES.json" in t)
    assert local_scan_idx > manifest_idx, "LOCAL_SCAN_RULES.json should be after MANIFEST.json"
    
    # Check content is embedded verbatim
    assert '"allowed_roots": ["src", "tests"]' in content
    assert "src/a.py" in content
    assert "TOO_LARGE" in content
    
    # Check fenced code blocks
    assert "```json" in content
    assert "```text" in content or "```txt" in content or "```" in content


def test_compile_deterministic(tmp_path: Path):
    """Run compilation twice and ensure identical bytes."""
    snapshots_root = tmp_path / "snapshots"
    full_dir = snapshots_root / "full"
    full_dir.mkdir(parents=True)
    
    # Create simple files
    (full_dir / "MANIFEST.json").write_text(json.dumps({"test": 1}))
    (full_dir / "LOCAL_SCAN_RULES.json").write_text(json.dumps({"mode": "test"}))
    (full_dir / "REPO_TREE.txt").write_text("tree")
    
    # First compilation
    out_path = compile_full_snapshot(
        snapshots_root=str(snapshots_root),
        full_dir_name="full",
        out_name="TEST_SNAPSHOT.md",
    )
    
    first_content = out_path.read_bytes()
    first_hash = hashlib.sha256(first_content).hexdigest()
    
    # Second compilation (should be identical)
    out_path2 = compile_full_snapshot(
        snapshots_root=str(snapshots_root),
        full_dir_name="full",
        out_name="TEST_SNAPSHOT.md",
    )
    
    second_content = out_path2.read_bytes()
    second_hash = hashlib.sha256(second_content).hexdigest()
    
    assert first_hash == second_hash, "Output should be deterministic"
    assert first_content == second_content, "Bytes should be identical"


def test_missing_files_section(tmp_path: Path):
    """Test that missing files are listed in Missing Files section."""
    snapshots_root = tmp_path / "snapshots"
    full_dir = snapshots_root / "full"
    full_dir.mkdir(parents=True)
    
    # Create only one file
    (full_dir / "MANIFEST.json").write_text(json.dumps({}))
    
    out_path = compile_full_snapshot(
        snapshots_root=str(snapshots_root),
        full_dir_name="full",
        out_name="TEST_SNAPSHOT.md",
    )
    
    content = out_path.read_text(encoding="utf-8")
    
    # Should have Missing Files section
    assert "Missing Files" in content
    # Should list LOCAL_SCAN_RULES.json as missing
    assert "LOCAL_SCAN_RULES.json" in content
    assert "REPO_TREE.txt" in content


def test_verify_deterministic(tmp_path: Path):
    """Test the verify_deterministic helper."""
    snapshots_root = tmp_path / "snapshots"
    full_dir = snapshots_root / "full"
    full_dir.mkdir(parents=True)
    
    (full_dir / "MANIFEST.json").write_text(json.dumps({"a": 1}))
    (full_dir / "LOCAL_SCAN_RULES.json").write_text(json.dumps({"b": 2}))
    
    # Should not raise and return True
    result = verify_deterministic(
        snapshots_root=str(snapshots_root),
        full_dir_name="full",
        out_name="TEST_VERIFY.md",
    )
    assert result is True, "Should be deterministic"
    
    # Now make a non-deterministic change (timestamp in MANIFEST)
    import time
    (full_dir / "MANIFEST.json").write_text(json.dumps({"a": 1, "time": time.time()}))
    
    # This should still be deterministic because we read the same file twice
    # (content hasn't changed between the two runs)
    result = verify_deterministic(
        snapshots_root=str(snapshots_root),
        full_dir_name="full",
        out_name="TEST_VERIFY2.md",
    )
    assert result is True, "Should still be deterministic (same input between runs)"


def test_encoding_handling(tmp_path: Path):
    """Test that non-UTF-8 files are handled gracefully."""
    snapshots_root = tmp_path / "snapshots"
    full_dir = snapshots_root / "full"
    full_dir.mkdir(parents=True)
    
    # Create a binary file (simulate corrupted text)
    (full_dir / "MANIFEST.json").write_text(json.dumps({"test": "正常"}))  # Chinese chars
    (full_dir / "LOCAL_SCAN_RULES.json").write_text(json.dumps({"mode": "test"}))
    
    # Create a file with invalid UTF-8 sequence
    (full_dir / "REPO_TREE.txt").write_bytes(b"normal text \xff\xfe invalid \x00")
    
    # Should not crash
    out_path = compile_full_snapshot(
        snapshots_root=str(snapshots_root),
        full_dir_name="full",
        out_name="TEST_ENCODING.md",
    )
    
    assert out_path.exists()
    # Should contain replacement characters or survive
    content = out_path.read_text(encoding="utf-8", errors="ignore")
    assert "normal text" in content


def test_empty_snapshots_dir(tmp_path: Path):
    """Test with empty snapshots/full directory."""
    snapshots_root = tmp_path / "snapshots"
    full_dir = snapshots_root / "full"
    full_dir.mkdir(parents=True)
    
    # No files at all
    out_path = compile_full_snapshot(
        snapshots_root=str(snapshots_root),
        full_dir_name="full",
        out_name="TEST_EMPTY.md",
    )
    
    assert out_path.exists()
    content = out_path.read_text(encoding="utf-8")
    assert "Missing Files" in content
    assert all(fname in content for fname in ["MANIFEST.json", "LOCAL_SCAN_RULES.json", "REPO_TREE.txt"])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])