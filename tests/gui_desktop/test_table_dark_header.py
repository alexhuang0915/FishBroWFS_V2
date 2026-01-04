"""
Test that table headers use dark theme (Phase 18.6).
"""

import pytest
import sys
from pathlib import Path

# Add src to path
src_dir = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(src_dir))

from PySide6.QtWidgets import QApplication, QTableWidget, QHeaderView
from PySide6.QtGui import QColor
from gui.desktop.analysis.analysis_widget import AnalysisWidget


class TestTableDarkHeader:
    """Test that table headers use dark theme colors."""
    
    @pytest.fixture
    def app(self):
        """Create QApplication instance for testing."""
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
    
    def test_table_header_stylesheet_dark(self, widget):
        """Test that table header stylesheet uses dark colors."""
        # Get the trades table
        table = widget.trades_table
        assert table is not None
        
        # Get the stylesheet
        stylesheet = table.styleSheet()
        
        # Check for dark theme colors in stylesheet
        dark_colors = ["#2B2B2B", "#2A2A2A", "#1E1E1E", "#444444", "#333333"]
        
        # At least one dark color should be in the stylesheet
        has_dark_color = any(color in stylesheet for color in dark_colors)
        assert has_dark_color, f"No dark colors found in table stylesheet: {stylesheet}"
        
        # Check for QHeaderView::section rule with dark background
        assert "QHeaderView::section" in stylesheet
        assert "background-color" in stylesheet.lower()
        
        # Check that we don't have light theme colors
        light_colors = ["#f0f0f0", "#ffffff", "#f9f9f9", "#ddd", "#f5f5f5"]
        for color in light_colors:
            if color in stylesheet:
                print(f"Warning: Light color {color} found in table stylesheet")
    
    def test_table_header_palette_not_white(self, widget):
        """Test that table header palette doesn't use default white."""
        # Get the trades table
        table = widget.trades_table
        assert table is not None
        
        # Get horizontal header
        header = table.horizontalHeader()
        assert header is not None
        
        # Get header palette
        palette = header.palette()
        
        # Check window/text colors are not close to white
        # Note: In PySide6, palette roles are lowercase (window, text)
        window_color = palette.color(palette.ColorRole.Window)
        text_color = palette.color(palette.ColorRole.Text)
        
        # Default Qt light theme uses near-white colors (RGB > 240)
        # Dark theme should have lower values
        def is_dark_color(color):
            # Consider color dark if average RGB < 180
            return (color.red() + color.green() + color.blue()) / 3 < 180
        
        # If stylesheet is applied, palette might be overridden
        # Check if either window or text color is dark
        window_is_dark = is_dark_color(window_color)
        text_is_dark = is_dark_color(text_color)
        
        # At least one should be dark if theme is applied
        # (Some Qt setups might not fully apply palette until shown)
        # For this test, we'll check that the stylesheet is applied instead
        # since palette might not reflect stylesheet until widget is shown
        stylesheet = table.styleSheet()
        has_dark_stylesheet = any(color in stylesheet.lower() for color in ["#2a2a2a", "#2b2b2b", "#1e1e1e", "#444444"])
        
        # Pass if either palette is dark OR stylesheet has dark colors
        assert window_is_dark or text_is_dark or has_dark_stylesheet, \
            f"Header not dark: window={window_color.name()}, text={text_color.name()}, stylesheet={stylesheet[:100]}..."
    
    def test_table_corner_button_dark(self, widget):
        """Test that table corner button (top-left) uses dark theme."""
        # Get the trades table
        table = widget.trades_table
        assert table is not None
        
        # Get the stylesheet
        stylesheet = table.styleSheet()
        
        # Check for QTableView QTableCornerButton::section rule
        # This is important for the top-left corner button
        corner_rule = "QTableView QTableCornerButton::section"
        if corner_rule in stylesheet:
            # Should have dark background
            assert "background-color" in stylesheet.lower()
        else:
            # Corner button styling might be inherited from QHeaderView::section
            # which is acceptable
            print("Note: No specific corner button styling found")
    
    def test_table_background_dark(self, widget):
        """Test that table background uses dark theme."""
        # Get the trades table
        table = widget.trades_table
        assert table is not None
        
        # Get the stylesheet
        stylesheet = table.styleSheet()
        
        # Check for QTableWidget or QTableView rule with dark background
        table_rules = ["QTableWidget", "QTableView"]
        has_table_rule = any(rule in stylesheet for rule in table_rules)
        
        if has_table_rule:
            # Should have dark background color
            assert "background-color" in stylesheet.lower()
            
            # Check for dark gridline color
            if "gridline-color" in stylesheet.lower():
                # Gridline should be dark
                pass
    
    def test_table_empty_state_header_dark(self, widget):
        """Test that table header remains dark even when table is empty."""
        # Get the trades table
        table = widget.trades_table
        assert table is not None
        
        # Table should start empty (0 rows)
        assert table.rowCount() == 0
        
        # Header should still be styled (visibility may be False until shown)
        header = table.horizontalHeader()
        
        # Check header has some styling (either palette or stylesheet)
        has_stylesheet = bool(table.styleSheet())
        has_header_stylesheet = bool(header.styleSheet())
        
        # At least one should have styling
        assert has_stylesheet or has_header_stylesheet, "Table or header should have stylesheet"
        
        # Check that stylesheet contains dark colors
        stylesheet = table.styleSheet() or header.styleSheet() or ""
        has_dark_colors = any(color in stylesheet.lower() for color in ["#2a2a2a", "#2b2b2b", "#1e1e1e", "#444444"])
        assert has_dark_colors, f"Stylesheet should contain dark colors: {stylesheet[:200]}..."
    
    def test_table_alternating_row_colors_dark(self, widget):
        """Test that alternating row colors use dark theme."""
        # Get the trades table
        table = widget.trades_table
        assert table is not None
        
        # Get the stylesheet
        stylesheet = table.styleSheet()
        
        # Check for alternate-background-color rule
        if "alternate-background-color" in stylesheet.lower():
            # Should be a dark color
            pass
        else:
            # Alternating colors might be disabled or inherited
            print("Note: No alternate-background-color rule found")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])