#!/usr/bin/env python3
"""Fix profile paths in test files to use profiles_root fixture."""

import re
from pathlib import Path

# Files to fix
files_to_fix = [
    "tests/test_session_classification_mnq.py",
    "tests/test_session_classification_mxf.py",
    "tests/test_kbar_no_cross_session.py",
    "tests/test_mnq_maintenance_break_no_cross.py",
    "tests/test_session_dst_mnq.py",
]

# Pattern to match the problematic path
pattern = r'Path\(__file__\)\.parent\.parent / "src" / "FishBroWFS_V2" / "data" / "profiles" / "(.*?)"'

# Replacement template
replacement = r'profiles_root / "\1"'

for file_path in files_to_fix:
    path = Path(file_path)
    if not path.exists():
        print(f"Warning: {file_path} does not exist, skipping")
        continue
    
    content = path.read_text(encoding="utf-8")
    
    # Check if the pattern exists
    if re.search(pattern, content):
        # Replace the path pattern
        new_content = re.sub(pattern, replacement, content)
        
        # Also need to update the fixture signature to include profiles_root
        # Look for @pytest.fixture\ndef mnq_profile() -> Path: or similar
        fixture_pattern = r'(@pytest\.fixture\s*\n\s*def \w+_profile\()(.*?)(\) -> Path:)'
        fixture_match = re.search(fixture_pattern, new_content, re.DOTALL)
        
        if fixture_match:
            # Add profiles_root parameter
            fixture_replacement = r'\1profiles_root: Path\3'
            new_content = re.sub(fixture_pattern, fixture_replacement, new_content, flags=re.DOTALL)
        
        path.write_text(new_content, encoding="utf-8")
        print(f"Fixed: {file_path}")
    else:
        print(f"No pattern found in {file_path}, checking for other patterns...")
        # Check for other variations
        alt_pattern = r'Path\(__file__\).*parent.*"src".*"data".*"profiles"'
        if re.search(alt_pattern, content):
            print(f"  Found alternative pattern in {file_path}, manual fix needed")

print("Done!")