from __future__ import annotations

from pathlib import Path

from core.paths import get_cache_root, get_outputs_root, get_numba_cache_root


def test_repo_root_clean_isolation() -> None:
    """
    Guardrail: tests must not write outputs/cache into the repo root.

    We enforce this by requiring the configured roots to live outside the repo,
    via env isolation in tests/conftest.py.
    """
    repo_root = Path(__file__).resolve().parents[2]

    outputs_root = get_outputs_root().resolve()
    cache_root = get_cache_root().resolve()
    numba_root = get_numba_cache_root().resolve()

    for p in (outputs_root, cache_root, numba_root):
        try:
            p.relative_to(repo_root)
        except Exception:
            continue
        raise AssertionError(f"Test root must not be inside repo: {p}")

