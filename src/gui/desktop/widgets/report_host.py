"""
Report Host Widget for displaying StrategyReportV1 and PortfolioReportV1.

Provides a QStackedWidget container that can show different report types
with appropriate headers and navigation.
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime

from PySide6.QtCore import Qt, Signal, Slot  # type: ignore
from PySide6.QtWidgets import (  # type: ignore
    QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget,
    QLabel, QPushButton, QFrame, QSizePolicy, QSpacerItem
)

from .metric_cards import MetricRow
from .charts.line_chart import LineChartWidget
from .charts.heatmap import HeatmapWidget
from .charts.histogram import HistogramWidget
from .report_widgets.portfolio_report_widget import PortfolioReportWidget

logger = logging.getLogger(__name__)


class ReportHostWidget(QWidget):
    """
    Host widget for displaying different report types.
    
    Features:
    - QStackedWidget for different report types
    - Header with report metadata
    - Navigation between report types
    - Metric cards for key metrics
    """
    
    # Signals
    report_loaded = Signal(str, str)  # report_type, report_id
    report_error = Signal(str, str)   # report_type, error_message
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_report_type: Optional[str] = None
        self.current_report_id: Optional[str] = None
        self.current_report_data: Optional[Dict[str, Any]] = None
        
        self.setup_ui()
    
    def setup_ui(self):
        """Initialize the UI components."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(8)
        
        # Header section
        self.header_widget = QWidget()
        self.header_widget.setStyleSheet("""
            QWidget {
                background-color: #2A2A2A;
                border-bottom: 1px solid #444444;
                padding: 8px;
            }
        """)
        header_layout = QVBoxLayout(self.header_widget)
        header_layout.setContentsMargins(8, 8, 8, 8)
        header_layout.setSpacing(4)
        
        # Title row
        title_layout = QHBoxLayout()
        
        self.report_type_label = QLabel("No Report Loaded")
        self.report_type_label.setStyleSheet("""
            QLabel {
                color: #E6E6E6;
                font-size: 16px;
                font-weight: bold;
            }
        """)
        title_layout.addWidget(self.report_type_label)
        
        title_layout.addSpacerItem(QSpacerItem(20, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
        
        # Report ID label
        self.report_id_label = QLabel("")
        self.report_id_label.setStyleSheet("""
            QLabel {
                color: #9A9A9A;
                font-size: 12px;
                font-family: monospace;
            }
        """)
        title_layout.addWidget(self.report_id_label)
        
        header_layout.addLayout(title_layout)
        
        # Metadata row
        metadata_layout = QHBoxLayout()
        
        self.metadata_label = QLabel("")
        self.metadata_label.setStyleSheet("color: #9A9A9A; font-size: 11px;")
        metadata_layout.addWidget(self.metadata_label)
        
        metadata_layout.addSpacerItem(QSpacerItem(20, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
        
        # Timestamp label
        self.timestamp_label = QLabel("")
        self.timestamp_label.setStyleSheet("color: #9A9A9A; font-size: 11px;")
        metadata_layout.addWidget(self.timestamp_label)
        
        header_layout.addLayout(metadata_layout)
        
        main_layout.addWidget(self.header_widget)
        
        # Metric cards row
        self.metric_row = MetricRow()
        main_layout.addWidget(self.metric_row)
        
        # Stacked widget for different report types
        self.stacked_widget = QStackedWidget()
        main_layout.addWidget(self.stacked_widget, 1)  # Stretch factor 1
        
        # Create placeholder widgets
        self._create_placeholder_widgets()
    
    def _create_placeholder_widgets(self):
        """Create placeholder widgets for different report types."""
        # Strategy report placeholder
        strategy_placeholder = QLabel("Strategy Report Viewer\n\nLoad a strategy report to see metrics and charts.")
        strategy_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        strategy_placeholder.setStyleSheet("""
            QLabel {
                color: #9A9A9A;
                font-size: 14px;
                padding: 40px;
            }
        """)
        self.strategy_widget_index = self.stacked_widget.addWidget(strategy_placeholder)
        
        # Portfolio report placeholder
        portfolio_placeholder = QLabel("Portfolio Report Viewer\n\nLoad a portfolio report to see correlation heatmaps and allocations.")
        portfolio_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        portfolio_placeholder.setStyleSheet("""
            QLabel {
                color: #9A9A9A;
                font-size: 14px;
                padding: 40px;
            }
        """)
        self.portfolio_widget_index = self.stacked_widget.addWidget(portfolio_placeholder)
        
        # Empty state
        empty_placeholder = QLabel("No Report Loaded\n\nUse show_strategy_report() or show_portfolio_report() to load a report.")
        empty_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_placeholder.setStyleSheet("""
            QLabel {
                color: #666666;
                font-size: 14px;
                padding: 40px;
            }
        """)
        self.empty_widget_index = self.stacked_widget.addWidget(empty_placeholder)
        
        # Show empty state by default
        self.stacked_widget.setCurrentIndex(self.empty_widget_index)
    
    def show_strategy_report(self, report_data: Dict[str, Any]):
        """
        Display a StrategyReportV1 report.
        
        Args:
            report_data: StrategyReportV1 JSON data
        """
        try:
            self.current_report_type = "strategy"
            self.current_report_data = report_data
            
            # Extract report ID
            job_id = report_data.get("job_id", "unknown")
            self.current_report_id = f"job:{job_id}"
            
            # Update header
            strategy_name = report_data.get("strategy_name", "Unknown Strategy")
            self.report_type_label.setText(f"Strategy Report: {strategy_name}")
            self.report_id_label.setText(f"Job: {job_id}")
            
            # Extract metadata
            created_at = report_data.get("created_at", "")
            status = report_data.get("status", "unknown")
            self.metadata_label.setText(f"Status: {status}")
            
            # Format timestamp
            if created_at:
                try:
                    dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    self.timestamp_label.setText(f"Created: {dt.strftime('%Y-%m-%d %H:%M:%S')}")
                except (ValueError, AttributeError):
                    self.timestamp_label.setText(f"Created: {created_at}")
            else:
                self.timestamp_label.setText("")
            
            # Update metric cards
            self._update_strategy_metrics(report_data)
            
            # TODO: Create and show actual strategy report widget
            # For now, show placeholder
            self.stacked_widget.setCurrentIndex(self.strategy_widget_index)
            
            # Emit signal
            self.report_loaded.emit("strategy", job_id)
            
        except Exception as e:
            logger.error(f"Error displaying strategy report: {e}")
            self.report_error.emit("strategy", str(e))
            self._show_error(f"Failed to display strategy report: {e}")
    
    def show_portfolio_report(self, report_data: Dict[str, Any]):
        """
        Display a PortfolioReportV1 report.
        
        Args:
            report_data: PortfolioReportV1 JSON data
        """
        try:
            self.current_report_type = "portfolio"
            self.current_report_data = report_data
            
            # Extract report ID
            portfolio_id = report_data.get("portfolio_id", "unknown")
            self.current_report_id = f"portfolio:{portfolio_id}"
            
            # Update header
            self.report_type_label.setText(f"Portfolio Report")
            self.report_id_label.setText(f"Portfolio: {portfolio_id}")
            
            # Extract metadata
            created_at = report_data.get("created_at", "")
            self.metadata_label.setText("")
            
            # Format timestamp
            if created_at:
                try:
                    dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    self.timestamp_label.setText(f"Created: {dt.strftime('%Y-%m-%d %H:%M:%S')}")
                except (ValueError, AttributeError):
                    self.timestamp_label.setText(f"Created: {created_at}")
            else:
                self.timestamp_label.setText("")
            
            # Update metric cards
            self._update_portfolio_metrics(report_data)
            
            # Create and show actual portfolio report widget
            portfolio_widget = PortfolioReportWidget(portfolio_id, report_data)
            
            # Replace placeholder with actual widget
            self.stacked_widget.removeWidget(self.stacked_widget.widget(self.portfolio_widget_index))
            self.portfolio_widget_index = self.stacked_widget.addWidget(portfolio_widget)
            self.stacked_widget.setCurrentIndex(self.portfolio_widget_index)
            
            # Emit signal
            self.report_loaded.emit("portfolio", portfolio_id)
            
        except Exception as e:
            logger.error(f"Error displaying portfolio report: {e}")
            self.report_error.emit("portfolio", str(e))
            self._show_error(f"Failed to display portfolio report: {e}")
    
    def _update_strategy_metrics(self, report_data: Dict[str, Any]):
        """Update metric cards for strategy report."""
        # Clear existing cards
        self.metric_row.clear_cards()
        
        # Extract key metrics
        metrics = report_data.get("metrics", {})
        score = metrics.get("score", 0)
        net_profit = metrics.get("net_profit", 0)
        max_drawdown = metrics.get("max_drawdown", 0)
        trades = metrics.get("trades", 0)
        win_rate = metrics.get("win_rate", 0)
        
        # Determine colors
        score_color = "#4CAF50" if score >= 0 else "#F44336"
        profit_color = "#4CAF50" if net_profit >= 0 else "#F44336"
        drawdown_color = "#F44336"  # Always red for drawdown
        
        # Create metric cards
        self.metric_row.create_and_add_card(
            "Score",
            f"{score:.2f}",
            "Strategy Score",
            score_color
        )
        
        self.metric_row.create_and_add_card(
            "Net Profit",
            f"${net_profit:,.2f}",
            "Total P&L",
            profit_color
        )
        
        self.metric_row.create_and_add_card(
            "Max DD",
            f"${max_drawdown:,.2f}",
            "Maximum Drawdown",
            drawdown_color
        )
        
        self.metric_row.create_and_add_card(
            "Trades",
            f"{trades}",
            "Total Trades"
        )
        
        self.metric_row.create_and_add_card(
            "Win Rate",
            f"{win_rate:.1%}",
            "Win Percentage"
        )
    
    def _update_portfolio_metrics(self, report_data: Dict[str, Any]):
        """Update metric cards for portfolio report."""
        # Clear existing cards
        self.metric_row.clear_cards()
        
        # Extract key metrics
        admitted_count = len(report_data.get("admitted_strategies", list()))
        rejected_count = len(report_data.get("rejected_strategies", list()))
        
        correlation = report_data.get("correlation", {})
        violations = correlation.get("violations", list())
        violation_count = len(violations)
        
        # Create metric cards
        self.metric_row.create_and_add_card(
            "Admitted",
            f"{admitted_count}",
            "Strategies"
        )
        
        self.metric_row.create_and_add_card(
            "Rejected",
            f"{rejected_count}",
            "Strategies"
        )
        
        self.metric_row.create_and_add_card(
            "Violations",
            f"{violation_count}",
            "Correlation Violations"
        )
        
        # Add portfolio metrics if available
        portfolio_metrics = report_data.get("portfolio_metrics", {})
        if portfolio_metrics:
            portfolio_score = portfolio_metrics.get("score", 0)
            expected_return = portfolio_metrics.get("expected_return", 0)
            
            self.metric_row.create_and_add_card(
                "Portfolio Score",
                f"{portfolio_score:.2f}",
                "Overall Score"
            )
            
            self.metric_row.create_and_add_card(
                "Expected Return",
                f"{expected_return:.2%}",
                "Annualized"
            )
    
    def _show_error(self, error_message: str):
        """Show error message in the widget."""
        error_widget = QLabel(f"Error: {error_message}")
        error_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)
        error_widget.setStyleSheet("""
            QLabel {
                color: #F44336;
                font-size: 14px;
                padding: 40px;
            }
        """)
        
        # Replace current widget with error
        current_index = self.stacked_widget.currentIndex()
        self.stacked_widget.removeWidget(self.stacked_widget.widget(current_index))
        self.stacked_widget.insertWidget(current_index, error_widget)
        self.stacked_widget.setCurrentIndex(current_index)
    
    def clear(self):
        """Clear the report display."""
        self.current_report_type = None
        self.current_report_id = None
        self.current_report_data = None
        
        self.report_type_label.setText("No Report Loaded")
        self.report_id_label.setText("")
        self.metadata_label.setText("")
        self.timestamp_label.setText("")
        
        self.metric_row.clear_cards()
        self.stacked_widget.setCurrentIndex(self.empty_widget_index)
    
    def get_current_report_info(self) -> Dict[str, Optional[str]]:
        """Get information about the currently displayed report."""
        return {
            "type": self.current_report_type,
            "id": self.current_report_id,
            "data": self.current_report_data
        }