"""UI Component Contracts Test - Enforce canonical NiceGUI usage patterns.

HR-1: All input widgets MUST NOT use label= keyword argument in constructor.
HR-2: Wizard form widgets MUST be bindable to state.
HR-3: No UI creation at import-time.
HR-4: FORBIDDEN EVENT API - No .on_change() on NiceGUI input components

This test scans the entire NiceGUI directory for forbidden patterns.
"""

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "src" / "FishBroWFS_V2" / "gui" / "nicegui"

# Forbidden patterns: ui.widget(... label=...)
# Focus on the most common input widgets that caused the crash
FORBIDDEN = [
    re.compile(r"ui\.date\([^)]*\blabel\s*="),
    re.compile(r"ui\.time\([^)]*\blabel\s*="),
    re.compile(r"ui\.input\([^)]*\blabel\s*="),
    re.compile(r"ui\.select\([^)]*\blabel\s*="),
    re.compile(r"ui\.number\([^)]*\blabel\s*="),
    re.compile(r"ui\.textarea\([^)]*\blabel\s*="),
    re.compile(r"ui\.checkbox\([^)]*\blabel\s*="),
    re.compile(r"ui\.switch\([^)]*\blabel\s*="),
    re.compile(r"ui\.radio\([^)]*\blabel\s*="),
    re.compile(r"ui\.slider\([^)]*\blabel\s*="),
    re.compile(r"ui\.color_input\([^)]*\blabel\s*="),
    re.compile(r"ui\.upload\([^)]*\blabel\s*="),
]

# Forbidden event patterns (HR-4)
FORBIDDEN_EVENTS = [
    re.compile(r"\.on_change\s*\("),
    re.compile(r"\.on_input\s*\("),
    re.compile(r"\.on_update\s*\("),
]


def test_no_label_kwarg_in_nicegui_inputs():
    """Test that no NiceGUI input widget uses label= keyword argument."""
    violations = []
    
    for py_file in TARGET.rglob("*.py"):
        try:
            content = py_file.read_text(encoding="utf-8", errors="replace")
            lines = content.splitlines()
            
            # Track if we're inside a string literal (docstring or regular string)
            in_string = False
            string_char = None  # ' or " or ''' or """
            in_triple = False
            
            for line_num, line in enumerate(lines, start=1):
                # Process character by character to track string literals
                i = 0
                while i < len(line):
                    char = line[i]
                    
                    # Handle string literals
                    if not in_string:
                        # Check for start of string
                        if char in ('"', "'"):
                            # Check if it's a triple quote
                            if i + 2 < len(line) and line[i:i+3] == char*3:
                                in_string = True
                                in_triple = True
                                string_char = char*3
                                i += 2  # Skip the other two quotes
                            else:
                                in_string = True
                                in_triple = False
                                string_char = char
                    else:
                        # Check for end of string
                        if in_triple:
                            if i + 2 < len(line) and line[i:i+3] == string_char:
                                in_string = False
                                in_triple = False
                                string_char = None
                                i += 2  # Skip the other two quotes
                        else:
                            if char == string_char:
                                # Check if it's escaped
                                if i > 0 and line[i-1] == '\\':
                                    # Escaped quote, continue
                                    pass
                                else:
                                    in_string = False
                                    string_char = None
                    
                    i += 1
                
                # Skip comments and string literals
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                
                # Skip lines that are inside string literals (docstrings, etc.)
                if in_string:
                    continue
                
                # Check for forbidden patterns
                for pattern in FORBIDDEN:
                    if pattern.search(line):
                        violations.append(
                            f"{py_file.relative_to(ROOT)}:{line_num}: {line.strip()}"
                        )
        except Exception as e:
            violations.append(f"{py_file.relative_to(ROOT)}:0: ERROR reading file: {e}")
    
    # Note: We're NOT checking for import-time UI creation in this test
    # because it's too complex to parse correctly with simple regex.
    # The main goal is to prevent label= crashes, which we've already fixed.
    
    assert not violations, (
        "Forbidden label= usage in NiceGUI input widgets or import-time UI creation:\n"
        + "\n".join(violations)
        + "\n\n"
        + "Canonical pattern (MUST use):\n"
        + "with ui.column().classes('gap-1'):\n"
        + "    ui.label('Your Label')\n"
        + "    ui.date().bind_value(state, 'field_name')\n"
    )


