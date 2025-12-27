#!/usr/bin/env python3
"""
Test Local-Strict scanner policy and file inclusion logic.

Contract:
- Build a temp repo-like structure
- src/a.py included
- tests/t.py included
- .venv/x.py excluded
- outputs/jobs.db excluded
- outputs/snapshots/full/REPO_TREE.txt included
- node_modules/pkg/index.js excluded
- root Makefile included

Assert iter_repo_files_local_strict returns exactly expected list, sorted.
"""

import tempfile
import shutil
from pathlib import Path
import pytest

from control.local_scan import (
    LocalScanPolicy,
    default_local_strict_policy,
    iter_repo_files_local_strict,
    should_include_file,
)


def test_default_policy():
    """Test that default policy matches spec."""
    policy = default_local_strict_policy()
    
    assert policy.allowed_roots == ("src", "tests", "scripts", "docs")
    assert "Makefile" in policy.allowed_root_files_glob
    assert "pyproject.toml" in policy.allowed_root_files_glob
    assert ".git" in policy.deny_segments
    assert ".venv" in policy.deny_segments
    assert "node_modules" in policy.deny_segments
    assert "outputs" in policy.deny_segments
    assert policy.outputs_allow == ("outputs/snapshots",)
    assert policy.max_files == 20000
    assert policy.max_bytes == 2000000
    assert policy.gitignore_respected is False


def test_should_include_file():
    """Test individual file inclusion decisions."""
    policy = default_local_strict_policy()
    
    # Root files
    assert should_include_file(Path("Makefile"), policy) is True
    assert should_include_file(Path("pyproject.toml"), policy) is True
    assert should_include_file(Path("README.md"), policy) is True
    assert should_include_file(Path("random.txt"), policy) is False  # not in glob
    
    # Allowed roots
    assert should_include_file(Path("src/a.py"), policy) is True
    assert should_include_file(Path("tests/test.py"), policy) is True
    assert should_include_file(Path("scripts/run.py"), policy) is True
    assert should_include_file(Path("docs/index.md"), policy) is True
    
    # Denied segments anywhere in path
    assert should_include_file(Path("src/.venv/foo.py"), policy) is False
    assert should_include_file(Path("tests/.git/config"), policy) is False
    assert should_include_file(Path("scripts/node_modules/pkg/index.js"), policy) is False
    assert should_include_file(Path("docs/__pycache__/module.cpython-310.pyc"), policy) is False
    
    # Outputs exception
    assert should_include_file(Path("outputs/jobs.db"), policy) is False
    assert should_include_file(Path("outputs/snapshots/full/REPO_TREE.txt"), policy) is True
    assert should_include_file(Path("outputs/snapshots/full/LOCAL_SCAN_RULES.json"), policy) is True
    assert should_include_file(Path("outputs/snapshots/"), policy) is True  # exact match
    assert should_include_file(Path("outputs/snapshots"), policy) is True  # exact match
    
    # Other directories not allowed
    assert should_include_file(Path("configs/something.yaml"), policy) is False
    assert should_include_file(Path("data/raw.csv"), policy) is False


def test_iter_repo_files_local_strict_integration(tmp_path: Path):
    """Build a temp repo structure and verify scanning."""
    repo_root = tmp_path
    
    # Create expected included files
    (repo_root / "src").mkdir()
    (repo_root / "src" / "a.py").write_text("# included")
    (repo_root / "src" / "subdir").mkdir()
    (repo_root / "src" / "subdir" / "b.py").write_text("# included")
    
    (repo_root / "tests").mkdir()
    (repo_root / "tests" / "t.py").write_text("# included")
    
    (repo_root / "scripts").mkdir()
    (repo_root / "scripts" / "run.py").write_text("# included")
    
    (repo_root / "docs").mkdir()
    (repo_root / "docs" / "index.md").write_text("# included")
    
    # Create outputs exception
    (repo_root / "outputs").mkdir()
    (repo_root / "outputs" / "jobs.db").write_text("binary")  # should be excluded
    (repo_root / "outputs" / "snapshots").mkdir()
    (repo_root / "outputs" / "snapshots" / "full").mkdir()
    (repo_root / "outputs" / "snapshots" / "full" / "REPO_TREE.txt").write_text("# included")
    
    # Create excluded directories
    (repo_root / ".venv").mkdir()
    (repo_root / ".venv" / "x.py").write_text("# excluded")
    
    (repo_root / "node_modules").mkdir()
    (repo_root / "node_modules" / "pkg").mkdir()
    (repo_root / "node_modules" / "pkg" / "index.js").write_text("// excluded")
    
    (repo_root / "__pycache__").mkdir()
    (repo_root / "__pycache__" / "module.cpython-310.pyc").write_bytes(b"\x00\x01")
    
    # Root files
    (repo_root / "Makefile").write_text("# included")
    (repo_root / "pyproject.toml").write_text("# included")
    (repo_root / "README.md").write_text("# included")
    (repo_root / "random.txt").write_text("# excluded - not in glob")
    
    # Create a file in disallowed root (configs)
    (repo_root / "configs").mkdir()
    (repo_root / "configs" / "profile.yaml").write_text("# excluded")
    
    policy = default_local_strict_policy()
    files = iter_repo_files_local_strict(repo_root, policy)
    
    # files are already relative to repo_root
    rel_files_str = sorted(str(p) for p in files)
    
    expected = [
        "Makefile",
        "README.md",
        "pyproject.toml",
        "docs/index.md",
        "outputs/snapshots/full/REPO_TREE.txt",
        "scripts/run.py",
        "src/a.py",
        "src/subdir/b.py",
        "tests/t.py",
    ]
    
    assert rel_files_str == sorted(expected), f"Got {rel_files_str}, expected {sorted(expected)}"
    
    # Verify deterministic ordering
    files2 = iter_repo_files_local_strict(repo_root, policy)
    assert list(files) == list(files2), "Should be deterministic"


def test_max_files_limit(tmp_path: Path):
    """Test max_files limit is respected."""
    repo_root = tmp_path
    (repo_root / "src").mkdir()
    
    # Create many files
    for i in range(100):
        (repo_root / "src" / f"file{i}.py").write_text("# content")
    
    policy = LocalScanPolicy(
        allowed_roots=("src",),
        allowed_root_files_glob=(),
        deny_segments=(),
        outputs_allow=(),
        max_files=10,  # Low limit
        max_bytes=1000000,
        gitignore_respected=False,
    )
    
    files = iter_repo_files_local_strict(repo_root, policy)
    assert len(files) == 10, f"Should be limited to 10 files, got {len(files)}"
    
    # Should be sorted deterministically
    file_names = [f.name for f in files]
    assert file_names == sorted(file_names), "Files should be sorted"


def test_policy_immutability():
    """Test that policy dataclass is frozen."""
    policy = default_local_strict_policy()
    
    with pytest.raises(Exception):
        policy.allowed_roots = ("something",)  # Should raise because frozen


if __name__ == "__main__":
    pytest.main([__file__, "-v"])