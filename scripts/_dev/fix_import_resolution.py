#!/usr/bin/env python3
"""
Fix import resolution errors for pyright zero-red.

Common patterns:
1. from src.config -> from config (since src is the root package)
2. from contracts.dimensions -> from .dimensions (relative within contracts)
3. from config.registry.timeframes -> from ..registry.timeframes (relative)
"""

import re
import os
from pathlib import Path
from typing import List, Tuple

def fix_imports_in_file(filepath: Path) -> List[Tuple[str, str]]:
    """Fix import statements in a file and return list of changes."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original = content
    changes = []
    
    # Pattern 1: from src.config -> from config
    # But only if file is inside src/ directory
    if 'src/' in str(filepath):
        # Replace "from src.config" with "from config"
        new_content = re.sub(r'from\s+src\.config\b', 'from config', content)
        if new_content != content:
            changes.append(('src.config', 'config'))
            content = new_content
        
        # Replace "import src.config" with "import config"
        new_content = re.sub(r'import\s+src\.config\b', 'import config', content)
        if new_content != content:
            changes.append(('import src.config', 'import config'))
            content = new_content
    
    # Pattern 2: from contracts.dimensions -> from .dimensions
    # Only for files inside contracts/ directory
    if 'contracts/' in str(filepath):
        # Replace "from contracts.dimensions" with "from .dimensions"
        new_content = re.sub(r'from\s+contracts\.dimensions\b', 'from .dimensions', content)
        if new_content != content:
            changes.append(('contracts.dimensions', '.dimensions'))
            content = new_content
        
        # Replace "import contracts.dimensions" with "from . import dimensions"
        # This is more complex, we'll handle common cases
        new_content = re.sub(r'import\s+contracts\.dimensions\b', 'from . import dimensions', content)
        if new_content != content:
            changes.append(('import contracts.dimensions', 'from . import dimensions'))
            content = new_content
    
    # Pattern 3: from config.registry.timeframes -> from ..registry.timeframes
    # For files in src/contracts/ or src/features/ etc.
    if 'src/' in str(filepath):
        # This is complex - we need to know the relative path
        # For now, we'll just note these need manual fixing
        pass
    
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
            changes = fix_imports_in_file(py_file)
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
                changes = fix_imports_in_file(py_file)
                if changes:
                    all_changes.append((py_file, changes))
                    print(f"Fixed {py_file}: {changes}")
            except Exception as e:
                print(f"Error processing {py_file}: {e}")
    
    print(f"\nTotal files modified: {len(all_changes)}")
    
    # Write summary
    summary_path = Path('outputs/_dp_evidence/phase_zero_red_fixpack_v1/import_fixes_summary.txt')
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(summary_path, 'w', encoding='utf-8') as f:
        f.write("Import Resolution Fixes Summary\n")
        f.write("=" * 40 + "\n\n")
        for filepath, changes in all_changes:
            f.write(f"{filepath}:\n")
            for old, new in changes:
                f.write(f"  {old} -> {new}\n")
            f.write("\n")
    
    print(f"Summary written to {summary_path}")

if __name__ == '__main__':
    main()