from __future__ import annotations

"""
Stage 0 Contract Tests

Stage 0 must remain a "vector/proxy" layer:
  - MUST NOT import engine/matcher/strategy kernel/pipeline grid runner.
  - MUST NOT create OrderIntent/Fill objects.

These tests are intentionally strict: they prevent "silent scope creep"
that would destroy throughput and blur semantics.
"""

import ast
from pathlib import Path


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_stage0_does_not_import_engine_or_runner_grid() -> None:
    root = Path(__file__).resolve().parent.parent
    p = root / "src" / "FishBroWFS_V2" / "stage0" / "ma_proxy.py"
    code = _read(p)
    tree = ast.parse(code)

    banned_prefixes = (
        "FishBroWFS_V2.engine",
        "FishBroWFS_V2.strategy",
        "FishBroWFS_V2.pipeline",
    )

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                name = a.name
                assert not name.startswith(banned_prefixes), f"banned import: {name}"
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            assert not mod.startswith(banned_prefixes), f"banned import-from: {mod}"


def test_stage0_file_exists() -> None:
    root = Path(__file__).resolve().parent.parent
    p = root / "src" / "FishBroWFS_V2" / "stage0" / "ma_proxy.py"
    assert p.exists(), "Stage0 module must exist"


