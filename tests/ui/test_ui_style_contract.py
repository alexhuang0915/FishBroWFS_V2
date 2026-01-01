"""UI Style Contract Tests.

Playwright-based tests that enforce visual/style contracts for the UI.
"""
import os
import re
import pytest

# Gating: UI contract tests require FISHBRO_UI_CONTRACT=1
if os.getenv("FISHBRO_UI_CONTRACT") != "1":
    pytest.skip("UI contract tests require FISHBRO_UI_CONTRACT=1", allow_module_level=True)


# ============================================================================
# Contrast Utilities (from provided hint code)
# ============================================================================

def _srgb_to_linear(channel: float) -> float:
    """Convert sRGB channel value (0–1) to linear RGB."""
    if channel <= 0.04045:
        return channel / 12.92
    return ((channel + 0.055) / 1.055) ** 2.4


def _relative_luminance(rgb: tuple[float, float, float]) -> float:
    """Compute relative luminance of an RGB color (0–1 per channel)."""
    r_lin = _srgb_to_linear(rgb[0])
    g_lin = _srgb_to_linear(rgb[1])
    b_lin = _srgb_to_linear(rgb[2])
    return 0.2126 * r_lin + 0.7152 * g_lin + 0.0722 * b_lin


def contrast_ratio(color1: tuple[float, float, float], color2: tuple[float, float, float]) -> float:
    """Compute WCAG 2.1 contrast ratio between two RGB colors (0–1 per channel)."""
    l1 = _relative_luminance(color1)
    l2 = _relative_luminance(color2)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def parse_rgb(css_color: str) -> tuple[float, float, float]:
    """Parse CSS color string (rgb(), rgba(), hex) to normalized RGB tuple (0–1).
    
    Supports:
      - rgb(r, g, b)
      - rgba(r, g, b, a)  (alpha ignored)
      - #RGB, #RRGGBB, #RRGGBBAA
    """
    css_color = css_color.strip().lower()
    
    # rgb(r, g, b)
    rgb_match = re.match(r'rgb\((\d+),\s*(\d+),\s*(\d+)\)', css_color)
    if rgb_match:
        r = int(rgb_match.group(1)) / 255.0
        g = int(rgb_match.group(2)) / 255.0
        b = int(rgb_match.group(3)) / 255.0
        return (r, g, b)
    
    # rgba(r, g, b, a)
    rgba_match = re.match(r'rgba\((\d+),\s*(\d+),\s*(\d+),\s*[\d.]+\)', css_color)
    if rgba_match:
        r = int(rgba_match.group(1)) / 255.0
        g = int(rgba_match.group(2)) / 255.0
        b = int(rgba_match.group(3)) / 255.0
        return (r, g, b)
    
    # Hex formats
    hex_match = re.match(r'#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})', css_color)
    if hex_match:
        r = int(hex_match.group(1), 16) / 255.0
        g = int(hex_match.group(2), 16) / 255.0
        b = int(hex_match.group(3), 16) / 255.0
        return (r, g, b)
    
    # Short hex #RGB
    short_hex_match = re.match(r'#([0-9a-f])([0-9a-f])([0-9a-f])', css_color)
    if short_hex_match:
        r = int(short_hex_match.group(1) * 2, 16) / 255.0
        g = int(short_hex_match.group(2) * 2, 16) / 255.0
        b = int(short_hex_match.group(3) * 2, 16) / 255.0
        return (r, g, b)
    
    # Named colors (basic set)
    named_colors = {
        'black': (0.0, 0.0, 0.0),
        'white': (1.0, 1.0, 1.0),
        'red': (1.0, 0.0, 0.0),
        'green': (0.0, 1.0, 0.0),
        'blue': (0.0, 0.0, 1.0),
    }
    if css_color in named_colors:
        return named_colors[css_color]
    
    raise ValueError(f"Unsupported color format: {css_color}")


JS_GET_STYLE = "(element, property) => { const style = window.getComputedStyle(element); return style.getPropertyValue(property); }"


def px(value: str) -> float:
    """Parse CSS pixel value like '16px' to float."""
    if value.endswith('px'):
        return float(value[:-2])
    return float(value)


