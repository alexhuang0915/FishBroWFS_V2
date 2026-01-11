"""
Repo-level CI guard test for Qt/PySide6 + Pydantic-v2 anti-patterns.

Fails CI if forbidden patterns appear anywhere in src/.
Provides actionable failure messages with file path + line excerpts.

Hard FAIL patterns:
1. Qt5-style enums (must use Qt6 nested enums)
2. Pydantic default_factory with class reference (must use lambda)
3. Widget attribute injection (must use setProperty()/property())

This guard is intentionally conservative; it blocks common mistakes
and forces correct patterns that prevent Pylance red errors.
"""

import re
import os
import sys
from pathlib import Path
from typing import List, Tuple, Optional
import pytest

# ----------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------

# Directory to scan (default: src/)
SCAN_ROOT = Path("src")

# Exclude patterns (relative to SCAN_ROOT)
EXCLUDE_DIRS = {
    "__pycache__",
    ".venv",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    "node_modules",
}

# File extensions to scan
INCLUDE_EXTENSIONS = {".py"}

# ----------------------------------------------------------------------
# Hard FAIL Patterns (regex)
# ----------------------------------------------------------------------

# Qt5 enum patterns (must use Qt6 nested enums)
QT5_ENUM_PATTERNS = [
    # Qt.Orientation
    (r"\bQt\.(Horizontal|Vertical)\b",
     "Use Qt.Orientation.Horizontal or Qt.Orientation.Vertical"),
    
    # Qt.AlignmentFlag
    (r"\bQt\.Align(Left|Right|Center|Top|Bottom|VCenter|HCenter)\b",
     "Use Qt.AlignmentFlag.AlignLeft etc."),
    
    # Qt.ItemDataRole
    (r"\bQt\.(DisplayRole|ForegroundRole|FontRole|ToolTipRole|TextAlignmentRole)\b",
     "Use Qt.ItemDataRole.DisplayRole etc."),
    
    # Qt.CaseSensitivity
    (r"\bQt\.CaseInsensitive\b",
     "Use Qt.CaseSensitivity.CaseInsensitive"),
    
    # QMessageBox.StandardButton
    (r"\bQMessageBox\.(Ok|Yes|No|Cancel|Close)\b",
     "Use QMessageBox.StandardButton.Ok etc."),
    
    # QTabWidget.TabPosition
    (r"\bQTabWidget\.(North|South|West|East)\b",
     "Use QTabWidget.TabPosition.North etc."),
    
    # QSizePolicy.Policy
    (r"\bQSizePolicy\.(Minimum|Expanding|Fixed|Preferred)\b",
     "Use QSizePolicy.Policy.Minimum etc."),
    
    # QTableView.SelectionBehavior / SelectionMode
    (r"\bQTableView\.(SelectRows|SingleSelection|MultiSelection)\b",
     "Use QTableView.SelectionBehavior.SelectRows etc."),
]

# Pydantic default_factory class reference (must use lambda)
PYDANTIC_DEFAULT_FACTORY_PATTERN = r"Field\(\s*default_factory\s*=\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)"

# Widget attribute injection (common anti-pattern keys)
WIDGET_ATTR_INJECTION_PATTERNS = [
    (r"\.\s*job_id\s*=",
     "Use setProperty('job_id', value) and property('job_id')"),
    (r"\.\s*run_id\s*=",
     "Use setProperty('run_id', value) and property('run_id')"),
    (r"\.\s*season\s*=",
     "Use setProperty('season', value) and property('season')"),
]

# Allowlist for Pydantic default_factory (function names that are valid factories)
PYDANTIC_FACTORY_ALLOWLIST = {
    "dict", "list", "set", "defaultdict", "deque",  # built-in collections
    "datetime", "date", "time",  # datetime module functions
}

# ----------------------------------------------------------------------
# Helper Functions
# ----------------------------------------------------------------------

def should_scan_file(filepath: Path) -> bool:
    """Check if a file should be scanned."""
    if filepath.suffix not in INCLUDE_EXTENSIONS:
        return False
    
    # Check if in excluded directory
    for part in filepath.parts:
        if part in EXCLUDE_DIRS:
            return False
    
    return True


