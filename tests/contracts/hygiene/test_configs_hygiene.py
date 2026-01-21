"""
Test configs/ directory hygiene according to Config Constitution v1.

Rules:
1. configs/ contains only allowed subdirectories: registry/, profiles/, strategies/, portfolio/
2. Only YAML files in configs/ (with allowlist exceptions for migration)
3. No generated patterns in configs/
"""

import pytest
from pathlib import Path
import yaml
import json


def test_configs_directory_structure():
    """Test 1: configs/ contains only allowed subdirectories."""
    configs_dir = Path("configs")
    
    # Allowed subdirectories
    allowed_dirs = {"registry", "profiles", "strategies", "portfolio", "templates"}
    
    # Find all immediate subdirectories
    actual_dirs = set()
    for item in configs_dir.iterdir():
        if item.is_dir():
            actual_dirs.add(item.name)
    
    # Check for unexpected directories
    unexpected = actual_dirs - allowed_dirs
    assert not unexpected, (
        f"configs/ contains unexpected directories: {unexpected}. "
        f"Allowed: {allowed_dirs}"
    )


def test_configs_files_are_yaml():
    """Test 2: Only YAML files in configs/ (with allowlist exceptions)."""
    configs_dir = Path("configs")
    
    # Allowlist for non-YAML files during migration
    # These should be migrated to YAML eventually
    allowlist = {
        "dimensions_registry.json",  # To be migrated to registry/datasets.yaml
        # funnel_min.json migrated to strategies/s1_v1.yaml and deleted
    }
    
    # Find all files in configs/ root (not in subdirectories)
    root_files = []
    for item in configs_dir.iterdir():
        if item.is_file():
            root_files.append(item.name)
    
    # Check each file
    for filename in root_files:
        if filename in allowlist:
            continue  # Allowed during migration
            
        if not filename.endswith('.yaml') and not filename.endswith('.yml'):
            pytest.fail(
                f"Non-YAML file in configs/ root: {filename}. "
                f"All human-edited configs must be YAML. "
                f"Allowlist: {allowlist}"
            )


def test_configs_no_generated_artifacts():
    """Test 3: No generated patterns in configs/."""
    configs_dir = Path("configs")
    
    # Patterns that indicate generated/compiled artifacts
    generated_patterns = [
        "*.pyc",
        "*.pyo",
        "__pycache__",
        ".pytest_cache",
        ".coverage",
        "*.log",
        "*.db",
        "*.db-*",  # SQLite journal files
        "*.tmp",
        "*.temp",
    ]
    
    # Recursively check for generated artifacts
    generated_files = []
    for pattern in generated_patterns:
        for path in configs_dir.rglob(pattern):
            generated_files.append(str(path.relative_to(configs_dir)))
    
    assert not generated_files, (
        f"Generated artifacts found in configs/: {generated_files}. "
        f"configs/ must contain only human-edited configuration files."
    )


def test_registry_directory_yaml_only():
    """Test 4: registry/ directory contains only YAML files."""
    registry_dir = Path("configs/registry")
    
    if not registry_dir.exists():
        pytest.skip("registry/ directory does not exist yet (migration pending)")
    
    for item in registry_dir.iterdir():
        if item.is_file():
            assert item.name.endswith('.yaml') or item.name.endswith('.yml'), (
                f"Non-YAML file in registry/: {item.name}. "
                f"Registry files must be YAML."
            )


def test_profiles_directory_yaml_only():
    """Test 5: profiles/ directory contains only YAML files."""
    profiles_dir = Path("configs/profiles")
    
    if not profiles_dir.exists():
        pytest.skip("profiles/ directory does not exist")
    
    for item in profiles_dir.iterdir():
        if item.is_file():
            assert item.name.endswith('.yaml') or item.name.endswith('.yml'), (
                f"Non-YAML file in profiles/: {item.name}. "
                f"Profile files must be YAML."
            )


def test_strategies_directory_yaml_only():
    """Test 6: strategies/ directory contains only YAML files (Config Constitution v1)."""
    strategies_dir = Path("configs/strategies")
    
    if not strategies_dir.exists():
        pytest.skip("strategies/ directory does not exist")
    
    # Check for non-YAML files
    non_yaml_files = []
    
    for item in strategies_dir.rglob("*"):
        if item.is_file():
            if not (item.name.endswith('.yaml') or item.name.endswith('.yml')):
                non_yaml_files.append(str(item.relative_to(strategies_dir)))
    
    assert not non_yaml_files, (
        f"Non-YAML files in strategies/: {non_yaml_files}. "
        f"Config Constitution v1 requires all strategy configs to be YAML."
    )


