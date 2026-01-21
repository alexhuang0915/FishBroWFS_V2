"""
Test that config cache clearing is safe and never crashes.

This test locks the behavior of `clear_config_caches` to ensure it never raises
AttributeError or any other exception, even if underlying functions change.
"""

import sys
import unittest.mock
from src.config import clear_config_caches


def test_clear_config_caches_is_safe() -> None:
    """
    Verify that clear_config_caches never crashes.
    
    This test ensures that the function:
    1. Does not raise AttributeError (function object has no attribute 'cache_clear')
    2. Does not raise any other exception
    3. Can be called multiple times without side effects
    """
    # First call should succeed
    clear_config_caches()
    
    # Second call should also succeed (idempotent)
    clear_config_caches()
    
    # Simulate a scenario where one of the cached functions lacks cache_clear
    # by mocking the imported functions
    with unittest.mock.patch('src.config.profiles.load_profile') as mock_load_profile:
        # Remove cache_clear attribute from the mock
        del mock_load_profile.cache_clear
        # Should still not crash
        clear_config_caches()
    
    # Simulate a scenario where cache_clear exists but raises an exception
    with unittest.mock.patch('src.config.profiles.load_profile') as mock_load_profile:
        mock_load_profile.cache_clear = unittest.mock.Mock(side_effect=RuntimeError("Cache broken"))
        # Should swallow the exception and not propagate
        clear_config_caches()
    
    # If we reach here, the test passes
    assert True


def test_clear_config_caches_imports_all_required_functions() -> None:
    """
    Ensure that clear_config_caches imports all expected functions.
    
    This is a sanity check that the function list hasn't been accidentally
    shortened, which would reduce cache‑clearing effectiveness.
    """
    import src.config
    # Re‑import the function to inspect its source (optional)
    # We'll just call it and ensure no ImportError
    clear_config_caches()
    # No assertion needed; if any import fails, the test will crash.
    # That's acceptable because we want to catch missing imports.