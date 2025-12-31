"""Test that all UI pages use the page_shell wrapper.

This test enforces the Page Wrapper Guarantee from the UI Constitution:
every page content must be rendered inside the same dark container with
consistent padding/width and min-height: 100vh.

The test inspects the source code of all page modules to verify they import
and call page_shell().
"""

import ast
import importlib
import inspect
import sys
from pathlib import Path
from typing import List, Set
import pytest


# List of all page modules that must use page_shell
PAGE_MODULES = [
    "gui.nicegui.pages.dashboard",
    "gui.nicegui.pages.wizard",
    "gui.nicegui.pages.history",
    "gui.nicegui.pages.candidates",
    "gui.nicegui.pages.portfolio",
    "gui.nicegui.pages.deploy",
    "gui.nicegui.pages.settings",
]


def get_page_module_path(module_name: str) -> Path:
    """Get the file path for a page module."""
    try:
        spec = importlib.util.find_spec(module_name)
        if spec and spec.origin:
            return Path(spec.origin)
    except (ImportError, AttributeError):
        pass
    
    # Fallback: construct path from module name
    parts = module_name.split(".")
    rel_path = Path("/".join(parts[1:]) + ".py")  # Skip 'gui' prefix
    return Path("src") / rel_path


def parse_imports(source_code: str) -> Set[str]:
    """Parse imports from Python source code."""
    imports = set()
    try:
        tree = ast.parse(source_code)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.add(node.module)
                    # Also add specific imports
                    for alias in node.names:
                        imports.add(f"{node.module}.{alias.name}")
    except SyntaxError:
        pass
    return imports


def find_page_shell_usage(source_code: str) -> bool:
    """Check if source code contains page_shell() call."""
    # Look for page_shell() function call
    if "page_shell(" in source_code:
        return True
    
    # Also check for render_in_constitution_shell() which is the lower-level API
    if "render_in_constitution_shell(" in source_code:
        return True
    
    return False


def get_render_function_source(module) -> str:
    """Get the source code of the render() function from a module."""
    try:
        render_func = getattr(module, "render", None)
        if render_func and callable(render_func):
            return inspect.getsource(render_func)
    except (TypeError, OSError):
        pass
    return ""


class TestPageShellUsedEverywhere:
    """Test that all pages use the page_shell wrapper."""
    
    @pytest.mark.parametrize("module_name", PAGE_MODULES)
    def test_page_imports_page_shell(self, module_name: str):
        """Verify that the page module imports page_shell or related constitution modules."""
        module_path = get_page_module_path(module_name)
        assert module_path.exists(), f"Page module not found: {module_path}"
        
        # Read source code
        source_code = module_path.read_text(encoding="utf-8")
        
        # Check imports
        imports = parse_imports(source_code)
        
        # Must import at least one of these
        required_imports = [
            "gui.nicegui.constitution.page_shell",
            "..constitution.page_shell",
            ".constitution.page_shell",
            "constitution.page_shell",
        ]
        
        # Check for any constitution-related import
        has_constitution_import = any(
            "constitution" in imp for imp in imports
        ) or any(
            imp.endswith(".page_shell") for imp in imports
        )
        
        assert has_constitution_import, (
            f"Page {module_name} does not import constitution.page_shell. "
            f"Found imports: {imports}"
        )
    
    @pytest.mark.parametrize("module_name", PAGE_MODULES)
    def test_page_calls_page_shell(self, module_name: str):
        """Verify that the page's render() function calls page_shell()."""
        module_path = get_page_module_path(module_name)
        assert module_path.exists(), f"Page module not found: {module_path}"
        
        # Read source code
        source_code = module_path.read_text(encoding="utf-8")
        
        # Check for page_shell() call in the entire module
        # (it should be in the render() function, but we'll check whole module)
        if not find_page_shell_usage(source_code):
            # Try to import the module and check the render function source
            try:
                module = importlib.import_module(module_name)
                render_source = get_render_function_source(module)
                if render_source and find_page_shell_usage(render_source):
                    return  # Success
            except ImportError:
                pass
            
            # If we get here, page_shell() was not found
            pytest.fail(
                f"Page {module_name} does not call page_shell() or "
                f"render_in_constitution_shell(). "
                f"All pages must wrap their content in the constitution shell."
            )
    
    @pytest.mark.parametrize("module_name", PAGE_MODULES)
    def test_page_has_correct_structure(self, module_name: str):
        """Verify that the page follows the correct render() -> page_shell() pattern."""
        module_path = get_page_module_path(module_name)
        source_code = module_path.read_text(encoding="utf-8")
        
        # Check for the pattern: def render(): ... page_shell(...)
        lines = source_code.split("\n")
        in_render_func = False
        render_func_indent = 0
        found_page_shell_in_render = False
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            # Look for render function definition
            if stripped.startswith("def render()") or stripped.startswith("def render():") or stripped.startswith("def render( )"):
                in_render_func = True
                # Calculate indentation
                render_func_indent = len(line) - len(line.lstrip())
                continue
            
            if in_render_func:
                # Check if we're still in the same function
                current_indent = len(line) - len(line.lstrip())
                if stripped and current_indent <= render_func_indent and not stripped.startswith("#"):
                    # We've left the render function
                    in_render_func = False
                    continue
                
                # Check for page_shell call
                if "page_shell(" in line or "render_in_constitution_shell(" in line:
                    found_page_shell_in_render = True
        
        assert found_page_shell_in_render, (
            f"Page {module_name} does not call page_shell() within its render() function. "
            f"The render() function must wrap its content with page_shell(title, content_fn)."
        )
    
    def test_all_pages_accounted_for(self):
        """Verify that we're testing all existing page modules."""
        pages_dir = Path("src/gui/nicegui/pages")
        if not pages_dir.exists():
            pytest.skip("Pages directory not found")
        
        # Find all Python files in pages directory
        page_files = list(pages_dir.glob("*.py"))
        
        # Exclude special pages that don't need page_shell
        # - forensics.py is a hidden diagnostic page
        # - __init__.py is not a page
        excluded_pages = {"__init__", "forensics"}
        page_modules_found = [f.stem for f in page_files if f.stem not in excluded_pages]
        
        # Convert our expected module names to just the filename stem
        expected_stems = [name.split(".")[-1] for name in PAGE_MODULES]
        
        # Check that all found pages are in our list
        for stem in page_modules_found:
            assert stem in expected_stems, (
                f"Page {stem}.py found but not in test list. "
                f"Add 'gui.nicegui.pages.{stem}' to PAGE_MODULES."
            )
        
        # Also check that all expected pages exist
        for stem in expected_stems:
            assert (pages_dir / f"{stem}.py").exists(), (
                f"Expected page {stem}.py not found in {pages_dir}"
            )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])