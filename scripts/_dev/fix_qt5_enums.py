#!/usr/bin/env python3
"""
Script to automatically fix Qt5-style enum violations by converting them to Qt6 nested enums.
"""

import os
import re
import sys
from pathlib import Path
from typing import List, Tuple

# Mapping of Qt5-style enums to Qt6 nested enums
QT5_TO_QT6_MAPPINGS = [
    # Qt.Orientation
    (r"\bQt\.Horizontal\b", "Qt.Orientation.Horizontal"),
    (r"\bQt\.Vertical\b", "Qt.Orientation.Vertical"),
    
    # Qt.AlignmentFlag
    (r"\bQt\.AlignLeft\b", "Qt.AlignmentFlag.AlignLeft"),
    (r"\bQt\.AlignRight\b", "Qt.AlignmentFlag.AlignRight"),
    (r"\bQt\.AlignCenter\b", "Qt.AlignmentFlag.AlignCenter"),
    (r"\bQt\.AlignTop\b", "Qt.AlignmentFlag.AlignTop"),
    (r"\bQt\.AlignBottom\b", "Qt.AlignmentFlag.AlignBottom"),
    (r"\bQt\.AlignVCenter\b", "Qt.AlignmentFlag.AlignVCenter"),
    (r"\bQt\.AlignHCenter\b", "Qt.AlignmentFlag.AlignHCenter"),
    
    # Qt.ItemDataRole
    (r"\bQt\.DisplayRole\b", "Qt.ItemDataRole.DisplayRole"),
    (r"\bQt\.ForegroundRole\b", "Qt.ItemDataRole.ForegroundRole"),
    (r"\bQt\.FontRole\b", "Qt.ItemDataRole.FontRole"),
    (r"\bQt\.ToolTipRole\b", "Qt.ItemDataRole.ToolTipRole"),
    (r"\bQt\.TextAlignmentRole\b", "Qt.ItemDataRole.TextAlignmentRole"),
    
    # Qt.CaseSensitivity
    (r"\bQt\.CaseInsensitive\b", "Qt.CaseSensitivity.CaseInsensitive"),
    
    # QMessageBox.StandardButton
    (r"\bQMessageBox\.Ok\b", "QMessageBox.StandardButton.Ok"),
    (r"\bQMessageBox\.Yes\b", "QMessageBox.StandardButton.Yes"),
    (r"\bQMessageBox\.No\b", "QMessageBox.StandardButton.No"),
    (r"\bQMessageBox\.Cancel\b", "QMessageBox.StandardButton.Cancel"),
    (r"\bQMessageBox\.Close\b", "QMessageBox.StandardButton.Close"),
    
    # QTabWidget.TabPosition
    (r"\bQTabWidget\.North\b", "QTabWidget.TabPosition.North"),
    (r"\bQTabWidget\.South\b", "QTabWidget.TabPosition.South"),
    (r"\bQTabWidget\.West\b", "QTabWidget.TabPosition.West"),
    (r"\bQTabWidget\.East\b", "QTabWidget.TabPosition.East"),
    
    # QSizePolicy.Policy
    (r"\bQSizePolicy\.Minimum\b", "QSizePolicy.Policy.Minimum"),
    (r"\bQSizePolicy\.Expanding\b", "QSizePolicy.Policy.Expanding"),
    (r"\bQSizePolicy\.Fixed\b", "QSizePolicy.Policy.Fixed"),
    (r"\bQSizePolicy\.Preferred\b", "QSizePolicy.Policy.Preferred"),
    
    # QTableView.SelectionBehavior / SelectionMode
    (r"\bQTableView\.SelectRows\b", "QTableView.SelectionBehavior.SelectRows"),
    (r"\bQTableView\.SingleSelection\b", "QTableView.SelectionMode.SingleSelection"),
    (r"\bQTableView\.MultiSelection\b", "QTableView.SelectionMode.MultiSelection"),
]

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

def fix_qt5_enums_in_file(filepath: Path) -> Tuple[int, List[str]]:
    """Fix Qt5-style enums in a single file."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
    except (UnicodeDecodeError, IOError) as e:
        print(f"  Error reading {filepath}: {e}")
        return 0, []
    
    original_content = content
    fixes_made = []
    
    for pattern, replacement in QT5_TO_QT6_MAPPINGS:
        # Use a function to replace only if the pattern matches
        def replace_match(match):
            matched = match.group(0)
            # Check if this is already a Qt6 nested enum (avoid double replacement)
            if "." in matched and matched.count(".") >= 2:
                # Already has at least two dots, might already be Qt6
                return matched
            return replacement
        
        new_content, count = re.subn(pattern, replace_match, content)
        if count > 0:
            content = new_content
            fixes_made.append(f"{pattern} -> {replacement} ({count} occurrences)")
    
    if content != original_content:
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            return len(fixes_made), fixes_made
        except IOError as e:
            print(f"  Error writing {filepath}: {e}")
            return 0, []
    
    return 0, []

def main():
    """Main function."""
    repo_root = Path.cwd()
    src_dir = repo_root / "src"
    
    if not src_dir.exists():
        print(f"Error: src directory not found at {src_dir}")
        sys.exit(1)
    
    print("Scanning for Qt5-style enum violations...")
    python_files = find_python_files(src_dir)
    print(f"Found {len(python_files)} Python files in src/")
    
    total_fixes = 0
    files_modified = 0
    
    for filepath in python_files:
        fixes, fix_list = fix_qt5_enums_in_file(filepath)
        if fixes > 0:
            files_modified += 1
            total_fixes += fixes
            print(f"  Fixed {fixes} violations in {filepath.relative_to(repo_root)}")
            for fix in fix_list[:3]:  # Show first 3 fixes
                print(f"    - {fix}")
            if len(fix_list) > 3:
                print(f"    - ... and {len(fix_list) - 3} more")
    
    print(f"\nSummary:")
    print(f"  Files modified: {files_modified}")
    print(f"  Total fixes: {total_fixes}")
    
    if total_fixes > 0:
        print("\nRunning qt-guard test to verify fixes...")
        os.system("python -m pytest tests/hardening/test_qt_pydantic_pylance_guard.py::test_no_qt5_enums -xvs")

if __name__ == "__main__":
    main()