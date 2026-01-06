"""
Line Chart Widget using QPainter for simple time series visualization.

Provides a basic line chart widget without external dependencies.
"""

import logging
from typing import List, Tuple, Optional, Union, Dict, Any
from datetime import datetime
import math

from PySide6.QtCore import Qt, QRectF, QPointF, QSize, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy
from PySide6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont,
    QPainterPath, QLinearGradient, QFontMetrics
)

logger = logging.getLogger(__name__)


class LineChartWidget(QWidget):
    """
    Simple line chart widget using QPainter.
    
    Supports:
    - Single or multiple data series
    - Time series or numeric x-axis
    - Basic axes with labels
    - Grid lines
    - Hover tooltips (optional)
    """
    
    # Signals
    point_hovered = Signal(float, float, str)  # x, y, label
    
    def __init__(
        self,
        title: str = "Line Chart",
        x_label: str = "X",
        y_label: str = "Y",
        parent=None
    ):
        super().__init__(parent)
        self.title = title
        self.x_label = x_label
        self.y_label = y_label
        
        # Data storage
        self.series: List[Dict[str, Any]] = []
        self.x_min: Optional[float] = None
        self.x_max: Optional[float] = None
        self.y_min: Optional[float] = None
        self.y_max: Optional[float] = None
        
        # Display settings
        self.margin = 50
        self.grid_enabled = True
        self.legend_enabled = True
        self.show_points = True
        
        # Colors
        self.series_colors = [
            QColor("#3A8DFF"),  # Blue
            QColor("#4CAF50"),  # Green
            QColor("#FF9800"),  # Orange
            QColor("#9C27B0"),  # Purple
            QColor("#F44336"),  # Red
            QColor("#00BCD4"),  # Cyan
        ]
        
        self.setup_ui()
        self.setMinimumSize(400, 300)
    
    def setup_ui(self):
        """Initialize the UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        
        # Title
        self.title_label = QLabel(self.title)
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #E6E6E6;")
        layout.addWidget(self.title_label)
        
        # Chart area will be painted in paintEvent
    
    def add_series(
        self,
        data: List[Tuple[float, float]],
        name: str = "Series",
        color: Optional[QColor] = None
    ):
        """
        Add a data series to the chart.
        
        Args:
            data: List of (x, y) tuples
            name: Series name for legend
            color: Optional color for this series
        """
        if not data:
            return
        
        # Determine color
        if color is None:
            color_idx = len(self.series) % len(self.series_colors)
            color = self.series_colors[color_idx]
        
        # Create series entry
        series = {
            "name": name,
            "data": data,
            "color": color,
            "visible": True
        }
        
        self.series.append(series)
        
        # Update bounds
        self._update_bounds()
        
        # Trigger repaint
        self.update()
    
    def add_time_series(
        self,
        data: List[Tuple[Union[datetime, str], float]],
        name: str = "Series",
        color: Optional[QColor] = None
    ):
        """
        Add a time series to the chart.
        
        Args:
            data: List of (timestamp, value) tuples
            name: Series name for legend
            color: Optional color for this series
        """
        # Convert timestamps to numeric values (seconds since epoch)
        numeric_data = []
        for timestamp, value in data:
            if isinstance(timestamp, datetime):
                x = timestamp.timestamp()
            elif isinstance(timestamp, str):
                try:
                    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    x = dt.timestamp()
                except (ValueError, AttributeError):
                    x = len(numeric_data)  # Fallback to index
            else:
                x = len(numeric_data)  # Fallback to index
            
            numeric_data.append((x, value))
        
        self.add_series(numeric_data, name, color)
    
    def clear_series(self):
        """Remove all series from the chart."""
        self.series.clear()
        self.x_min = self.x_max = self.y_min = self.y_max = None
        self.update()
    
    def _update_bounds(self):
        """Update min/max bounds from all series."""
        self.x_min = self.x_max = self.y_min = self.y_max = None
        
        for series in self.series:
            if not series["visible"]:
                continue
            
            for x, y in series["data"]:
                if self.x_min is None or x < self.x_min:
                    self.x_min = x
                if self.x_max is None or x > self.x_max:
                    self.x_max = x
                if self.y_min is None or y < self.y_min:
                    self.y_min = y
                if self.y_max is None or y > self.y_max:
                    self.y_max = y
        
        # Add some padding
        if self.x_min is not None and self.x_max is not None:
            x_range = self.x_max - self.x_min
            if x_range == 0:
                x_range = 1
            self.x_min -= x_range * 0.05
            self.x_max += x_range * 0.05
        
        if self.y_min is not None and self.y_max is not None:
            y_range = self.y_max - self.y_min
            if y_range == 0:
                y_range = 1
            self.y_min -= y_range * 0.05
            self.y_max += y_range * 0.05
    
    def paintEvent(self, event):
        """Paint the chart."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Get drawing area
        width = self.width()
        height = self.height()
        
        if width <= 2 * self.margin or height <= 2 * self.margin:
            return
        
        chart_rect = QRectF(
            self.margin,
            self.margin,
            width - 2 * self.margin,
            height - 2 * self.margin
        )
        
        # Draw background
        painter.fillRect(self.rect(), QColor("#1E1E1E"))
        
        # Draw grid if enabled
        if self.grid_enabled:
            self._draw_grid(painter, chart_rect)
        
        # Draw axes
        self._draw_axes(painter, chart_rect)
        
        # Draw series if we have bounds
        if (self.x_min is not None and self.x_max is not None and
            self.y_min is not None and self.y_max is not None):
            
            for series in self.series:
                if series["visible"]:
                    self._draw_series(painter, chart_rect, series)
        
        # Draw legend if enabled
        if self.legend_enabled and self.series:
            self._draw_legend(painter, chart_rect)
    
    def _draw_grid(self, painter: QPainter, chart_rect: QRectF):
        """Draw grid lines."""
        pen = QPen(QColor("#444444"))
        pen.setWidth(1)
        pen.setStyle(Qt.DotLine)
        painter.setPen(pen)
        
        # Vertical grid lines
        for i in range(1, 5):
            x = chart_rect.left() + (chart_rect.width() * i / 5)
            painter.drawLine(int(x), int(chart_rect.top()), int(x), int(chart_rect.bottom()))
        
        # Horizontal grid lines
        for i in range(1, 5):
            y = chart_rect.top() + (chart_rect.height() * i / 5)
            painter.drawLine(int(chart_rect.left()), int(y), int(chart_rect.right()), int(y))
    
    def _draw_axes(self, painter: QPainter, chart_rect: QRectF):
        """Draw axes and labels."""
        pen = QPen(QColor("#E6E6E6"))
        pen.setWidth(2)
        painter.setPen(pen)
        
        # Draw axes lines
        painter.drawLine(
            int(chart_rect.left()), int(chart_rect.bottom()),
            int(chart_rect.right()), int(chart_rect.bottom())
        )
        painter.drawLine(
            int(chart_rect.left()), int(chart_rect.top()),
            int(chart_rect.left()), int(chart_rect.bottom())
        )
        
        # Draw axis labels
        painter.setFont(QFont("Arial", 9))
        painter.setPen(QColor("#9A9A9A"))
        
        # X-axis label
        if self.x_label:
            x_label_rect = QRectF(
                chart_rect.left(),
                chart_rect.bottom() + 10,
                chart_rect.width(),
                20
            )
            painter.drawText(x_label_rect, Qt.AlignCenter, self.x_label)
        
        # Y-axis label
        if self.y_label:
            # Rotate for vertical text
            painter.save()
            y_label_rect = QRectF(
                5,
                chart_rect.top() + chart_rect.height() / 2,
                20,
                chart_rect.height()
            )
            painter.translate(y_label_rect.center())
            painter.rotate(-90)
            painter.drawText(QRectF(-y_label_rect.height()/2, -y_label_rect.width()/2,
                                  y_label_rect.height(), y_label_rect.width()),
                           Qt.AlignCenter, self.y_label)
            painter.restore()
        
        # Draw tick labels if we have bounds
        if (self.x_min is not None and self.x_max is not None and
            self.y_min is not None and self.y_max is not None):
            
            # X-axis ticks
            for i in range(6):
                x = chart_rect.left() + (chart_rect.width() * i / 5)
                value = self.x_min + (self.x_max - self.x_min) * i / 5
                
                # Format value
                if isinstance(value, float):
                    label = f"{value:.2f}"
                else:
                    label = str(value)
                
                tick_rect = QRectF(x - 25, chart_rect.bottom() + 5, 50, 15)
                painter.drawText(tick_rect, Qt.AlignCenter, label)
            
            # Y-axis ticks
            for i in range(6):
                y = chart_rect.bottom() - (chart_rect.height() * i / 5)
                value = self.y_min + (self.y_max - self.y_min) * i / 5
                
                # Format value
                if isinstance(value, float):
                    label = f"{value:.2f}"
                else:
                    label = str(value)
                
                tick_rect = QRectF(chart_rect.left() - 45, y - 7, 40, 15)
                painter.drawText(tick_rect, Qt.AlignRight | Qt.AlignVCenter, label)
    
    def _draw_series(self, painter: QPainter, chart_rect: QRectF, series: Dict[str, Any]):
        """Draw a single data series."""
        data = series["data"]
        color = series["color"]
        
        if len(data) < 2:
            return
        
        # Create path for line
        path = QPainterPath()
        
        # Convert first point
        x1, y1 = data[0]
        chart_x1 = self._map_x_to_chart(x1, chart_rect)
        chart_y1 = self._map_y_to_chart(y1, chart_rect)
        path.moveTo(chart_x1, chart_y1)
        
        # Add line segments
        for x, y in data[1:]:
            chart_x = self._map_x_to_chart(x, chart_rect)
            chart_y = self._map_y_to_chart(y, chart_rect)
            path.lineTo(chart_x, chart_y)
        
        # Draw line
        pen = QPen(color)
        pen.setWidth(2)
        painter.setPen(pen)
        painter.drawPath(path)
        
        # Draw points if enabled
        if self.show_points:
            painter.setBrush(QBrush(color))
            for x, y in data:
                chart_x = self._map_x_to_chart(x, chart_rect)
                chart_y = self._map_y_to_chart(y, chart_rect)
                painter.drawEllipse(QPointF(chart_x, chart_y), 3, 3)
    
    def _draw_legend(self, painter: QPainter, chart_rect: QRectF):
        """Draw legend in top-right corner."""
        legend_x = chart_rect.right() - 150
        legend_y = chart_rect.top() + 10
        
        painter.setFont(QFont("Arial", 9))
        
        for i, series in enumerate(self.series):
            if not series["visible"]:
                continue
            
            color = series["color"]
            name = series["name"]
            
            # Draw color swatch
            swatch_rect = QRectF(legend_x, legend_y + i * 20, 12, 12)
            painter.fillRect(swatch_rect, color)
            painter.setPen(QColor("#E6E6E6"))
            painter.drawRect(swatch_rect)
            
            # Draw series name
            text_rect = QRectF(legend_x + 15, legend_y + i * 20, 135, 15)
            painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, name)
    
    def _map_x_to_chart(self, x: float, chart_rect: QRectF) -> float:
        """Map data x-coordinate to chart coordinate."""
        if self.x_min == self.x_max:
            return chart_rect.left() + chart_rect.width() / 2
        return chart_rect.left() + ((x - self.x_min) / (self.x_max - self.x_min)) * chart_rect.width()
    
    def _map_y_to_chart(self, y: float, chart_rect: QRectF) -> float:
        """Map data y-coordinate to chart coordinate."""
        if self.y_min == self.y_max:
            return chart_rect.top() + chart_rect.height() / 2
        return chart_rect.bottom() - ((y - self.y_min) / (self.y_max - self.y_min)) * chart_rect.height()
    
    def set_title(self, title: str):
        """Set chart title."""
        self.title = title
        self.title_label.setText(title)
        self.update()
    
    def set_axis_labels(self, x_label: str, y_label: str):
        """Set axis labels."""
        self.x_label = x_label
        self.y_label = y_label
        self.update()
    
    def set_grid_enabled(self, enabled: bool):
        """Enable or disable grid."""
        self.grid_enabled = enabled
        self.update()
    
    def set_legend_enabled(self, enabled: bool):
        """Enable or disable legend."""
        self.legend_enabled = enabled
        self.update()
    
    def set_show_points(self, show: bool):
        """Enable or disable point markers."""
        self.show_points = show
        self.update()