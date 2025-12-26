#!/usr/bin/env python3
"""Fix profile paths in test files to use configs/profiles instead of src/FishBroWFS_V2/data/profiles."""

import re
from pathlib import Path

def fix_file(file_path: Path):
    """Fix profile paths in a single file."""
    content = file_path.read_text(encoding="utf-8")
    
    # Replace src/FishBroWFS_V2/data/profiles with configs/profiles
    # Handle both quoted and unquoted paths
    patterns = [
        (r'"src/FishBroWFS_V2/data/profiles/([^"]+)"', r'"configs/profiles/\1"'),
        (r"'src/FishBroWFS_V2/data/profiles/([^']+)'", r"'configs/profiles/\1'"),
        (r'src/FishBroWFS_V2/data/profiles/(\w+\.yaml)', r'configs/profiles/\1'),
        (r'FishBroWFS_V2/data/profiles', r'configs/profiles'),
        (r'/data/profiles/', r'/profiles/'),
    ]
    
    original = content
    for pattern, replacement in patterns:
        content = re.sub(pattern, replacement, content)
    
    if content != original:
        print(f"Fixed {file_path}")
        file_path.write_text(content, encoding="utf-8")
        return True
    return False

def main():
    repo_root = Path(__file__).parent.parent
    tests_root = repo_root / "tests"
    
    # List of test files that need fixing (from the error output)
    test_files = [
        "test_portfolio_artifacts_hash_stable.py",
        "test_portfolio_compile_jobs.py",
        "test_portfolio_spec_loader.py",
        "test_portfolio_validate.py",
        "test_profiles_exist_in_configs.py",
    ]
    
    fixed_count = 0
    for test_file in test_files:
        file_path = tests_root / test_file
        if file_path.exists():
            if fix_file(file_path):
                fixed_count += 1
        else:
            print(f"Warning: {file_path} not found")
    
    print(f"Fixed {fixed_count} files")
    
    # Also fix any other test files that might have the pattern
    print("\nScanning for other files with legacy profile paths...")
    for py_file in tests_root.rglob("*.py"):
        # Skip legacy and manual directories
        rel_path = py_file.relative_to(tests_root)
        if str(rel_path).startswith("legacy/") or str(rel_path).startswith("manual/"):
            continue
        
        content = py_file.read_text(encoding="utf-8")
        if "FishBroWFS_V2/data/profiles" in content or "/data/profiles/" in content:
            if py_file.name not in test_files:
                print(f"Found legacy path in {py_file}")
                if fix_file(py_file):
                    fixed_count += 1
    
    print(f"Total files fixed: {fixed_count}")

if __name__ == "__main__":
    main()