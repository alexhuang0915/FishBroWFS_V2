import pytest
import os
import logging
from pipeline.runner_grid import run_grid
import numpy as np

def test_runner_bad_env_var_warning(caplog):
    """L1 Runner: Verify warning on malformed env var."""
    # We need to set the env var and run run_grid
    # run_grid reads env var inside.
    
    # Minimal inputs
    open_ = np.array([100.0, 101.0, 102.0])
    high = np.array([101.0, 102.0, 103.0])
    low = np.array([99.0, 100.0, 101.0])
    close = np.array([100.5, 101.5, 102.5])
    params = np.array([[10, 20, 1.5]])
    
    with patch.dict(os.environ, {"FISHBRO_PERF_TRIGGER_RATE": "not_a_float"}):
        with caplog.at_level(logging.WARNING):
            try:
                run_grid(open_, high, low, close, params, commission=0, slip=0)
            except Exception:
                pass # We don't care if it fails later, just want to check the warning log
            
            assert "Invalid FISHBRO_PERF_TRIGGER_RATE" in caplog.text
            assert "Falling back to 1.0" in caplog.text

def test_runner_strict_env_var_failure():
    """L1 Runner: Verify strict mode raises error on malformed env var."""
    open_ = np.array([100.0])
    high = np.array([101.0])
    low = np.array([99.0])
    close = np.array([100.5])
    params = np.array([[10, 20, 1.5]])

    with patch.dict(os.environ, {"FISHBRO_PERF_TRIGGER_RATE": "bad", "FISHBRO_STRICT_ENV": "1"}):
        with pytest.raises(ValueError, match="Invalid FISHBRO_PERF_TRIGGER_RATE"):
             run_grid(open_, high, low, close, params, commission=0, slip=0)

from unittest.mock import patch