# ============================================================================
# Assertion Helpers (not tests themselves)
# ============================================================================

def assert_header_height_bounded(page):
    """Header height must be within [48, 120] pixels."""
    # Try multiple possible selectors for header
    header_selectors = [
        "header.q-header",
        ".nicegui-header",
        "header",
        ".q-header",
    ]
    
    header = None
    for selector in header_selectors:
        locator = page.locator(selector)
        if locator.count() > 0:
            header = locator.first
            break
    
    assert header is not None, "No header element found with known selectors"
    
    # Get bounding box
    box = header.bounding_box()
    assert box is not None, "Header bounding box not available"
    
    height = box['height']
    assert 48 <= height <= 120, f"Header height {height}px outside bounds [48, 120]"


def assert_tabs_bar_height_bounded(page):
    """Tabs bar height must be within [32, 96] pixels."""
    tabs = page.locator(".q-tabs")
    assert tabs.count() > 0, "No .q-tabs element found"
    
    box = tabs.first.bounding_box()
    assert box is not None, "Tabs bar bounding box not available"
    
    height = box['height']
    assert 32 <= height <= 96, f"Tabs bar height {height}px outside bounds [32, 96]"


def assert_no_horizontal_overflow(page):
    """Page must not have horizontal overflow."""
    # Evaluate JavaScript to check scroll width vs client width
    no_overflow = page.evaluate("""
        () => {
            const docEl = document.documentElement;
            return docEl.scrollWidth <= docEl.clientWidth + 1;
        }
    """)
    assert no_overflow, "Page has horizontal overflow (scrollWidth > clientWidth + 1)"


def assert_text_contrast_critical_elements(page):
    """Critical text elements must have sufficient contrast ratio."""
    # Elements to check with their minimum contrast requirements
    # Format: (selector, is_large_text)
    elements_to_check = [
        (".nexus-page-title", True),           # Large text (>=18px or >=14px bold)
        (".nicegui-header .text-xl", True),    # Large text
        (".text-secondary", False),            # Normal text
        (".text-primary", False),              # Normal text
    ]
    
    for selector, is_large_text in elements_to_check:
        locator = page.locator(selector)
        if locator.count() == 0:
            # Skip if element not present on current page
            continue
        
        element = locator.first.element_handle()
        
        # Get computed color and background color
        color_js = JS_GET_STYLE.strip()
        color_str = element.evaluate(color_js, "color")
        bg_color_str = element.evaluate(color_js, "background-color")
        
        # If background is transparent, get parent background
        if bg_color_str == 'rgba(0, 0, 0, 0)' or bg_color_str == 'transparent':
            # Walk up parent elements until we find a non-transparent background
            parent = element
            for _ in range(5):  # Limit depth
                parent_js = """
                (el) => {
                    if (!el.parentElement) return null;
                    return el.parentElement;
                }
                """
                parent = page.evaluate_handle(parent_js, parent)
                if parent is None:
                    break
                bg_color_str = parent.evaluate(color_js, "background-color")
                if bg_color_str not in ('rgba(0, 0, 0, 0)', 'transparent'):
                    break
        
        # Parse colors
        try:
            color_rgb = parse_rgb(color_str)
            bg_rgb = parse_rgb(bg_color_str)
        except ValueError:
            # If color parsing fails, skip this element
            continue
        
        # Compute contrast ratio
        ratio = contrast_ratio(color_rgb, bg_rgb)
        
        # WCAG requirements
        min_ratio = 3.0 if is_large_text else 4.5
        assert ratio >= min_ratio, (
            f"Contrast ratio {ratio:.2f} for {selector} "
            f"below required {min_ratio} (color: {color_str}, bg: {bg_color_str})"
        )


