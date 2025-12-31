"""Test contract that ensures Quasar content components have dark overrides.

This test locks down the CSS overrides for .q-card, .q-stepper, .q-panel, etc.
Ensures the theme's build_global_css() includes the required selectors with
!important and var(--bg-panel-dark).
"""
import re
import pytest

from gui.nicegui.theme.nexus_theme import build_global_css


def test_css_contains_quasar_dark_overrides():
    """Assert CSS contains the required selectors with !important and var(--bg-panel-dark)."""
    css = build_global_css()
    
    # Required selectors (as per specification)
    required_selectors = [
        r'\.q-card',
        r'\.q-stepper',
        r'\.q-stepper__content',
        r'\.q-panel',
        r'\.q-stepper__step-content',
        r'\.q-item',
    ]
    
    # Combined pattern: selector followed by { ... background-color: var(--bg-panel-dark) !important; ... }
    # We'll check each selector appears somewhere in the CSS and that the background-color rule exists.
    for selector in required_selectors:
        # Ensure selector appears in CSS
        assert re.search(selector, css), f"Selector {selector} not found in CSS"
    
    # Ensure the background-color rule with var(--bg-panel-dark) and !important appears
    # The rule is defined as a block covering all selectors together (lines 217-221)
    # We'll check that the block exists.
    bg_rule_pattern = r'background-color:\s*var\(--bg-panel-dark\)\s*!important'
    assert re.search(bg_rule_pattern, css), f"CSS missing background-color: var(--bg-panel-dark) !important"
    
    # Also ensure color rule with var(--text-primary) !important
    color_rule_pattern = r'color:\s*var\(--text-primary\)\s*!important'
    assert re.search(color_rule_pattern, css), f"CSS missing color: var(--text-primary) !important"
    
    # Verify the block includes all selectors (optional but good)
    # The actual CSS block we added is:
    # .q-card, .q-stepper, .q-stepper__content, .q-panel,
    # .q-stepper__step-content, .q-item {
    #     background-color: var(--bg-panel-dark) !important;
    #     color: var(--text-primary) !important;
    # }
    # We'll check that at least one of the selectors appears before the block.
    # Simpler: ensure the combined selector line appears.
    combined_line = '.q-card, .q-stepper, .q-stepper__content, .q-panel,'
    assert combined_line in css, f"Combined selector line missing: {combined_line}"


def test_css_contains_layout_constitution_classes():
    """Assert CSS contains the layout constitution classes."""
    css = build_global_css()
    
    required_classes = [
        '.nexus-page-fill',
        '.nexus-content',
        '.nexus-page-title',
        '.nexus-islands',
    ]
    
    for cls in required_classes:
        assert cls in css, f"Layout class {cls} not found in CSS"
    
    # Ensure .nexus-content has max-width: 1200px
    assert 'max-width: 1200px' in css, "CSS missing max-width: 1200px for .nexus-content"
    
    # Ensure .nexus-islands has grid-template-columns and min-height
    assert 'grid-template-columns' in css, "CSS missing grid-template-columns for .nexus-islands"
    assert 'min-height' in css, "CSS missing min-height for .nexus-islands"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])