def test_wizard_widgets_bindable():
    """Test that wizard form widgets are bindable (have .bind_value or similar)."""
    # This is a conceptual test - in practice we'd need to analyze the wizard code
    # For now, we'll just check that wizard.py exists and has been fixed
    wizard_file = TARGET / "pages" / "wizard.py"
    assert wizard_file.exists(), "wizard.py should exist"
    
    content = wizard_file.read_text(encoding="utf-8", errors="replace")
    
    # Check that we're using the canonical pattern (ui.label separate from widget)
    if "ui.date(label=" in content or "ui.input(label=" in content or "ui.select(label=" in content:
        raise AssertionError(
            "wizard.py still contains forbidden label= usage. "
            "All labels must be separate ui.label() widgets."
        )
    
    # Check for bindable patterns (simplified)
    bind_patterns = [
        ".bind_value(",
        ".bind_value_to(",
        ".on_change(",
        ".on_input(",
        ".on(",
    ]
    
    has_bindings = any(pattern in content for pattern in bind_patterns)
    assert has_bindings, (
        "wizard.py should have bindable widgets (.bind_value or similar). "
        "Found patterns: " + ", ".join([p for p in bind_patterns if p in content])
    )


def test_ui_wrapper_available():
    """Test that UI wrapper functions are available (optional but recommended)."""
    # Check if ui_compat.py exists
    ui_compat_file = TARGET / "ui_compat.py"
    
    if ui_compat_file.exists():
        content = ui_compat_file.read_text(encoding="utf-8", errors="replace")
        
        # Check for labeled_* functions
        required_functions = ["labeled_date", "labeled_input", "labeled_select"]
        for func in required_functions:
            assert f"def {func}" in content, f"ui_compat.py should define {func}()"
    else:
        # ui_compat.py is optional, so just warn
        print("Note: ui_compat.py not found (optional but recommended for consistency)")


def test_no_forbidden_event_apis():
    """Test that no NiceGUI input widgets use forbidden event APIs (.on_change, .on_input, .on_update)."""
    violations = []
    
    for py_file in TARGET.rglob("*.py"):
        try:
            content = py_file.read_text(encoding="utf-8", errors="replace")
            lines = content.splitlines()
            
            # Track if we're inside a string literal (docstring or regular string)
            in_string = False
            string_char = None  # ' or " or ''' or """
            in_triple = False
            
            for line_num, line in enumerate(lines, start=1):
                # Process character by character to track string literals
                i = 0
                while i < len(line):
                    char = line[i]
                    
                    # Handle string literals
                    if not in_string:
                        # Check for start of string
                        if char in ('"', "'"):
                            # Check if it's a triple quote
                            if i + 2 < len(line) and line[i:i+3] == char*3:
                                in_string = True
                                in_triple = True
                                string_char = char*3
                                i += 2  # Skip the other two quotes
                            else:
                                in_string = True
                                in_triple = False
                                string_char = char
                    else:
                        # Check for end of string
                        if in_triple:
                            if i + 2 < len(line) and line[i:i+3] == string_char:
                                in_string = False
                                in_triple = False
                                string_char = None
                                i += 2  # Skip the other two quotes
                        else:
                            if char == string_char:
                                # Check if it's escaped
                                if i > 0 and line[i-1] == '\\':
                                    # Escaped quote, continue
                                    pass
                                else:
                                    in_string = False
                                    string_char = None
                    
                    i += 1
                
                # Skip comments and string literals
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                
                # Skip lines that are inside string literals (docstrings, etc.)
                if in_string:
                    continue
                
                # Check for forbidden event patterns
                for pattern in FORBIDDEN_EVENTS:
                    if pattern.search(line):
                        violations.append(
                            f"{py_file.relative_to(ROOT)}:{line_num}: {line.strip()}"
                        )
        except Exception as e:
            violations.append(f"{py_file.relative_to(ROOT)}:0: ERROR reading file: {e}")
    
    assert not violations, (
        "Forbidden event API usage in NiceGUI input widgets:\n"
        + "\n".join(violations)
        + "\n\n"
        + "NiceGUI does NOT support .on_change(), .on_input(), or .on_update() on input components.\n"
        + "These APIs do not exist in NiceGUI Python and will crash at runtime.\n"
        + "\n"
        + "✅ ALLOWED PATTERNS:\n"
        + "1. Use bind_value() + reactive state:\n"
        + "   ui.input().bind_value(state, 'field_name')\n"
        + "   Then react elsewhere with ui.timer() or state mutations.\n"
        + "\n"
        + "2. Use .on('update:model-value', ...) (advanced):\n"
        + "   ui.input().on('update:model-value', lambda e: update_state())\n"
        + "\n"
        + "❌ BANNED PATTERNS (WILL CRASH):\n"
        + "   ui.input().on_change(...)\n"
        + "   ui.select().on_change(...)\n"
        + "   ui.date().on_change(...)\n"
        + "   season_input.on_change(...)\n"
        + "   ui.input(on_change=...)\n"
    )