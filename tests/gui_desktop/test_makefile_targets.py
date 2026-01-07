"""
Test that Makefile contains required desktop targets.
"""
import re
from pathlib import Path


def test_makefile_contains_up_target():
    """Check that Makefile has up: target that launches desktop UI."""
    makefile_path = Path("Makefile")
    assert makefile_path.exists(), "Makefile not found"
    
    content = makefile_path.read_text()
    
    # Check for up: target
    assert "up:" in content, "Makefile missing 'up:' target"
    
    # Check that up target runs the launcher script
    lines = content.splitlines()
    up_found = False
    
    for i, line in enumerate(lines):
        if line.strip().startswith("up:"):
            # Check next non-empty line for command (skip echo lines and comments)
            # Need to handle multi-line commands with backslashes
            for j in range(i + 1, min(i + 40, len(lines))):
                if lines[j].strip() and not lines[j].startswith("\t#") and not lines[j].strip().startswith("@echo") and not lines[j].strip().startswith("@#"):
                    # Should contain scripts/desktop_launcher.py
                    # Check current line and following lines (for multi-line commands)
                    check_lines = [lines[j]]
                    # If line ends with backslash, include next line
                    k = j
                    while k < min(i + 40, len(lines)) and lines[k].strip().endswith('\\'):
                        k += 1
                        if k < len(lines):
                            check_lines.append(lines[k])
                    
                    combined = ' '.join([l.strip() for l in check_lines])
                    if "scripts/desktop_launcher.py" in combined:
                        up_found = True
                    break
    
    assert up_found, "up: target should run scripts/desktop_launcher.py"


def test_makefile_help_includes_desktop():
    """Check that make help includes Desktop section."""
    makefile_path = Path("Makefile")
    content = makefile_path.read_text()
    
    # Look for help text pattern
    # Usually there's a help: target with echo statements
    help_section = re.search(r'^help:.*?(?=^\w+:|\Z)', content, re.MULTILINE | re.DOTALL)
    assert help_section, "Makefile missing help: target"
    
    help_text = help_section.group(0)
    
    # Check for Desktop mention
    assert "Desktop is the ONLY product UI" in help_text, "Makefile help should mention 'Desktop is the ONLY product UI'"
    
    # Check for PRODUCT COMMANDS
    assert "PRODUCT COMMANDS" in help_text, "Makefile help should contain 'PRODUCT COMMANDS'"
    
    # Check for up and down commands
    assert "make up" in help_text, "Makefile help should mention 'make up'"
    assert "make down" in help_text, "Makefile help should mention 'make down'"