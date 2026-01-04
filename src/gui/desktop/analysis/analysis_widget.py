"""
Analytics Suite for Desktop UI - Phase 18.

Provides 4 pro tabs: Dashboard, Risk, Period, Trades.
Loads data from valid artifact directory (artifact_* with required files).
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any

import pandas as pd
import numpy as np
from matplotlib.figure import Figure
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar
import matplotlib.pyplot as plt

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QLabel,
    QTableWidget, QTableWidgetItem, QGroupBox, QGridLayout,
    QScrollArea, QFrame, QSizePolicy, QSplitter
)

logger = logging.getLogger(__name__)


class AnalysisWidget(QWidget):
    """Analytics suite widget with 4 tabs for artifact analysis."""
    
    # Signal emitted when artifact is loaded
    artifact_loaded = Signal(str)  # artifact path
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        
        # Data storage
        self.artifact_path: Optional[Path] = None
        self.metrics: Dict[str, Any] = {}
        self.trades_df: Optional[pd.DataFrame] = None
        self.equity_df: Optional[pd.DataFrame] = None
        self.report: Dict[str, Any] = {}
        
        # UI components
        self.tab_widget: Optional[QTabWidget] = None
        self.dashboard_canvas: Optional[FigureCanvas] = None
        self.risk_canvas: Optional[FigureCanvas] = None
        self.period_canvas: Optional[FigureCanvas] = None
        self.trades_table: Optional[QTableWidget] = None
        
        self.setup_ui()
    
    def setup_ui(self):
        """Initialize the UI with 4 tabs."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(2, 2, 2, 2)
        main_layout.setSpacing(4)
        
        # Status label
        self.status_label = QLabel("No analysis results. Run Analysis to see strategy report.")
        self.status_label.setStyleSheet("color: #9A9A9A; font-style: italic; font-size: 11px;")
        main_layout.addWidget(self.status_label)
        
        # Tab widget - compact
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabPosition(QTabWidget.North)
        self.tab_widget.setStyleSheet("""
            QTabWidget::pane {
                border: none;
                background-color: #121212;
            }
            QTabBar::tab {
                background-color: #1E1E1E;
                color: #9A9A9A;
                padding: 4px 8px;
                margin-right: 1px;
                border: none;
                font-size: 10px;
            }
            QTabBar::tab:selected {
                background-color: #121212;
                color: #E6E6E6;
                border-bottom: 2px solid #3A8DFF;
                font-weight: bold;
            }
            QTabBar::tab:hover {
                background-color: #2A2A2A;
                color: #E6E6E6;
            }
        """)
        
        # Create tabs
        self.create_dashboard_tab()
        self.create_risk_tab()
        self.create_period_tab()
        self.create_trades_tab()
        
        main_layout.addWidget(self.tab_widget)
        
        # Tabs are always enabled, show placeholder when no artifact
        self.set_report_loaded(False)
    
    def create_dashboard_tab(self):
        """Create Dashboard tab with KPI cards, equity curve and metrics grid."""
        tab = QWidget()
        tab.setStyleSheet("background-color: #121212;")
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        
        # KPI Metric Cards (top strip)
        kpi_layout = QHBoxLayout()
        kpi_layout.setSpacing(8)
        
        # Create 4 KPI cards
        self.kpi_cards = {}
        kpi_defs = [
            ("Net Profit", "net_profit", "$ {:,.2f}", "#29D38D"),
            ("Drawdown", "max_dd", "$ {:,.2f}", "#FF4D4D"),
            ("Win Rate", "win_rate", "{:.1f}%", "#2F80ED"),
            ("Trades", "trades", "{:,}", "#E6E6E6"),
        ]
        
        for title, key, fmt, color in kpi_defs:
            card = self.create_kpi_card(title, key, fmt, color)
            self.kpi_cards[key] = card
            kpi_layout.addWidget(card)
        
        layout.addLayout(kpi_layout)
        
        # Equity curve plot - dominant height
        equity_group = QGroupBox("Equity Curve")
        equity_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 1px solid #555555;
                border-radius: 3px;
                margin-top: 4px;
                padding-top: 6px;
                font-size: 11px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 6px;
                padding: 0 3px 0 3px;
                color: #E6E6E6;
            }
        """)
        equity_layout = QVBoxLayout()
        equity_layout.setContentsMargins(2, 2, 2, 2)
        
        # Matplotlib figure for equity curve - dark theme
        plt.style.use('dark_background')
        self.dashboard_figure = Figure(figsize=(10, 4), dpi=100, facecolor='#121212')
        self.dashboard_canvas = FigureCanvas(self.dashboard_figure)
        self.dashboard_canvas.setStyleSheet("background-color: #121212;")
        self.dashboard_toolbar = NavigationToolbar(self.dashboard_canvas, self)
        
        equity_layout.addWidget(self.dashboard_toolbar)
        equity_layout.addWidget(self.dashboard_canvas)
        equity_group.setLayout(equity_layout)
        layout.addWidget(equity_group, 70)  # 70% stretch
        
        # Metrics grid - compact
        metrics_group = QGroupBox("Key Metrics")
        metrics_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 1px solid #555555;
                border-radius: 3px;
                margin-top: 4px;
                padding-top: 6px;
                font-size: 11px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 6px;
                padding: 0 3px 0 3px;
                color: #E6E6E6;
            }
        """)
        metrics_layout = QGridLayout()
        metrics_layout.setVerticalSpacing(4)
        metrics_layout.setHorizontalSpacing(8)
        
        # Create metric labels - compact grid
        self.metric_labels = {}
        metric_defs = [
            ("Net Profit", "net_profit", "$ {:,.2f}", "#00FF88"),
            ("Max Drawdown", "max_dd", "$ {:,.2f}", "#FF3B3B"),
            ("Sharpe", "sharpe", "{:.2f}", "#E6E6E6"),
            ("Profit Factor", "profit_factor", "{:.2f}", "#E6E6E6"),
            ("Win Rate", "win_rate", "{:.1f}%", "#E6E6E6"),
            ("SQN", "sqn", "{:.2f}", "#E6E6E6"),
            ("Trades", "trades", "{:,}", "#E6E6E6"),
        ]
        
        for i, (label, key, fmt, color) in enumerate(metric_defs):
            row = i // 4
            col = (i % 4) * 2
            
            label_widget = QLabel(f"{label}:")
            label_widget.setStyleSheet("color: #9A9A9A; font-size: 10px;")
            metrics_layout.addWidget(label_widget, row, col)
            
            value_label = QLabel("-")
            value_label.setStyleSheet(f"font-weight: bold; color: {color}; font-size: 11px;")
            metrics_layout.addWidget(value_label, row, col + 1)
            self.metric_labels[key] = value_label
        
        metrics_group.setLayout(metrics_layout)
        layout.addWidget(metrics_group, 30)  # 30% stretch
        
        self.tab_widget.addTab(tab, "Dashboard")
    
    def create_kpi_card(self, title: str, key: str, fmt: str, color: str) -> QFrame:
        """Create a KPI metric card widget."""
        card = QFrame()
        card.setFrameStyle(QFrame.StyledPanel)
        card.setStyleSheet(f"""
            QFrame {{
                background-color: #1E1E1E;
                border: 1px solid #2A2A2A;
                border-radius: 4px;
                padding: 8px;
                min-width: 120px;
            }}
            QFrame:hover {{
                border: 1px solid {color};
            }}
        """)
        
        card_layout = QVBoxLayout(card)
        card_layout.setSpacing(4)
        
        # Title
        title_label = QLabel(title)
        title_label.setStyleSheet("color: #9A9A9A; font-size: 10px; font-weight: bold;")
        title_label.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(title_label)
        
        # Value
        value_label = QLabel("—")
        value_label.setStyleSheet(f"color: {color}; font-size: 14px; font-weight: bold;")
        value_label.setAlignment(Qt.AlignCenter)
        card_layout.addWidget(value_label)
        
        # Store reference
        setattr(card, "value_label", value_label)
        setattr(card, "key", key)
        setattr(card, "fmt", fmt)
        
        return card
    
    def create_risk_tab(self):
        """Create Risk tab with underwater plot and PnL histogram."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Underwater plot (drawdown)
        drawdown_group = QGroupBox("Underwater Plot (Drawdown)")
        drawdown_layout = QVBoxLayout()
        
        self.risk_figure = Figure(figsize=(10, 8), dpi=100)
        self.risk_canvas = FigureCanvas(self.risk_figure)
        self.risk_toolbar = NavigationToolbar(self.risk_canvas, self)
        
        drawdown_layout.addWidget(self.risk_toolbar)
        drawdown_layout.addWidget(self.risk_canvas)
        drawdown_group.setLayout(drawdown_layout)
        layout.addWidget(drawdown_group)
        
        # Risk metrics
        risk_metrics_group = QGroupBox("Risk Metrics")
        risk_metrics_layout = QGridLayout()
        
        risk_metric_defs = [
            ("Volatility (Annual)", "volatility_annual", "{:.2f}%"),
            ("VaR (95%)", "var_95", "$ {:,.2f}"),
            ("CVaR (95%)", "cvar_95", "$ {:,.2f}"),
            ("Skewness", "skewness", "{:.3f}"),
            ("Kurtosis", "kurtosis", "{:.3f}"),
        ]
        
        self.risk_metric_labels = {}
        for i, (label, key, fmt) in enumerate(risk_metric_defs):
            row = i // 3
            col = (i % 3) * 2
            
            risk_metrics_layout.addWidget(QLabel(f"{label}:"), row, col)
            value_label = QLabel("-")
            value_label.setStyleSheet("font-weight: bold;")
            risk_metrics_layout.addWidget(value_label, row, col + 1)
            self.risk_metric_labels[key] = value_label
        
        risk_metrics_group.setLayout(risk_metrics_layout)
        layout.addWidget(risk_metrics_group)
        
        self.tab_widget.addTab(tab, "Risk")
    
    def create_period_tab(self):
        """Create Period tab with monthly returns heatmap."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # Monthly returns heatmap
        heatmap_group = QGroupBox("Monthly Returns Heatmap")
        heatmap_layout = QVBoxLayout()
        
        self.period_figure = Figure(figsize=(10, 6), dpi=100)
        self.period_canvas = FigureCanvas(self.period_figure)
        self.period_toolbar = NavigationToolbar(self.period_canvas, self)
        
        heatmap_layout.addWidget(self.period_toolbar)
        heatmap_layout.addWidget(self.period_canvas)
        heatmap_group.setLayout(heatmap_layout)
        layout.addWidget(heatmap_group)
        
        # Period summary
        summary_group = QGroupBox("Period Summary")
        summary_layout = QGridLayout()
        
        self.period_labels = {
            "best_month": QLabel("-"),
            "worst_month": QLabel("-"),
            "positive_months": QLabel("-"),
            "negative_months": QLabel("-"),
        }
        
        summary_layout.addWidget(QLabel("Best Month:"), 0, 0)
        summary_layout.addWidget(self.period_labels["best_month"], 0, 1)
        
        summary_layout.addWidget(QLabel("Worst Month:"), 0, 2)
        summary_layout.addWidget(self.period_labels["worst_month"], 0, 3)
        
        summary_layout.addWidget(QLabel("Positive Months:"), 1, 0)
        summary_layout.addWidget(self.period_labels["positive_months"], 1, 1)
        
        summary_layout.addWidget(QLabel("Negative Months:"), 1, 2)
        summary_layout.addWidget(self.period_labels["negative_months"], 1, 3)
        
        summary_group.setLayout(summary_layout)
        layout.addWidget(summary_group)
        
        self.tab_widget.addTab(tab, "Period")
    
    def create_trades_tab(self):
        """Create Trades tab with table of all trades using QSplitter."""
        tab = QWidget()
        main_layout = QVBoxLayout(tab)
        
        # Create vertical splitter for table (top) and stats (bottom)
        splitter = QSplitter(Qt.Vertical)
        
        # Top: Trade History table
        table_group = QGroupBox("Trade History")
        table_layout = QVBoxLayout()
        
        self.trades_table = QTableWidget()
        self.trades_table.setColumnCount(8)
        self.trades_table.setHorizontalHeaderLabels([
            "Entry Time", "Exit Time", "Side", "Entry Price",
            "Exit Price", "PnL", "Bars Held", "Return %"
        ])
        self.trades_table.setSortingEnabled(True)
        self.trades_table.setAlternatingRowColors(True)
        self.trades_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        # Apply dark theme styling
        self.trades_table.setStyleSheet("""
            QTableWidget {
                background-color: #1E1E1E;
                alternate-background-color: #2A2A2A;
                gridline-color: #2A2A2A;
                border: 1px solid #2A2A2A;
                border-radius: 3px;
                font-size: 10px;
                color: #E6E6E6;
            }
            QHeaderView::section {
                background-color: #2A2A2A;
                padding: 4px;
                border: 1px solid #2A2A2A;
                font-weight: bold;
                color: #E6E6E6;
                font-size: 10px;
            }
            QTableView QTableCornerButton::section {
                background-color: #2A2A2A;
                border: 1px solid #2A2A2A;
            }
            QTableWidget::item {
                padding: 2px;
            }
            QTableWidget::item:selected {
                background-color: rgba(47, 128, 237, 0.3);
                color: #E6E6E6;
            }
        """)
        
        table_layout.addWidget(self.trades_table)
        table_group.setLayout(table_layout)
        
        # Bottom: Trade Statistics
        stats_group = QGroupBox("Trade Statistics")
        stats_layout = QGridLayout()
        
        self.trade_stats_labels = {
            "total_trades": QLabel("-"),
            "winning_trades": QLabel("-"),
            "losing_trades": QLabel("-"),
            "win_rate": QLabel("-"),
            "avg_win": QLabel("-"),
            "avg_loss": QLabel("-"),
            "largest_win": QLabel("-"),
            "largest_loss": QLabel("-"),
        }
        
        stats = [
            ("Total Trades", "total_trades"),
            ("Winning Trades", "winning_trades"),
            ("Losing Trades", "losing_trades"),
            ("Win Rate", "win_rate"),
            ("Avg Win", "avg_win"),
            ("Avg Loss", "avg_loss"),
            ("Largest Win", "largest_win"),
            ("Largest Loss", "largest_loss"),
        ]
        
        for i, (label, key) in enumerate(stats):
            row = i // 4
            col = (i % 4) * 2
            
            label_widget = QLabel(f"{label}:")
            label_widget.setStyleSheet("color: #9A9A9A;")
            stats_layout.addWidget(label_widget, row, col)
            stats_layout.addWidget(self.trade_stats_labels[key], row, col + 1)
        
        stats_group.setLayout(stats_layout)
        
        # Add widgets to splitter
        splitter.addWidget(table_group)
        splitter.addWidget(stats_group)
        
        # Set stretch factors (4:1 ratio)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 1)
        
        # Set initial sizes
        splitter.setSizes([600, 150])
        
        main_layout.addWidget(splitter)
        
        self.tab_widget.addTab(tab, "Trades")
    
    def set_report_loaded(self, loaded: bool):
        """Set whether a report is loaded (show placeholder or content)."""
        # Always keep tabs enabled
        self.tab_widget.setEnabled(True)
        
        # Update status label
        if loaded:
            self.status_label.setText(f"Loaded strategy result: {self.artifact_path.name if self.artifact_path else 'Unknown'}")
            self.status_label.setStyleSheet("color: #4caf50;")
        else:
            self.status_label.setText("No analysis results. Run Analysis to see strategy report.")
            self.status_label.setStyleSheet("color: #9A9A9A; font-style: italic;")
        
        # Show placeholder or content based on loaded state
        # For now, we'll just update the UI which handles empty states
        self.update_ui()
    
    def load_artifact(self, artifact_path: Path) -> bool:
        """
        Load strategy result data from directory.
        
        Returns True if successful (even for partial runs with metrics.json),
        False only for truly invalid runs (missing metrics.json, corrupt JSON, non-existent path).
        """
        try:
            # Check if directory exists
            if not artifact_path.exists():
                self.status_label.setText(f"Run directory does not exist: {artifact_path}")
                self.status_label.setStyleSheet("color: #f44336;")
                return False
            
            # Check for metrics.json (minimum requirement for partial runs)
            metrics_path = artifact_path / "metrics.json"
            if not metrics_path.exists():
                self.status_label.setText(f"No metrics.json found in {artifact_path.name}")
                self.status_label.setStyleSheet("color: #f44336;")
                return False
            
            # Try to load metrics.json to ensure it's valid
            try:
                with open(metrics_path, "r", encoding="utf-8") as f:
                    self.metrics = json.load(f)
            except Exception as e:
                self.status_label.setText(f"Invalid metrics.json: {str(e)}")
                self.status_label.setStyleSheet("color: #f44336;")
                return False
            
            self.artifact_path = artifact_path
            
            # Load other files if they exist (tolerant loading)
            # Load trades.parquet
            trades_path = artifact_path / "trades.parquet"
            if trades_path.exists() and trades_path.stat().st_size > 0:
                try:
                    self.trades_df = pd.read_parquet(trades_path)
                except Exception as e:
                    logger.warning(f"Failed to load trades.parquet from {artifact_path}: {e}")
                    self.trades_df = None
            
            # Load equity.parquet
            equity_path = artifact_path / "equity.parquet"
            if equity_path.exists() and equity_path.stat().st_size > 0:
                try:
                    self.equity_df = pd.read_parquet(equity_path)
                except Exception as e:
                    logger.warning(f"Failed to load equity.parquet from {artifact_path}: {e}")
                    self.equity_df = None
            
            # Load report.json
            report_path = artifact_path / "report.json"
            if report_path.exists():
                try:
                    with open(report_path, "r", encoding="utf-8") as f:
                        self.report = json.load(f)
                except Exception as e:
                    logger.warning(f"Failed to load report.json from {artifact_path}: {e}")
                    self.report = {}
            
            # Update UI and set report loaded
            self.update_ui()
            
            # Determine if this is a partial or full load
            has_equity_or_trades = (self.equity_df is not None and not self.equity_df.empty) or \
                                  (self.trades_df is not None and not self.trades_df.empty)
            
            if has_equity_or_trades or self.report:
                self.set_report_loaded(True)
                self.status_label.setText(f"Loaded strategy result: {artifact_path.name}")
                self.status_label.setStyleSheet("color: #4caf50;")
            else:
                # Partial run - only metrics available
                self.set_report_loaded(True)  # Still show as loaded, but with limited data
                self.status_label.setText(f"Loaded partial run (metrics only): {artifact_path.name}")
                self.status_label.setStyleSheet("color: #ff9800;")
            
            self.artifact_loaded.emit(str(artifact_path))
            return True
            
        except Exception as e:
            logger.error(f"Failed to load strategy result {artifact_path}: {e}")
            self.status_label.setText(f"Error loading strategy result: {str(e)}")
            self.status_label.setStyleSheet("color: #f44336;")
            return False
    
    def _get_metric(self, key):
        """Return metric value from metrics.json or report.json, or None if missing."""
        # Try metrics dict first
        if key in self.metrics:
            val = self.metrics[key]
            if val is not None:
                return val
        # Try report metrics
        if self.report and "metrics" in self.report:
            val = self.report["metrics"].get(key)
            if val is not None:
                return val
        # Not found
        return None

    def update_ui(self):
        """Update all UI components with loaded data."""
        self.update_dashboard()
        self.update_risk_tab()
        self.update_period_tab()
        self.update_trades_tab()
    
    def update_dashboard(self):
        """Update dashboard tab with equity curve, KPI cards, and metrics."""
        # Clear previous plots
        self.dashboard_figure.clear()
        
        # Plot equity curve if available
        if self.equity_df is not None and not self.equity_df.empty:
            ax = self.dashboard_figure.add_subplot(111)
            ax.set_facecolor('#121212')
            self.dashboard_figure.patch.set_facecolor('#121212')
            
            # Plot equity
            ax.plot(self.equity_df["ts"], self.equity_df["equity"],
                   linewidth=2, color="#2F80ED", label="Equity")
            
            # Add buy & hold baseline if available
            if "buy_hold" in self.equity_df.columns:
                ax.plot(self.equity_df["ts"], self.equity_df["buy_hold"],
                       linewidth=1, color="#A8A8A8", linestyle="--", label="Buy & Hold", alpha=0.7)
            
            # Formatting - dark theme
            ax.set_title("Equity Curve", fontsize=12, fontweight="bold", color="#E6E6E6")
            ax.set_xlabel("Date", color="#A8A8A8", fontsize=10)
            ax.set_ylabel("Equity ($)", color="#A8A8A8", fontsize=10)
            ax.grid(True, alpha=0.2, color="#2A2A2A")
            ax.legend(facecolor='#1E1E1E', edgecolor='#2A2A2A', labelcolor='#E6E6E6')
            ax.tick_params(colors='#A8A8A8')
            
            # Set spine colors
            for spine in ax.spines.values():
                spine.set_color('#2A2A2A')
            
            # Format x-axis dates
            self.dashboard_figure.autofmt_xdate()
        
        self.dashboard_canvas.draw()
        
        # Update metrics - only the ones we're displaying
        metrics_to_display = {}
        for key in ["net_profit", "max_dd", "sharpe", "profit_factor", "win_rate", "sqn", "trades"]:
            metrics_to_display[key] = self._get_metric(key)
        
        # Format and display metrics
        formats = {
            "net_profit": "${:,.2f}",
            "max_dd": "${:,.2f}",
            "sharpe": "{:.2f}",
            "profit_factor": "{:.2f}",
            "win_rate": "{:.1f}%",
            "sqn": "{:.2f}",
            "trades": "{:,}",
        }
        
        for key, label in self.metric_labels.items():
            value = metrics_to_display.get(key)
            fmt = formats.get(key, "{}")
            if value is None:
                label.setText("N/A")
            else:
                try:
                    label.setText(fmt.format(value))
                except (ValueError, KeyError):
                    label.setText(str(value))
        
        # Update KPI cards
        kpi_values = {
            "net_profit": metrics_to_display.get("net_profit"),
            "max_dd": metrics_to_display.get("max_dd"),
            "win_rate": metrics_to_display.get("win_rate"),
            "trades": metrics_to_display.get("trades"),
        }
        
        kpi_formats = {
            "net_profit": "${:,.2f}",
            "max_dd": "${:,.2f}",
            "win_rate": "{:.1f}%",
            "trades": "{:,}",
        }
        
        for key, card in self.kpi_cards.items():
            value = kpi_values.get(key)
            fmt = kpi_formats.get(key, "{}")
            if value is None:
                card.value_label.setText("N/A")
            else:
                try:
                    card.value_label.setText(fmt.format(value))
                except (ValueError, KeyError):
                    card.value_label.setText("—")
    
    def update_risk_tab(self):
        """Update risk tab with underwater plot and PnL histogram."""
        # Clear previous plots
        self.risk_figure.clear()
        
        if self.equity_df is not None and not self.equity_df.empty:
            # Create 2 subplots
            ax1 = self.risk_figure.add_subplot(211)
            ax2 = self.risk_figure.add_subplot(212)
            
            # 1. Underwater plot (drawdown)
            if "drawdown" in self.equity_df.columns:
                drawdown = self.equity_df["drawdown"] * 100  # Convert to percentage
                ax1.fill_between(self.equity_df["ts"], drawdown, 0,
                               where=drawdown < 0, color="#f44336", alpha=0.7)
                ax1.plot(self.equity_df["ts"], drawdown, color="#d32f2f", linewidth=1)
                ax1.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
                ax1.set_title("Underwater Plot (Drawdown)", fontsize=14, fontweight="bold")
                ax1.set_ylabel("Drawdown (%)", fontsize=12)
                ax1.grid(True, alpha=0.3)
            
            # 2. PnL histogram
            if self.trades_df is not None and not self.trades_df.empty:
                pnl = self.trades_df["pnl"]
                colors = ["#4caf50" if x >= 0 else "#f44336" for x in pnl]
                ax2.hist(pnl, bins=20, color=colors, edgecolor='black', alpha=0.7)
                ax2.axvline(x=0, color='black', linestyle='--', linewidth=1)
                ax2.set_title("PnL Distribution", fontsize=14, fontweight="bold")
                ax2.set_xlabel("PnL ($)", fontsize=12)
                ax2.set_ylabel("Frequency", fontsize=12)
                ax2.grid(True, alpha=0.3)
            
            self.risk_figure.tight_layout()
        
        self.risk_canvas.draw()
        
        # Update risk metrics
        if self.trades_df is not None and not self.trades_df.empty:
            pnl = self.trades_df["pnl"]
            
            # Calculate risk metrics
            risk_metrics = {
                "volatility_annual": self.report.get("analytics", {}).get("volatility_annual", 0),
                "var_95": float(np.percentile(pnl, 5)) if len(pnl) > 0 else 0,
                "cvar_95": float(pnl[pnl <= np.percentile(pnl, 5)].mean()) if len(pnl) > 0 else 0,
                "skewness": float(pnl.skew()) if len(pnl) > 0 else 0,
                "kurtosis": float(pnl.kurtosis()) if len(pnl) > 0 else 0,
            }
            
            # Format and display
            risk_formats = {
                "volatility_annual": "{:.2f}%",
                "var_95": "${:,.2f}",
                "cvar_95": "${:,.2f}",
                "skewness": "{:.3f}",
                "kurtosis": "{:.3f}",
            }
            
            for key, label in self.risk_metric_labels.items():
                value = risk_metrics.get(key, 0)
                fmt = risk_formats.get(key, "{}")
                try:
                    label.setText(fmt.format(value))
                except (ValueError, KeyError):
                    label.setText(str(value))
    
    def update_period_tab(self):
        """Update period tab with monthly returns heatmap."""
        # Clear previous plots
        self.period_figure.clear()
        
        if "monthly_returns" in self.report:
            monthly_returns = self.report["monthly_returns"]
            
            if monthly_returns:
                # Prepare data for heatmap
                years = sorted(set(int(k.split("-")[0]) for k in monthly_returns.keys()))
                months = list(range(1, 13))
                
                # Create matrix
                data = np.full((len(years), 12), np.nan)
                for key, value in monthly_returns.items():
                    year_str, month_str = key.split("-")
                    year_idx = years.index(int(year_str))
                    month_idx = int(month_str) - 1
                    data[year_idx, month_idx] = value
                
                # Create heatmap
                ax = self.period_figure.add_subplot(111)
                im = ax.imshow(data, cmap="RdYlGn", aspect="auto")
                
                # Set labels
                ax.set_xticks(range(12))
                ax.set_xticklabels(["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])
                ax.set_yticks(range(len(years)))
                ax.set_yticklabels([str(y) for y in years])
                
                # Add colorbar
                cbar = self.period_figure.colorbar(im, ax=ax)
                cbar.set_label("Return (%)", rotation=270, labelpad=15)
                
                # Add text annotations
                for i in range(len(years)):
                    for j in range(12):
                        value = data[i, j]
                        if not np.isnan(value):
                            color = "black" if abs(value) < 5 else "white"
                            ax.text(j, i, f"{value:.1f}%",
                                   ha="center", va="center", color=color, fontsize=8)
                
                ax.set_title("Monthly Returns Heatmap", fontsize=14, fontweight="bold")
                
                # Calculate period statistics
                returns_list = list(monthly_returns.values())
                if returns_list:
                    self.period_labels["best_month"].setText(f"{max(returns_list):.2f}%")
                    self.period_labels["worst_month"].setText(f"{min(returns_list):.2f}%")
                    self.period_labels["positive_months"].setText(
                        f"{sum(1 for r in returns_list if r > 0)} / {len(returns_list)}"
                    )
                    self.period_labels["negative_months"].setText(
                        f"{sum(1 for r in returns_list if r < 0)} / {len(returns_list)}"
                    )
        
        self.period_canvas.draw()
    
    def update_trades_tab(self):
        """Update trades tab with table and statistics."""
        if self.trades_df is not None and not self.trades_df.empty:
            # Populate table
            self.trades_table.setRowCount(len(self.trades_df))
            
            for i, (_, trade) in enumerate(self.trades_df.iterrows()):
                # Entry time
                entry_item = QTableWidgetItem(str(trade.get("entry_ts", "")))
                entry_item.setData(Qt.UserRole, trade.get("entry_ts"))
                self.trades_table.setItem(i, 0, entry_item)
                
                # Exit time
                exit_item = QTableWidgetItem(str(trade.get("exit_ts", "")))
                exit_item.setData(Qt.UserRole, trade.get("exit_ts"))
                self.trades_table.setItem(i, 1, exit_item)
                
                # Side
                side_item = QTableWidgetItem(str(trade.get("side", "")))
                side_item.setForeground(Qt.darkGreen if trade.get("side") == "LONG" else Qt.darkRed)
                self.trades_table.setItem(i, 2, side_item)
                
                # Entry price
                self.trades_table.setItem(i, 3, QTableWidgetItem(f"{trade.get('entry_px', 0):.2f}"))
                
                # Exit price
                self.trades_table.setItem(i, 4, QTableWidgetItem(f"{trade.get('exit_px', 0):.2f}"))
                
                # PnL
                pnl = trade.get("pnl", 0)
                pnl_item = QTableWidgetItem(f"{pnl:,.2f}")
                pnl_item.setForeground(Qt.darkGreen if pnl >= 0 else Qt.darkRed)
                self.trades_table.setItem(i, 5, pnl_item)
                
                # Bars held
                self.trades_table.setItem(i, 6, QTableWidgetItem(str(trade.get("bars_held", 0))))
                
                # Return %
                entry_px = trade.get("entry_px", 1)
                return_pct = (pnl / entry_px * 100) if entry_px != 0 else 0
                return_item = QTableWidgetItem(f"{return_pct:.2f}%")
                return_item.setForeground(Qt.darkGreen if return_pct >= 0 else Qt.darkRed)
                self.trades_table.setItem(i, 7, return_item)
            
            # Resize columns to content
            self.trades_table.resizeColumnsToContents()
            
            # Update trade statistics
            trade_stats = self.report.get("trade_statistics", {})
            if not trade_stats and not self.trades_df.empty:
                # Calculate statistics if not in report
                pnl = self.trades_df["pnl"]
                trade_stats = {
                    "total_trades": len(self.trades_df),
                    "winning_trades": int((pnl > 0).sum()),
                    "losing_trades": int((pnl < 0).sum()),
                    "win_rate": (pnl > 0).sum() / len(pnl) * 100 if len(pnl) > 0 else 0,
                    "avg_win": float(pnl[pnl > 0].mean()) if (pnl > 0).any() else 0,
                    "avg_loss": float(pnl[pnl < 0].mean()) if (pnl < 0).any() else 0,
                    "largest_win": float(pnl.max()),
                    "largest_loss": float(pnl.min()),
                }
            
            # Format and display statistics
            stat_formats = {
                "total_trades": "{:,}",
                "winning_trades": "{:,}",
                "losing_trades": "{:,}",
                "win_rate": "{:.1f}%",
                "avg_win": "${:,.2f}",
                "avg_loss": "${:,.2f}",
                "largest_win": "${:,.2f}",
                "largest_loss": "${:,.2f}",
            }
            
            for key, label in self.trade_stats_labels.items():
                value = trade_stats.get(key, 0)
                fmt = stat_formats.get(key, "{}")
                try:
                    label.setText(fmt.format(value))
                except (ValueError, KeyError):
                    label.setText(str(value))
    
    def clear(self):
        """Clear all data and reset UI."""
        self.artifact_path = None
        self.metrics = {}
        self.trades_df = None
        self.equity_df = None
        self.report = {}
        
        # Clear plots
        for fig in [self.dashboard_figure, self.risk_figure, self.period_figure]:
            fig.clear()
        
        # Clear tables
        if self.trades_table:
            self.trades_table.setRowCount(0)
        
        # Reset labels
        for label_dict in [self.metric_labels, self.risk_metric_labels,
                          self.period_labels, self.trade_stats_labels]:
            for label in label_dict.values():
                label.setText("-")
        
        # Reset KPI cards
        for card in self.kpi_cards.values():
            card.value_label.setText("—")
        
        # Update canvases
        for canvas in [self.dashboard_canvas, self.risk_canvas, self.period_canvas]:
            if canvas:
                canvas.draw()
        
        self.set_report_loaded(False)
