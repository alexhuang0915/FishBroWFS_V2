"""
Policy guard: ensure no duplicate test basenames across tests/ directory.

Duplicate basenames cause pytest import mismatch errors and reduce clarity.
This test will fail if any duplicate basenames are found.
"""
from pathlib import Path
from collections import defaultdict


def test_no_duplicate_test_basenames():
    """Fail if any duplicate test file basenames exist under tests/."""
    root = Path(__file__).resolve().parent.parent  # project root
    tests_dir = root / "tests"
    if not tests_dir.exists():
        return  # should not happen

    by_name = defaultdict(list)
    for py_path in tests_dir.rglob("*.py"):
        if py_path.name == "__init__.py":
            continue
        by_name[py_path.name].append(py_path.relative_to(root))

    duplicates = {k: v for k, v in by_name.items() if len(v) > 1}
    if not duplicates:
        return  # success

    # Build error message with deterministic ordering
    lines = ["Duplicate test basenames detected:"]
    for basename in sorted(duplicates):
        lines.append(f"- {basename}")
        for path in sorted(duplicates[basename]):
            lines.append(f"  - {path}")

    # Also include a helpful hint
    lines.append("\nTo fix: rename or merge duplicate files.")
    raise AssertionError("\n".join(lines))


if __name__ == "__main__":
    # Allow manual execution for debugging
    try:
        test_no_duplicate_test_basenames()
        print("✓ No duplicate test basenames.")
    except AssertionError as e:
        print(e)
        raise