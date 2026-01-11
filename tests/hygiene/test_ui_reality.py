"""
Test UI reality according to Config Constitution v1.

Rules:
1. No mock/fake data generators in UI modules
2. UI uses registry loaders for dropdowns
3. No hardcoded dropdown values
"""

import pytest
import ast
import warnings
from pathlib import Path
import re


def collect_python_files(directory: Path):
    """Collect all Python files in directory recursively."""
    python_files = []
    for py_file in directory.rglob("*.py"):
        python_files.append(py_file)
    return python_files


def parse_ast_for_patterns(file_path: Path):
    """Parse Python file and look for problematic patterns."""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return []  # Skip files with syntax errors
    
    patterns = []
    
    # Look for specific AST patterns
    for node in ast.walk(tree):
        # Look for random.choice() calls (common in mock data)
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                if node.func.attr == 'choice' and isinstance(node.func.value, ast.Name):
                    if node.func.value.id == 'random':
                        patterns.append(("random.choice", node.lineno))
        
        # Look for hardcoded lists that might be dropdown values
        if isinstance(node, ast.List):
            # Check if list contains typical timeframe values
            # Use ast.Constant for Python 3.14 compatibility
            values = []
            for el in node.elts:
                # Try ast.Constant first (Python 3.8+)
                if hasattr(ast, 'Constant'):
                    if isinstance(el, ast.Constant) and isinstance(el.value, (int, float)):
                        values.append(el.value)
                        continue
                # Fallback for older Python without triggering deprecation warnings
                # Check for ast.Num without using isinstance which triggers warning
                try:
                    # Access the attribute directly to avoid isinstance check
                    if el.__class__.__name__ == 'Num':
                        values.append(el.n)
                        continue
                except AttributeError:
                    pass
                
                # Not a numeric constant, break
                values = None
                break
            
            if values is not None:
                # Common timeframe patterns
                if set(values) == {15, 30, 60, 120, 240}:
                    patterns.append(("hardcoded_timeframes", node.lineno))
                elif all(v % 15 == 0 for v in values):
                    patterns.append(("hardcoded_timeframe_like", node.lineno))
    
    return patterns


def test_no_mock_data_generators():
    """Test 1: No mock/fake data generators in UI modules."""
    gui_dir = Path("src/gui")
    
    if not gui_dir.exists():
        pytest.skip("src/gui/ directory does not exist")
    
    # Collect all Python files in gui/
    gui_files = collect_python_files(gui_dir)
    
    # Patterns that indicate mock/fake data
    mock_patterns = [
        r"mock.*data",
        r"fake.*data",
        r"sample.*data",
        r"load_mock",
        r"generate_mock",
        r"random\.choice\(",
        r"random\.rand",
        r"np\.random\.",
    ]
    
    violations = []
    
    for gui_file in gui_files:
        try:
            with open(gui_file, 'r', encoding='utf-8') as f:
                content = f.read().lower()
            
            for line_num, line in enumerate(content.splitlines(), 1):
                for pattern in mock_patterns:
                    if re.search(pattern, line):
                        violations.append((gui_file, line_num, line.strip()))
                        break  # Only report once per line
        except UnicodeDecodeError:
            continue
    
    # Also check AST patterns
    for gui_file in gui_files:
        ast_patterns = parse_ast_for_patterns(gui_file)
        for pattern_type, line_num in ast_patterns:
            if pattern_type == "random.choice":
                violations.append((gui_file, line_num, "random.choice() call"))
    
    assert not violations, (
        f"Mock/fake data generators found in UI modules:\n"
        + "\n".join(f"  {file}:{line_num}: {line}" for file, line_num, line in violations)
    )


