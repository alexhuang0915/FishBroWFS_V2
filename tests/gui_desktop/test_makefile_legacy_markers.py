"""
Test that Makefile mark expressions correctly exclude/include legacy UI tests.
"""

import re
from pathlib import Path


def test_makefile_contains_correct_mark_expressions():
    """Verify Makefile contains the expected mark expression strings."""
    makefile_path = Path("Makefile")
    assert makefile_path.exists()
    
    content = makefile_path.read_text()
    
    # Find PYTEST_MARK_EXPR_PRODUCT definition
    product_match = re.search(r'PYTEST_MARK_EXPR_PRODUCT\s*\?=\s*(.+)', content)
    assert product_match is not None
    product_expr = product_match.group(1).strip()
    
    # Should exclude legacy_ui and slow
    assert "not legacy_ui" in product_expr
    assert "not slow" in product_expr
    
    # Find PYTEST_MARK_EXPR_ALL definition
    all_match = re.search(r'PYTEST_MARK_EXPR_ALL\s*\?=\s*(.+)', content)
    assert all_match is not None
    all_expr = all_match.group(1).strip()
    
    # Should exclude legacy_ui only
    assert "not legacy_ui" in all_expr
    
    # Verify check-legacy target exists and contains -m "legacy_ui"
    # Look for the target definition and the command line
    check_legacy_section = re.search(r'^check-legacy:.*?(?:\n\t.*?)*?-m "legacy_ui"', content, re.MULTILINE | re.DOTALL)
    assert check_legacy_section is not None, "check-legacy target should run only legacy_ui tests"
    
    # Verify help text mentions legacy UI as deprecated
    help_section = re.search(r'Legacy Ops.*deprecated', content, re.DOTALL)
    assert help_section is not None, "Help should mention Legacy Ops (Deprecated)"
    
    # Verify gui target mentions deprecated (could be in echo line after target)
    gui_section = re.search(r'^gui:.*?(?:\n\t.*?)*?deprecated', content, re.MULTILINE | re.DOTALL)
    assert gui_section is not None, "gui target should be labeled deprecated"


def test_makefile_targets_exist():
    """Verify required Makefile targets exist."""
    makefile_path = Path("Makefile")
    content = makefile_path.read_text()
    
    required_targets = [
        "dashboard",
        "gui",
        "check",
        "check-legacy",
        "desktop",
        "desktop-offscreen",
    ]
    
    for target in required_targets:
        # Look for target definition (target: at start of line)
        pattern = rf'^{target}:'
        match = re.search(pattern, content, re.MULTILINE)
        assert match is not None, f"Makefile missing target: {target}"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])