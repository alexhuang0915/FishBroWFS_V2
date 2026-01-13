"""
Heatmap Widget using QPainter for matrix visualization.

Provides a basic heatmap widget for correlation matrices and similar data.
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


class HeatmapWidget(QWidget):
    """
    Heatmap widget for matrix visualization using QPainter.
    
    Supports:
    - Matrix data with row/column labels
    - Color gradient for values
    - Cell highlighting
    - Value labels in cells (optional)
    """
    
    # Signals
    cell_hovered = Signal(int, int, float, str, str)  # row, col, value, row_label, col_label
    cell_clicked = Signal(int, int, float, str, str)  # row, col, value, row_label, col_label
    
    def __init__(
        self,
        title: str = "Heatmap",
        parent=None
    ):
        super().__init__(parent)
        self.title = title
        
        # Data storage
        self.matrix: List[List[float]] = list()
        self.row_labels: List[str] = list()
        self.col_labels: List[str] = list()
        self.value_min: float = 0.0
        self.value_max: float = 1.0
        
        # Display settings
        self.margin = 60
        self.cell_padding = 2
        self.show_values = True
        self.show_grid = True
        
        # Color gradient
        self.gradient = self._create_default_gradient()
        
        # Hover tracking
        self.hovered_cell: Optional[Tuple[int, int]] = None
        
        self.setup_ui()
        self.setMinimumSize(400, 400)
    
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
    
    def _create_default_gradient(self) -> List[Tuple[float, QColor]]:
        """Create default blue-white-red gradient."""
        return [
            (0.0, QColor("#1E88E5")),   # Blue (low)
            (0.5, QColor("#FFFFFF")),   # White (middle)
            (1.0, QColor("#D32F2F"))    # Red (high)
        ]
    
    def set_data(
        self,
        matrix: List[List[float]],
        row_labels: Optional[List[str]] = None,
        col_labels: Optional[List[str]] = None
    ):
        """
        Set heatmap data.
        
        Args:
            matrix: 2D list of float values
            row_labels: Optional labels for rows
            col_labels: Optional labels for columns
        """
        if not matrix:
            return
        
        self.matrix = matrix
        
        # Set labels or generate defaults
        n_rows = len(matrix)
        n_cols = len(matrix[0]) if matrix else 0
        
        if row_labels is None:
            self.row_labels = [f"Row {i+1}" for i in range(n_rows)]
        else:
            self.row_labels = row_labels
        
        if col_labels is None:
            self.col_labels = [f"Col {j+1}" for j in range(n_cols)]
        else:
            self.col_labels = col_labels
        
        # Calculate value range
        self._calculate_value_range()
        
        # Trigger repaint
        self.update()
    
    def set_correlation_matrix(
        self,
        matrix: List[List[float]],
        labels: List[str]
    ):
        """
        Set correlation matrix data (square matrix with same row/col labels).
        
        Args:
            matrix: Square correlation matrix
            labels: Labels for both rows and columns
        """
        self.set_data(matrix, labels, labels)
    
    def _calculate_value_range(self):
        """Calculate min/max values from matrix."""
        if not self.matrix:
            self.value_min = 0.0
            self.value_max = 1.0
            return
        
        # Find min and max
        all_values = [val for row in self.matrix for val in row]
        if not all_values:
            self.value_min = 0.0
            self.value_max = 1.0
            return
        
        self.value_min = min(all_values)
        self.value_max = max(all_values)
        
        # Ensure range is not zero
        if self.value_max - self.value_min < 1e-10:
            self.value_max = self.value_min + 1.0
    
    def clear_data(self):
        """Clear all data from the heatmap."""
        self.matrix = list()
        self.row_labels = list()
        self.col_labels = list()
        self.hovered_cell = None
        self.update()
    
    def paintEvent(self, event):
        """Paint the heatmap."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Get drawing area
        width = self.width()
        height = self.height()
        
        if width <= 2 * self.margin or height <= 2 * self.margin:
            return
        
        # Draw background
        painter.fillRect(self.rect(), QColor("#1E1E1E"))
        
        # Calculate cell size
        n_rows = len(self.matrix)
        n_cols = len(self.matrix[0]) if self.matrix else 0
        
        if n_rows == 0 or n_cols == 0:
            # Draw placeholder
            painter.setPen(QColor("#9A9A9A"))
            painter.setFont(QFont("Arial", 12))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No data available")
            return
        
        available_width = width - 2 * self.margin
        available_height = height - 2 * self.margin
        
        cell_width = (available_width - (n_cols - 1) * self.cell_padding) / n_cols
        cell_height = (available_height - (n_rows - 1) * self.cell_padding) / n_rows
        
        # Draw heatmap cells
        for i in range(n_rows):
            for j in range(n_cols):
                value = self.matrix[i][j]
                
                # Calculate cell position
                x = self.margin + j * (cell_width + self.cell_padding)
                y = self.margin + i * (cell_height + self.cell_padding)
                
                # Calculate color
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
                
                # Draw value label if enabled
                if self.show_values and cell_width > 20 and cell_height > 20:
                    self._draw_cell_value(painter, cell_rect, value)
        
        # Draw grid if enabled
        if self.show_grid:
            self._draw_grid(painter, n_rows, n_cols, cell_width, cell_height)
        
        # Draw labels
        self._draw_labels(painter, n_rows, n_cols, cell_width, cell_height)
        
        # Draw color legend
        self._draw_legend(painter, width, height)
    
    def _value_to_color(self, value: float) -> QColor:
        """Convert value to color using gradient."""
        # Normalize value to [0, 1]
        t = (value - self.value_min) / (self.value_max - self.value_min)
        t = max(0.0, min(1.0, t))
        
        # Find gradient segment
        for k in range(len(self.gradient) - 1):
            t1, color1 = self.gradient[k]
            t2, color2 = self.gradient[k + 1]
            
            if t1 <= t <= t2:
                # Interpolate between colors
                segment_t = (t - t1) / (t2 - t1)
                r = int(color1.red() + (color2.red() - color1.red()) * segment_t)
                g = int(color1.green() + (color2.green() - color1.green()) * segment_t)
                b = int(color1.blue() + (color2.blue() - color1.blue()) * segment_t)
                return QColor(r, g, b)
        
        # Fallback
        return QColor("#FFFFFF")
    
    def _draw_cell_value(self, painter: QPainter, cell_rect: QRectF, value: float):
        """Draw value label in cell."""
        painter.save()
        
        # Format value
        if abs(value) < 0.01:
            label = f"{value:.3f}"
        elif abs(value) < 0.1:
            label = f"{value:.3f}"
        elif abs(value) < 1.0:
            label = f"{value:.2f}"
        else:
            label = f"{value:.1f}"
        
        # Choose text color based on cell brightness
        cell_color = self._value_to_color(value)
        brightness = (0.299 * cell_color.red() + 0.587 * cell_color.green() + 0.114 * cell_color.blue()) / 255
        text_color = QColor("#000000") if brightness > 0.5 else QColor("#FFFFFF")
        
        # Draw text
        painter.setPen(text_color)
        painter.setFont(QFont("Arial", 8))
        painter.drawText(cell_rect, Qt.AlignmentFlag.AlignCenter, label)
        
        painter.restore()
    
    def _draw_grid(self, painter: QPainter, n_rows: int, n_cols: int, cell_width: float, cell_height: float):
        """Draw grid lines between cells."""
        painter.setPen(QPen(QColor("#666666"), 1))
        
        # Vertical lines
        for j in range(n_cols + 1):
            x = self.margin + j * (cell_width + self.cell_padding)
            painter.drawLine(
                int(x), int(self.margin),
                int(x), int(self.margin + n_rows * (cell_height + self.cell_padding))
            )
        
        # Horizontal lines
        for i in range(n_rows + 1):
            y = self.margin + i * (cell_height + self.cell_padding)
            painter.drawLine(
                int(self.margin), int(y),
                int(self.margin + n_cols * (cell_width + self.cell_padding)), int(y)
            )
    
    def _draw_labels(self, painter: QPainter, n_rows: int, n_cols: int, cell_width: float, cell_height: float):
        """Draw row and column labels."""
        painter.setPen(QColor("#E6E6E6"))
        painter.setFont(QFont("Arial", 9))
        
        # Row labels (left side)
        for i in range(n_rows):
            if i < len(self.row_labels):
                label = self.row_labels[i]
                y = self.margin + i * (cell_height + self.cell_padding) + cell_height / 2
                
                # Truncate label if too long
                if len(label) > 15:
                    label = label[:12] + "..."
                
                label_rect = QRectF(
                    5,
                    y - 10,
                    self.margin - 10,
                    20
                )
                painter.drawText(label_rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, label)
        
        # Column labels (top side)
        for j in range(n_cols):
            if j < len(self.col_labels):
                label = self.col_labels[j]
                x = self.margin + j * (cell_width + self.cell_padding) + cell_width / 2
                
                # Truncate label if too long
                if len(label) > 15:
                    label = label[:12] + "..."
                
                label_rect = QRectF(
                    x - 50,
                    self.margin - 25,
                    100,
                    20
                )
                painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, label)
    
    def _draw_legend(self, painter: QPainter, width: int, height: int):
        """Draw color gradient legend."""
        legend_width = 200
        legend_height = 20
        legend_x = width - legend_width - 20
        legend_y = height - 40
        
        # Draw gradient bar
        gradient_rect = QRectF(legend_x, legend_y, legend_width, legend_height)
        
        # Create gradient
        qgradient = QLinearGradient(gradient_rect.left(), gradient_rect.center().y(),
                                   gradient_rect.right(), gradient_rect.center().y())
        
        for t, color in self.gradient:
            qgradient.setColorAt(t, color)
        
        painter.fillRect(gradient_rect, qgradient)
        painter.setPen(QPen(QColor("#E6E6E6"), 1))
        painter.drawRect(gradient_rect)
        
        # Draw min/max labels
        painter.setFont(QFont("Arial", 8))
        painter.setPen(QColor("#9A9A9A"))
        
        min_label = f"{self.value_min:.2f}"
        max_label = f"{self.value_max:.2f}"
        
        min_rect = QRectF(legend_x - 30, legend_y, 30, legend_height)
        max_rect = QRectF(legend_x + legend_width, legend_y, 30, legend_height)
        
        painter.drawText(min_rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, min_label)
        painter.drawText(max_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, max_label)
    
    def mouseMoveEvent(self, event):
        """Handle mouse move for cell highlighting."""
        if not self.matrix:
            return
        
        n_rows = len(self.matrix)
        n_cols = len(self.matrix[0]) if self.matrix else 0
        
        if n_rows == 0 or n_cols == 0:
            return
        
        # Calculate cell size
        width = self.width()
        height = self.height()
        available_width = width - 2 * self.margin
        available_height = height - 2 * self.margin
        
        cell_width = (available_width - (n_cols - 1) * self.cell_padding) / n_cols
        cell_height = (available_height - (n_rows - 1) * self.cell_padding) / n_rows
        
        # Find hovered cell
        x = event.position().x()
        y = event.position().y()
        
        col = int((x - self.margin) / (cell_width + self.cell_padding))
        row = int((y - self.margin) / (cell_height + self.cell_padding))
        
        if 0 <= row < n_rows and 0 <= col < n_cols:
            self.hovered_cell = (row, col)
            
            # Emit signal
            value = self.matrix[row][col]
            row_label = self.row_labels[row] if row < len(self.row_labels) else ""
            col_label = self.col_labels[col] if col < len(self.col_labels) else ""
            self.cell_hovered.emit(row, col, value, row_label, col_label)
        else:
            self.hovered_cell = None
        
        self.update()
    
    def mousePressEvent(self, event):
        """Handle mouse click for cell selection."""
        if not self.matrix or self.hovered_cell is None:
            return
        
        row, col = self.hovered_cell
        value = self.matrix[row][col]
        row_label = self.row_labels[row] if row < len(self.row_labels) else ""
        col_label = self.col_labels[col] if col < len(self.col_labels) else ""
        
        self.cell_clicked.emit(row, col, value, row_label, col_label)
    
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
    
    def set_gradient(self, gradient: List[Tuple[float, QColor]]):
        """
        Set custom color gradient.
        
        Args:
            gradient: List of (position [0-1], color) tuples
        """
        self.gradient = gradient
        self.update()