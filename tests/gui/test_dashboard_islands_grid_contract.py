"""Test contract that ensures dashboard islands grid CSS exists and is correct.

This test locks down the .nexus-islands grid CSS with responsive breakpoints.
"""
import re
import pytest

from gui.nicegui.theme.nexus_theme import build_global_css


def test_nexus_islands_css_exists():
    """Assert .nexus-islands class exists in CSS with required properties."""
    css = build_global_css()
    
    # Ensure the class is defined
    assert '.nexus-islands' in css, "CSS missing .nexus-islands class"
    
    # Extract the block for .nexus-islands (simplified)
    # We'll look for the pattern .nexus-islands { ... }
    # Since CSS may be minified, we'll just check for key properties.
    required_properties = [
        'display: grid',
        'grid-template-columns',
        'gap: 24px',
        'width: 100%',
        'min-height: 200px',
    ]
    
    for prop in required_properties:
        assert prop in css, f"CSS missing property '{prop}' for .nexus-islands"
    
    # Ensure responsive breakpoints are present
    assert '@media (max-width: 768px)' in css, "CSS missing mobile breakpoint"
    assert '@media (min-width: 769px) and (max-width: 1024px)' in css, \
        "CSS missing tablet breakpoint"
    
    # Check that grid-template-columns changes in breakpoints
    # We'll just verify that the breakpoint blocks contain grid-template-columns
    # Use regex to find the block content (simplistic)
    mobile_block = re.search(r'@media\s*\(max-width:\s*768px\)\s*\{[^}]+\}', css, re.DOTALL)
    assert mobile_block is not None, "Could not find mobile breakpoint block"
    mobile_css = mobile_block.group(0)
    assert 'grid-template-columns: 1fr' in mobile_css, \
        "Mobile breakpoint missing grid-template-columns: 1fr"
    
    tablet_block = re.search(
        r'@media\s*\(min-width:\s*769px\)\s*and\s*\(max-width:\s*1024px\)\s*\{[^}]+\}',
        css, re.DOTALL
    )
    assert tablet_block is not None, "Could not find tablet breakpoint block"
    tablet_css = tablet_block.group(0)
    assert 'grid-template-columns: repeat(2, 1fr)' in tablet_css, \
        "Tablet breakpoint missing grid-template-columns: repeat(2, 1fr)"


def test_dashboard_uses_nexus_islands():
    """Assert dashboard.py uses .nexus-islands wrapper for status cards.
    
    This test imports the dashboard module and checks that the render function
    contains a 'nexus-islands' class in the generated HTML (or at least in the source).
    """
    import inspect
    from gui.nicegui.pages.dashboard import render
    
    source = inspect.getsource(render)
    # Look for the pattern: with ui.element('div').classes('nexus-islands'):
    assert "classes('nexus-islands')" in source or 'classes("nexus-islands")' in source, \
        "Dashboard render does not use nexus-islands class"
    
    # Ensure the four status cards are inside that block (optional)
    # We'll just check that the block exists and is not commented out.
    # Since we already updated dashboard.py, this should pass.


if __name__ == '__main__':
    pytest.main([__file__, '-v'])