"""
Test that Makefile contains required desktop targets.
"""
import re
from pathlib import Path


def test_makefile_contains_desktop_target():
    """Check that Makefile has desktop: target."""
    makefile_path = Path("Makefile")
    assert makefile_path.exists(), "Makefile not found"
    
    content = makefile_path.read_text()
    
    # Check for desktop: target
    assert "desktop:" in content, "Makefile missing 'desktop:' target"
    
    # Check for desktop-offscreen: target
    assert "desktop-offscreen:" in content, "Makefile missing 'desktop-offscreen:' target"
    
    # Check that desktop target runs the launcher script
    lines = content.splitlines()
    desktop_found = False
    desktop_offscreen_found = False
    
    for i, line in enumerate(lines):
        if line.strip().startswith("desktop:"):
            # Check next non-empty line for command (skip echo lines and comments)
            # Need to handle multi-line commands with backslashes
            for j in range(i + 1, min(i + 15, len(lines))):
                if lines[j].strip() and not lines[j].startswith("\t#") and not lines[j].strip().startswith("@echo") and not lines[j].strip().startswith("@#"):
                    # Should contain scripts/desktop_launcher.py
                    # Check current line and following lines (for multi-line commands)
                    check_lines = [lines[j]]
                    # If line ends with backslash, include next line
                    k = j
                    while k < min(i + 15, len(lines)) and lines[k].strip().endswith('\\'):
                        k += 1
                        if k < len(lines):
                            check_lines.append(lines[k])
                    
                    combined = ' '.join([l.strip() for l in check_lines])
                    if "scripts/desktop_launcher.py" in combined:
                        desktop_found = True
                    break
    
    for i, line in enumerate(lines):
        if line.strip().startswith("desktop-offscreen:"):
            # Check next non-empty line for command (skip echo lines)
            for j in range(i + 1, min(i + 10, len(lines))):
                if lines[j].strip() and not lines[j].startswith("\t#") and not lines[j].strip().startswith("@echo"):
                    # Should contain QT_QPA_PLATFORM=offscreen or $(DESKTOP_OFFSCREEN)
                    if "QT_QPA_PLATFORM=offscreen" in lines[j] or "$(DESKTOP_OFFSCREEN)" in lines[j]:
                        desktop_offscreen_found = True
                    break
    
    assert desktop_found, "desktop: target should run scripts/desktop_launcher.py"
    assert desktop_offscreen_found, "desktop-offscreen: target should set QT_QPA_PLATFORM=offscreen"


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
    assert "Desktop" in help_text, "Makefile help should mention Desktop"
    
    # Check for desktop-offscreen mention
    assert "desktop-offscreen" in help_text.lower(), "Makefile help should mention desktop-offscreen"