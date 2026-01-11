"""
Strategy Report Widget for CTA-grade Analytics UI.

Professional tear-sheet display for StrategyReportV1 with:
- Headline metric cards (CTA layout)
- Equity/Drawdown/Both toggle chart
- Rolling Sharpe selector (20/60/120) with graceful "Not Available"
- Monthly return heatmap with hover tooltips
- Return distribution histogram with hover tooltips
- Trade summary table (graceful missing fields)
- Report toolbar: Export JSON, Export PNG, Jump to Evidence
"""

import json
import logging
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, Signal, Slot, QSize, QRect  # type: ignore
from PySide6.QtWidgets import (  # type: ignore
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QGroupBox, QScrollArea, QSizePolicy, QComboBox,
    QButtonGroup, QToolButton, QFileDialog, QMessageBox,
    QStackedWidget, QFrame, QSplitter
)
from PySide6.QtGui import (  # type: ignore
    QPainter, QPixmap, QDesktopServices, QColor, QFont, QPen, QBrush
)
from PySide6.QtCore import QUrl  # type: ignore

from ...widgets.metric_cards import MetricCard, MetricRow
from ...widgets.charts.line_chart import LineChartWidget
from ...widgets.charts.histogram import HistogramWidget
from ...widgets.charts.monthly_heatmap import MonthlyHeatmapWidget
from ...services.supervisor_client import (
    get_strategy_report_v1, get_reveal_evidence_path, SupervisorClientError
)

logger = logging.getLogger(__name__)


