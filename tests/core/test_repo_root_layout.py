from __future__ import annotations

from pathlib import Path


def test_repo_root_layout_no_dev_files() -> None:
    """
    Guardrail: keep repo root clean.

    Dev scripts, scratch tests, and logs must not live in the repository root.
    """
    repo_root = Path(__file__).resolve().parents[2]

    forbidden = [
        "REMOVE.md",
        "run_wfs_loop.py",
        "simulate_worker.py",
        "test_delete_click_logic.py",
        "test_deletion_logic.py",
        "worker.log",
    ]
    present = [name for name in forbidden if (repo_root / name).exists()]
    assert not present, f"Forbidden files present in repo root: {present}"

