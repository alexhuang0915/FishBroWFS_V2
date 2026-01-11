#!/usr/bin/env python3
"""
Fix Pydantic v2 Field(default_factory=Class) errors.

Common pattern:
    field: SomeClass = Field(default_factory=SomeClass)
    
Should be:
    field: SomeClass = Field(default_factory=lambda: SomeClass())
    
But if SomeClass has required parameters, we need to pass defaults.
"""

import re
import ast
import os
from pathlib import Path
from typing import List, Tuple, Optional

def fix_pydantic_field_in_file(filepath: Path) -> List[Tuple[str, str]]:
    """Fix Pydantic Field(default_factory=Class) issues in a file."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original = content
    changes = []
    
    # Pattern: Field(default_factory=ClassName)
    # We'll use AST to be more precise
    try:
        tree = ast.parse(content)
    except SyntaxError:
        print(f"Syntax error in {filepath}, skipping")
        return changes
    
    # We'll do a simple regex approach for now
    # Look for Field(default_factory=SomeClass) where SomeClass starts with capital
    pattern = r'Field\s*\(\s*default_factory\s*=\s*([A-Z][a-zA-Z0-9_]*)\s*[),]'
    
    def replace_match(match):
        class_name = match.group(1)
        # Replace with lambda
        return f'Field(default_factory=lambda: {class_name}()'
    
    new_content = re.sub(pattern, replace_match, content)
    
    if new_content != content:
        changes.append(('Field(default_factory=Class)', 'Field(default_factory=lambda: Class())'))
        content = new_content
    
    # Also fix cases where the class might have parentheses already
    # Field(default_factory=SomeClass())
    pattern2 = r'Field\s*\(\s*default_factory\s*=\s*([A-Z][a-zA-Z0-9_]*)\s*\(\s*\)\s*[),]'
    
    def replace_match2(match):
        class_name = match.group(1)
        # Already has (), keep as is but wrap in lambda
        return f'Field(default_factory=lambda: {class_name}()'
    
    new_content = re.sub(pattern2, replace_match2, content)
    
    if new_content != content:
        changes.append(('Field(default_factory=Class())', 'Field(default_factory=lambda: Class())'))
        content = new_content
    
    if content != original:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
    
    return changes

def main():
    src_dir = Path('src')
    if not src_dir.exists():
        print("src directory not found")
        return
    
    all_changes = []
    
    # Walk through all Python files in src
    for py_file in src_dir.rglob('*.py'):
        try:
            changes = fix_pydantic_field_in_file(py_file)
            if changes:
                all_changes.append((py_file, changes))
                print(f"Fixed {py_file}: {changes}")
        except Exception as e:
            print(f"Error processing {py_file}: {e}")
    
    # Also check tests directory
    tests_dir = Path('tests')
    if tests_dir.exists():
        for py_file in tests_dir.rglob('*.py'):
            try:
                changes = fix_pydantic_field_in_file(py_file)
                if changes:
                    all_changes.append((py_file, changes))
                    print(f"Fixed {py_file}: {changes}")
            except Exception as e:
                print(f"Error processing {py_file}: {e}")
    
    print(f"\nTotal files modified: {len(all_changes)}")
    
    # Write summary
    summary_path = Path('outputs/_dp_evidence/phase_zero_red_fixpack_v1/pydantic_fixes_summary.txt')
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(summary_path, 'w', encoding='utf-8') as f:
        f.write("Pydantic v2 Field Fixes Summary\n")
        f.write("=" * 40 + "\n\n")
        for filepath, changes in all_changes:
            f.write(f"{filepath}:\n")
            for old, new in changes:
                f.write(f"  {old} -> {new}\n")
            f.write("\n")
    
    print(f"Summary written to {summary_path}")

if __name__ == '__main__':
    main()