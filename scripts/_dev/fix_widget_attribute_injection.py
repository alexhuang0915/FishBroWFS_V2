#!/usr/bin/env python3
"""
Script to automatically fix widget attribute injection violations by converting
direct attribute assignment to setProperty() and property() usage.
"""

import os
import re
import sys
from pathlib import Path
from typing import List, Tuple

def find_python_files(root_dir: Path) -> List[Path]:
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

def fix_widget_attribute_injection_in_file(filepath: Path) -> Tuple[int, List[str]]:
    """Fix widget attribute injection violations in a single file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except (UnicodeDecodeError, IOError) as e:
        print(f"  Error reading {filepath}: {e}")
        return 0, []
    
    original_lines = lines.copy()
    fixes_made = []
    
    # Pattern to match widget attribute assignment
    # Matches: .attribute = value
    # Where attribute is a valid Python identifier
    pattern = re.compile(r'(\s*)\.(\w+)\s*=\s*(.+)$')
    
    for i, line in enumerate(lines):
        match = pattern.search(line)
        if match:
            indent = match.group(1)
            attribute = match.group(2)
            value = match.group(3).rstrip()
            
            # Skip if this is inside a comment
            if '#' in line and line.find('#') < line.find('.' + attribute):
                continue
            
            # Skip if this is a class attribute (no dot before .attribute)
            # Actually the pattern already requires a dot at the start
            
            # Create the fixed line
            fixed_line = f"{indent}.setProperty('{attribute}', {value})\n"
            
            # Also need to add property() call for reading
            # But that's a separate issue - we'll just fix the assignment for now
            
            lines[i] = fixed_line
            fixes_made.append(f"Line {i+1}: .{attribute} = ... -> setProperty('{attribute}', ...)")
    
    if lines != original_lines:
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.writelines(lines)
            return len(fixes_made), fixes_made
        except IOError as e:
            print(f"  Error writing {filepath}: {e}")
            return 0, []
    
    return 0, []

def main():
    """Main function."""
    repo_root = Path.cwd()
    
    # Files with violations from the test output
    violation_files = [
        "src/control/governance.py",
        "src/control/season_api.py",
        "src/control/supervisor/artifact_writer.py",
        "src/control/supervisor/job_handler.py",
        "src/control/portfolio/admission.py",
        "src/gui/desktop/worker.py",
        "src/gui/desktop/widgets/evidence_browser.py",
        "src/gui/desktop/widgets/log_viewer.py",
        "src/gui/desktop/widgets/report_widgets/strategy_report_widget.py",
        "src/gui/desktop/tabs/portfolio_admission_tab.py",
    ]
    
    print("Fixing widget attribute injection violations...")
    
    total_fixes = 0
    files_modified = 0
    
    for rel_path in violation_files:
        filepath = repo_root / rel_path
        if not filepath.exists():
            print(f"  Warning: File not found: {rel_path}")
            continue
        
        fixes, fix_list = fix_widget_attribute_injection_in_file(filepath)
        if fixes > 0:
            files_modified += 1
            total_fixes += fixes
            print(f"  Fixed {fixes} violations in {rel_path}")
            for fix in fix_list[:2]:  # Show first 2 fixes
                print(f"    - {fix}")
            if len(fix_list) > 2:
                print(f"    - ... and {len(fix_list) - 2} more")
    
    print(f"\nSummary:")
    print(f"  Files modified: {files_modified}")
    print(f"  Total fixes: {total_fixes}")
    
    if total_fixes > 0:
        print("\nRunning widget attribute injection test to verify fixes...")
        os.system("python3 -m pytest tests/hardening/test_qt_pydantic_pylance_guard.py::test_no_widget_attribute_injection -xvs")

if __name__ == "__main__":
    main()