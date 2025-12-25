
#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path


def _is_under(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except Exception:
        return False


def clean_repo_caches(repo_root: Path, dry_run: bool = False) -> tuple[int, int]:
    """
    Remove Python bytecode caches inside repo_root:
      - __pycache__ directories
      - *.pyc, *.pyo
    Does NOT touch anything outside repo_root.
    """
    removed_dirs = 0
    removed_files = 0

    for p in repo_root.rglob("__pycache__"):
        if not p.is_dir():
            continue
        if not _is_under(p, repo_root):
            continue
        if dry_run:
            print(f"[DRY] rmdir: {p}")
        else:
            for child in p.rglob("*"):
                try:
                    if child.is_file() or child.is_symlink():
                        child.unlink(missing_ok=True)
                        removed_files += 1
                except Exception:
                    pass
            try:
                p.rmdir()
                removed_dirs += 1
            except Exception:
                pass

    for ext in ("*.pyc", "*.pyo"):
        for p in repo_root.rglob(ext):
            if not p.is_file() and not p.is_symlink():
                continue
            if not _is_under(p, repo_root):
                continue
            if dry_run:
                print(f"[DRY] rm: {p}")
            else:
                try:
                    p.unlink(missing_ok=True)
                    removed_files += 1
                except Exception:
                    pass

    return removed_dirs, removed_files


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    dry_run = os.environ.get("FISHBRO_DRY_RUN", "").strip() == "1"
    removed_dirs, removed_files = clean_repo_caches(repo_root, dry_run=dry_run)

    if dry_run:
        print("[DRY] Done.")
        return

    print(f"Cleaned {removed_dirs} __pycache__ directories and {removed_files} bytecode files.")


if __name__ == "__main__":
    main()


