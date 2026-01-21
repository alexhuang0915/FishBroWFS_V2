import pytest
import os
import logging
from unittest.mock import patch, MagicMock

def test_jit_import_failure_warning(caplog):
    """L1-1: Verify warning is logged when Numba import fails."""
    # We can't easily unload numba if it's already loaded, 
    # but we can verify the logic by mocking the module where it's used/imported if we could reload
    # OR we can inspect the source code's try/except block behavior simulation.
    # Since we modified engine_jit.py, let's try to simulate the import failure by 
    # manipulating sys.modules or using a subprocess test.
    # Subprocess is cleaner for import side-effects.
    
    code = """
import sys
import logging
logging.basicConfig(level=logging.WARNING)
# Mock numba to fail import
import builtins
real_import = builtins.__import__
def mock_import(name, *args, **kwargs):
    if name == 'numba':
        raise ImportError("Mocked import error")
    return real_import(name, *args, **kwargs)
builtins.__import__ = mock_import

from engine import engine_jit
"""
    import subprocess
    import sys
    
    res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env={**os.environ, "PYTHONPATH": "src"})
    assert "Numba import failed" in res.stderr
    assert "Falling back to Python reference engine" in res.stderr

def test_jit_strict_mode_failure():
    """L1-1: Verify FISHBRO_STRICT_JIT=1 raises error on Numba failure."""
    code = """
import sys
import os
# Mock numba to fail import
import builtins
real_import = builtins.__import__
def mock_import(name, *args, **kwargs):
    if name == 'numba':
        raise ImportError("Mocked import error")
    return real_import(name, *args, **kwargs)
builtins.__import__ = mock_import

try:
    from engine import engine_jit
except RuntimeError as e:
    print(f"Caught expected error: {e}")
    sys.exit(0)
sys.exit(1)
"""
    import subprocess
    import sys
    
    env = {**os.environ, "PYTHONPATH": "src", "FISHBRO_STRICT_JIT": "1"}
    res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env)
    assert res.returncode == 0
    assert "Numba import failed in STRICT mode" in res.stdout
