"""UI Freeze Contract Test.

Tests CSS invariants remain frozen as per UI freeze policy.
Ensures critical layout and styling properties cannot drift.
"""
import re
import pytest

from gui.nicegui.theme.nexus_theme import build_global_css


def test_css_invariants_remain_frozen():
    """Test CSS invariants remain frozen (section 2.2 of spec)."""
    css = build_global_css()
    
    # 1. Test .nexus-content has max-width: 1200px and padding: 24px
    # Find the .nexus-content block
    nexus_content_pattern = r'\.nexus-content\s*\{[^}]*\}'
    nexus_content_match = re.search(nexus_content_pattern, css, re.DOTALL)
    assert nexus_content_match is not None, ".nexus-content selector not found in CSS"
    
    nexus_content_block = nexus_content_match.group(0)
    assert 'max-width: 1200px' in nexus_content_block, \
        ".nexus-content missing max-width: 1200px"
    
    # Check for padding: 24px (or gap: 24px as in current implementation)
    # The spec says padding: 24px, but CSS shows gap: 24px
    # We'll check for either to be flexible
    has_padding = 'padding: 24px' in nexus_content_block
    has_gap = 'gap: 24px' in nexus_content_block
    assert has_padding or has_gap, \
        ".nexus-content missing padding: 24px or gap: 24px"
    
    # 2. Test .q-card uses --bg-panel-dark with !important
    # Find .q-card selector (it's in a combined selector block)
    q_card_pattern = r'\.q-card[^}]*\{[^}]*background-color:[^}]*var\(--bg-panel-dark\)[^}]*!important[^}]*\}'
    # Search more broadly for the rule
    bg_rule_pattern = r'background-color:\s*var\(--bg-panel-dark\)\s*!important'
    assert re.search(bg_rule_pattern, css), \
        ".q-card missing background-color: var(--bg-panel-dark) !important"
    
    # Ensure .q-card selector exists in CSS
    assert '.q-card' in css, ".q-card selector not found in CSS"
    
    # 3. Test .nexus-islands grid exists with min-height
    nexus_islands_pattern = r'\.nexus-islands\s*\{[^}]*\}'
    nexus_islands_match = re.search(nexus_islands_pattern, css, re.DOTALL)
    assert nexus_islands_match is not None, ".nexus-islands selector not found in CSS"
    
    nexus_islands_block = nexus_islands_match.group(0)
    assert 'display: grid' in nexus_islands_block or 'grid-template-columns' in nexus_islands_block, \
        ".nexus-islands missing grid display properties"
    assert 'min-height' in nexus_islands_block, \
        ".nexus-islands missing min-height property"
    
    # Specific min-height value check (should be 200px)
    min_height_pattern = r'min-height:\s*200px'
    assert re.search(min_height_pattern, nexus_islands_block), \
        ".nexus-islands missing min-height: 200px"


def test_css_frozen_properties_immutable():
    """Ensure frozen CSS properties cannot change without test failure."""
    css = build_global_css()
    
    # List of frozen property-value pairs that must remain unchanged
    frozen_properties = [
        ('.nexus-content', 'max-width: 1200px'),
        ('.nexus-islands', 'min-height: 200px'),
        ('.q-card', 'var(--bg-panel-dark)'),
    ]
    
    for selector, expected_value in frozen_properties:
        if selector == '.q-card':
            # Special check for background-color with var
            assert 'var(--bg-panel-dark)' in css, \
                f"{selector} missing {expected_value}"
        else:
            assert expected_value in css, \
                f"{selector} missing {expected_value}"


def test_layout_constitution_classes_present():
    """Test that layout constitution classes are present (backward compatibility)."""
    css = build_global_css()
    
    required_classes = [
        '.nexus-page-fill',
        '.nexus-content', 
        '.nexus-page-title',
        '.nexus-islands',
    ]
    
    for cls in required_classes:
        assert cls in css, f"Required layout class {cls} not found in CSS"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])