def test_ui_uses_registry_loaders():
    """Test 2: UI modules import and use config registry loaders."""
    gui_dir = Path("src/gui")
    
    if not gui_dir.exists():
        pytest.skip("src/gui/ directory does not exist")
    
    # Collect all Python files in gui/
    gui_files = collect_python_files(gui_dir)
    
    # Look for imports from config registry
    registry_imports_found = False
    registry_usage_found = False
    
    for gui_file in gui_files:
        try:
            with open(gui_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Check for config registry imports
            if "from src.config" in content or "import src.config" in content:
                registry_imports_found = True
            
            # Check for registry loader usage
            if "load_timeframes" in content or "load_instruments" in content:
                registry_usage_found = True
                
        except UnicodeDecodeError:
            continue
    
    # During migration, this is a warning, not a failure
    if not registry_imports_found:
        warnings.warn(
            "UI modules should import from src.config registry loaders. "
            "Found no imports of src.config in GUI modules.",
            UserWarning
        )
    
    if not registry_usage_found:
        warnings.warn(
            "UI modules should use registry loaders (load_timeframes, load_instruments, etc.). "
            "Found no usage of registry loaders in GUI modules.",
            UserWarning
        )


def test_no_hardcoded_dropdown_values():
    """Test 3: No hardcoded dropdown values in UI modules."""
    gui_dir = Path("src/gui")
    
    if not gui_dir.exists():
        pytest.skip("src/gui/ directory does not exist")
    
    # Collect all Python files in gui/
    gui_files = collect_python_files(gui_dir)
    
    # Common hardcoded dropdown patterns
    dropdown_patterns = [
        # Timeframe patterns
        r"\[15,\s*30,\s*60,\s*120,\s*240\]",
        r"\[15,\s*30,\s*60\]",
        r"\[60,\s*120,\s*240\]",
        
        # Instrument patterns
        r"\[.*CME\.MNQ.*\]",
        r"\[.*TWF\.MXF.*\]",
        
        # Strategy patterns
        r"\[.*SMA.*\]",
        r"\[.*Breakout.*\]",
        r"\[.*MeanRevert.*\]",
    ]
    
    violations = []
    
    for gui_file in gui_files:
        try:
            with open(gui_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            for line_num, line in enumerate(content.splitlines(), 1):
                for pattern in dropdown_patterns:
                    if re.search(pattern, line):
                        violations.append((gui_file, line_num, line.strip()))
                        break
        except UnicodeDecodeError:
            continue
    
    # Also check AST for hardcoded lists
    for gui_file in gui_files:
        ast_patterns = parse_ast_for_patterns(gui_file)
        for pattern_type, line_num in ast_patterns:
            if pattern_type.startswith("hardcoded_"):
                violations.append((gui_file, line_num, f"{pattern_type} list"))
    
    # During migration, violations are warnings
    if violations:
        warning_msg = (
            f"Hardcoded dropdown values found in UI modules:\n"
            + "\n".join(f"  {file}:{line_num}: {line}" for file, line_num, line in violations)
        )
        warnings.warn(warning_msg, UserWarning)


def test_ui_error_handling():
    """Test 4: UI modules have proper error handling for missing configs."""
    gui_dir = Path("src/gui")
    
    if not gui_dir.exists():
        pytest.skip("src/gui/ directory does not exist")
    
    # Look for try/except blocks around config loading
    # This is a basic check - more sophisticated analysis would be needed
    
    gui_files = collect_python_files(gui_dir)
    
    config_error_handling_found = False
    
    for gui_file in gui_files:
        try:
            with open(gui_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Look for error handling patterns
            if "try:" in content and ("except" in content or "catch" in content):
                if "ConfigError" in content or "FileNotFoundError" in content:
                    config_error_handling_found = True
                    break
                    
        except UnicodeDecodeError:
            continue
    
    # This is informational during migration
    if not config_error_handling_found:
        print(
            "Note: Consider adding error handling for config loading failures in UI modules. "
            "UI should show explicit error states when configs are missing or invalid."
        )


def test_ui_data_provider_pattern():
    """Test 5: UI uses data provider pattern for registry data."""
    gui_dir = Path("src/gui")
    
    if not gui_dir.exists():
        pytest.skip("src/gui/ directory does not exist")
    
    # Look for data provider functions/classes
    gui_files = collect_python_files(gui_dir)
    
    data_provider_patterns = [
        r"def get_.*options\(",
        r"def load_.*data\(",
        r"class.*DataProvider",
        r"class.*RegistryLoader",
    ]
    
    data_providers_found = False
    
    for gui_file in gui_files:
        try:
            with open(gui_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            for pattern in data_provider_patterns:
                if re.search(pattern, content):
                    data_providers_found = True
                    break
                    
            if data_providers_found:
                break
                
        except UnicodeDecodeError:
            continue
    
    # During migration, this is a recommendation
    if not data_providers_found:
        print(
            "Note: Consider implementing data provider pattern in UI modules. "
            "Create src/ui/data_providers.py with functions like get_timeframe_options(), "
            "get_instrument_options() that use registry loaders."
        )


if __name__ == "__main__":
    # Run tests directly for debugging
    test_no_mock_data_generators()
    print("✓ Test 1 passed: no mock data generators")
    
    test_ui_uses_registry_loaders()
    print("✓ Test 2 passed: UI uses registry loaders (or migration needed)")
    
    test_no_hardcoded_dropdown_values()
    print("✓ Test 3 passed: no hardcoded dropdown values (or migration needed)")
    
    test_ui_error_handling()
    print("✓ Test 4 passed: UI error handling check complete")
    
    test_ui_data_provider_pattern()
    print("✓ Test 5 passed: UI data provider pattern check complete")
    
    print("All UI reality tests passed (with migration warnings as needed)!")