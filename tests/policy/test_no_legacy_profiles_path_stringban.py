"""Policy test: No non-legacy test may reference legacy src/data/profiles paths."""

from __future__ import annotations

from pathlib import Path

BANNED = [
    "FishBroWFS_V2/data/profiles",
    "/data/profiles/",
    '"src" / "FishBroWFS_V2" / "data" / "profiles"',
    "'src' / 'FishBroWFS_V2' / 'data' / 'profiles'",
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


def test_no_legacy_profiles_path_stringban():
    """Test that no non-legacy test uses legacy profile paths."""
    repo_root = Path(__file__).resolve().parent.parent.parent
    tests_root = repo_root / "tests"
    assert tests_root.exists(), f"Missing tests root: {tests_root}"

    offenders = []
    for f in _iter_py_files(tests_root):
        # Exclude legacy, manual, and policy directories
        rel_path = f.relative_to(tests_root)
        if str(rel_path).startswith("legacy/") or str(rel_path).startswith("manual/") or str(rel_path).startswith("policy/"):
            continue
        
        # Exclude this test file itself (it contains the banned strings in BANNED list)
        if f.name == "test_no_legacy_profiles_path_stringban.py":
            continue
        
        txt = f.read_text(encoding="utf-8")
        for needle in BANNED:
            lines = _find_matches(txt, needle)
            if lines:
                offenders.append((str(f), needle, lines[:5]))

    assert not offenders, "Legacy profile path violations in non-legacy tests:\n" + "\n".join(
        [f"- {path}: {needle} @ lines {lines}" for path, needle, lines in offenders]
    )


if __name__ == "__main__":
    # Quick manual test
    test_no_legacy_profiles_path_stringban()
    print("✅ No legacy profile path violations found in non-legacy tests")