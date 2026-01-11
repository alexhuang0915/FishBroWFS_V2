#!/usr/bin/env python3
"""
Script to add # type: ignore to PySide6 and matplotlib backend imports.
Run from project root.
"""

import os
import re
from pathlib import Path

# Patterns to match imports that need # type: ignore
PATTERNS = [
    r'^\s*from PySide6\..*import',
    r'^\s*import PySide6\..*',
    r'^\s*from matplotlib\.backends\..*import',
    r'^\s*import matplotlib\.backends\..*',
    r'^\s*from matplotlib\.figure import',
    r'^\s*import matplotlib\.figure',
    r'^\s*from matplotlib\.pyplot import',
    r'^\s*import matplotlib\.pyplot',
]

def should_add_ignore(line: str) -> bool:
    """Check if line needs # type: ignore."""
    for pattern in PATTERNS:
        if re.match(pattern, line):
            return True
    return False

def process_file(filepath: Path) -> bool:
    """Process a single file, adding # type: ignore where needed."""
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    modified = False
    new_lines = []
    
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        # Skip if already has # type: ignore
        if '# type: ignore' in line:
            new_lines.append(line)
            continue
        
        # Check if this import needs # type: ignore
        if should_add_ignore(line.rstrip()):
            # Add # type: ignore at end of line
            if line.strip().endswith(')'):
                # Multi-line import ending with )
                new_lines.append(line.rstrip() + '  # type: ignore\n')
            else:
                new_lines.append(line.rstrip() + '  # type: ignore\n')
            modified = True
        else:
            new_lines.append(line)
    
    if modified:
        print(f"  Modified {filepath}")
        with open(filepath, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
        return True
    return False

def main():
    project_root = Path.cwd()
    src_dir = project_root / 'src'
    
    if not src_dir.exists():
        print("Error: src directory not found")
        return
    
    # Find all Python files in src
    python_files = list(src_dir.rglob('*.py'))
    
    print(f"Found {len(python_files)} Python files")
    
    modified_count = 0
    for filepath in python_files:
        if process_file(filepath):
            modified_count += 1
    
    print(f"\nModified {modified_count} files")

if __name__ == '__main__':
    main()