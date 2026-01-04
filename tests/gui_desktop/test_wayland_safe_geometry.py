"""
Wayland-safe Sizing Unit Test (Phase 18.7.2).

Tests that window geometry logic respects Wayland constraints:
- On Wayland: use resize() only, never maximize
- On X11/Windows: can use setGeometry with default position

This test is logic-only and tests by examining source code and using simple logic tests.
"""
import pytest
import os
import re


def test_wayland_detection_logic():
    """Test Wayland detection logic by implementing it directly."""
    # Re-implement the logic from control_station.py
    def _is_wayland_test(wayland_display, qt_platform):
        qt_platform_lower = (qt_platform or "").lower()
        is_xcb = "xcb" in qt_platform_lower
        return bool(wayland_display) and not is_xcb
    
    # Test cases
    test_cases = [
        # (WAYLAND_DISPLAY, QT_QPA_PLATFORM, expected_is_wayland)
        ("wayland-0", "", True),
        ("wayland-0", "xcb", False),
        ("wayland-0", "XCB", False),
        ("wayland-0", "wayland", True),
        ("wayland-0", "Wayland", True),
        ("", "", False),
        ("", "xcb", False),
        ("", "wayland", False),  # No WAYLAND_DISPLAY, so not Wayland
        ("wayland-1", "offscreen", True),  # offscreen != xcb
        ("wayland-1", "xcb_egl", False),  # contains xcb
    ]
    
    for wayland_display, qt_platform, expected in test_cases:
        result = _is_wayland_test(wayland_display, qt_platform)
        assert result == expected, f"Failed for WAYLAND_DISPLAY={wayland_display}, QT_QPA_PLATFORM={qt_platform}: expected {expected}, got {result}"


def test_control_station_uses_wayland_safe_geometry():
    """Test that ControlStation constructor uses the Wayland-safe geometry function."""
    # Read the source file directly
    with open('src/gui/desktop/control_station.py', 'r') as f:
        source = f.read()
    
    # Verify that _apply_initial_geometry is defined
    assert 'def _apply_initial_geometry' in source, "_apply_initial_geometry function should be defined"
    assert 'def _is_wayland' in source, "_is_wayland function should be defined"
    
    # Verify that ControlStation.setup_ui calls _apply_initial_geometry
    # Find the setup_ui method
    setup_ui_match = re.search(r'def setup_ui\(self\):(.*?)(?=\n    def|\nclass|\Z)', source, re.DOTALL)
    assert setup_ui_match, "setup_ui method should be defined"
    setup_ui_body = setup_ui_match.group(1)
    
    assert '_apply_initial_geometry' in setup_ui_body, "ControlStation.setup_ui should call _apply_initial_geometry"
    assert '1920' in setup_ui_body or 'target_w' in setup_ui_body, "ControlStation.setup_ui should specify window dimensions"
    
    # Verify the function signatures
    assert '_is_wayland() -> bool:' in source or 'def _is_wayland() -> bool:' in source, "_is_wayland should have proper type hint"
    assert 'target_w: int = 1920' in source or 'target_w=1920' in source, "_apply_initial_geometry should have default width 1920"
    assert 'target_h: int = 1080' in source or 'target_h=1080' in source, "_apply_initial_geometry should have default height 1080"


def test_no_maximize_in_source_code():
    """Ensure ControlStation source code doesn't call maximize methods."""
    # Read the source file directly
    with open('src/gui/desktop/control_station.py', 'r') as f:
        source = f.read()
    
    # Check for maximize-related calls
    assert 'showMaximized' not in source, "ControlStation should not call showMaximized()"
    assert 'setWindowState' not in source or 'Qt.WindowMaximized' not in source, "ControlStation should not set window state to maximized"
    
    # Check that the geometry logic is Wayland-safe
    # Should have logic for Wayland detection
    assert 'WAYLAND_DISPLAY' in source, "Should check WAYLAND_DISPLAY environment variable"
    assert 'QT_QPA_PLATFORM' in source, "Should check QT_QPA_PLATFORM environment variable"
    
    # Should have different behavior for Wayland vs X11
    assert '_is_wayland()' in source, "Should call _is_wayland() function"
    assert 'if _is_wayland():' in source or 'if _is_wayland()' in source, "Should have conditional for Wayland"


def test_wayland_safe_geometry_implementation():
    """Test that the geometry implementation is Wayland-safe."""
    # Read the source file directly
    with open('src/gui/desktop/control_station.py', 'r') as f:
        source = f.read()
    
    # Find the _apply_initial_geometry function
    geometry_match = re.search(r'def _apply_initial_geometry\(.*?\):(.*?)(?=\n\S|\Z)', source, re.DOTALL)
    assert geometry_match, "_apply_initial_geometry function should be defined"
    geometry_body = geometry_match.group(1)
    
    # Should have Wayland-specific logic
    assert 'if _is_wayland():' in geometry_body or 'if _is_wayland()' in geometry_body, "Should have Wayland conditional"
    
    # Should use resize() on Wayland
    assert 'window.resize' in geometry_body, "Should call resize() method"
    
    # Should NOT use setGeometry on Wayland (but can use it on X11)
    # We'll check that setGeometry is only in the else branch
    lines = geometry_body.split('\n')
    in_wayland_branch = False
    set_geometry_in_wayland = False
    
    for line in lines:
        if 'if _is_wayland():' in line or 'if _is_wayland()' in line:
            in_wayland_branch = True
        elif 'else:' in line or 'elif' in line or line.strip() and not line.startswith(' ') and not line.startswith('\t'):
            in_wayland_branch = False
        
        if 'setGeometry' in line and in_wayland_branch:
            set_geometry_in_wayland = True
    
    assert not set_geometry_in_wayland, "Should not call setGeometry() in Wayland branch"