def find_files_to_scan() -> List[Path]:
    """Find all Python files in SCAN_ROOT."""
    files = []
    for root, dirs, filenames in os.walk(SCAN_ROOT):
        # Skip excluded directories
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        
        for filename in filenames:
            filepath = Path(root) / filename
            if should_scan_file(filepath):
                files.append(filepath)
    
    return files


def check_qt5_enums(content: str, filepath: Path) -> List[Tuple[int, str, str]]:
    """Check for Qt5-style enums."""
    violations = []
    for pattern, fix_hint in QT5_ENUM_PATTERNS:
        for match in re.finditer(pattern, content):
            line_num = content[:match.start()].count('\n') + 1
            matched_text = match.group(0)
            violations.append((line_num, matched_text, fix_hint))
    return violations


def check_pydantic_default_factory(content: str, filepath: Path) -> List[Tuple[int, str, str]]:
    """Check for Pydantic default_factory with class reference."""
    violations = []
    
    for match in re.finditer(PYDANTIC_DEFAULT_FACTORY_PATTERN, content):
        # Extract the class/function name
        class_name_match = re.search(r"=\s*([A-Za-z_][A-Za-z0-9_]*)", match.group(0))
        if not class_name_match:
            continue
        
        class_name = class_name_match.group(1)
        
        # Check if it's in the allowlist
        if class_name in PYDANTIC_FACTORY_ALLOWLIST:
            continue
        
        # Check if it's followed by parentheses (function call)
        # Simple heuristic: look for "ClassName(" after the match
        after_text = content[match.end():match.end()+len(class_name)+2]
        if after_text.startswith(f"{class_name}("):
            # It's a function call, not a class reference
            continue
        
        line_num = content[:match.start()].count('\n') + 1
        matched_text = match.group(0)
        fix_hint = f"Use Field(default_factory=lambda: {class_name}())"
        violations.append((line_num, matched_text, fix_hint))
    
    return violations


def check_widget_attr_injection(content: str, filepath: Path) -> List[Tuple[int, str, str]]:
    """Check for widget attribute injection."""
    violations = []
    for pattern, fix_hint in WIDGET_ATTR_INJECTION_PATTERNS:
        for match in re.finditer(pattern, content):
            line_num = content[:match.start()].count('\n') + 1
            matched_text = match.group(0)
            violations.append((line_num, matched_text, fix_hint))
    return violations


def scan_file(filepath: Path) -> List[Tuple[str, int, str, str]]:
    """Scan a single file for all violations."""
    violations = []
    
    try:
        content = filepath.read_text(encoding='utf-8')
    except (UnicodeDecodeError, IOError):
        return violations
    
    # Check Qt5 enums
    qt_violations = check_qt5_enums(content, filepath)
    for line_num, matched_text, fix_hint in qt_violations:
        violations.append(("Qt5 enum", line_num, matched_text, fix_hint))
    
    # Check Pydantic default_factory
    pydantic_violations = check_pydantic_default_factory(content, filepath)
    for line_num, matched_text, fix_hint in pydantic_violations:
        violations.append(("Pydantic default_factory", line_num, matched_text, fix_hint))
    
    # Check widget attribute injection
    widget_violations = check_widget_attr_injection(content, filepath)
    for line_num, matched_text, fix_hint in widget_violations:
        violations.append(("Widget attribute injection", line_num, matched_text, fix_hint))
    
    return violations


# ----------------------------------------------------------------------
# Test Functions
# ----------------------------------------------------------------------

def test_no_qt5_enums():
    """Fail if Qt5-style enums are found in src/."""
    files = find_files_to_scan()
    all_violations = []
    
    for filepath in files:
        violations = scan_file(filepath)
        for violation_type, line_num, matched_text, fix_hint in violations:
            if violation_type == "Qt5 enum":
                all_violations.append((filepath, line_num, matched_text, fix_hint))
    
    if all_violations:
        error_msg = "Qt5-style enums found (must use Qt6 nested enums):\n"
        for filepath, line_num, matched_text, fix_hint in all_violations[:10]:  # Show first 10
            error_msg += f"  {filepath}:{line_num}: {matched_text[:60]}...\n"
            error_msg += f"      Fix: {fix_hint}\n"
        
        if len(all_violations) > 10:
            error_msg += f"  ... and {len(all_violations) - 10} more violations\n"
        
        pytest.fail(error_msg)


