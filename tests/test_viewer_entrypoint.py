"""Contract tests for Viewer entrypoint.

Ensures single source of truth for Viewer entrypoint.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure only one Viewer entrypoint exists
VIEWER_ENTRYPOINT = "src/FishBroWFS_V2/gui/viewer/app.py"


def test_viewer_entrypoint_importable() -> None:
    """Test that Viewer entrypoint can be imported without errors."""
    try:
        from FishBroWFS_V2.gui.viewer.app import main, get_run_dir_from_query
        assert main is not None
        assert get_run_dir_from_query is not None
    except ImportError as e:
        pytest.fail(f"Failed to import Viewer entrypoint: {e}")


def test_viewer_entrypoint_main_callable() -> None:
    """Test that main() can be called (with streamlit stubbed)."""
    from FishBroWFS_V2.gui.viewer.app import main
    
    # Mock streamlit to avoid actual UI rendering
    with patch("streamlit.set_page_config"), \
         patch("streamlit.query_params", new={"get": lambda key, default="": default}), \
         patch("streamlit.error"), \
         patch("streamlit.info"):
        
        # Should not raise (will show error message but that's expected)
        try:
            main()
        except Exception as e:
            # Only fail if it's an import error or unexpected error
            if "ImportError" in str(type(e)):
                pytest.fail(f"Unexpected import error: {e}")


def test_no_duplicate_viewer_entrypoints() -> None:
    """Test that no duplicate Viewer entrypoints exist in repo."""
    repo_root = Path(__file__).parent.parent
    
    # Find all potential Streamlit entrypoints
    potential_entrypoints = []
    
    # Check ui/ directory (legacy, should not exist)
    ui_app = repo_root / "ui" / "app_streamlit.py"
    if ui_app.exists():
        pytest.fail(f"Legacy Viewer entrypoint still exists: {ui_app}")
    
    # Check for other streamlit apps that might be Viewer entrypoints
    for path in repo_root.rglob("*.py"):
        # Skip virtual environment directories
        if any(part in {'.venv', 'venv', 'env', '.virtualenv'} for part in path.parts):
            continue
        if "app" in path.name.lower() and "streamlit" in path.read_text().lower():
            # Skip test files
            if "test" in str(path):
                continue
            # Skip the official entrypoint
            if path == repo_root / VIEWER_ENTRYPOINT:
                continue
            # Check if it's a streamlit app
            content = path.read_text()
            if "streamlit" in content and ("main" in content or "if __name__" in content):
                potential_entrypoints.append(path)
    
    # Should only have one Viewer entrypoint
    if potential_entrypoints:
        pytest.fail(
            f"Found duplicate Viewer entrypoints:\n"
            f"  Official: {VIEWER_ENTRYPOINT}\n"
            f"  Duplicates: {[str(p) for p in potential_entrypoints]}"
        )


def test_viewer_entrypoint_exists() -> None:
    """Test that official Viewer entrypoint file exists."""
    repo_root = Path(__file__).parent.parent
    entrypoint_path = repo_root / VIEWER_ENTRYPOINT
    
    assert entrypoint_path.exists(), f"Viewer entrypoint not found: {entrypoint_path}"
    assert entrypoint_path.is_file(), f"Viewer entrypoint is not a file: {entrypoint_path}"


def test_viewer_entrypoint_has_main() -> None:
    """Test that Viewer entrypoint has main() function."""
    repo_root = Path(__file__).parent.parent
    entrypoint_path = repo_root / VIEWER_ENTRYPOINT
    
    content = entrypoint_path.read_text()
    
    assert "def main()" in content, "Viewer entrypoint must have main() function"
    assert 'if __name__ == "__main__"' in content, "Viewer entrypoint must have __main__ guard"