class StrategyReportWidget(QWidget):
    """
    CTA-grade Strategy Report Widget.
    
    Displays StrategyReportV1 payload with professional analytics.
    """
    
    # Signals
    log_signal = Signal(str)
    
    def __init__(self, job_id: str, report_data: Dict[str, Any]):
        """
        Initialize the strategy report widget.
        
        Args:
            job_id: The job ID for this report
            report_data: The StrategyReportV1 payload
        """
        super().__init__()
        self.job_id: str = job_id
        self.report_data: Dict[str, Any] = report_data
        self.metric_cards: List[MetricCard] = []

        # UI Widgets
        self.export_json_btn: QPushButton
        self.export_png_btn: QPushButton
        self.jump_evidence_btn: QPushButton
        self.metrics_row: MetricRow
        self.toggle_group: QButtonGroup
        self.equity_btn: QToolButton
        self.drawdown_btn: QToolButton
        self.both_btn: QToolButton
        self.equity_chart: LineChartWidget
        self.sharpe_combo: QComboBox
        self.sharpe_chart_stack: QStackedWidget
        self.sharpe_chart: LineChartWidget
        self.sharpe_placeholder: QLabel
        self.monthly_heatmap: MonthlyHeatmapWidget
        self.histogram: HistogramWidget
        self.trade_table: QTableWidget

        # Data properties
        self.equity_series: List[Tuple[Any, Any]] = []
        self.drawdown_series: List[Tuple[Any, Any]] = []
        self.sharpe_data: Dict[str, Any] = {}
        
        self.setup_ui()
        self.populate_data()
    
    def setup_ui(self):
        """Initialize the UI components."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)
        
        # Toolbar
        self.setup_toolbar(main_layout)
        
        # Header section
        self.setup_header(main_layout)
        
        # Headline metrics row
        self.setup_metrics_row(main_layout)
        
        # Create splitter for charts and tables
        splitter = QSplitter(Qt.Orientation.Vertical)
        
        # Top section: Charts
        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(12)
        
        # Equity/Drawdown chart with toggle
        self.setup_equity_drawdown_chart(top_layout)
        
        # Rolling Sharpe selector
        self.setup_rolling_sharpe_chart(top_layout)
        
        # Bottom section: Tables and heatmap
        bottom_widget = QWidget()
        bottom_layout = QHBoxLayout(bottom_widget)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(12)
        
        # Left: Monthly heatmap
        self.setup_monthly_heatmap(bottom_layout)
        
        # Right: Histogram and trade table
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(12)
        
        # Histogram
        self.setup_histogram(right_layout)
        
        # Trade summary table
        self.setup_trade_table(right_layout)
        
        bottom_layout.addWidget(right_widget, 40)  # 40% width
        
        # Add widgets to splitter
        splitter.addWidget(top_widget)
        splitter.addWidget(bottom_widget)
        splitter.setSizes([400, 300])  # Initial sizes
        
        main_layout.addWidget(splitter, 1)  # Take remaining space
    
    def setup_toolbar(self, parent_layout: QVBoxLayout):
        """Setup the top toolbar with export buttons."""
        toolbar = QWidget()
        toolbar.setStyleSheet("background-color: #2A2A2A; border-radius: 4px; padding: 4px;")
        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(8, 4, 8, 4)
        
        # Export JSON button
        self.export_json_btn = QPushButton("📊 Export JSON")
        self.export_json_btn.setToolTip("Export report data as JSON file")
        self.export_json_btn.clicked.connect(self.export_json)
        
        # Export PNG button
        self.export_png_btn = QPushButton("🖼️ Export PNG (Charts)")
        self.export_png_btn.setToolTip("Export charts as PNG image")
        self.export_png_btn.clicked.connect(self.export_png)
        
        # Jump to Evidence button
        self.jump_evidence_btn = QPushButton("📁 Jump to Evidence")
        self.jump_evidence_btn.setToolTip("Open evidence folder for this job")
        self.jump_evidence_btn.clicked.connect(self.jump_to_evidence)
        
        # Style buttons
        for btn in [self.export_json_btn, self.export_png_btn, self.jump_evidence_btn]:
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #3A3A3A;
                    color: #E6E6E6;
                    border: 1px solid #555555;
                    border-radius: 4px;
                    padding: 6px 12px;
                    font-size: 11px;
                }
                QPushButton:hover {
                    background-color: #4A4A4A;
                    border-color: #3A8DFF;
                }
                QPushButton:pressed {
                    background-color: #2A2A2A;
                }
            """)
        
        toolbar_layout.addWidget(self.export_json_btn)
        toolbar_layout.addWidget(self.export_png_btn)
        toolbar_layout.addWidget(self.jump_evidence_btn)
        toolbar_layout.addStretch()
        
        parent_layout.addWidget(toolbar)
    
    def setup_header(self, parent_layout: QVBoxLayout):
        """Setup the report header section."""
        header_group = QGroupBox("Strategy Report")
        header_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 2px solid #1a237e;
                background-color: #1E1E1E;
                margin-top: 5px;
                padding-top: 8px;
                font-size: 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px 0 4px;
                color: #E6E6E6;
            }
        """)
        
        header_layout = QGridLayout()
        
        # Basic info from report meta
        meta = self.report_data.get('meta', {})
        header_layout.addWidget(QLabel(f"<b>Strategy:</b> {meta.get('strategy_name', 'Unknown')}"), 0, 0)
        header_layout.addWidget(QLabel(f"<b>Job ID:</b> {self.job_id}"), 0, 1)
        header_layout.addWidget(QLabel(f"<b>Created:</b> {meta.get('created_at', 'N/A')}"), 1, 0)
        header_layout.addWidget(QLabel(f"<b>Status:</b> {meta.get('status', 'N/A')}"), 1, 1)
        
        header_group.setLayout(header_layout)
        parent_layout.addWidget(header_group)
    
    def setup_metrics_row(self, parent_layout: QVBoxLayout):
        """Setup the headline metric cards row."""
        self.metrics_row = MetricRow()
        parent_layout.addWidget(self.metrics_row)
    
    def setup_equity_drawdown_chart(self, parent_layout: QVBoxLayout):
        """Setup equity/drawdown chart with toggle buttons."""
        chart_group = QGroupBox("Equity & Drawdown")
        chart_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 1px solid #555555;
                background-color: #1E1E1E;
                margin-top: 5px;
                padding-top: 8px;
                font-size: 11px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px 0 4px;
                color: #E6E6E6;
            }
        """)
        
        chart_layout = QVBoxLayout()
        
        # Toggle buttons
        toggle_widget = QWidget()
        toggle_layout = QHBoxLayout(toggle_widget)
        toggle_layout.setContentsMargins(0, 0, 0, 0)
        
        self.toggle_group = QButtonGroup(self)
        self.toggle_group.setExclusive(True)
        
        self.equity_btn = QToolButton()
        self.equity_btn.setText("Equity")
        self.equity_btn.setCheckable(True)
        self.equity_btn.setChecked(True)
        
        self.drawdown_btn = QToolButton()
        self.drawdown_btn.setText("Drawdown")
        self.drawdown_btn.setCheckable(True)
        
        self.both_btn = QToolButton()
        self.both_btn.setText("Both")
        self.both_btn.setCheckable(True)
        
        for btn in [self.equity_btn, self.drawdown_btn, self.both_btn]:
            btn.setStyleSheet("""
                QToolButton {
                    background-color: #3A3A3A;
                    color: #E6E6E6;
                    border: 1px solid #555555;
                    border-radius: 3px;
                    padding: 4px 12px;
                    font-size: 11px;
                }
                QToolButton:checked {
                    background-color: #1a237e;
                    color: white;
                }
                QToolButton:hover {
                    background-color: #4A4A4A;
                }
            """)
            self.toggle_group.addButton(btn)
            toggle_layout.addWidget(btn)
        
        toggle_layout.addStretch()
        chart_layout.addWidget(toggle_widget)
        
        # Chart widget
        self.equity_chart = LineChartWidget("Equity Curve", "Time", "Equity")
        self.equity_chart.setMinimumHeight(300)
        chart_layout.addWidget(self.equity_chart)
        
        # Connect toggle signals
        self.equity_btn.toggled.connect(self.update_chart_mode)
        self.drawdown_btn.toggled.connect(self.update_chart_mode)
        self.both_btn.toggled.connect(self.update_chart_mode)
        
        chart_group.setLayout(chart_layout)
        parent_layout.addWidget(chart_group)
    
    def setup_rolling_sharpe_chart(self, parent_layout: QVBoxLayout):
        """Setup rolling Sharpe chart with window selector."""
        sharpe_group = QGroupBox("Rolling Sharpe")
        sharpe_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 1px solid #555555;
                background-color: #1E1E1E;
                margin-top: 5px;
                padding-top: 8px;
                font-size: 11px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px 0 4px;
                color: #E6E6E6;
            }
        """)
        
        sharpe_layout = QVBoxLayout()
        
        # Window selector
        selector_widget = QWidget()
        selector_layout = QHBoxLayout(selector_widget)
        selector_layout.setContentsMargins(0, 0, 0, 0)
        
        selector_layout.addWidget(QLabel("Window:"))
        
        self.sharpe_combo = QComboBox()
        self.sharpe_combo.addItems(["20", "60", "120"])
        self.sharpe_combo.setCurrentIndex(0)
        self.sharpe_combo.setStyleSheet("""
            QComboBox {
                background-color: #3A3A3A;
                color: #E6E6E6;
                border: 1px solid #555555;
                border-radius: 3px;
                padding: 4px;
                min-width: 80px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px transparent;
                border-top: 5px solid #E6E6E6;
            }
        """)
        
        selector_layout.addWidget(self.sharpe_combo)
        selector_layout.addStretch()
        
        sharpe_layout.addWidget(selector_widget)
        
        # Chart widget or placeholder
        self.sharpe_chart_stack = QStackedWidget()
        
        # Actual chart
        self.sharpe_chart = LineChartWidget("Rolling Sharpe", "Time", "Sharpe Ratio")
        self.sharpe_chart.setMinimumHeight(250)
        
        # Placeholder for missing data
        self.sharpe_placeholder = QLabel("Rolling Sharpe: Not Available")
        self.sharpe_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sharpe_placeholder.setStyleSheet("color: #9A9A9A; font-size: 14px; padding: 40px;")
        
        self.sharpe_chart_stack.addWidget(self.sharpe_chart)
        self.sharpe_chart_stack.addWidget(self.sharpe_placeholder)
        
        sharpe_layout.addWidget(self.sharpe_chart_stack)
        
        # Connect combo signal
        self.sharpe_combo.currentTextChanged.connect(self.update_sharpe_window)
        
        sharpe_group.setLayout(sharpe_layout)
        parent_layout.addWidget(sharpe_group)
    
    def setup_monthly_heatmap(self, parent_layout: QHBoxLayout):
        """Setup monthly return heatmap."""
        heatmap_group = QGroupBox("Monthly Returns Heatmap")
        heatmap_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 1px solid #555555;
                background-color: #1E1E1E;
                margin-top: 5px;
                padding-top: 8px;
                font-size: 11px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px 0 4px;
                color: #E6E6E6;
            }
        """)
        
        heatmap_layout = QVBoxLayout()
        
        self.monthly_heatmap = MonthlyHeatmapWidget()
        self.monthly_heatmap.setMinimumHeight(300)
        
        heatmap_layout.addWidget(self.monthly_heatmap)
        heatmap_group.setLayout(heatmap_layout)
        
        parent_layout.addWidget(heatmap_group, 60)  # 60% width
    
    def setup_histogram(self, parent_layout: QVBoxLayout):
        """Setup returns distribution histogram."""
        hist_group = QGroupBox("Returns Distribution")
        hist_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 1px solid #555555;
                background-color: #1E1E1E;
                margin-top: 5px;
                padding-top: 8px;
                font-size: 11px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px 0 4px;
                color: #E6E6E6;
            }
        """)
        
        hist_layout = QVBoxLayout()
        
        self.histogram = HistogramWidget("Returns Distribution", "Return", "Frequency")
        self.histogram.setMinimumHeight(200)
        
        hist_layout.addWidget(self.histogram)
        hist_group.setLayout(hist_layout)
        
        parent_layout.addWidget(hist_group)
    
    def setup_trade_table(self, parent_layout: QVBoxLayout):
        """Setup trade summary table."""
        table_group = QGroupBox("Trade Summary")
        table_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 1px solid #555555;
                background-color: #1E1E1E;
                margin-top: 5px;
                padding-top: 8px;
                font-size: 11px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px 0 4px;
                color: #E6E6E6;
            }
        """)
        
        table_layout = QVBoxLayout()
        
        self.trade_table = QTableWidget()
        self.trade_table.setColumnCount(2)
        self.trade_table.setHorizontalHeaderLabels(["Metric", "Value"])
        self.trade_table.horizontalHeader().setStretchLastSection(True)
        self.trade_table.setAlternatingRowColors(True)
        self.trade_table.setStyleSheet("""
            QTableWidget {
                background-color: #1E1E1E;
                color: #E6E6E6;
                border: 1px solid #555555;
                font-size: 11px;
            }
            QTableWidget::item {
                padding: 4px;
            }
            QHeaderView::section {
                background-color: #2A2A2A;
                color: #E6E6E6;
                border: 1px solid #555555;
                padding: 4px;
                font-weight: bold;
            }
            QTableWidget::item:selected {
                background-color: #1a237e;
            }
        """)
        
        table_layout.addWidget(self.trade_table)
        table_group.setLayout(table_layout)
        
        parent_layout.addWidget(table_group)
    
    def populate_data(self):
        """Populate all UI components with report data."""
        try:
            # Populate headline metrics
            self.populate_metrics()
            
            # Populate equity/drawdown chart
            self.populate_equity_drawdown()
            
            # Populate rolling Sharpe
            self.populate_rolling_sharpe()
            
            # Populate monthly heatmap
            self.populate_monthly_heatmap()
            
            # Populate histogram
            self.populate_histogram()
            
            # Populate trade table
            self.populate_trade_table()
            
        except Exception as e:
            logger.error(f"Error populating report data: {e}")
            self.log_signal.emit(f"Error loading report data: {e}")
    
    def populate_metrics(self):
        """Populate headline metric cards."""
        try:
            metrics = self.report_data.get('headline_metrics', {})
            
            # Required metrics with fallbacks
            metric_defs = [
                ("Net Profit", metrics.get('net_profit'), "currency", None),
                ("Max Drawdown", metrics.get('max_drawdown'), "percentage", None),
                ("Net/MDD", metrics.get('net_mdd_ratio'), "ratio", None),
                ("Sharpe", metrics.get('sharpe_ratio'), "ratio", None),
                ("Trades", metrics.get('total_trades'), "count", None),
                ("Win Rate", metrics.get('win_rate'), "percentage", None),
            ]
            
            cards = []
            for name, value, unit, _ in metric_defs:
                if value is None:
                    display_value = "—"
                    color = "neutral"
                else:
                    # Format based on unit
                    if unit == "currency":
                        display_value = f"${value:,.2f}"
                    elif unit == "percentage":
                        display_value = f"{value:.2%}"
                    elif unit == "ratio":
                        display_value = f"{value:.2f}"
                    elif unit == "count":
                        display_value = f"{value:,}"
                    else:
                        display_value = str(value)
                    
                    # Color logic
                    if name == "Net/MDD" and value is not None and value < 1.0:
                        color = "warning"
                    elif name == "Max Drawdown" and value is not None:
                        # Check if it's a percentage (string with % or float < 1)
                        if isinstance(value, (int, float)):
                            if value > 0.20:  # 20% threshold
                                color = "danger"
                            else:
                                color = "neutral"
                        else:
                            color = "neutral"
                    else:
                        color = "neutral"
                
                cards.append({
                    'title': name,
                    'value': display_value,
                    'color': color
                })
            
            self.metrics_row.set_metrics(cards)
            
        except Exception as e:
            logger.error(f"Error populating metrics: {e}")
    
    def populate_equity_drawdown(self):
        """Populate equity and drawdown series."""
        try:
            series = self.report_data.get('series', {})
            equity_data = series.get('equity_curve', [])
            drawdown_data = series.get('drawdown_curve', [])
            
            # Convert to chart format
            equity_points = []
            drawdown_points = []
            
            for point in equity_data:
                if 'timestamp' in point and 'value' in point:
                    equity_points.append((point['timestamp'], point['value']))
            
            for point in drawdown_data:
                if 'timestamp' in point and 'value' in point:
                    drawdown_points.append((point['timestamp'], point['value']))
            
            # Enable/disable toggle buttons based on data availability
            has_equity = len(equity_points) > 0
            has_drawdown = len(drawdown_points) > 0
            
            self.equity_btn.setEnabled(has_equity)
            self.drawdown_btn.setEnabled(has_drawdown)
            self.both_btn.setEnabled(has_equity and has_drawdown)
            
            if not has_equity:
                self.equity_btn.setToolTip("Equity data not available")
            if not has_drawdown:
                self.drawdown_btn.setToolTip("Drawdown data not available")
            if not (has_equity and has_drawdown):
                self.both_btn.setToolTip("Both series not available")
            
            # Store data for toggling
            self.equity_series = equity_points
            self.drawdown_series = drawdown_points
            
            # Initial display
            self.update_chart_mode()
            
        except Exception as e:
            logger.error(f"Error populating equity/drawdown: {e}")
            self.equity_chart.set_placeholder_text("Equity/Drawdown data not available")
    
    def update_chart_mode(self):
        """Update chart based on selected mode."""
        try:
            if self.equity_btn.isChecked():
                # Show only equity
                if hasattr(self, 'equity_series') and self.equity_series:
                    self.equity_chart.set_series({"Equity": self.equity_series})
                else:
                    self.equity_chart.set_placeholder_text("Equity data not available")
            
            elif self.drawdown_btn.isChecked():
                # Show only drawdown
                if hasattr(self, 'drawdown_series') and self.drawdown_series:
                    self.equity_chart.set_series({"Drawdown": self.drawdown_series})
                else:
                    self.equity_chart.set_placeholder_text("Drawdown data not available")
            
            elif self.both_btn.isChecked():
                # Show both
                series_dict = {}
                if hasattr(self, 'equity_series') and self.equity_series:
                    series_dict["Equity"] = self.equity_series
                if hasattr(self, 'drawdown_series') and self.drawdown_series:
                    series_dict["Drawdown"] = self.drawdown_series
                
                if series_dict:
                    self.equity_chart.set_series(series_dict)
                else:
                    self.equity_chart.set_placeholder_text("No series data available")
        
        except Exception as e:
            logger.error(f"Error updating chart mode: {e}")
    
    def populate_rolling_sharpe(self):
        """Populate rolling Sharpe chart."""
        try:
            series = self.report_data.get('series', {})
            rolling_sharpe = series.get('rolling_sharpe')
            
            if not rolling_sharpe:
                # No data available
                self.sharpe_chart_stack.setCurrentWidget(self.sharpe_placeholder)
                self.sharpe_combo.setEnabled(False)
                return
            
            # Determine format
            if isinstance(rolling_sharpe, dict):
                # Windowed data
                self.sharpe_data = rolling_sharpe
                self.sharpe_chart_stack.setCurrentWidget(self.sharpe_chart)
                self.sharpe_combo.setEnabled(True)
                # Show initial window
                self.update_sharpe_window()
            elif isinstance(rolling_sharpe, list):
                # Single series
                self.sharpe_data = {"default": rolling_sharpe}
                self.sharpe_chart_stack.setCurrentWidget(self.sharpe_chart)
                self.sharpe_combo.setEnabled(False)
                # Convert to points
                points = []
                for i, value in enumerate(rolling_sharpe):
                    points.append((i, value))
                self.sharpe_chart.set_series({"Sharpe": points})
            else:
                # Unknown format
                self.sharpe_chart_stack.setCurrentWidget(self.sharpe_placeholder)
                self.sharpe_combo.setEnabled(False)
        
        except Exception as e:
            logger.error(f"Error populating rolling Sharpe: {e}")
            self.sharpe_chart_stack.setCurrentWidget(self.sharpe_placeholder)
    
    def update_sharpe_window(self, window_str: str = None):
        """Update Sharpe chart for selected window."""
        try:
            if not hasattr(self, 'sharpe_data'):
                return
            
            if window_str is None:
                window_str = self.sharpe_combo.currentText()
            
            window_data = self.sharpe_data.get(window_str)
            if not window_data:
                # Try to find closest match
                for key in self.sharpe_data.keys():
                    if str(key) == window_str:
                        window_data = self.sharpe_data[key]
                        break
            
            if window_data:
                points = []
                for i, value in enumerate(window_data):
                    points.append((i, value))
                self.sharpe_chart.set_series({"Sharpe": points})
        
        except Exception as e:
            logger.error(f"Error updating Sharpe window: {e}")
    
    def populate_monthly_heatmap(self):
        """Populate monthly returns heatmap."""
        try:
            tables = self.report_data.get('tables', {})
            monthly_data = tables.get('monthly_heatmap')
            
            if monthly_data:
                self.monthly_heatmap.set_data(monthly_data)
            else:
                self.monthly_heatmap.set_placeholder_text("Monthly heatmap data not available")
        
        except Exception as e:
            logger.error(f"Error populating monthly heatmap: {e}")
            self.monthly_heatmap.set_placeholder_text("Error loading heatmap")
    
    def populate_histogram(self):
        """Populate returns distribution histogram."""
        try:
            distributions = self.report_data.get('distributions', {})
            return_dist = distributions.get('return_distribution')
            
            if return_dist:
                # Expect format: {"bins": [...], "counts": [...]}
                bins = return_dist.get('bins', [])
                counts = return_dist.get('counts', [])
                
                if bins and counts:
                    self.histogram.set_data(bins, counts)
                else:
                    self.histogram.set_placeholder_text("Return distribution data not available")
            else:
                self.histogram.set_placeholder_text("Return distribution data not available")
        
        except Exception as e:
            logger.error(f"Error populating histogram: {e}")
            self.histogram.set_placeholder_text("Error loading distribution")
    
    def populate_trade_table(self):
        """Populate trade summary table."""
        try:
            tables = self.report_data.get('tables', {})
            trade_summary = tables.get('trade_summary', {})
            
            # Define metrics to show
            metric_defs = [
                ("Total Trades", trade_summary.get('total_trades'), "count"),
                ("Win Rate", trade_summary.get('win_rate'), "percentage"),
                ("Avg Win", trade_summary.get('avg_win'), "currency"),
                ("Avg Loss", trade_summary.get('avg_loss'), "currency"),
                ("Profit Factor", trade_summary.get('profit_factor'), "ratio"),
                ("Expectancy", trade_summary.get('expectancy'), "currency"),
            ]
            
            self.trade_table.setRowCount(len(metric_defs))
            
            for i, (name, value, unit) in enumerate(metric_defs):
                # Metric name
                name_item = QTableWidgetItem(name)
                name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.trade_table.setItem(i, 0, name_item)
                
                # Value
                if value is None:
                    display_value = "—"
                else:
                    if unit == "currency":
                        display_value = f"${value:,.2f}"
                    elif unit == "percentage":
                        display_value = f"{value:.2%}"
                    elif unit == "ratio":
                        display_value = f"{value:.2f}"
                    elif unit == "count":
                        display_value = f"{value:,}"
                    else:
                        display_value = str(value)
                
                value_item = QTableWidgetItem(display_value)
                value_item.setFlags(value_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                value_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.trade_table.setItem(i, 1, value_item)
            
            self.trade_table.resizeColumnsToContents()
        
        except Exception as e:
            logger.error(f"Error populating trade table: {e}")
            self.trade_table.setRowCount(1)
            self.trade_table.setItem(0, 0, QTableWidgetItem("Error loading trade summary"))
            self.trade_table.setItem(0, 1, QTableWidgetItem("—"))
    
    def export_json(self):
        """Export report data as JSON file."""
        try:
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Export Report as JSON",
                f"strategy_report_{self.job_id}.json",
                "JSON Files (*.json)"
            )
            
            if file_path:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(self.report_data, f, indent=2, ensure_ascii=False)
                
                self.log_signal.emit(f"Report exported to {file_path}")
                QMessageBox.information(
                    self,
                    "Export Successful",
                    f"Report data exported to:\n{file_path}"
                )
        
        except Exception as e:
            logger.error(f"Error exporting JSON: {e}")
            QMessageBox.critical(
                self,
                "Export Failed",
                f"Failed to export report: {e}"
            )
    
    def export_png(self):
        """Export charts as PNG image."""
        try:
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Export Charts as PNG",
                f"strategy_charts_{self.job_id}.png",
                "PNG Files (*.png)"
            )
            
            if not file_path:
                return
            
            # Collect chart widgets
            charts = []
            
            # Equity/Drawdown chart
            if hasattr(self, 'equity_chart'):
                charts.append(("Equity/Drawdown Chart", self.equity_chart))
            
            # Sharpe chart (if visible)
            if (hasattr(self, 'sharpe_chart_stack') and 
                self.sharpe_chart_stack.currentWidget() == self.sharpe_chart):
                charts.append(("Rolling Sharpe", self.sharpe_chart))
            
            # Monthly heatmap
            if hasattr(self, 'monthly_heatmap'):
                charts.append(("Monthly Heatmap", self.monthly_heatmap))
            
            # Histogram
            if hasattr(self, 'histogram'):
                charts.append(("Returns Distribution", self.histogram))
            
            if not charts:
                QMessageBox.warning(
                    self,
                    "No Charts Available",
                    "No charts are available for export."
                )
                return
            
            # Calculate total height
            margin = 20
            title_height = 30
            total_height = margin * 2 + len(charts) * title_height
            
            for _, widget in charts:
                total_height += widget.height()
            
            # Create pixmap
            pixmap = QPixmap(1200, total_height)
            pixmap.fill(QColor("#1E1E1E"))
            
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            
            # Draw charts
            y_offset = margin
            
            for title, widget in charts:
                # Draw title
                painter.setPen(QColor("#E6E6E6"))
                painter.setFont(QFont("Arial", 12, QFont.Weight.Bold))
                painter.drawText(20, y_offset + 20, title)
                y_offset += title_height
                
                # Grab widget pixmap
                widget_pixmap = widget.grab()
                
                # Scale if too wide
                if widget_pixmap.width() > 1160:
                    widget_pixmap = widget_pixmap.scaled(
                        1160, 
                        widget_pixmap.height(),
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation
                    )
                
                # Draw widget
                x_center = (1200 - widget_pixmap.width()) // 2
                painter.drawPixmap(x_center, y_offset, widget_pixmap)
                y_offset += widget_pixmap.height() + margin
            
            painter.end()
            
            # Save to file
            pixmap.save(file_path, "PNG")
            
            self.log_signal.emit(f"Charts exported to {file_path}")
            QMessageBox.information(
                self,
                "Export Successful",
                f"Charts exported to:\n{file_path}"
            )
        
        except Exception as e:
            logger.error(f"Error exporting PNG: {e}")
            QMessageBox.critical(
                self,
                "Export Failed",
                f"Failed to export charts: {e}"
            )
    
    def jump_to_evidence(self):
        """Open evidence folder for this job."""
        try:
            # Get evidence path via API
            evidence_path = get_reveal_evidence_path(self.job_id)
            
            if evidence_path:
                # Open folder in file explorer
                QDesktopServices.openUrl(QUrl.fromLocalFile(evidence_path))
                self.log_signal.emit(f"Opened evidence folder: {evidence_path}")
            else:
                QMessageBox.warning(
                    self,
                    "Evidence Not Available",
                    "Evidence folder is not available for this job."
                )
        
        except Exception as e:
            logger.error(f"Error jumping to evidence: {e}")
            QMessageBox.critical(
                self,
                "Error",
                f"Failed to open evidence folder: {e}"
            )
