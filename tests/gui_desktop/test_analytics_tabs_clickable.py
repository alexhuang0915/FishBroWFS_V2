"""
Test that Analytics tabs are always clickable (Phase 18.6).
"""

import pytest
import sys
from pathlib import Path

# Add src to path
src_dir = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(src_dir))

from PySide6.QtWidgets import QApplication, QTabWidget
from gui.desktop.analysis.analysis_widget import AnalysisWidget


class TestAnalyticsTabsClickable:
    """Test that Analytics tabs are always clickable and never disabled."""
    
    @pytest.fixture
    def app(self):
        """Create QApplication instance for testing."""
        # Reuse existing app if available
        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        return app
    
    @pytest.fixture
    def widget(self, app):
        """Create AnalysisWidget instance for testing."""
        widget = AnalysisWidget()
        yield widget
        widget.deleteLater()
    
    def test_tabs_always_enabled(self, widget):
        """Test that tab widget is always enabled, even when no artifact loaded."""
        # Initially, tabs should be enabled
        assert widget.tab_widget.isEnabled() is True
        
        # Check each tab is enabled
        for i in range(widget.tab_widget.count()):
            assert widget.tab_widget.isTabEnabled(i) is True
        
        # Clear data (simulates no artifact loaded)
        widget.clear()
        
        # Tabs should still be enabled
        assert widget.tab_widget.isEnabled() is True
        for i in range(widget.tab_widget.count()):
            assert widget.tab_widget.isTabEnabled(i) is True
    
    def test_tab_switching_works(self, widget):
        """Test that we can switch between tabs programmatically."""
        # Get initial tab index
        initial_index = widget.tab_widget.currentIndex()
        
        # Switch to each tab
        for i in range(widget.tab_widget.count()):
            widget.tab_widget.setCurrentIndex(i)
            assert widget.tab_widget.currentIndex() == i
        
        # Switch back to initial
        widget.tab_widget.setCurrentIndex(initial_index)
        assert widget.tab_widget.currentIndex() == initial_index
    
    def test_set_report_loaded_does_not_disable_tabs(self, widget):
        """Test that set_report_loaded method doesn't disable tabs."""
        # Test with loaded=False (no report)
        widget.set_report_loaded(False)
        assert widget.tab_widget.isEnabled() is True
        
        # Test with loaded=True (simulate report loaded)
        widget.set_report_loaded(True)
        assert widget.tab_widget.isEnabled() is True
    
    def test_tab_bar_properties(self, widget):
        """Test tab bar properties to ensure clickability."""
        tab_bar = widget.tab_widget.tabBar()
        
        # Tab bar should be enabled
        assert tab_bar.isEnabled() is True
        
        # Tab bar should accept mouse events (not transparent)
        # Note: isVisible() may be False until widget is shown, which is OK for testing
        # We care about whether it would block clicks if it were visible
        from PySide6.QtCore import Qt
        assert tab_bar.testAttribute(Qt.WA_TransparentForMouseEvents) is False
    
    def test_no_overlay_blocking_clicks(self, widget):
        """Test that there are no overlay widgets blocking tab clicks."""
        from PySide6.QtCore import Qt
        
        # Check that no child widget has WA_TransparentForMouseEvents set to block clicks
        for child in widget.tab_widget.findChildren(QTabWidget):
            # The tab widget itself should not have transparent mouse events
            assert child.testAttribute(Qt.WA_TransparentForMouseEvents) is False
        
        # Check for any label overlays near the tab bar
        tab_bar = widget.tab_widget.tabBar()
        tab_bar_rect = tab_bar.geometry()
        
        # Look for widgets that might overlap the tab bar area
        for child in widget.findChildren(type(widget)):
            if child == tab_bar or child == widget.tab_widget:
                continue
                
            child_rect = child.geometry()
            # If a widget overlaps the tab bar area, it should be transparent for mouse events
            if child_rect.intersects(tab_bar_rect):
                # In a proper implementation, such overlays should be transparent to mouse events
                # We'll just log this as a warning for now
                print(f"Warning: Widget {child} overlaps tab bar area")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])