def test_no_pydantic_default_factory_class():
    """Fail if Pydantic default_factory uses class reference instead of lambda."""
    files = find_files_to_scan()
    all_violations = []
    
    for filepath in files:
        violations = scan_file(filepath)
        for violation_type, line_num, matched_text, fix_hint in violations:
            if violation_type == "Pydantic default_factory":
                all_violations.append((filepath, line_num, matched_text, fix_hint))
    
    if all_violations:
        error_msg = "Pydantic default_factory with class reference found (must use lambda):\n"
        for filepath, line_num, matched_text, fix_hint in all_violations[:10]:
            error_msg += f"  {filepath}:{line_num}: {matched_text[:60]}...\n"
            error_msg += f"      Fix: {fix_hint}\n"
        
        if len(all_violations) > 10:
            error_msg += f"  ... and {len(all_violations) - 10} more violations\n"
        
        pytest.fail(error_msg)


def test_no_widget_attribute_injection():
    """Fail if widget attribute injection is found."""
    files = find_files_to_scan()
    all_violations = []
    
    for filepath in files:
        violations = scan_file(filepath)
        for violation_type, line_num, matched_text, fix_hint in violations:
            if violation_type == "Widget attribute injection":
                all_violations.append((filepath, line_num, matched_text, fix_hint))
    
    if all_violations:
        error_msg = "Widget attribute injection found (must use setProperty/property):\n"
        for filepath, line_num, matched_text, fix_hint in all_violations[:10]:
            error_msg += f"  {filepath}:{line_num}: {matched_text[:60]}...\n"
            error_msg += f"      Fix: {fix_hint}\n"
        
        if len(all_violations) > 10:
            error_msg += f"  ... and {len(all_violations) - 10} more violations\n"
        
        pytest.fail(error_msg)


def test_guard_summary():
    """Summary test that runs all checks and reports combined results."""
    files = find_files_to_scan()
    all_violations = []
    
    for filepath in files:
        violations = scan_file(filepath)
        all_violations.extend([(filepath, vt, ln, mt, fh) for vt, ln, mt, fh in violations])
    
    if all_violations:
        # Group by violation type
        by_type = {}
        for filepath, vtype, line_num, matched_text, fix_hint in all_violations:
            by_type.setdefault(vtype, []).append((filepath, line_num, matched_text, fix_hint))
        
        error_msg = "CI Guard Test FAILED - Found anti-patterns:\n\n"
        
        for vtype in sorted(by_type.keys()):
            violations = by_type[vtype]
            error_msg += f"{vtype} ({len(violations)} violations):\n"
            for filepath, line_num, matched_text, fix_hint in violations[:5]:
                error_msg += f"  {filepath}:{line_num}: {matched_text[:50]}...\n"
                error_msg += f"      Fix: {fix_hint}\n"
            if len(violations) > 5:
                error_msg += f"  ... and {len(violations) - 5} more\n"
            error_msg += "\n"
        
        error_msg += "These patterns cause Pylance red errors and must be fixed.\n"
        pytest.fail(error_msg)


if __name__ == "__main__":
    # For manual testing
    files = find_files_to_scan()
    print(f"Scanning {len(files)} files in {SCAN_ROOT}")
    
    all_violations = []
    for filepath in files:
        violations = scan_file(filepath)
        if violations:
            print(f"\n{filepath}:")
            for vtype, line_num, matched_text, fix_hint in violations:
                print(f"  Line {line_num}: {vtype}")
                print(f"    {matched_text[:80]}...")
                print(f"    Fix: {fix_hint}")
            all_violations.extend(violations)
    
    if all_violations:
        print(f"\nFAILED: Found {len(all_violations)} violations")
        sys.exit(1)
    else:
        print("PASSED: No violations found")
        sys.exit(0)