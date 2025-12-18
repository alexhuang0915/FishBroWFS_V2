"""Contract test: No ui namespace imports anywhere in FishBroWFS_V2.

Ensures the entire FishBroWFS_V2 package does not import from ui namespace.
This is a "truth test" to prevent any ui.* imports from being reintroduced.
"""

from __future__ import annotations

import pkgutil

import pytest


def test_no_ui_namespace_anywhere() -> None:
    """Test that FishBroWFS_V2 package does not import from ui namespace."""
    import FishBroWFS_V2
    
    # Walk through all modules in FishBroWFS_V2 package
    # If any module imports ui.*, it will fail during import
    for importer, modname, ispkg in pkgutil.walk_packages(FishBroWFS_V2.__path__, FishBroWFS_V2.__name__ + "."):
        try:
            # Import module - this will fail if it imports ui.* and ui doesn't exist
            __import__(modname, fromlist=[""])
        except ImportError as e:
            # Check if error is related to ui namespace
            if "ui" in str(e) and ("No module named" in str(e) or "cannot import name" in str(e)):
                pytest.fail(
                    f"Module {modname} imports from ui namespace (ui module no longer exists): {e}"
                )
            # Re-raise other ImportErrors (might be legitimate missing dependencies)
            raise
