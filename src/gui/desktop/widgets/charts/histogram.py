"""
Histogram Widget using QPainter for distribution visualization.

Provides a basic histogram widget for displaying frequency distributions.
"""

import logging
from typing import List, Tuple, Optional, Dict, Any
import math

from PySide6.QtCore import Qt, QRectF, QSize, Signal  # type: ignore
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy  # type: ignore
from PySide6.QtGui import (  # type: ignore
    QPainter, QPen, QBrush, QColor, QFont,
    QFontMetrics, QLinearGradient
)

logger = logging.getLogger(__name__)


class HistogramWidget(QWidget):
    """
    Histogram widget for distribution visualization using QPainter.
    
    Supports:
    - Bin edges and counts
    - Custom bar colors
    - Axis labels and grid
    - Value labels on bars (optional)
    """
    
    # Signals
    bar_hovered = Signal(int, float, float, float)  # bin_index, bin_start, bin_end, count
    
    def __init__(
        self,
        title: str = "Histogram",
        x_label: str = "Value",
        y_label: str = "Frequency",
        parent=None
    ):
        super().__init__(parent)
        self.title = title
        self.x_label = x_label
        self.y_label = y_label
        
        # Data storage
        self.bin_edges: List[float] = list()
        self.bin_counts: List[float] = list()
        self.bin_labels: List[str] = list()
        
        # Display settings
        self.margin = 60
        self.bar_padding = 2
        self.show_values = True
        self.show_grid = True
        self.bar_color = QColor("#3A8DFF")
        self.hover_color = QColor("#FF9800")
        
        # Hover tracking
        self.hovered_bar: Optional[int] = None
        
        self.setup_ui()
        self.setMinimumSize(400, 300)
    
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
    
    def set_data(
        self,
        bin_edges: List[float],
        bin_counts: List[float],
        bin_labels: Optional[List[str]] = None
    ):
        """
        Set histogram data.
        
        Args:
            bin_edges: List of bin edges (length = n_bins + 1)
            bin_counts: List of counts for each bin (length = n_bins)
            bin_labels: Optional labels for each bin
        """
        if len(bin_edges) < 2 or len(bin_counts) != len(bin_edges) - 1:
            logger.error(f"Invalid histogram data: {len(bin_edges)} edges, {len(bin_counts)} counts")
            return
        
        self.bin_edges = bin_edges
        self.bin_counts = bin_counts
        
        # Generate bin labels if not provided
        if bin_labels is None:
            self.bin_labels = list()
            for i in range(len(bin_counts)):
                start = bin_edges[i]
                end = bin_edges[i + 1]
                self.bin_labels.append(f"{start:.2f}-{end:.2f}")
        else:
            self.bin_labels = bin_labels
        
        # Trigger repaint
        self.update()
    
    def set_uniform_bins(
        self,
        values: List[float],
        n_bins: int = 10,
        bin_range: Optional[Tuple[float, float]] = None
    ):
        """
        Create histogram from raw values with uniform bins.
        
        Args:
            values: List of raw values
            n_bins: Number of bins
            bin_range: Optional (min, max) range for bins
        """
        if not values:
            return
        
        # Determine range
        if bin_range is None:
            data_min = min(values)
            data_max = max(values)
        else:
            data_min, data_max = bin_range
        
        # Create bin edges
        bin_width = (data_max - data_min) / n_bins
        bin_edges = [data_min + i * bin_width for i in range(n_bins + 1)]
        
        # Count values in bins
        bin_counts = list((0,)) * n_bins
        for value in values:
            if data_min <= value <= data_max:
                bin_idx = min(int((value - data_min) / bin_width), n_bins - 1)
                bin_counts[bin_idx] += 1
        
        self.set_data(bin_edges, bin_counts)
    
    def clear_data(self):
        """Clear all data from the histogram."""
        self.bin_edges = list()
        self.bin_counts = list()
        self.bin_labels = list()
        self.hovered_bar = None
        self.update()
    
    def paintEvent(self, event):
        """Paint the histogram."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Get drawing area
        width = self.width()
        height = self.height()
        
        if width <= 2 * self.margin or height <= 2 * self.margin:
            return
        
        # Draw background
        painter.fillRect(self.rect(), QColor("#1E1E1E"))
        
        n_bins = len(self.bin_counts)
        
        if n_bins == 0:
            # Draw placeholder
            painter.setPen(QColor("#9A9A9A"))
            painter.setFont(QFont("Arial", 12))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No data available")
            return
        
        available_width = width - 2 * self.margin
        available_height = height - 2 * self.margin
        
        bar_width = (available_width - (n_bins - 1) * self.bar_padding) / n_bins
        
        # Find max count for scaling
        max_count = max(self.bin_counts) if self.bin_counts else 1
        
        # Draw grid if enabled
        if self.show_grid:
            self._draw_grid(painter, available_width, available_height, max_count)
        
        # Draw axes
        self._draw_axes(painter, available_width, available_height)
        
        # Draw bars
        for i in range(n_bins):
            count = self.bin_counts[i]
            
            # Calculate bar position and height
            x = self.margin + i * (bar_width + self.bar_padding)
            bar_height = (count / max_count) * available_height if max_count > 0 else 0
            y = self.margin + available_height - bar_height
            
            # Choose color
            if self.hovered_bar == i:
                color = self.hover_color
            else:
                color = self.bar_color
            
            # Draw bar
            bar_rect = QRectF(x, y, bar_width, bar_height)
            painter.setPen(QPen(QColor("#444444"), 1))
            painter.setBrush(QBrush(color))
            painter.drawRect(bar_rect)
            
            # Draw value label if enabled
            if self.show_values and bar_width > 30 and bar_height > 20:
                self._draw_bar_value(painter, bar_rect, count)
        
        # Draw bin labels
        self._draw_bin_labels(painter, n_bins, bar_width, available_height)
        
        # Draw axis labels
        self._draw_axis_labels(painter, available_width, available_height)
    
    def _draw_grid(self, painter: QPainter, available_width: float, available_height: float, max_count: float):
        """Draw grid lines."""
        pen = QPen(QColor("#444444"))
        pen.setWidth(1)
        pen.setStyle(Qt.DotLine)
        painter.setPen(pen)
        
        # Horizontal grid lines (frequency)
        for i in range(1, 5):
            y = self.margin + (available_height * i / 5)
            painter.drawLine(
                int(self.margin), int(y),
                int(self.margin + available_width), int(y)
            )
    
    def _draw_axes(self, painter: QPainter, available_width: float, available_height: float):
        """Draw axes lines."""
        pen = QPen(QColor("#E6E6E6"))
        pen.setWidth(2)
        painter.setPen(pen)
        
        # X-axis
        painter.drawLine(
            int(self.margin), int(self.margin + available_height),
            int(self.margin + available_width), int(self.margin + available_height)
        )
        
        # Y-axis
        painter.drawLine(
            int(self.margin), int(self.margin),
            int(self.margin), int(self.margin + available_height)
        )
    
    def _draw_bar_value(self, painter: QPainter, bar_rect: QRectF, count: float):
        """Draw value label on bar."""
        painter.save()
        
        # Format count
        if count.is_integer():
            label = f"{int(count)}"
        else:
            label = f"{count:.1f}"
        
        # Draw text (white for visibility)
        painter.setPen(QColor("#FFFFFF"))
        painter.setFont(QFont("Arial", 9))
        
        # Position text at top of bar
        text_rect = QRectF(
            bar_rect.left(),
            bar_rect.top() - 20,
            bar_rect.width(),
            15
        )
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, label)
        
        painter.restore()
    
    def _draw_bin_labels(self, painter: QPainter, n_bins: int, bar_width: float, available_height: float):
        """Draw bin labels on x-axis."""
        painter.setPen(QColor("#9A9A9A"))
        painter.setFont(QFont("Arial", 9))
        
        for i in range(n_bins):
            if i < len(self.bin_labels):
                label = self.bin_labels[i]
                
                # Truncate if too long
                if len(label) > 10:
                    label = label[:7] + "..."
                
                x = self.margin + i * (bar_width + self.bar_padding) + bar_width / 2
                y = self.margin + available_height + 15
                
                label_rect = QRectF(x - 40, y, 80, 20)
                painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, label)
    
    def _draw_axis_labels(self, painter: QPainter, available_width: float, available_height: float):
        """Draw axis labels."""
        painter.setPen(QColor("#9A9A9A"))
        painter.setFont(QFont("Arial", 10))
        
        # X-axis label
        if self.x_label:
            x_label_rect = QRectF(
                self.margin,
                self.margin + available_height + 35,
                available_width,
                20
            )
            painter.drawText(x_label_rect, Qt.AlignmentFlag.AlignCenter, self.x_label)
        
        # Y-axis label
        if self.y_label:
            # Rotate for vertical text
            painter.save()
            y_label_rect = QRectF(
                5,
                self.margin + available_height / 2 - 100,
                20,
                200
            )
            painter.translate(y_label_rect.center())
            painter.rotate(-90)
            painter.drawText(QRectF(-100, -10, 200, 20), Qt.AlignmentFlag.AlignCenter, self.y_label)
            painter.restore()
    
    def mouseMoveEvent(self, event):
        """Handle mouse move for bar highlighting and tooltips."""
        if not self.bin_counts:
            return
        
        n_bins = len(self.bin_counts)
        
        # Calculate bar size
        width = self.width()
        available_width = width - 2 * self.margin
        bar_width = (available_width - (n_bins - 1) * self.bar_padding) / n_bins
        
        # Find hovered bar
        x = event.position().x()
        bar_idx = int((x - self.margin) / (bar_width + self.bar_padding))
        
        if 0 <= bar_idx < n_bins:
            self.hovered_bar = bar_idx
            
            # Get bar data
            count = self.bin_counts[bar_idx]
            bin_start = self.bin_edges[bar_idx]
            bin_end = self.bin_edges[bar_idx + 1]
            
            # Calculate percentage if total count is available
            total_count = sum(self.bin_counts)
            percentage = (count / total_count * 100) if total_count > 0 else 0
            
            # Show tooltip
            tooltip_text = f"Bin: [{bin_start:.3f}, {bin_end:.3f})\nCount: {count}\nPercentage: {percentage:.1f}%"
            from PySide6.QtWidgets import QToolTip  # type: ignore
            QToolTip.showText(event.globalPosition().toPoint(), tooltip_text, self)
            
            # Emit signal
            self.bar_hovered.emit(bar_idx, bin_start, bin_end, count)
        else:
            self.hovered_bar = None
            from PySide6.QtWidgets import QToolTip  # type: ignore
            QToolTip.hideText()
        
        self.update()
    
    def set_title(self, title: str):
        """Set histogram title."""
        self.title = title
        self.title_label.setText(title)
        self.update()
    
    def set_axis_labels(self, x_label: str, y_label: str):
        """Set axis labels."""
        self.x_label = x_label
        self.y_label = y_label
        self.update()
    
    def set_bar_color(self, color: QColor):
        """Set bar color."""
        self.bar_color = color
        self.update()
    
    def set_show_values(self, show: bool):
        """Enable or disable value labels on bars."""
        self.show_values = show
        self.update()
    
    def set_show_grid(self, show: bool):
        """Enable or disable grid lines."""
        self.show_grid = show
        self.update()
    
    def leaveEvent(self, event):
        """Hide tooltip when mouse leaves widget."""
        from PySide6.QtWidgets import QToolTip  # type: ignore
        QToolTip.hideText()
        self.hovered_bar = None
        self.update()
    
    def get_statistics(self) -> Dict[str, float]:
        """Calculate basic statistics from histogram data."""
        if not self.bin_counts or not self.bin_edges:
            return {}
        
        # Calculate weighted mean
        total_count = sum(self.bin_counts)
        if total_count == 0:
            return {}
        
        weighted_sum = 0
        for i, count in enumerate(self.bin_counts):
            bin_center = (self.bin_edges[i] + self.bin_edges[i + 1]) / 2
            weighted_sum += bin_center * count
        
        mean = weighted_sum / total_count
        
        # Calculate variance
        variance_sum = 0
        for i, count in enumerate(self.bin_counts):
            bin_center = (self.bin_edges[i] + self.bin_edges[i + 1]) / 2
            variance_sum += count * (bin_center - mean) ** 2
        
        variance = variance_sum / total_count
        std_dev = math.sqrt(variance)
        
        # Find mode (bin with highest count)
        mode_idx = max(range(len(self.bin_counts)), key=lambda i: self.bin_counts[i])
        mode = (self.bin_edges[mode_idx] + self.bin_edges[mode_idx + 1]) / 2
        
        return {
            "mean": mean,
            "std_dev": std_dev,
            "mode": mode,
            "total_count": total_count,
            "max_count": max(self.bin_counts),
            "n_bins": len(self.bin_counts)
        }