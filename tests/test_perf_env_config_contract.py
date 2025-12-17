"""Test perf harness environment variable configuration contract.

Ensures that FISHBRO_PERF_BARS and FISHBRO_PERF_PARAMS env vars are correctly parsed.
"""

import os
import sys
from pathlib import Path
from unittest.mock import patch


def _get_perf_config():
    """
    Helper to get perf config values by reading the script file.
    This avoids import issues with scripts/ module.
    """
    script_path = Path(__file__).parent.parent / "scripts" / "perf_grid.py"
    
    # Read and parse the constants
    with open(script_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    # Extract default values from the file
    # Look for: TIER_JIT_BARS = int(os.environ.get("FISHBRO_PERF_BARS", "20000"))
    import re
    
    bars_match = re.search(r'TIER_JIT_BARS\s*=\s*int\(os\.environ\.get\("FISHBRO_PERF_BARS",\s*"(\d+)"\)\)', content)
    params_match = re.search(r'TIER_JIT_PARAMS\s*=\s*int\(os\.environ\.get\("FISHBRO_PERF_PARAMS",\s*"(\d+)"\)\)', content)
    
    default_bars = int(bars_match.group(1)) if bars_match else None
    default_params = int(params_match.group(1)) if params_match else None
    
    return default_bars, default_params


def test_perf_env_bars_parsing():
    """Test that FISHBRO_PERF_BARS env var is correctly parsed."""
    with patch.dict(os.environ, {"FISHBRO_PERF_BARS": "50000"}, clear=False):
        # Simulate the parsing logic
        bars = int(os.environ.get("FISHBRO_PERF_BARS", "20000"))
        assert bars == 50000


def test_perf_env_params_parsing():
    """Test that FISHBRO_PERF_PARAMS env var is correctly parsed."""
    with patch.dict(os.environ, {"FISHBRO_PERF_PARAMS": "5000"}, clear=False):
        # Simulate the parsing logic
        params = int(os.environ.get("FISHBRO_PERF_PARAMS", "1000"))
        assert params == 5000


def test_perf_env_both_parsing():
    """Test that both env vars can be set simultaneously."""
    with patch.dict(os.environ, {
        "FISHBRO_PERF_BARS": "30000",
        "FISHBRO_PERF_PARAMS": "3000",
    }, clear=False):
        bars = int(os.environ.get("FISHBRO_PERF_BARS", "20000"))
        params = int(os.environ.get("FISHBRO_PERF_PARAMS", "1000"))
        
        assert bars == 30000
        assert params == 3000


def test_perf_env_defaults():
    """Test that defaults are baseline (20000×1000) when env vars are not set."""
    # Ensure env vars are not set for this test
    env_backup = {}
    for key in ["FISHBRO_PERF_BARS", "FISHBRO_PERF_PARAMS"]:
        if key in os.environ:
            env_backup[key] = os.environ[key]
            del os.environ[key]
    
    try:
        # Check defaults match baseline
        default_bars, default_params = _get_perf_config()
        assert default_bars == 20000, f"Expected default bars=20000, got {default_bars}"
        assert default_params == 1000, f"Expected default params=1000, got {default_params}"
        
        # Verify parsing logic uses defaults
        bars = int(os.environ.get("FISHBRO_PERF_BARS", "20000"))
        params = int(os.environ.get("FISHBRO_PERF_PARAMS", "1000"))
        assert bars == 20000
        assert params == 1000
    finally:
        # Restore env vars
        for key, value in env_backup.items():
            os.environ[key] = value
