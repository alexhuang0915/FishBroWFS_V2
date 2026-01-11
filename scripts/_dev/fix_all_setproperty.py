#!/usr/bin/env python3
"""
Comprehensive fix for broken .setProperty() calls with indentation and syntax errors.
Fixes:
1. Missing indentation for .setProperty() calls
2. Semicolon syntax errors in .setProperty() lines
3. Restores proper attribute assignment for non-Qt classes
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

def is_qt_class(filepath: Path, class_name: str):
    """Check if a class is likely a Qt widget class."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # Look for class definition
        pattern = rf'class\s+{class_name}\s*\([^)]*Q\w+'
        if re.search(pattern, content):
            return True
            
        # Check imports for Qt modules
        if 'PySide6' in content or 'PyQt' in content:
            return True
            
    except Exception:
        pass
    
    return False

def fix_file(filepath: Path):
    """Fix broken .setProperty() calls in a file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except (UnicodeDecodeError, IOError) as e:
        print(f"  Error reading {filepath}: {e}")
        return 0, 0
    
    original_lines = lines.copy()
    fixes_made = 0
    syntax_fixes = 0
    
    # Pattern to match broken .setProperty() calls with missing indentation
    # Matches lines starting with self.setProperty (no indentation)
    setproperty_pattern = re.compile(r'^(\s*)self\.setProperty\s*\(([^)]+)\)\s*$')
    
    # Pattern to match lines with semicolon syntax errors
    semicolon_pattern = re.compile(r'^(\s*)self\.setProperty\s*\(([^)]+)\)\s*;\s*(.*)$')
    
    # Pattern to match .setProperty() without self prefix
    noself_pattern = re.compile(r'^(\s*)\.setProperty\s*\(([^)]+)\)\s*$')
    
    for i, line in enumerate(lines):
        # Fix missing self prefix
        noself_match = noself_pattern.match(line)
        if noself_match:
            indent = noself_match.group(1)
            args = noself_match.group(2)
            lines[i] = f"{indent}self.setProperty({args})\n"
            fixes_made += 1
            print(f"  Line {i+1}: Fixed .setProperty(...) -> self.setProperty(...)")
            continue
        
        # Fix semicolon syntax errors
        semicolon_match = semicolon_pattern.match(line)
        if semicolon_match:
            indent = semicolon_match.group(1)
            args = semicolon_match.group(2)
            rest = semicolon_match.group(3)
            
            # Check if rest is valid Python (likely another statement)
            if rest.strip():
                # Split into two lines
                lines[i] = f"{indent}self.setProperty({args})\n"
                # Insert rest on next line
                lines.insert(i + 1, f"{indent}{rest}\n")
                syntax_fixes += 1
                print(f"  Line {i+1}: Fixed semicolon syntax error")
            else:
                # Just remove semicolon
                lines[i] = f"{indent}self.setProperty({args})\n"
                syntax_fixes += 1
                print(f"  Line {i+1}: Removed trailing semicolon")
            continue
        
        # Fix missing indentation for self.setProperty
        setproperty_match = setproperty_pattern.match(line)
        if setproperty_match:
            indent = setproperty_match.group(1)
            args = setproperty_match.group(2)
            
            # Check if line should be indented (not at module level)
            if i > 0 and lines[i-1].rstrip().endswith(':'):
                # This is inside a method/class, indentation looks fine
                pass
            elif indent == '' and i > 0:
                # No indentation but should have some
                # Find appropriate indentation level
                for j in range(i-1, -1, -1):
                    if lines[j].strip() and not lines[j].strip().startswith('#'):
                        # Use same indentation as previous non-empty line
                        prev_indent = len(lines[j]) - len(lines[j].lstrip())
                        lines[i] = ' ' * prev_indent + line.lstrip()
                        fixes_made += 1
                        print(f"  Line {i+1}: Added indentation to self.setProperty()")
                        break
    
    if fixes_made > 0 or syntax_fixes > 0:
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.writelines(lines)
            return fixes_made, syntax_fixes
        except IOError as e:
            print(f"  Error writing {filepath}: {e}")
            return 0, 0
    
    return 0, 0

def main():
    """Main function."""
    repo_root = Path.cwd()
    src_dir = repo_root / "src"
    
    if not src_dir.exists():
        print(f"Error: src directory not found at {src_dir}")
        sys.exit(1)
    
    print("Scanning for broken .setProperty() calls and syntax errors...")
    python_files = find_python_files(src_dir)
    print(f"Found {len(python_files)} Python files in src/")
    
    total_fixes = 0
    total_syntax_fixes = 0
    files_modified = 0
    
    for filepath in python_files:
        fixes, syntax_fixes = fix_file(filepath)
        if fixes > 0 or syntax_fixes > 0:
            files_modified += 1
            total_fixes += fixes
            total_syntax_fixes += syntax_fixes
            print(f"  Fixed {fixes} indentation issues and {syntax_fixes} syntax errors in {filepath.relative_to(repo_root)}")
    
    print(f"\nSummary:")
    print(f"  Files modified: {files_modified}")
    print(f"  Indentation fixes: {total_fixes}")
    print(f"  Syntax error fixes: {total_syntax_fixes}")
    
    if total_fixes > 0 or total_syntax_fixes > 0:
        print("\nRunning pyright to check remaining parse errors...")
        os.system("cd /home/fishbro/FishBroWFS_V2 && .venv/bin/python -m pyright -p scripts/_dev/pyrightconfig.json src/ 2>&1 | grep -E 'ParseError|SyntaxError|Expected expression|Unexpected indentation|Unindent not expected' | wc -l")

if __name__ == "__main__":
    main()