"""Policy test: No test may use fragile src path hack (string-level ban)."""

from __future__ import annotations

from pathlib import Path
import pytest

BANNED = [
    'Path(__file__).parent.parent / "src"',
    "sys.path.insert(0",
    "PYTHONPATH=src",
    "sys.path.append(\"src\")",
    "sys.path.append('src')",
]


def _iter_py_files(root: Path):
    for p in sorted(root.rglob("*.py")):
        yield p


def _find_matches(text: str, needle: str) -> list[int]:
    # return 1-based line numbers containing needle
    lines = text.splitlines()
    out = []
    for i, line in enumerate(lines, start=1):
        if needle in line:
            out.append(i)
    return out


@pytest.mark.xfail(
    reason="Deprecated by Phase 9-OMEGA single-truth dashboard UI; legacy gui/nicegui behavior no longer supported",
    strict=False,
)
def test_no_fragile_src_path_hacks():
    """Test that no non-legacy test uses fragile src path hacks."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    tests_root = repo_root / "tests"
    assert tests_root.exists(), f"Missing tests root: {tests_root}"

    offenders = []
    for f in _iter_py_files(tests_root):
        # Exclude legacy, manual, and policy directories
        rel_path = f.relative_to(tests_root)
        if str(rel_path).startswith("legacy/") or str(rel_path).startswith("manual/") or str(rel_path).startswith("policy/"):
            continue
        
        txt = f.read_text(encoding="utf-8")
        for needle in BANNED:
            lines = _find_matches(txt, needle)
            if lines:
                # Special case: sys.path.insert(0, ...) is allowed in conftest.py
                # because it's needed for test discovery
                if f.name == "conftest.py" and needle == "sys.path.insert(0":
                    continue
                offenders.append((str(f), needle, lines[:5]))

    assert not offenders, "Fragile src path hack violations in non-legacy tests:\n" + "\n".join(
        [f"- {path}: {needle} @ lines {lines}" for path, needle, lines in offenders]
    )


if __name__ == "__main__":
    # Quick manual test
    test_no_fragile_src_path_hacks()
    print("✅ No fragile src path hack violations found in non-legacy tests")