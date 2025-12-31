"""Test contract that ensures all 7 tabs/pages use page_shell and have PAGE_SHELL_ENABLED = True.

This test locks down the enforcement of the layout constitution across the GUI.
"""
import importlib
import sys
import pytest

# List of page modules as per specification
PAGE_MODULES = [
    'gui.nicegui.pages.dashboard',
    'gui.nicegui.pages.wizard',
    'gui.nicegui.pages.history',
    'gui.nicegui.pages.candidates',
    'gui.nicegui.pages.portfolio',
    'gui.nicegui.pages.deploy',
    'gui.nicegui.pages.settings',
]


def test_page_shell_enabled_flag_exists():
    """Assert each page module has PAGE_SHELL_ENABLED = True."""
    for module_path in PAGE_MODULES:
        try:
            module = importlib.import_module(module_path)
        except ImportError as e:
            pytest.fail(f"Failed to import {module_path}: {e}")
        
        # Check that PAGE_SHELL_ENABLED is defined and equals True
        assert hasattr(module, 'PAGE_SHELL_ENABLED'), \
            f"Module {module_path} missing PAGE_SHELL_ENABLED constant"
        assert module.PAGE_SHELL_ENABLED is True, \
            f"Module {module_path} PAGE_SHELL_ENABLED is {module.PAGE_SHELL_ENABLED}, expected True"


def test_page_shell_imported():
    """Assert each page module imports page_shell from constitution."""
    for module_path in PAGE_MODULES:
        module = importlib.import_module(module_path)
        # Check that 'page_shell' is in the module's namespace
        assert 'page_shell' in dir(module), \
            f"Module {module_path} does not import page_shell"
        # Verify it's the correct function (optional)
        from gui.nicegui.constitution.page_shell import page_shell as expected
        assert module.page_shell is expected, \
            f"Module {module_path} page_shell is not the expected function"


def test_page_shell_used_in_render():
    """Smoke test: ensure each page's render function calls page_shell.
    
    This is a heuristic check: we look for a call to page_shell in the source code.
    """
    import inspect
    for module_path in PAGE_MODULES:
        module = importlib.import_module(module_path)
        # Find the render function (usually named 'render' or 'page')
        render_func = None
        for name, obj in inspect.getmembers(module, inspect.isfunction):
            if name in ('render', 'page', 'render_page'):
                render_func = obj
                break
        if render_func is None:
            # Some pages may have a different pattern; skip if not found
            continue
        source = inspect.getsource(render_func)
        # Check that 'page_shell' appears in the source (call)
        assert 'page_shell' in source, \
            f"Render function in {module_path} does not call page_shell"
        # Optionally check that it's called with arguments (title, content_fn)
        # but we'll keep it simple.


if __name__ == '__main__':
    pytest.main([__file__, '-v'])