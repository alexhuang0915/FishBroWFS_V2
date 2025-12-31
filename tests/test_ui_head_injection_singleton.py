"""Enforce singleton head/style injection authority.

Ensures that only `src/gui/nicegui/theme/nexus_theme.py` can inject head/style content.
"""
import ast
import re
from pathlib import Path
import pytest

# Repository root (relative to this test file)
REPO_ROOT = Path(__file__).parent.parent
UI_ROOT = REPO_ROOT / "src" / "gui" / "nicegui"

# Allowed file (the only file permitted to contain injection calls)
ALLOWED_FILE = UI_ROOT / "theme" / "nexus_theme.py"

# Patterns that are considered "injection" calls
FORBIDDEN_PATTERNS = [
    r"ui\.add_head_html",
    r"ui\.add_css",
    r"ui\.add_head_script",
    # Also catch any add_*html wrappers
    r"add_.*html",
]

# Pattern to find :root { blocks
ROOT_SELECTOR_PATTERN = r":root\s*\{"


def find_files_with_pattern(root: Path, pattern: str) -> list[tuple[Path, int, str]]:
    """Return list of (file, line_number, line_content) matching regex pattern."""
    matches = []
    for py_file in root.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        for i, line in enumerate(content.splitlines(), start=1):
            if re.search(pattern, line):
                matches.append((py_file, i, line.strip()))
    return matches


def test_no_injection_outside_theme_module():
    """No injection calls in src/gui/nicegui/** except theme/nexus_theme.py."""
    errors = []
    for pattern in FORBIDDEN_PATTERNS:
        matches = find_files_with_pattern(UI_ROOT, pattern)
        for file, line_no, line in matches:
            if file == ALLOWED_FILE:
                continue
            errors.append(f"{file.relative_to(REPO_ROOT)}:{line_no}: {line}")

    if errors:
        error_msg = "\n".join(errors)
        raise AssertionError(
            f"Found {len(errors)} forbidden injection call(s) outside {ALLOWED_FILE.relative_to(REPO_ROOT)}:\n{error_msg}"
        )


def test_exactly_one_root_selector_in_theme():
    """Exactly one occurrence of `:root {` under src/gui/nicegui/**, and it must be in nexus_theme.py."""
    matches = find_files_with_pattern(UI_ROOT, ROOT_SELECTOR_PATTERN)
    
    # Filter out matches not in allowed file
    non_allowed = [(f, l, c) for f, l, c in matches if f != ALLOWED_FILE]
    if non_allowed:
        error_lines = "\n".join(f"{f.relative_to(REPO_ROOT)}:{l}: {c}" for f, l, c in non_allowed)
        raise AssertionError(
            f"Found `:root {{` outside {ALLOWED_FILE.relative_to(REPO_ROOT)}:\n{error_lines}"
        )
    
    # Ensure exactly one match in allowed file
    allowed_matches = [(f, l, c) for f, l, c in matches if f == ALLOWED_FILE]
    if len(allowed_matches) != 1:
        raise AssertionError(
            f"Expected exactly one `:root {{` in {ALLOWED_FILE.relative_to(REPO_ROOT)}, found {len(allowed_matches)}"
        )


def test_allowed_file_contains_injection_calls():
    """Sanity check: allowed file should contain at least one injection call."""
    # This test ensures we haven't accidentally removed all injection calls from the theme module.
    content = ALLOWED_FILE.read_text(encoding="utf-8")
    found = False
    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, content):
            found = True
            break
    assert found, f"Expected at least one injection call in {ALLOWED_FILE.relative_to(REPO_ROOT)}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])