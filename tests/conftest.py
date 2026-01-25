from __future__ import annotations

import sys
from pathlib import Path
import os

import pytest


repo_root = Path(__file__).resolve().parents[1]
src_path = repo_root / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

@pytest.fixture(autouse=True)
def _isolate_repo_writes(tmp_path_factory: pytest.TempPathFactory):
    """
    Keep repo root clean during tests by redirecting outputs/cache/numba caches
    to a temporary directory (unless a test overrides them explicitly).
    """
    base = tmp_path_factory.mktemp("fishbro_test_root")
    defaults = {
        "FISHBRO_OUTPUTS_ROOT": str(base / "outputs"),
        "FISHBRO_CACHE_ROOT": str(base / "cache"),
        "NUMBA_CACHE_DIR": str(base / "cache" / "numba"),
    }

    old = {k: os.environ.get(k) for k in defaults}
    try:
        # Force isolation by default: tests should not write into repo-root outputs/cache.
        # Individual tests may override these env vars temporarily if needed.
        for k, v in defaults.items():
            os.environ[k] = v

        Path(os.environ["FISHBRO_OUTPUTS_ROOT"]).mkdir(parents=True, exist_ok=True)
        Path(os.environ["FISHBRO_CACHE_ROOT"]).mkdir(parents=True, exist_ok=True)
        Path(os.environ["NUMBA_CACHE_DIR"]).mkdir(parents=True, exist_ok=True)
        yield
    finally:
        for k, prev in old.items():
            if prev is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = prev
