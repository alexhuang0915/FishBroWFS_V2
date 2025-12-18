"""Contract test: Viewer must not import ui namespace.

Ensures Viewer code only uses FishBroWFS_V2.* imports, not ui.*
"""

from __future__ import annotations

import ast
import pkgutil
from pathlib import Path

import pytest


def test_viewer_no_ui_imports() -> None:
    """Test that Viewer package does not import from ui namespace."""
    import FishBroWFS_V2.gui.viewer as viewer
    
    ui_imports: list[tuple[str, str]] = []
    
    # Walk through all modules in viewer package
    for importer, modname, ispkg in pkgutil.walk_packages(viewer.__path__, viewer.__name__ + "."):
        try:
            # Import module to trigger any import errors
            module = __import__(modname, fromlist=[""])
            
            # Get source file path
            if hasattr(module, "__file__") and module.__file__:
                source_path = Path(module.__file__)
                if source_path.exists() and source_path.suffix == ".py":
                    # Parse AST to find imports
                    with source_path.open("r", encoding="utf-8") as f:
                        tree = ast.parse(f.read(), filename=str(source_path))
                    
                    # Check all imports
                    for node in ast.walk(tree):
                        if isinstance(node, ast.Import):
                            for alias in node.names:
                                if alias.name.startswith("ui."):
                                    ui_imports.append((modname, alias.name))
                        elif isinstance(node, ast.ImportFrom):
                            if node.module and node.module.startswith("ui."):
                                ui_imports.append((modname, f"from {node.module}"))
        except Exception as e:
            # Skip modules that fail to import (might be missing dependencies)
            # But log for debugging
            if "ImportError" not in str(type(e)):
                pytest.fail(f"Unexpected error importing {modname}: {e}")
    
    # Should have no ui.* imports
    if ui_imports:
        pytest.fail(
            f"Viewer package contains ui.* imports:\n"
            + "\n".join(f"  {mod}: {imp}" for mod, imp in ui_imports)
        )


def test_viewer_imports_compile() -> None:
    """Test that all Viewer imports can be compiled."""
    import FishBroWFS_V2.gui.viewer as viewer
    
    # Try to import all modules (will catch import errors)
    for importer, modname, ispkg in pkgutil.walk_packages(viewer.__path__, viewer.__name__ + "."):
        try:
            __import__(modname, fromlist=[""])
        except ImportError as e:
            # Only fail if it's a missing dependency we can't handle
            if "ui." in str(e):
                pytest.fail(f"Viewer module {modname} imports ui.*: {e}")


def test_viewer_entrypoint_no_ui_import() -> None:
    """Test that Viewer entrypoint does not import ui."""
    repo_root = Path(__file__).parent.parent
    entrypoint_path = repo_root / "src/FishBroWFS_V2/gui/viewer/app.py"
    
    assert entrypoint_path.exists()
    
    content = entrypoint_path.read_text()
    
    # Check for ui.* imports
    if "from ui." in content or "import ui." in content:
        pytest.fail("Viewer entrypoint contains ui.* imports")


def test_viewer_pages_no_ui_artifact_reader_import() -> None:
    """Test that Viewer pages do not import ui.core.artifact_reader."""
    repo_root = Path(__file__).parent.parent
    pages_dir = repo_root / "src/FishBroWFS_V2/gui/viewer/pages"
    
    if not pages_dir.exists():
        return  # No pages directory
    
    for page_file in pages_dir.glob("*.py"):
        if page_file.name == "__init__.py":
            continue
        
        content = page_file.read_text()
        
        # Check for ui.core.artifact_reader imports (should use FishBroWFS_V2.core.artifact_reader)
        if "from ui.core.artifact_reader" in content or "import ui.core.artifact_reader" in content:
            pytest.fail(f"Viewer page {page_file.name} imports ui.core.artifact_reader (should use FishBroWFS_V2.core.artifact_reader)")


def test_viewer_page_scaffold_no_ui_artifact_reader_import() -> None:
    """Test that Viewer page_scaffold does not import ui.core.artifact_reader."""
    repo_root = Path(__file__).parent.parent
    scaffold_file = repo_root / "src/FishBroWFS_V2/gui/viewer/page_scaffold.py"
    
    assert scaffold_file.exists()
    
    content = scaffold_file.read_text()
    
    # Check for ui.core.artifact_reader imports (should use FishBroWFS_V2.core.artifact_reader)
    if "from ui.core.artifact_reader" in content or "import ui.core.artifact_reader" in content:
        pytest.fail("Viewer page_scaffold imports ui.core.artifact_reader (should use FishBroWFS_V2.core.artifact_reader)")
