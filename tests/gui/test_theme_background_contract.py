"""Theme background contract test.

Ensures the Nexus theme CSS includes required selectors and utility classes
to prevent white background breaches.
"""
import re
from unittest.mock import patch, MagicMock
import pytest

from gui.nicegui.theme.nexus_theme import inject_global_css, apply_nexus_theme
from gui.nicegui.theme.nexus_tokens import TOKENS


class TestThemeBackgroundContract:
    """Test that theme CSS covers all necessary selectors and provides utility classes."""

    def test_css_contains_required_selectors(self):
        """Verify CSS includes html, body, #q-app, .q-layout, .q-page, .q-page-container."""
        captured_css = []
        with patch("gui.nicegui.theme.nexus_theme.ui.add_head_html") as mock_add:
            def capture_css(html):
                captured_css.append(html)
            mock_add.side_effect = capture_css
            inject_global_css()
        
        assert len(captured_css) == 1
        css = captured_css[0]
        # Ensure it's a style tag
        assert "<style>" in css
        assert "</style>" in css
        # Extract CSS content
        match = re.search(r"<style>(.*?)</style>", css, re.DOTALL)
        assert match is not None
        css_content = match.group(1)
        
        # Required selectors (case-insensitive, allow whitespace variations)
        required_selectors = [
            r"html,\s*body",
            r"#q-app",
            r"\.q-layout",
            r"\.q-page",
            r"\.q-page-container",
            r"\.nicegui-content",
            r"\.nicegui-page",
            r"\.q-drawer",
            r"\.q-header",
            r"\.q-footer",
            r"\.q-toolbar",
            # Dynamic Quasar/SPA selectors
            r"\.q-page--active",
            r"\.q-layout-padding",
            r"\.q-scrollarea,\s*\.q-scrollarea__content",
            r"\.q-page-sticky",
            # Root Wrapper Failsafe (KEY) - nested div selectors
            r"#q-app\s*>\s*div",
            r"#q-app\s*>\s*div\s*>\s*div",
            r"#q-app\s*>\s*div\s*>\s*div\s*>\s*div",
            r'\[role="main"\]',
        ]
        for selector in required_selectors:
            pattern = re.compile(selector, re.IGNORECASE)
            assert pattern.search(css_content) is not None, f"Missing selector: {selector}"
        
        # Ensure background-color is set for these selectors with !important
        # Check that at least some selectors have background-color with !important
        bg_important_pattern = r"background-color\s*:\s*[^;]*!important"
        assert re.search(bg_important_pattern, css_content, re.IGNORECASE) is not None, \
            "Missing background-color with !important"
        
        # Check that var(--bg-primary) is defined
        assert "--bg-primary:" in css_content
        
        # Check min-height: 100vh is present for key selectors
        min_height_pattern = r"min-height\s*:\s*100vh"
        assert re.search(min_height_pattern, css_content, re.IGNORECASE) is not None, \
            "Missing min-height: 100vh"
        
    def test_css_contains_nexus_utility_classes(self):
        """Verify CSS includes .bg-nexus-primary, .bg-nexus-panel-dark, etc."""
        captured_css = []
        with patch("gui.nicegui.theme.nexus_theme.ui.add_head_html") as mock_add:
            def capture_css(html):
                captured_css.append(html)
            mock_add.side_effect = capture_css
            inject_global_css()
        
        css = captured_css[0]
        match = re.search(r"<style>(.*?)</style>", css, re.DOTALL)
        css_content = match.group(1)
        
        required_utility_classes = [
            r"\.bg-nexus-primary",
            r"\.bg-nexus-panel-dark",
            r"\.bg-nexus-panel-medium",
            r"\.bg-nexus-panel-light",
        ]
        for cls in required_utility_classes:
            pattern = re.compile(cls)
            assert pattern.search(css_content) is not None, f"Missing utility class: {cls}"
        
        # Ensure they map to correct CSS custom properties
        # Remove spaces and semicolons for matching
        normalized = css_content.replace(" ", "").replace(";", "")
        assert "background-color:var(--bg-primary)" in normalized
        assert "background-color:var(--bg-panel-dark)" in normalized
        assert "background-color:var(--bg-panel-medium)" in normalized
        assert "background-color:var(--bg-panel-light)" in normalized
    
    def test_theme_apply_idempotent(self):
        """apply_nexus_theme should only inject CSS once."""
        with patch("gui.nicegui.theme.nexus_theme.ui.add_head_html") as mock_add:
            mock_add.return_value = None
            # Reset module state
            import gui.nicegui.theme.nexus_theme as theme_module
            theme_module._THEME_APPLIED = False
            theme_module._THEME_APPLY_COUNT = 0
            
            # First call
            apply_nexus_theme()
            assert mock_add.call_count >= 2  # fonts + css, maybe tailwind
            call_count_first = mock_add.call_count
            
            # Second call
            apply_nexus_theme()
            # Should not add more head HTML
            assert mock_add.call_count == call_count_first, "Second call added extra HTML"
            
            # Verify flag is set
            assert theme_module._THEME_APPLIED is True
    
    def test_tokens_match_css_variables(self):
        """Ensure CSS variables are populated with token values."""
        captured_css = []
        with patch("gui.nicegui.theme.nexus_theme.ui.add_head_html") as mock_add:
            def capture_css(html):
                captured_css.append(html)
            mock_add.side_effect = capture_css
            inject_global_css()
        
        css = captured_css[0]
        match = re.search(r"<style>(.*?)</style>", css, re.DOTALL)
        css_content = match.group(1)
        
        # Check that tokens appear in CSS
        assert TOKENS['backgrounds']['primary'] in css_content
        assert TOKENS['backgrounds']['panel_dark'] in css_content
        assert TOKENS['backgrounds']['panel_medium'] in css_content
        assert TOKENS['backgrounds']['panel_light'] in css_content
        
        # Check that CSS variables are defined
        assert f"--bg-primary: {TOKENS['backgrounds']['primary']}" in css_content
        assert f"--bg-panel-dark: {TOKENS['backgrounds']['panel_dark']}" in css_content
        assert f"--bg-panel-medium: {TOKENS['backgrounds']['panel_medium']}" in css_content
        assert f"--bg-panel-light: {TOKENS['backgrounds']['panel_light']}" in css_content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])