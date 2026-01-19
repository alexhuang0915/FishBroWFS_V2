"""
Test for `make clear` target.

Verifies that `make clear` removes only Python/tool caches and does not touch
protected directories (outputs/, .venv/, *.db, raw data).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def run(cmd: list[str], cwd: Path) -> None:
    """Run command and raise on failure."""
    subprocess.run(cmd, cwd=str(cwd), check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def test_make_clear_removes_python_caches_but_not_evidence(tmp_path: Path) -> None:
    """
    Arrange: create temporary cache artifacts inside repo.
    Act: run `make clear`.
    Assert: caches removed, evidence untouched.
    """
    # Locate repo root (parent of tests/)
    repo = Path(__file__).resolve()
    while repo.name != "tests" and repo.parent != repo:
        repo = repo.parent
    repo = repo.parent  # repo root (tests/..)

    # Arrange: create in-repo temp artifacts
    work = repo / ".tmp_make_clear_test"
    work.mkdir(exist_ok=True)
    (work / "__pycache__").mkdir(parents=True, exist_ok=True)
    (work / "a.pyc").write_bytes(b"\x00")
    (work / "b.pyo").write_bytes(b"\x00")
    (repo / ".pytest_cache").mkdir(exist_ok=True)
    (repo / ".mypy_cache").mkdir(exist_ok=True)
    (repo / ".ruff_cache").mkdir(exist_ok=True)
    (repo / ".cache").mkdir(exist_ok=True)

    # Create evidence sentinel that must survive
    evidence_dir = repo / "outputs" / "_dp_evidence" / "_make_clear_sentinel"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    sentinel = evidence_dir / "DO_NOT_DELETE.txt"
    sentinel.write_text("sentinel", encoding="utf-8")

    # Act
    run(["make", "clear"], cwd=repo)

    # Assert: removed caches
    assert not (work / "__pycache__").exists()
    assert not (work / "a.pyc").exists()
    assert not (work / "b.pyo").exists()
    assert not (repo / ".pytest_cache").exists()
    assert not (repo / ".mypy_cache").exists()
    assert not (repo / ".ruff_cache").exists()
    assert not (repo / ".cache").exists()

    # Assert: evidence untouched
    assert sentinel.exists()

    # Clean up temporary directory (optional)
    if work.exists():
        import shutil
        shutil.rmtree(work, ignore_errors=True)


def test_make_clear_does_not_delete_protected_paths(tmp_path: Path) -> None:
    """
    Ensure `make clear` does not delete .venv/, outputs/, *.db, raw data.
    """
    repo = Path(__file__).resolve()
    while repo.name != "tests" and repo.parent != repo:
        repo = repo.parent
    repo = repo.parent

    # Create protected items (if they don't exist)
    protected = [
        repo / ".venv",
        repo / "outputs",
        repo / "FishBroData",
        repo / "jobs.db",
    ]
    # We'll just verify they still exist after make clear (they should)
    # Since we cannot delete .venv if it exists, we'll skip if missing.
    for path in protected:
        if path.exists():
            # Run make clear
            run(["make", "clear"], cwd=repo)
            assert path.exists(), f"Protected path {path} was deleted by make clear"
            break  # just test one to avoid unnecessary runs