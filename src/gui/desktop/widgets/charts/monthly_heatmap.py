"""
Monthly Return Heatmap Widget using QPainter.

Displays a calendar-style heatmap of monthly returns with hover tooltips.
"""

import logging
from typing import List, Tuple, Optional, Dict, Any
from datetime import datetime
import math

from PySide6.QtCore import Qt, QRectF, QSize, Signal  # type: ignore
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy, QToolTip  # type: ignore
from PySide6.QtGui import (  # type: ignore
    QPainter, QPen, QBrush, QColor, QFont,
    QFontMetrics, QLinearGradient
)

logger = logging.getLogger(__name__)


class MonthlyHeatmapWidget(QWidget):
    """
    Monthly heatmap widget for calendar-style return visualization.
    
    Displays:
    - Rows: Years (sorted descending)
    - Columns: Jan..Dec
    - Cells: Monthly return values with color coding
    - Tooltips: YYYY-MMM: value on hover
    """
    
    # Signals
    cell_hovered = Signal(str, str, float)  # year, month, value
    
    def __init__(
        self,
        title: str = "Monthly Returns Heatmap",
        parent=None
    ):
        super().__init__(parent)
        self.title = title
        
        # Data storage
        self.monthly_data: Dict[str, Dict[str, float]] = {}  # year -> month -> value
        self.years: List[str] = list()
        self.months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", 
                      "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        
        # Display settings
        self.margin = 60
        self.cell_size = 40
        self.cell_padding = 2
        self.show_values = True
        self.show_grid = True
        
        # Color settings
        self.positive_color = QColor("#4CAF50")  # Green
        self.negative_color = QColor("#F44336")  # Red
        self.neutral_color = QColor("#757575")   # Gray
        self.missing_color = QColor("#424242")   # Dark gray
        
        # Hover tracking
        self.hovered_cell: Optional[Tuple[int, int]] = None  # (row, col)
        
        self.setup_ui()
        self.setMinimumSize(600, 400)
    
    def setup_ui(self):
        """Initialize the UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        
        # Title
        self.title_label = QLabel(self.title)
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #E6E6E6;")
        layout.addWidget(self.title_label)
        
        # Chart area will be painted in paintEvent
    
    def set_data(self, monthly_data: Dict[str, Dict[str, float]]):
        """
        Set monthly return data.
        
        Args:
            monthly_data: Dict with year as key, dict of month->value as value
                Example: {"2024": {"Jan": 0.05, "Feb": -0.02, ...}, ...}
        """
        self.monthly_data = monthly_data
        
        # Extract and sort years (descending)
        self.years = sorted(monthly_data.keys(), reverse=True)
        
        # Trigger repaint
        self.update()
    
    def set_data_from_list(self, data_list: List[Dict[str, Any]]):
        """
        Set monthly data from a list of dicts with year, month, value.
        
        Args:
            data_list: List of dicts with keys: year, month, value
                Example: [{"year": "2024", "month": "Jan", "value": 0.05}, ...]
        """
        monthly_data = {}
        
        for item in data_list:
            year = str(item.get("year", ""))
            month = item.get("month", "")
            value = item.get("value", 0.0)
            
            if year not in monthly_data:
                monthly_data[year] = {}
            
            # Convert month name to standard format
            month_name = self._normalize_month(month)
            if month_name:
                monthly_data[year][month_name] = value
        
        self.set_data(monthly_data)
    
    def _normalize_month(self, month: str) -> Optional[str]:
        """Normalize month name to standard 3-letter abbreviation."""
        month_lower = month.lower()
        month_map = {
            "jan": "Jan", "january": "Jan",
            "feb": "Feb", "february": "Feb",
            "mar": "Mar", "march": "Mar",
            "apr": "Apr", "april": "Apr",
            "may": "May",
            "jun": "Jun", "june": "Jun",
            "jul": "Jul", "july": "Jul",
            "aug": "Aug", "august": "Aug",
            "sep": "Sep", "september": "Sep",
            "oct": "Oct", "october": "Oct",
            "nov": "Nov", "november": "Nov",
            "dec": "Dec", "december": "Dec"
        }
        
        for key, value in month_map.items():
            if month_lower.startswith(key):
                return value
        
        # Try to parse numeric month
        try:
            month_num = int(month)
            if 1 <= month_num <= 12:
                return self.months[month_num - 1]
        except (ValueError, TypeError):
            pass
        
        return None
    
    def clear_data(self):
        """Clear all data from the heatmap."""
        self.monthly_data = {}
        self.years = list()
        self.hovered_cell = None
        self.update()
    
    def paintEvent(self, event):
        """Paint the monthly heatmap."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Get drawing area
        width = self.width()
        height = self.height()
        
        if width <= 2 * self.margin or height <= 2 * self.margin:
            return
        
        # Draw background
        painter.fillRect(self.rect(), QColor("#1E1E1E"))
        
        n_years = len(self.years)
        n_months = len(self.months)
        
        if n_years == 0 or n_months == 0:
            # Draw placeholder
            painter.setPen(QColor("#9A9A9A"))
            painter.setFont(QFont("Arial", 12))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No monthly data available")
            return
        
        # Calculate cell size based on available space
        available_width = width - 2 * self.margin
        available_height = height - 2 * self.margin
        
        cell_width = min(self.cell_size, (available_width - 100) / n_months)
        cell_height = min(self.cell_size, (available_height - 50) / n_years)
        
        # Adjust cell size to fit available space
        cell_width = max(20, cell_width)
        cell_height = max(20, cell_height)
        
        # Draw month headers (top)
        painter.setPen(QColor("#E6E6E6"))
        painter.setFont(QFont("Arial", 10, QFont.Bold))
        
        for j, month in enumerate(self.months):
            x = self.margin + 80 + j * (cell_width + self.cell_padding)
            y = self.margin - 10
            
            month_rect = QRectF(x, y, cell_width, 20)
            painter.drawText(month_rect, Qt.AlignmentFlag.AlignCenter, month)
        
        # Draw year labels (left)
        painter.setFont(QFont("Arial", 10))
        
        for i, year in enumerate(self.years):
            x = self.margin + 10
            y = self.margin + i * (cell_height + self.cell_padding) + cell_height / 2
            
            year_rect = QRectF(x, y - 10, 60, 20)
            painter.drawText(year_rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, year)
        
        # Draw heatmap cells
        for i, year in enumerate(self.years):
            year_data = self.monthly_data.get(year, {})
            
            for j, month in enumerate(self.months):
                value = year_data.get(month)
                
                # Calculate cell position
                x = self.margin + 80 + j * (cell_width + self.cell_padding)
                y = self.margin + i * (cell_height + self.cell_padding)
                
                # Determine cell color
                color = self._value_to_color(value)
                
                # Draw cell
                cell_rect = QRectF(x, y, cell_width, cell_height)
                
                # Highlight hovered cell
                if self.hovered_cell == (i, j):
                    painter.setPen(QPen(QColor("#FFFFFF"), 2))
                else:
                    painter.setPen(QPen(QColor("#444444"), 1))
                
                painter.setBrush(QBrush(color))
                painter.drawRect(cell_rect)
                
                # Draw value if enabled and cell is large enough
                if self.show_values and value is not None and cell_width > 25 and cell_height > 20:
                    self._draw_cell_value(painter, cell_rect, value)
        
        # Draw grid if enabled
        if self.show_grid:
            self._draw_grid(painter, n_years, n_months, cell_width, cell_height)
        
        # Draw legend
        self._draw_legend(painter, width, height)
    
    def _value_to_color(self, value: Optional[float]) -> QColor:
        """Convert value to color."""
        if value is None:
            return self.missing_color
        
        # Determine color based on value
        if value > 0:
            # Positive: green gradient (darker for higher values)
            intensity = min(1.0, value / 0.2)  # Cap at 20% for color scaling
            r = int(self.positive_color.red() * (0.7 + 0.3 * intensity))
            g = int(self.positive_color.green() * (0.7 + 0.3 * intensity))
            b = int(self.positive_color.blue() * (0.7 + 0.3 * intensity))
            return QColor(r, g, b)
        elif value < 0:
            # Negative: red gradient (darker for more negative values)
            intensity = min(1.0, abs(value) / 0.2)  # Cap at 20% for color scaling
            r = int(self.negative_color.red() * (0.7 + 0.3 * intensity))
            g = int(self.negative_color.green() * (0.7 + 0.3 * intensity))
            b = int(self.negative_color.blue() * (0.7 + 0.3 * intensity))
            return QColor(r, g, b)
        else:
            # Zero: neutral
            return self.neutral_color
    
    def _draw_cell_value(self, painter: QPainter, cell_rect: QRectF, value: float):
        """Draw value label in cell."""
        painter.save()
        
        # Format value as percentage
        label = f"{value:+.1%}" if abs(value) >= 0.001 else "0.0%"
        
        # Choose text color based on cell brightness
        cell_color = self._value_to_color(value)
        brightness = (0.299 * cell_color.red() + 0.587 * cell_color.green() + 0.114 * cell_color.blue()) / 255
        text_color = QColor("#000000") if brightness > 0.5 else QColor("#FFFFFF")
        
        # Draw text
        painter.setPen(text_color)
        painter.setFont(QFont("Arial", 8))
        painter.drawText(cell_rect, Qt.AlignmentFlag.AlignCenter, label)
        
        painter.restore()
    
    def _draw_grid(self, painter: QPainter, n_years: int, n_months: int, cell_width: float, cell_height: float):
        """Draw grid lines between cells."""
        painter.setPen(QPen(QColor("#666666"), 1))
        
        # Vertical lines
        for j in range(n_months + 1):
            x = self.margin + 80 + j * (cell_width + self.cell_padding)
            painter.drawLine(
                int(x), int(self.margin),
                int(x), int(self.margin + n_years * (cell_height + self.cell_padding))
            )
        
        # Horizontal lines
        for i in range(n_years + 1):
            y = self.margin + i * (cell_height + self.cell_padding)
            painter.drawLine(
                int(self.margin + 80), int(y),
                int(self.margin + 80 + n_months * (cell_width + self.cell_padding)), int(y)
            )
    
    def _draw_legend(self, painter: QPainter, width: int, height: int):
        """Draw color legend."""
        legend_width = 200
        legend_height = 20
        legend_x = width - legend_width - 20
        legend_y = height - 40
        
        # Draw gradient bar
        gradient_rect = QRectF(legend_x, legend_y, legend_width, legend_height)
        
        # Create gradient from red to green
        qgradient = QLinearGradient(gradient_rect.left(), gradient_rect.center().y(),
                                   gradient_rect.right(), gradient_rect.center().y())
        qgradient.setColorAt(0.0, self.negative_color)
        qgradient.setColorAt(0.5, self.neutral_color)
        qgradient.setColorAt(1.0, self.positive_color)
        
        painter.fillRect(gradient_rect, qgradient)
        painter.setPen(QPen(QColor("#E6E6E6"), 1))
        painter.drawRect(gradient_rect)
        
        # Draw labels
        painter.setFont(QFont("Arial", 8))
        painter.setPen(QColor("#9A9A9A"))
        
        neg_rect = QRectF(legend_x - 30, legend_y, 30, legend_height)
        zero_rect = QRectF(legend_x + legend_width / 2 - 15, legend_y + legend_height + 2, 30, 15)
        pos_rect = QRectF(legend_x + legend_width, legend_y, 30, legend_height)
        
        painter.drawText(neg_rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, "-20%")
        painter.drawText(zero_rect, Qt.AlignmentFlag.AlignCenter, "0%")
        painter.drawText(pos_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "+20%")
    
    def mouseMoveEvent(self, event):
        """Handle mouse move for cell highlighting and tooltips."""
        if not self.years or not self.months:
            return
        
        n_years = len(self.years)
        n_months = len(self.months)
        
        # Calculate cell size
        width = self.width()
        available_width = width - 2 * self.margin
        
        cell_width = min(self.cell_size, (available_width - 100) / n_months)
        cell_height = min(self.cell_size, (available_width - 100) / n_months)
        cell_width = max(20, cell_width)
        cell_height = max(20, cell_height)
        
        # Find hovered cell
        x = event.position().x()
        y = event.position().y()
        
        col = int((x - self.margin - 80) / (cell_width + self.cell_padding))
        row = int((y - self.margin) / (cell_height + self.cell_padding))
        
        if 0 <= row < n_years and 0 <= col < n_months:
            self.hovered_cell = (row, col)
            
            # Get cell data
            year = self.years[row]
            month = self.months[col]
            year_data = self.monthly_data.get(year, {})
            value = year_data.get(month)
            
            # Show tooltip
            if value is not None:
                tooltip_text = f"{year}-{month}: {value:+.2%}"
                QToolTip.showText(event.globalPosition().toPoint(), tooltip_text, self)
            
            # Emit signal
            self.cell_hovered.emit(year, month, value if value is not None else 0.0)
        else:
            self.hovered_cell = None
            QToolTip.hideText()
        
        self.update()
    
    def leaveEvent(self, event):
        """Hide tooltip when mouse leaves widget."""
        QToolTip.hideText()
        self.hovered_cell = None
        self.update()
    
    def set_title(self, title: str):
        """Set heatmap title."""
        self.title = title
        self.title_label.setText(title)
        self.update()
    
    def set_show_values(self, show: bool):
        """Enable or disable value labels in cells."""
        self.show_values = show
        self.update()
    
    def set_show_grid(self, show: bool):
        """Enable or disable grid lines."""
        self.show_grid = show
        self.update()
    
    def set_colors(self, positive: QColor, negative: QColor, neutral: QColor, missing: QColor):
        """Set custom colors for the heatmap."""
        self.positive_color = positive
        self.negative_color = negative
        self.neutral_color = neutral
        self.missing_color = missing
        self.update()