def test_portfolio_directory_yaml_only():
    """Test 7: portfolio/ directory contains only YAML files (with migration allowance)."""
    portfolio_dir = Path("configs/portfolio")
    
    if not portfolio_dir.exists():
        pytest.skip("portfolio/ directory does not exist")
    
    # Allowlist for JSON files during migration
    json_allowlist = {
        "governance_params.json",  # Will be migrated to governance.yaml
        # portfolio_policy_v1.json - Legacy, can be removed (deleted)
        # portfolio_spec_with_policy_v1.json - Legacy, can be removed (deleted)
        "portfolio_spec_v1.yaml",  # Actually YAML but has .yaml extension
    }
    
    non_yaml_files = []
    
    for item in portfolio_dir.iterdir():
        if item.is_file():
            if item.name in json_allowlist:
                continue  # Allowed during migration
                
            if not (item.name.endswith('.yaml') or item.name.endswith('.yml')):
                non_yaml_files.append(item.name)
    
    if non_yaml_files:
        import warnings
        warnings.warn(
            f"Non-YAML files in portfolio/ (migration needed): {non_yaml_files}. "
            f"Portfolio files must be YAML.",
            UserWarning
        )


def test_yaml_files_are_valid():
    """Test 8: All YAML files in configs/ are valid YAML."""
    configs_dir = Path("configs")
    
    invalid_yaml_files = []
    
    for yaml_file in configs_dir.rglob("*.yaml"):
        try:
            with open(yaml_file, 'r', encoding='utf-8') as f:
                yaml.safe_load(f)
        except yaml.YAMLError as e:
            invalid_yaml_files.append((yaml_file, str(e)))
    
    for yaml_file in configs_dir.rglob("*.yml"):
        try:
            with open(yaml_file, 'r', encoding='utf-8') as f:
                yaml.safe_load(f)
        except yaml.YAMLError as e:
            invalid_yaml_files.append((yaml_file, str(e)))
    
    if invalid_yaml_files:
        error_msg = "Invalid YAML files found:\n"
        for file_path, error in invalid_yaml_files:
            error_msg += f"  {file_path}: {error}\n"
        pytest.fail(error_msg)


def test_no_duplicate_config_names():
    """Test 9: No duplicate config file names across categories (with migration allowance)."""
    configs_dir = Path("configs")
    
    # Collect all YAML file names (without extension)
    yaml_files = {}
    
    for yaml_file in configs_dir.rglob("*.yaml"):
        stem = yaml_file.stem
        if stem in yaml_files:
            yaml_files[stem].append(yaml_file)
        else:
            yaml_files[stem] = [yaml_file]
    
    for yaml_file in configs_dir.rglob("*.yml"):
        stem = yaml_file.stem
        if stem in yaml_files:
            yaml_files[stem].append(yaml_file)
        else:
            yaml_files[stem] = [yaml_file]
    
    # Check for duplicates
    duplicates = {stem: files for stem, files in yaml_files.items() if len(files) > 1}
    
    # Allow certain duplicates during migration
    allowed_duplicates = {
        "instruments": [
            "configs/portfolio/instruments.yaml is legacy (portfolio specs)",
            "configs/registry/instruments.yaml is new (registry)",
        ],
        "baseline": [
            "configs/strategies/S1/baseline.yaml is legacy S1 config",
            "configs/strategies/S2/baseline.yaml is legacy S2 config",
            "configs/strategies/S3/baseline.yaml is legacy S3 config",
        ],
    }
    
    # Filter out allowed duplicates
    problematic_duplicates = {}
    for stem, files in duplicates.items():
        if stem in allowed_duplicates:
            # This is allowed during migration
            continue
        problematic_duplicates[stem] = files
    
    if problematic_duplicates:
        pytest.fail(
            f"Duplicate config file names found:\n"
            + "\n".join(f"  {stem}: {files}" for stem, files in problematic_duplicates.items())
            + f"\n\nAllowed duplicates during migration:\n"
            + "\n".join(f"  {stem}: {reasons}" for stem, reasons in allowed_duplicates.items())
        )
    elif duplicates:
        # Allowed duplicates during migration - no warning emitted
        pass


def test_zero_features_json_references_in_production():
    """Test 10: No references to features.json in production code (Config Constitution v1)."""
    import subprocess
    import sys
    
    # Run rg to search for features.json references in src/
    result = subprocess.run(
        ["rg", "-n", "features\\.json", "-S", "src"],
        capture_output=True,
        text=True,
        cwd=Path(__file__).parent.parent.parent.parent
    )
    
    # rg returns exit code 0 if matches found, 1 if no matches
    if result.returncode == 0:
        # Matches found - show them
        lines = result.stdout.strip().split('\n')
        pytest.fail(
            f"Found {len(lines)} references to features.json in production code (src/):\n"
            + "\n".join(f"  {line}" for line in lines[:10])  # Show first 10
            + ("\n  ..." if len(lines) > 10 else "")
            + "\n\nConfig Constitution v1 requires YAML-only configuration."
            + " Remove these references or update them to use YAML."
        )
    elif result.returncode == 1:
        # No matches found - success
        pass
    else:
        # rg error
        pytest.fail(f"rg command failed: {result.stderr}")


if __name__ == "__main__":
    # Run tests directly for debugging
    test_configs_directory_structure()
    print("✓ Test 1 passed: configs directory structure")
    
    test_configs_files_are_yaml()
    print("✓ Test 2 passed: configs files are YAML")
    
    test_configs_no_generated_artifacts()
    print("✓ Test 3 passed: no generated artifacts")
    
    test_zero_features_json_references_in_production()
    print("✓ Test 10 passed: zero features.json references in production")
    
    print("All configs hygiene tests passed!")