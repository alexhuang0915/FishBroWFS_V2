#!/usr/bin/env python3
"""
Script to fix broken .setProperty() calls created by the widget attribute injection fix script.
Finds lines with .setProperty('attr', value) without 'self' prefix and fixes them.
"""

import os
import re
import sys
from pathlib import Path

def find_python_files(root_dir: Path):
    """Find all Python files in the directory tree."""
    python_files = []
    for dirpath, dirnames, filenames in os.walk(root_dir):
        # Skip excluded directories
        dirnames[:] = [d for d in dirnames if d not in {
            "__pycache__", ".venv", ".git", ".pytest_cache", "node_modules"
        }]
        
        for filename in filenames:
            if filename.endswith(".py"):
                python_files.append(Path(dirpath) / filename)
    
    return python_files

def fix_broken_setproperty(filepath: Path):
    """Fix broken .setProperty() calls in a file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except (UnicodeDecodeError, IOError) as e:
        print(f"  Error reading {filepath}: {e}")
        return 0
    
    original_lines = lines.copy()
    fixes_made = 0
    
    # Pattern to match broken .setProperty() calls
    # Matches: .setProperty('attr', value)
    # Where there's no self or other object before the dot
    pattern = re.compile(r'^(\s*)\.setProperty\s*\(\s*[\'"]([^\'"]+)[\'"]\s*,\s*(.+)\s*\)\s*$')
    
    for i, line in enumerate(lines):
        match = pattern.match(line)
        if match:
            indent = match.group(1)
            attr = match.group(2)
            value = match.group(3).rstrip()
            
            # Check if previous line ends with colon (method definition)
            if i > 0 and lines[i-1].rstrip().endswith(':'):
                # This is inside a method, should be self.setProperty
                fixed_line = f"{indent}self.setProperty('{attr}', {value})\n"
            else:
                # Not sure, but at least add self.
                fixed_line = f"{indent}self.setProperty('{attr}', {value})\n"
            
            lines[i] = fixed_line
            fixes_made += 1
            print(f"  Line {i+1}: Fixed .setProperty('{attr}', ...) -> self.setProperty('{attr}', ...)")
    
    if fixes_made > 0:
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.writelines(lines)
            return fixes_made
        except IOError as e:
            print(f"  Error writing {filepath}: {e}")
            return 0
    
    return 0

def main():
    """Main function."""
    repo_root = Path.cwd()
    src_dir = repo_root / "src"
    
    if not src_dir.exists():
        print(f"Error: src directory not found at {src_dir}")
        sys.exit(1)
    
    print("Scanning for broken .setProperty() calls...")
    python_files = find_python_files(src_dir)
    print(f"Found {len(python_files)} Python files in src/")
    
    total_fixes = 0
    files_modified = 0
    
    for filepath in python_files:
        fixes = fix_broken_setproperty(filepath)
        if fixes > 0:
            files_modified += 1
            total_fixes += fixes
            print(f"  Fixed {fixes} broken .setProperty() calls in {filepath.relative_to(repo_root)}")
    
    print(f"\nSummary:")
    print(f"  Files modified: {files_modified}")
    print(f"  Total fixes: {total_fixes}")
    
    if total_fixes > 0:
        print("\nRunning pyright to check for remaining parse errors...")
        os.system("cd /home/fishbro/FishBroWFS_V2 && .venv/bin/python -m pyright -p scripts/_dev/pyrightconfig.json src/ 2>&1 | grep -c 'Expected expression\\|Unexpected indentation\\|Unindent not expected'")

if __name__ == "__main__":
    main()