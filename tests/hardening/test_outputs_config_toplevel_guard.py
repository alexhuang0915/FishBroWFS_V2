import os
import sys
from pathlib import Path

def test_outputs_config_toplevel_guard():
    """Guard that prevents drift in outputs/ and configs/ top-level entries."""
    
    # A) Locate repo root robustly
    test_file_path = Path(__file__).resolve()
    repo_root = None
    for parent in test_file_path.parents:
        if (parent / "pyproject.toml").exists() or (parent / ".git").exists() or (parent / "Makefile").exists():
            repo_root = parent
            break
    
    if repo_root is None:
        raise AssertionError("Could not locate repository root. Must contain pyproject.toml, .git, or Makefile")
    
    # B) Verify directories exist
    outputs_dir = repo_root / "outputs"
    configs_dir = repo_root / "configs"
    
    if not outputs_dir.exists() or not outputs_dir.is_dir():
        raise AssertionError("outputs/ directory missing; repo contract requires it.")
    
    if not configs_dir.exists() or not configs_dir.is_dir():
        raise AssertionError("configs/ directory missing; repo contract requires it.")
    
    # C) Load allowlists
    outputs_allowlist_path = repo_root / "docs" / "contracts" / "OUTPUTS_TOPLEVEL_ALLOWLIST_V1.txt"
    configs_allowlist_path = repo_root / "docs" / "contracts" / "CONFIGS_TOPLEVEL_ALLOWLIST_V1.txt"
    
    # Read and parse outputs allowlist
    allowed_outputs = set()
    with open(outputs_allowlist_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '/' in line:
                raise AssertionError(f"Invalid entry in allowlist: '{line}' contains '/'")
            allowed_outputs.add(line)
    
    # Read and parse configs allowlist
    allowed_configs = set()
    with open(configs_allowlist_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            if '/' in line:
                raise AssertionError(f"Invalid entry in allowlist: '{line}' contains '/'")
            allowed_configs.add(line)
    
    # D) Compute actual top-level sets
    actual_outputs = {p.name for p in outputs_dir.iterdir() if p.name not in {".DS_Store", "Thumbs.db"}}
    actual_configs = {p.name for p in configs_dir.iterdir() if p.name not in {".DS_Store", "Thumbs.db"}}
    
    # E) Compare
    unexpected_outputs = actual_outputs - allowed_outputs
    unexpected_configs = actual_configs - allowed_configs
    
    if unexpected_outputs:
        raise AssertionError(f"Unexpected outputs top-level entries: {sorted(unexpected_outputs)}. If intentional, update docs/contracts/OUTPUTS_TOPLEVEL_ALLOWLIST_V1.txt")
    
    if unexpected_configs:
        raise AssertionError(f"Unexpected configs top-level entries: {sorted(unexpected_configs)}. If intentional, update docs/contracts/CONFIGS_TOPLEVEL_ALLOWLIST_V1.txt")
    
    # If we reach here, all is good
    assert True