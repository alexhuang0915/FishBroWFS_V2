"""
UI Widgets for Professional CTA Desktop UI.

This package provides reusable UI components for the Phase C desktop interface.
"""

from .metric_cards import MetricCard, MetricRow
from .log_viewer import LogViewerDialog
from .report_host import ReportHostWidget

# Chart widgets
from .charts.line_chart import LineChartWidget
from .charts.heatmap import HeatmapWidget
from .charts.histogram import HistogramWidget

__all__ = [
    # Metric cards
    "MetricCard",
    "MetricRow",
    
    # Log viewer
    "LogViewerDialog",
    
    # Report host
    "ReportHostWidget",
    
    # Charts
    "LineChartWidget",
    "HeatmapWidget",
    "HistogramWidget",
]