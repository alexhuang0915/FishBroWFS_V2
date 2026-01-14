"""
Hard fail guard: No GUI timeframe literal lists.

PURPOSE:
Make it impossible to reintroduce hardcoded timeframe dropdown option lists in GUI code.
This is a hard gate: any GUI module defining a timeframe-like literal list must FAIL pytest.

SCOPE:
- GUI code only (to avoid false positives in non-UI domains):
  - `src/gui/`
- We specifically target timeframe dropdown/options lists, not arbitrary numeric constants.

HARD RULE:
Within `src/gui/`, do not define any module-level or function-local list/tuple literal that looks like a "timeframe options list".
All timeframe options must come from the single provider:
- `get_timeframe_ids()`
- `get_timeframe_id_label_pairs()`

ALLOWLIST:
- Single timeframe string (e.g. default selection `"60m"`) is allowed
- Non-options data structures are allowed if they are not options-like
- Legacy modules that must remain temporarily (empty for now)
"""

from typing import Optional

import ast
import re
from pathlib import Path
import pytest

# Timeframe token pattern: matches strings like "5m", "60m", "2h", "1d", "1D", "1w"
TIMEFRAME_TOKEN_PATTERN = re.compile(r'^\d+[mhdw]$', re.IGNORECASE)

# Keywords that suggest options-like usage
OPTIONS_KEYWORDS = {
    'timeframe', 'tf', 'interval', 'granularity', 'resolution', 
    'freq', 'frequency', 'options', 'choices', 'values', 'list'
}

# Allowlist of file paths that are exempt from this rule (must be small and documented)
ALLOWLIST = {
    # Add paths here only with explicit justification and TODO for removal
    # Example: "src/gui/legacy/old_module.py"
}

def is_timeframe_token(s: object) -> bool:
    """Check if string looks like a timeframe token."""
    if not isinstance(s, str):
        return False
    return bool(TIMEFRAME_TOKEN_PATTERN.match(s))


def extract_string_value(el: ast.AST) -> Optional[str]:
    """Extract string value from AST node safely."""
    # Python 3.8+ uses ast.Constant for strings (project requires >=3.10)
    if isinstance(el, ast.Constant):
        val = el.value
        if isinstance(val, str):
            return val
        # Not a string (could be int, float, etc.)
        return None
    return None

def is_options_like_name(name: str) -> bool:
    """Check if variable name suggests options-like usage."""
    name_lower = name.lower()
    return any(keyword in name_lower for keyword in OPTIONS_KEYWORDS)

def scan_file_for_violations(file_path: Path):
    """Scan a Python file for timeframe literal list violations."""
    violations = []
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except (UnicodeDecodeError, OSError):
        return violations  # Skip binary or unreadable files
    
    try:
        tree = ast.parse(content, filename=str(file_path))
    except SyntaxError:
        return violations  # Skip files with syntax errors
    
    for node in ast.walk(tree):
        # Look for assignments to names
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if not isinstance(target, ast.Name):
                    continue
                
                var_name = target.id
                
                # Check if the value is a list or tuple literal
                if isinstance(node.value, (ast.List, ast.Tuple)):
                    elements = node.value.elts
                    
                    # Collect string constants from elements
                    string_values = [
                        sv for sv in (extract_string_value(el) for el in elements)
                        if sv is not None
                    ]
                    
                    # Need at least 2 string elements to be considered an options list
                    if len(string_values) >= 2:
                        # Count how many look like timeframe tokens
                        timeframe_count = sum(1 for s in string_values if is_timeframe_token(s))
                        
                        if timeframe_count >= 2 and is_options_like_name(var_name):
                            violations.append({
                                'file': file_path,
                                'line': node.lineno,
                                'var_name': var_name,
                                'values': string_values,
                                'reason': f"Found {timeframe_count} timeframe tokens in list assigned to options-like variable '{var_name}'"
                            })
    
        # Check for UI calls with literal lists (addItems, setItems, etc.)
        if isinstance(node, ast.Call):
            if node.args and isinstance(node.args[0], (ast.List, ast.Tuple)):
                if isinstance(node.func, ast.Attribute) and hasattr(node.func, 'attr'):
                    method_name = node.func.attr
                    if method_name in ('addItems', 'setItems'):
                        elements = node.args[0].elts
                        string_values = [
                            sv for sv in (extract_string_value(el) for el in elements)
                            if sv is not None
                        ]
                        if len(string_values) >= 2:
                            timeframe_count = sum(1 for s in string_values if is_timeframe_token(s))
                            if timeframe_count >= 2:
                                violations.append({
                                    'file': file_path,
                                    'line': node.lineno,
                                    'method': method_name,
                                    'values': string_values[:5],
                                    'reason': f"{method_name}() called with literal list containing {timeframe_count} timeframe tokens"
                                })
    
    return violations

def test_no_gui_timeframe_literal_lists():
    """Fail if any GUI module contains timeframe literal lists."""
    gui_dir = Path("src/gui")
    
    if not gui_dir.exists():
        pytest.skip("src/gui/ directory does not exist")
    
    # Collect all Python files in gui/
    python_files = list(gui_dir.rglob("*.py"))
    python_files.sort()  # Deterministic order
    
    all_violations = []
    
    for py_file in python_files:
        if str(py_file) in ALLOWLIST:
            continue
        
        violations = scan_file_for_violations(py_file)
        all_violations.extend(violations)
    
    if all_violations:
        # Format error message
        error_lines = [
            "Found GUI timeframe literal lists (use timeframe_options provider instead):"
        ]
        for v in all_violations:
            error_lines.append(
                f"  {v['file']}:{v['line']}: {v['reason']}"
            )
            # Show first few values as example
            sample_values = v['values'][:3]
            if len(v['values']) > 3:
                sample_values.append("...")
            error_lines.append(f"    Values: {sample_values}")
        
        error_msg = "\n".join(error_lines)
        pytest.fail(error_msg)

if __name__ == "__main__":
    # Run test directly for debugging
    test_no_gui_timeframe_literal_lists()
    print("✓ No GUI timeframe literal lists found")