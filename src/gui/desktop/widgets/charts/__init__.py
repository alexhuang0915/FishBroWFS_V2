"""
Chart Widgets for Professional CTA Desktop UI.

This package provides charting components using QPainter (no external dependencies).
"""

from .line_chart import LineChartWidget
from .heatmap import HeatmapWidget
from .histogram import HistogramWidget

__all__ = [
    "LineChartWidget",
    "HeatmapWidget",
    "HistogramWidget",
]