from pathlib import Path


def test_cursorignore_targets_tooling_artifacts_only():
    """
    Ensure .cursorignore is reserved for tooling/noise suppression, not source roots.
    """
    path = Path(".cursorignore")
    assert path.exists(), ".cursorignore is missing from repo root"

    content = path.read_text().splitlines()
    banned_root_patterns = {"src/", "tests/", "configs/", "docs/"}

    for line in content:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        for banned in banned_root_patterns:
            assert banned not in stripped, (
                f".cursorignore may only block tooling/noise; "
                f"remove '{banned}' from ignore patterns"
            )
