"""Strict test for single Streamlit entrypoint.

Phase 10.1: Prevent any new Streamlit entrypoints from being created.
This test is stricter than test_viewer_entrypoint.py.
"""

from __future__ import annotations

from pathlib import Path
import re
import pytest


def test_no_streamlit_imports_outside_allowlist() -> None:
    """Test that no files outside allowlist import streamlit.
    
    This is a stricter version of test_no_duplicate_viewer_entrypoints.
    It ensures that only explicitly allowed files can import streamlit.
    """
    repo_root = Path(__file__).parent.parent
    
    # Allowlist of files that are allowed to import streamlit
    # These are the ONLY files that should import streamlit
    allowlist = {
        # Official viewer entrypoint
        repo_root / "src" / "FishBroWFS_V2" / "gui" / "viewer" / "app.py",
        # Research console page (called from viewer)
        repo_root / "src" / "FishBroWFS_V2" / "gui" / "research" / "page.py",
    }
    
    # Patterns to detect streamlit imports
    streamlit_patterns = [
        r"^\s*import\s+streamlit",
        r"^\s*from\s+streamlit\s+import",
        r"^\s*import\s+.*streamlit\s+as",
    ]
    
    # Compile regex patterns
    compiled_patterns = [re.compile(pattern) for pattern in streamlit_patterns]
    
    # Find all Python files in the repo
    python_files = list(repo_root.rglob("*.py"))
    
    # Track violations
    violations = []
    
    for py_file in python_files:
        # Skip test files (they're allowed to import streamlit for testing)
        if "test" in str(py_file) or "tests" in str(py_file):
            continue
        
        # Skip virtual environment directories
        if any(part in {'.venv', 'venv', 'env', '.virtualenv'} for part in py_file.parts):
            continue
        
        # Skip if file is in allowlist
        if py_file in allowlist:
            continue
        
        # Check if file contains streamlit import
        try:
            content = py_file.read_text(encoding="utf-8")
            
            for pattern in compiled_patterns:
                if pattern.search(content, re.MULTILINE):
                    violations.append(str(py_file))
                    break  # Found one violation, no need to check other patterns
        except (UnicodeDecodeError, OSError):
            # Skip files that can't be read
            continue
    
    # Assert no violations
    if violations:
        violation_list = "\n".join(f"  - {v}" for v in sorted(violations))
        pytest.fail(
            f"Found {len(violations)} files importing streamlit outside allowlist:\n"
            f"{violation_list}\n\n"
            f"Allowlist:\n"
            f"  - {allowlist.pop()}\n"
            f"  - {allowlist.pop()}\n\n"
            f"To fix:\n"
            f"1. Remove streamlit import from these files\n"
            f"2. Or if legitimate, add to allowlist (requires review)\n"
            f"3. Remember: Only viewer/app.py can be a Streamlit entrypoint"
        )


def test_no_main_function_outside_entrypoint() -> None:
    """Test that no files outside entrypoint have main() function with streamlit.
    
    This catches files that might be trying to become entrypoints.
    """
    repo_root = Path(__file__).parent.parent
    
    # Official entrypoint
    entrypoint = repo_root / "src" / "FishBroWFS_V2" / "gui" / "viewer" / "app.py"
    
    # Find all Python files with main() function and streamlit
    python_files = list(repo_root.rglob("*.py"))
    
    violations = []
    
    for py_file in python_files:
        # Skip test files
        if "test" in str(py_file) or "tests" in str(py_file):
            continue
        
        # Skip virtual environment directories
        if any(part in {'.venv', 'venv', 'env', '.virtualenv'} for part in py_file.parts):
            continue
        
        # Skip the official entrypoint
        if py_file == entrypoint:
            continue
        
        try:
            content = py_file.read_text(encoding="utf-8")
            
            # Check if file has both streamlit and main() function
            has_streamlit = "streamlit" in content.lower()
            has_main_function = "def main(" in content
            
            if has_streamlit and has_main_function:
                violations.append(str(py_file))
        except (UnicodeDecodeError, OSError):
            continue
    
    if violations:
        violation_list = "\n".join(f"  - {v}" for v in sorted(violations))
        pytest.fail(
            f"Found {len(violations)} files with main() function and streamlit imports:\n"
            f"{violation_list}\n\n"
            f"These might be trying to become Streamlit entrypoints.\n"
            f"Only {entrypoint} should have main() function with streamlit."
        )


