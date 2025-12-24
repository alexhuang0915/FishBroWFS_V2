
"""Contract test: No ui namespace imports allowed.

Ensures the entire FishBroWFS_V2 package does not import from ui namespace.
"""

from __future__ import annotations

import ast
import pkgutil
from pathlib import Path

import pytest


def test_no_ui_namespace_importable() -> None:
    """Test that FishBroWFS_V2 package does not import from ui namespace."""
    import FishBroWFS_V2 as pkg
    
    ui_imports: list[tuple[str, str]] = []
    
    # Walk through all modules in FishBroWFS_V2 package
    for importer, modname, ispkg in pkgutil.walk_packages(pkg.__path__, pkg.__name__ + "."):
        try:
            # Import module to trigger any import errors
            module = __import__(modname, fromlist=[""])
            
            # Get source file path
            if hasattr(module, "__file__") and module.__file__:
                source_path = Path(module.__file__)
                if source_path.exists() and source_path.suffix == ".py":
                    # Parse AST to find imports
                    try:
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
                    except (SyntaxError, UnicodeDecodeError):
                        # Skip files that can't be parsed (might be binary or invalid)
                        pass
        except Exception as e:
            # Skip modules that fail to import (might be missing dependencies)
            # But log for debugging if it's not an ImportError
            if "ImportError" not in str(type(e)) and "ModuleNotFoundError" not in str(type(e)):
                pytest.fail(f"Unexpected error importing {modname}: {e}")
    
    # Should have no ui.* imports
    if ui_imports:
        pytest.fail(
            f"FishBroWFS_V2 package contains ui.* imports:\n"
            + "\n".join(f"  {mod}: {imp}" for mod, imp in ui_imports)
        )


def test_viewer_no_ui_imports() -> None:
    """Test that Viewer package specifically does not import from ui namespace."""
    import FishBroWFS_V2.gui.viewer as viewer
    
    ui_imports: list[tuple[str, str]] = []
    
    # Walk through all modules in viewer package
    for importer, modname, ispkg in pkgutil.walk_packages(viewer.__path__, viewer.__name__ + "."):
        try:
            module = __import__(modname, fromlist=[""])
            
            if hasattr(module, "__file__") and module.__file__:
                source_path = Path(module.__file__)
                if source_path.exists() and source_path.suffix == ".py":
                    try:
                        with source_path.open("r", encoding="utf-8") as f:
                            tree = ast.parse(f.read(), filename=str(source_path))
                        
                        for node in ast.walk(tree):
                            if isinstance(node, ast.Import):
                                for alias in node.names:
                                    if alias.name.startswith("ui."):
                                        ui_imports.append((modname, alias.name))
                            elif isinstance(node, ast.ImportFrom):
                                if node.module and node.module.startswith("ui."):
                                    ui_imports.append((modname, f"from {node.module}"))
                    except (SyntaxError, UnicodeDecodeError):
                        pass
        except Exception as e:
            if "ImportError" not in str(type(e)) and "ModuleNotFoundError" not in str(type(e)):
                pytest.fail(f"Unexpected error importing {modname}: {e}")
    
    if ui_imports:
        pytest.fail(
            f"Viewer package contains ui.* imports:\n"
            + "\n".join(f"  {mod}: {imp}" for mod, imp in ui_imports)
        )


def test_no_ui_directory_exists() -> None:
    """Test that ui/ directory does not exist in repo root (repo structure contract)."""
    repo_root = Path(__file__).parent.parent
    ui_dir = repo_root / "ui"
    
    if ui_dir.exists():
        pytest.fail(f"ui/ directory must not exist in repo root, but found at {ui_dir}")


def test_makefile_no_ui_paths() -> None:
    """Test that Makefile does not reference ui/ paths (old namespace)."""
    repo_root = Path(__file__).parent.parent
    makefile_path = repo_root / "Makefile"
    
    assert makefile_path.exists()
    
    content = makefile_path.read_text()
    
    # Check for ui/ references (excluding comments)
    lines = content.split("\n")
    for i, line in enumerate(lines, 1):
        # Skip comments
        if line.strip().startswith("#"):
            continue
        
        # Normalize line for checking
        line_lower = line.lower()
        
        # Prohibited patterns (old ui namespace)
        # 1. Path references containing "/ui/" (excluding "gui/")
        if "/ui/" in line and "/gui/" not in line:
            pytest.fail(f"Makefile line {i} contains prohibited /ui/ path: {line.strip()}")
        
        # 2. Import-like references to "FishBroWFS_V2.ui." (case-insensitive)
        if "fishbro_wfs_v2.ui." in line_lower:
            pytest.fail(f"Makefile line {i} contains prohibited FishBroWFS_V2.ui. import: {line.strip()}")
        
        # 3. Specific old module "ui.app_streamlit"
        if "ui.app_streamlit" in line_lower:
            pytest.fail(f"Makefile line {i} contains prohibited ui.app_streamlit: {line.strip()}")
        
        # 4. Standalone "ui." as a module prefix (with word boundary)
        # We'll use a simple check: "ui." preceded by whitespace or start of line
        # but exclude "gui." and "build" etc.
        import re
        if re.search(r'(^|\s)ui\.', line) and not re.search(r'(^|\s)gui\.', line):
            # Allow if it's part of a longer word like "build" (but "ui." is likely a module)
            # Additional check: ensure it's not part of a larger word like "build"
            if not re.search(r'\bui\.', line):  # word boundary check
                continue
            pytest.fail(f"Makefile line {i} contains prohibited ui. module reference: {line.strip()}")