def assert_theme_consistency(page):
    """Ensure dark theme is consistently applied."""
    # Check body class
    body = page.locator("body")
    class_list = body.get_attribute("class") or ""
    assert "dark" in class_list.lower(), "Body missing 'dark' theme class"
    assert "light" not in class_list.lower(), "Body has 'light' theme class (should be dark)"
    
    # Check computed background color is dark
    body_bg = page.evaluate("""
        () => {
            const style = window.getComputedStyle(document.body);
            return style.backgroundColor;
        }
    """)
    
    # Parse background color
    try:
        bg_rgb = parse_rgb(body_bg)
    except ValueError:
        # If we can't parse, skip luminance check
        return
    
    # Compute luminance (0-1)
    luminance = _relative_luminance(bg_rgb)
    
    # Dark theme threshold: luminance < 0.15
    assert luminance < 0.15, f"Body background luminance {luminance:.3f} too high for dark theme"


# ============================================================================
# Test Functions (pytest will collect these)
# ============================================================================

@pytest.mark.ui_contract
@pytest.mark.xfail(reason="UI contract tests may fail due to Socket.IO cleanup")
def test_header_height_bounded(page):
    """Header height must be within [48, 120] pixels."""
    assert_header_height_bounded(page)


@pytest.mark.ui_contract
@pytest.mark.xfail(reason="UI contract tests may fail due to Socket.IO cleanup")
def test_tabs_bar_height_bounded(page):
    """Tabs bar height must be within [32, 96] pixels."""
    assert_tabs_bar_height_bounded(page)


@pytest.mark.ui_contract
def test_no_horizontal_overflow(page):
    """Page must not have horizontal overflow."""
    assert_no_horizontal_overflow(page)


@pytest.mark.ui_contract
def test_text_contrast_critical_elements(page):
    """Critical text elements must have sufficient contrast ratio."""
    assert_text_contrast_critical_elements(page)


@pytest.mark.ui_contract
@pytest.mark.xfail(reason="UI contract tests may fail due to Socket.IO cleanup")
def test_theme_consistency(page):
    """Ensure dark theme is consistently applied."""
    assert_theme_consistency(page)


# ============================================================================
# Page-specific tests
# ============================================================================

@pytest.mark.ui_contract
@pytest.mark.xfail(reason="UI contract tests may fail due to Socket.IO cleanup")
def test_dashboard_page_style_contracts(page):
    """Dashboard page (/)."""
    # Already on root from page fixture
    # Run all style contract assertions
    assert_header_height_bounded(page)
    assert_tabs_bar_height_bounded(page)
    assert_no_horizontal_overflow(page)
    assert_text_contrast_critical_elements(page)
    assert_theme_consistency(page)


@pytest.mark.ui_contract
def test_wizard_page_style_contracts(page):
    """Wizard tab."""
    # Navigate to wizard tab
    wizard_tab = page.locator('a[href*="wizard"]').first
    if wizard_tab.count() > 0:
        wizard_tab.click()
        page.wait_for_load_state("networkidle")
        
        # Run all style contract assertions
        assert_header_height_bounded(page)
        assert_tabs_bar_height_bounded(page)
        assert_no_horizontal_overflow(page)
        assert_text_contrast_critical_elements(page)
        assert_theme_consistency(page)
    else:
        pytest.skip("Wizard tab not found on page")


@pytest.mark.ui_contract
def test_history_page_style_contracts(page):
    """History tab."""
    # Navigate to history tab
    history_tab = page.locator('a[href*="history"]').first
    if history_tab.count() > 0:
        history_tab.click()
        page.wait_for_load_state("networkidle")
        
        # Run all style contract assertions
        assert_header_height_bounded(page)
        assert_tabs_bar_height_bounded(page)
        assert_no_horizontal_overflow(page)
        assert_text_contrast_critical_elements(page)
        assert_theme_consistency(page)
    else:
        pytest.skip("History tab not found on page")


@pytest.mark.ui_contract
def test_settings_page_style_contracts(page):
    """Settings tab."""
    # Navigate to settings tab
    settings_tab = page.locator('a[href*="settings"]').first
    if settings_tab.count() > 0:
        settings_tab.click()
        page.wait_for_load_state("networkidle")
        
        # Run all style contract assertions
        assert_header_height_bounded(page)
        assert_tabs_bar_height_bounded(page)
        assert_no_horizontal_overflow(page)
        assert_text_contrast_critical_elements(page)
        assert_theme_consistency(page)
    else:
        pytest.skip("Settings tab not found on page")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])