def test_no_name_main_guard_outside_entrypoint() -> None:
    """Test that no files outside entrypoint have __name__ guard with streamlit.
    
    This catches potential entrypoints.
    """
    repo_root = Path(__file__).parent.parent
    
    # Official entrypoint
    entrypoint = repo_root / "src" / "FishBroWFS_V2" / "gui" / "viewer" / "app.py"
    
    # Find all Python files with __name__ guard and streamlit
    python_files = list(repo_root.rglob("*.py"))
    
    violations = []
    
    for py_file in python_files:
        # Skip test files
        if "test" in str(py_file) or "tests" in str(py_file):
            continue
        
        # Skip virtual environment directories
        if any(part in {'.venv', 'venv', 'env', '.virtualenv'} for part in py_file.parts):
            continue
        
        # Skip the official entrypoint
        if py_file == entrypoint:
            continue
        
        try:
            content = py_file.read_text(encoding="utf-8")
            
            # Check if file has both streamlit and __name__ guard
            has_streamlit = "streamlit" in content.lower()
            has_name_guard = '__name__' in content and '__main__' in content
            
            if has_streamlit and has_name_guard:
                violations.append(str(py_file))
        except (UnicodeDecodeError, OSError):
            continue
    
    if violations:
        violation_list = "\n".join(f"  - {v}" for v in sorted(violations))
        pytest.fail(
            f"Found {len(violations)} files with __name__ guard and streamlit imports:\n"
            f"{violation_list}\n\n"
            f"These might be trying to become Streamlit entrypoints.\n"
            f"Only {entrypoint} should have __name__ guard with streamlit."
        )


def test_allowlist_files_exist() -> None:
    """Test that allowlist files actually exist."""
    repo_root = Path(__file__).parent.parent
    
    allowlist_files = [
        repo_root / "src" / "FishBroWFS_V2" / "gui" / "viewer" / "app.py",
        repo_root / "src" / "FishBroWFS_V2" / "gui" / "research" / "page.py",
    ]
    
    missing_files = []
    for file_path in allowlist_files:
        if not file_path.exists():
            missing_files.append(str(file_path))
    
    if missing_files:
        missing_list = "\n".join(f"  - {f}" for f in missing_files)
        pytest.fail(
            f"Allowlist files not found:\n{missing_list}\n\n"
            f"These files are expected to exist in the allowlist."
        )


def test_allowlist_files_have_correct_structure() -> None:
    """Test that allowlist files have correct structure."""
    repo_root = Path(__file__).parent.parent
    
    # viewer/app.py should have main() and __name__ guard
    viewer_app = repo_root / "src" / "FishBroWFS_V2" / "gui" / "viewer" / "app.py"
    viewer_content = viewer_app.read_text(encoding="utf-8")
    
    assert "def main()" in viewer_content, "viewer/app.py must have main() function"
    assert '__name__' in viewer_content and '__main__' in viewer_content, \
        "viewer/app.py must have __name__ guard"
    assert "streamlit" in viewer_content.lower(), \
        "viewer/app.py must import streamlit"
    
    # research/page.py should NOT have main() or __name__ guard
    research_page = repo_root / "src" / "FishBroWFS_V2" / "gui" / "research" / "page.py"
    research_content = research_page.read_text(encoding="utf-8")
    
    assert "def render(" in research_content, "research/page.py must have render() function"
    assert "def main()" not in research_content, "research/page.py must NOT have main() function"
    assert not ('__name__' in research_content and '__main__' in research_content), \
        "research/page.py must NOT have __name__ guard"
    assert "streamlit" in research_content.lower(), \
        "research/page.py must import streamlit"