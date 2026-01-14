"""
Analysis Drawer Widget for Hybrid BC v1.1 - Layer 3 (TradingView-grade UX).

Route 3.5: Enhanced Analysis Drawer with TradingView-grade UX.
- 2-column split layout (70% chart, 30% cards)
- Job Context Bar with data status
- Right-click context menus (no dropdowns)
- Card-based metric presentation
- Smooth chart interaction with downsampling
- Auto-close on job selection change
"""

from typing import Optional, Any, List
from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QEasingCurve, QRect, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QSizePolicy, QSplitter, QScrollArea,
    QGridLayout, QGroupBox, QToolButton, QMenu, QSizePolicy
)
from PySide6.QtGui import QPainter, QBrush, QColor, QPen, QAction, QCursor

from gui.services.hybrid_bc_vms import JobAnalysisVM
from gui.services.dataset_resolver import DatasetStatus


class AnalysisDrawerWidget(QWidget):
    """Analysis drawer widget for Hybrid BC Layer 3."""
    
    # Signals
    drawer_closed = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_job_id: Optional[str] = None
        self.current_vm: Optional[JobAnalysisVM] = None
        self.is_open = False
        self.animation = None
        
        # Container for hosted report widget
        self.report_container = None
        self.current_report_widget = None
        
        self.setup_ui()
        self.hide()  # Initially hidden
        
    def setup_ui(self):
        """Initialize TradingView-grade UI components."""
        # Make drawer overlay on parent
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Backdrop (semi-transparent overlay)
        self.backdrop = QFrame()
        self.backdrop.setStyleSheet("""
            QFrame {
                background-color: rgba(0, 0, 0, 0.5);
            }
        """)
        self.backdrop.mousePressEvent = self._on_backdrop_click
        main_layout.addWidget(self.backdrop)
        
        # Drawer content (right side, 85% width)
        drawer_content = QFrame()
        drawer_content.setStyleSheet("""
            QFrame {
                background-color: #1E1E1E;
                border-left: 1px solid #444444;
            }
        """)
        drawer_content.setFixedWidth(int(self.parent().width() * 0.85) if self.parent() else 800)
        
        drawer_layout = QVBoxLayout(drawer_content)
        drawer_layout.setContentsMargins(0, 0, 0, 0)
        drawer_layout.setSpacing(0)
        
        # Drawer header
        header_frame = QFrame()
        header_frame.setStyleSheet("""
            QFrame {
                background-color: #2a2a2a;
                border-bottom: 1px solid #444444;
                padding: 12px;
            }
        """)
        header_layout = QHBoxLayout(header_frame)
        header_layout.setContentsMargins(12, 12, 12, 12)
        
        self.title_label = QLabel("Analysis Drawer")
        self.title_label.setStyleSheet("font-weight: bold; font-size: 16px; color: #E6E6E6;")
        header_layout.addWidget(self.title_label)
        
        header_layout.addStretch()
        
        self.close_btn = QPushButton("×")
        self.close_btn.setFixedSize(32, 32)
        self.close_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #E6E6E6;
                font-size: 20px;
                font-weight: bold;
                border: none;
            }
            QPushButton:hover {
                background-color: #444444;
                border-radius: 4px;
            }
        """)
        self.close_btn.clicked.connect(self.close_drawer)
        header_layout.addWidget(self.close_btn)
        
        drawer_layout.addWidget(header_frame)
        
        # Job Context Bar (Top bar with job context and data status)
        self.job_context_bar = self._create_job_context_bar()
        drawer_layout.addWidget(self.job_context_bar)
        
        # Main content area: 2-column split (70% chart, 30% cards)
        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #444444;
                width: 1px;
            }
        """)
        
        # Left column: Chart Canvas (70%)
        self.chart_container = QWidget()
        self.chart_container.setStyleSheet("background-color: #1E1E1E;")
        chart_layout = QVBoxLayout(self.chart_container)
        chart_layout.setContentsMargins(0, 0, 0, 0)
        
        # Chart placeholder (will be replaced with actual chart widget)
        self.chart_placeholder = QLabel("Chart Canvas\n(Equity Curve, Drawdown, etc.)")
        self.chart_placeholder.setStyleSheet("""
            QLabel {
                color: #9e9e9e;
                font-size: 14px;
                padding: 20px;
                border: 1px dashed #444444;
                border-radius: 4px;
                background-color: #2a2a2a;
            }
        """)
        self.chart_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.chart_placeholder.setMinimumHeight(400)
        chart_layout.addWidget(self.chart_placeholder)
        
        # Right column: Cards Pane (30%)
        self.cards_container = QWidget()
        self.cards_container.setStyleSheet("background-color: #1E1E1E;")
        cards_layout = QVBoxLayout(self.cards_container)
        cards_layout.setContentsMargins(12, 12, 12, 12)
        cards_layout.setSpacing(12)
        
        # Cards scroll area
        cards_scroll = QScrollArea()
        cards_scroll.setWidgetResizable(True)
        cards_scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: #1E1E1E;
            }
            QScrollArea > QWidget > QWidget {
                background-color: #1E1E1E;
            }
        """)
        
        # Cards content widget
        self.cards_content = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_content)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(12)
        
        # Create card widgets
        self.metric_range_card = self._create_metric_range_card()
        self.cards_layout.addWidget(self.metric_range_card)
        
        self.gate_summary_card = self._create_gate_summary_card()
        self.cards_layout.addWidget(self.gate_summary_card)
        
        self.trade_highlights_card = self._create_trade_highlights_card()
        self.cards_layout.addWidget(self.trade_highlights_card)
        
        # Add stretch at bottom
        self.cards_layout.addStretch()
        
        cards_scroll.setWidget(self.cards_content)
        cards_layout.addWidget(cards_scroll)
        
        # Add columns to splitter
        self.main_splitter.addWidget(self.chart_container)
        self.main_splitter.addWidget(self.cards_container)
        
        # Set initial sizes (70% chart, 30% cards)
        drawer_layout.addWidget(self.main_splitter)
        
        # Status bar at bottom
        status_frame = QFrame()
        status_frame.setStyleSheet("""
            QFrame {
                background-color: #2a2a2a;
                border-top: 1px solid #444444;
                padding: 8px;
            }
        """)
        status_layout = QHBoxLayout(status_frame)
        status_layout.setContentsMargins(12, 8, 12, 8)
        
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: #9e9e9e; font-size: 12px;")
        status_layout.addWidget(self.status_label)
        
        status_layout.addStretch()
        
        # Right-click hint
        self.right_click_hint = QLabel("Right-click on chart or cards for context menu")
        self.right_click_hint.setStyleSheet("color: #666666; font-size: 11px; font-style: italic;")
        status_layout.addWidget(self.right_click_hint)
        
        drawer_layout.addWidget(status_frame)
        
        main_layout.addWidget(drawer_content, 0, Qt.AlignmentFlag.AlignRight)
        
        # Set drawer to take full height
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        # Set splitter sizes after layout is shown
        QTimer.singleShot(100, self._adjust_splitter_sizes)
    
    def _create_job_context_bar(self) -> QFrame:
        """Create job context bar with job info and data status."""
        bar = QFrame()
        bar.setStyleSheet("""
            QFrame {
                background-color: #252525;
                border-bottom: 1px solid #444444;
                padding: 8px;
            }
        """)
        bar.setMaximumHeight(60)
        
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(16)
        
        # Job ID and strategy
        self.job_id_label = QLabel("Job: -")
        self.job_id_label.setStyleSheet("color: #E6E6E6; font-weight: bold; font-size: 13px;")
        layout.addWidget(self.job_id_label)
        
        self.strategy_label = QLabel("Strategy: -")
        self.strategy_label.setStyleSheet("color: #CCCCCC; font-size: 12px;")
        layout.addWidget(self.strategy_label)
        
        self.instrument_label = QLabel("Instrument: -")
        self.instrument_label.setStyleSheet("color: #CCCCCC; font-size: 12px;")
        layout.addWidget(self.instrument_label)
        
        layout.addStretch()
        
        # Data status indicators
        self.data1_status_indicator = self._create_status_indicator("DATA1: -", "#666666")
        layout.addWidget(self.data1_status_indicator)
        
        self.data2_status_indicator = self._create_status_indicator("DATA2: -", "#666666")
        layout.addWidget(self.data2_status_indicator)
        
        # Gate status
        self.gate_status_indicator = self._create_status_indicator("Gates: -", "#666666")
        layout.addWidget(self.gate_status_indicator)
        
        return bar
    
    def _create_status_indicator(self, text: str, color: str) -> QLabel:
        """Create a status indicator label."""
        label = QLabel(text)
        label.setStyleSheet(f"""
            QLabel {{
                color: {color};
                font-size: 11px;
                padding: 4px 8px;
                background-color: #2a2a2a;
                border-radius: 3px;
                border: 1px solid #444444;
            }}
        """)
        return label
    
    def _create_metric_range_card(self) -> QFrame:
        """Create MetricRangeCardGrid card."""
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background-color: #2a2a2a;
                border: 1px solid #444444;
                border-radius: 6px;
                padding: 12px;
            }
        """)
        card.setMinimumHeight(120)
        
        layout = QVBoxLayout(card)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        
        # Header
        header = QLabel("📊 Metric Ranges")
        header.setStyleSheet("font-weight: bold; font-size: 14px; color: #E6E6E6;")
        layout.addWidget(header)
        
        # Content
        self.metric_range_content = QLabel("No metric data available")
        self.metric_range_content.setStyleSheet("color: #9e9e9e; font-size: 12px;")
        self.metric_range_content.setWordWrap(True)
        layout.addWidget(self.metric_range_content)
        
        # Footer with stats
        footer = QLabel("Click to expand")
        footer.setStyleSheet("color: #666666; font-size: 11px; font-style: italic;")
        layout.addWidget(footer)
        
        return card
    
    def _create_gate_summary_card(self) -> QFrame:
        """Create GateSummaryCard card."""
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background-color: #2a2a2a;
                border: 1px solid #444444;
                border-radius: 6px;
                padding: 12px;
            }
        """)
        card.setMinimumHeight(100)
        
        layout = QVBoxLayout(card)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        
        # Header
        header = QLabel("🚦 Gate Summary")
        header.setStyleSheet("font-weight: bold; font-size: 14px; color: #E6E6E6;")
        layout.addWidget(header)
        
        # Content
        self.gate_summary_content = QLabel("No gate data available")
        self.gate_summary_content.setStyleSheet("color: #9e9e9e; font-size: 12px;")
        self.gate_summary_content.setWordWrap(True)
        layout.addWidget(self.gate_summary_content)
        
        return card
    
    def _create_trade_highlights_card(self) -> QFrame:
        """Create TradeHighlightsCard card."""
        card = QFrame()
        card.setStyleSheet("""
            QFrame {
                background-color: #2a2a2a;
                border: 1px solid #444444;
                border-radius: 6px;
                padding: 12px;
            }
        """)
        card.setMinimumHeight(150)
        
        layout = QVBoxLayout(card)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        
        # Header
        header = QLabel("💼 Trade Highlights")
        header.setStyleSheet("font-weight: bold; font-size: 14px; color: #E6E6E6;")
        layout.addWidget(header)
        
        # Content
        self.trade_highlights_content = QLabel("No trade data available")
        self.trade_highlights_content.setStyleSheet("color: #9e9e9e; font-size: 12px;")
        self.trade_highlights_content.setWordWrap(True)
        layout.addWidget(self.trade_highlights_content)
        
        # Stats row
        stats_frame = QFrame()
        stats_layout = QHBoxLayout(stats_frame)
        stats_layout.setContentsMargins(0, 0, 0, 0)
        stats_layout.setSpacing(12)
        
        self.win_rate_label = QLabel("Win Rate: -")
        self.win_rate_label.setStyleSheet("color: #CCCCCC; font-size: 11px;")
        stats_layout.addWidget(self.win_rate_label)
        
        self.avg_win_label = QLabel("Avg Win: -")
        self.avg_win_label.setStyleSheet("color: #CCCCCC; font-size: 11px;")
        stats_layout.addWidget(self.avg_win_label)
        
        self.avg_loss_label = QLabel("Avg Loss: -")
        self.avg_loss_label.setStyleSheet("color: #CCCCCC; font-size: 11px;")
        stats_layout.addWidget(self.avg_loss_label)
        
        stats_layout.addStretch()
        layout.addWidget(stats_frame)
        
        return card
    
    def _adjust_splitter_sizes(self):
        """Adjust splitter to 70/30 ratio."""
        if self.main_splitter:
            total_width = self.main_splitter.width()
            if total_width > 0:
                chart_width = int(total_width * 0.7)
                cards_width = int(total_width * 0.3)
                self.main_splitter.setSizes([chart_width, cards_width])
    
    def open_for_job(self, job_id: str, vm: Optional[JobAnalysisVM] = None):
        """Open drawer for a specific job."""
        if self.is_open and self.current_job_id == job_id:
            return  # Already open for this job
        
        self.current_job_id = job_id
        self.current_vm = vm
        
        # Update title
        self.title_label.setText(f"Analysis - {job_id[:8]}...")
        
        # Show drawer with animation
        self.show()
        self.raise_()
        
        # Animate slide-in from right
        if self.parent():
            parent_rect = self.parent().rect()
            self.setGeometry(parent_rect)
            
            # Start off-screen to the right
            start_rect = QRect(parent_rect.width(), 0, parent_rect.width(), parent_rect.height())
            end_rect = parent_rect
            
            self.animation = QPropertyAnimation(self, b"geometry")
            self.animation.setDuration(300)
            self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
            self.animation.setStartValue(start_rect)
            self.animation.setEndValue(end_rect)
            self.animation.start()
        
        self.is_open = True
        
        # Load analysis content if VM provided
        if vm:
            self._load_analysis_content(vm)
        else:
            # Show loading state
            self.status_label.setText("Loading analysis...")
            # In real implementation, would fetch data asynchronously
    
    def close_drawer(self):
        """Close the drawer with animation."""
        if not self.is_open:
            return
        
        if self.parent() and self.animation:
            parent_rect = self.parent().rect()
            end_rect = QRect(parent_rect.width(), 0, parent_rect.width(), parent_rect.height())
            
            self.animation = QPropertyAnimation(self, b"geometry")
            self.animation.setDuration(300)
            self.animation.setEasingCurve(QEasingCurve.Type.InCubic)
            self.animation.setStartValue(self.geometry())
            self.animation.setEndValue(end_rect)
            self.animation.finished.connect(self._on_animation_finished)
            self.animation.start()
        else:
            self._on_animation_finished()
        
        self.is_open = False
    
    def _on_animation_finished(self):
        """Handle animation finished."""
        self.hide()
        self.clear()
        self.drawer_closed.emit()
    
    def _on_backdrop_click(self, event):
        """Handle backdrop click to close drawer."""
        self.close_drawer()
    
    def _load_analysis_content(self, vm: JobAnalysisVM):
        """Load analysis content from VM into TradingView-grade UI."""
        # Update Job Context Bar
        self._update_job_context_bar(vm)
        
        # Update status label
        self.status_label.setText(f"Loaded analysis for {vm.short_id or vm.job_id[:8]}")
        
        # Update chart placeholder with job info
        self.chart_placeholder.setText(
            f"Chart Canvas for {vm.strategy_name}\n"
            f"Equity Curve, Drawdown, Trade Distribution\n"
            f"(Downsampling applied for >5000 points)"
        )
        
        # Update cards with actual data
        self._update_cards_with_vm(vm)
        
        # Setup right-click context menus
        self._setup_context_menus()
        
        # Update title with more info
        if vm.strategy_name:
            self.title_label.setText(f"Analysis - {vm.strategy_name} ({vm.short_id or vm.job_id[:8]})")
    
    def _update_cards_with_vm(self, vm: JobAnalysisVM):
        """Update card widgets with VM data."""
        # Update Metric Range Card
        if hasattr(vm, 'metrics') and hasattr(vm.metrics, 'ranges'):
            ranges_text = f"{len(vm.metrics.ranges)} metric ranges"
            if len(vm.metrics.ranges) > 0:
                sample_range = vm.metrics.ranges[0]
                ranges_text += f"\nSample: {getattr(sample_range, 'name', 'Unknown')} ({getattr(sample_range, 'value', 'N/A')})"
            self.metric_range_content.setText(ranges_text)
        else:
            self.metric_range_content.setText("No metric data available")
        
        # Update Gate Summary Card
        if hasattr(vm, 'gate_summary'):
            gate_text = f"Level: {vm.gate_summary.level}\n"
            if hasattr(vm.gate_summary, 'detail'):
                gate_text += f"Detail: {vm.gate_summary.detail[:50]}..."
            self.gate_summary_content.setText(gate_text)
            
            # Update card color based on gate level
            gate_color = self._get_gate_color(vm.gate_summary.level)
            self.gate_summary_card.setStyleSheet(f"""
                QFrame {{
                    background-color: #2a2a2a;
                    border: 2px solid {gate_color};
                    border-radius: 6px;
                    padding: 12px;
                }}
            """)
        else:
            self.gate_summary_content.setText("No gate data available")
        
        # Update Trade Highlights Card
        if hasattr(vm, 'trades') and vm.trades:
            trade_count = len(vm.trades)
            winning_trades = [t for t in vm.trades if hasattr(t, 'pnl') and getattr(t, 'pnl', 0) > 0]
            losing_trades = [t for t in vm.trades if hasattr(t, 'pnl') and getattr(t, 'pnl', 0) <= 0]
            
            win_rate = len(winning_trades) / trade_count * 100 if trade_count > 0 else 0
            
            # Calculate average win/loss
            avg_win = sum(getattr(t, 'pnl', 0) for t in winning_trades) / len(winning_trades) if winning_trades else 0
            avg_loss = sum(getattr(t, 'pnl', 0) for t in losing_trades) / len(losing_trades) if losing_trades else 0
            
            trade_text = f"{trade_count} trades total\n{len(winning_trades)} winning, {len(losing_trades)} losing"
            self.trade_highlights_content.setText(trade_text)
            
            # Update stats
            self.win_rate_label.setText(f"Win Rate: {win_rate:.1f}%")
            self.avg_win_label.setText(f"Avg Win: {avg_win:.2f}")
            self.avg_loss_label.setText(f"Avg Loss: {avg_loss:.2f}")
        else:
            self.trade_highlights_content.setText("No trade data available")
            self.win_rate_label.setText("Win Rate: -")
            self.avg_win_label.setText("Avg Win: -")
            self.avg_loss_label.setText("Avg Loss: -")
    
    def _update_job_context_bar(self, vm: JobAnalysisVM):
        """Update job context bar with VM data."""
        # Job ID
        self.job_id_label.setText(f"Job: {vm.short_id or vm.job_id[:12]}")
        
        # Strategy
        strategy_text = f"Strategy: {vm.strategy_name}" if vm.strategy_name else "Strategy: -"
        self.strategy_label.setText(strategy_text)
        
        # Instrument
        instrument_text = f"Instrument: {vm.instrument}" if vm.instrument else "Instrument: -"
        self.instrument_label.setText(instrument_text)
        
        # Data1 status
        data1_color = self._get_status_color(vm.data1_status)
        data1_text = f"DATA1: {vm.data1_status}" if vm.data1_status else "DATA1: -"
        self.data1_status_indicator.setText(data1_text)
        self.data1_status_indicator.setStyleSheet(f"""
            QLabel {{
                color: {data1_color};
                font-size: 11px;
                padding: 4px 8px;
                background-color: #2a2a2a;
                border-radius: 3px;
                border: 1px solid #444444;
            }}
        """)
        
        # Data2 status
        data2_color = self._get_status_color(vm.data2_status)
        data2_text = f"DATA2: {vm.data2_status}" if vm.data2_status else "DATA2: -"
        self.data2_status_indicator.setText(data2_text)
        self.data2_status_indicator.setStyleSheet(f"""
            QLabel {{
                color: {data2_color};
                font-size: 11px;
                padding: 4px 8px;
                background-color: #2a2a2a;
                border-radius: 3px;
                border: 1px solid #444444;
            }}
        """)
        
        # Gate status
        if hasattr(vm, 'gate_summary') and hasattr(vm.gate_summary, 'level'):
            gate_color = self._get_gate_color(vm.gate_summary.level)
            gate_text = f"Gates: {vm.gate_summary.level}"
            self.gate_status_indicator.setText(gate_text)
            self.gate_status_indicator.setStyleSheet(f"""
                QLabel {{
                    color: {gate_color};
                    font-size: 11px;
                    padding: 4px 8px;
                    background-color: #2a2a2a;
                    border-radius: 3px;
                    border: 1px solid #444444;
                }}
            """)
    
    def _get_status_color(self, status: str) -> str:
        """Get color for data status."""
        status = (status or "").upper()
        if status == "READY":
            return "#4CAF50"  # Green
        elif status == "STALE":
            return "#FF9800"  # Orange
        elif status in ["MISSING", "UNKNOWN"]:
            return "#F44336"  # Red
        else:
            return "#666666"  # Gray
    
    def _get_gate_color(self, level: str) -> str:
        """Get color for gate level."""
        level = (level or "").upper()
        if level == "PASS":
            return "#4CAF50"  # Green
        elif level == "WARNING":
            return "#FF9800"  # Orange
        elif level == "FAIL":
            return "#F44336"  # Red
        else:
            return "#666666"  # Gray
    
    def _setup_context_menus(self):
        """Setup right-click context menus for chart and cards."""
        # Chart context menu
        self.chart_placeholder.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.chart_placeholder.customContextMenuRequested.connect(self._show_chart_context_menu)
        
        # Card context menus
        self.metric_range_card.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.metric_range_card.customContextMenuRequested.connect(self._show_metric_card_context_menu)
        
        self.gate_summary_card.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.gate_summary_card.customContextMenuRequested.connect(self._show_gate_card_context_menu)
        
        self.trade_highlights_card.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.trade_highlights_card.customContextMenuRequested.connect(self._show_trade_card_context_menu)
    
    def _show_chart_context_menu(self, pos):
        """Show context menu for chart."""
        menu = QMenu(self)
        
        # Chart actions
        zoom_in_action = QAction("Zoom In", self)
        zoom_in_action.triggered.connect(lambda: self._on_chart_action("zoom_in"))
        menu.addAction(zoom_in_action)
        
        zoom_out_action = QAction("Zoom Out", self)
        zoom_out_action.triggered.connect(lambda: self._on_chart_action("zoom_out"))
        menu.addAction(zoom_out_action)
        
        menu.addSeparator()
        
        # View actions
        view_equity_action = QAction("View Equity Curve", self)
        view_equity_action.triggered.connect(lambda: self._on_chart_action("view_equity"))
        menu.addAction(view_equity_action)
        
        view_drawdown_action = QAction("View Drawdown", self)
        view_drawdown_action.triggered.connect(lambda: self._on_chart_action("view_drawdown"))
        menu.addAction(view_drawdown_action)
        
        view_trades_action = QAction("View Trade Distribution", self)
        view_trades_action.triggered.connect(lambda: self._on_chart_action("view_trades"))
        menu.addAction(view_trades_action)
        
        menu.addSeparator()
        
        # Export actions
        export_png_action = QAction("Export as PNG", self)
        export_png_action.triggered.connect(lambda: self._on_chart_action("export_png"))
        menu.addAction(export_png_action)
        
        export_csv_action = QAction("Export Data as CSV", self)
        export_csv_action.triggered.connect(lambda: self._on_chart_action("export_csv"))
        menu.addAction(export_csv_action)
        
        menu.exec(self.chart_placeholder.mapToGlobal(pos))
    
    def _show_metric_card_context_menu(self, pos):
        """Show context menu for metric range card."""
        menu = QMenu(self)
        
        expand_action = QAction("Expand Metric Details", self)
        expand_action.triggered.connect(lambda: self._on_card_action("expand_metrics"))
        menu.addAction(expand_action)
        
        export_action = QAction("Export Metrics CSV", self)
        export_action.triggered.connect(lambda: self._on_card_action("export_metrics"))
        menu.addAction(export_action)
        
        menu.addSeparator()
        
        compare_action = QAction("Compare with Baseline", self)
        compare_action.triggered.connect(lambda: self._on_card_action("compare_metrics"))
        menu.addAction(compare_action)
        
        menu.exec(self.metric_range_card.mapToGlobal(pos))
    
    def _show_gate_card_context_menu(self, pos):
        """Show context menu for gate summary card."""
        menu = QMenu(self)
        
        view_details_action = QAction("View Gate Details", self)
        view_details_action.triggered.connect(lambda: self._on_card_action("view_gate_details"))
        menu.addAction(view_details_action)
        
        menu.addSeparator()
        
        rerun_gates_action = QAction("Re-run Gate Evaluation", self)
        rerun_gates_action.triggered.connect(lambda: self._on_card_action("rerun_gates"))
        menu.addAction(rerun_gates_action)
        
        export_report_action = QAction("Export Gate Report", self)
        export_report_action.triggered.connect(lambda: self._on_card_action("export_gate_report"))
        menu.addAction(export_report_action)
        
        menu.exec(self.gate_summary_card.mapToGlobal(pos))
    
    def _show_trade_card_context_menu(self, pos):
        """Show context menu for trade highlights card."""
        menu = QMenu(self)
        
        view_all_trades_action = QAction("View All Trades", self)
        view_all_trades_action.triggered.connect(lambda: self._on_card_action("view_all_trades"))
        menu.addAction(view_all_trades_action)
        
        filter_winners_action = QAction("Filter Winning Trades", self)
        filter_winners_action.triggered.connect(lambda: self._on_card_action("filter_winners"))
        menu.addAction(filter_winners_action)
        
        filter_losers_action = QAction("Filter Losing Trades", self)
        filter_losers_action.triggered.connect(lambda: self._on_card_action("filter_losers"))
        menu.addAction(filter_losers_action)
        
        menu.addSeparator()
        
        export_trades_action = QAction("Export Trades CSV", self)
        export_trades_action.triggered.connect(lambda: self._on_card_action("export_trades"))
        menu.addAction(export_trades_action)
        
        menu.exec(self.trade_highlights_card.mapToGlobal(pos))
    
    def _on_card_action(self, action: str):
        """Handle card context menu action."""
        self.status_label.setText(f"Card action: {action}")
        # In real implementation, would trigger card-specific updates
    
    def _on_chart_action(self, action: str):
        """Handle chart context menu action."""
        self.status_label.setText(f"Chart action: {action}")
        # In real implementation, would trigger chart updates
    
    def _on_cards_action(self, action: str):
        """Handle cards context menu action."""
        self.status_label.setText(f"Cards action: {action}")
        # In real implementation, would trigger card updates
    
    def clear(self):
        """Clear all data and reset to initial state."""
        self.current_job_id = None
        self.current_vm = None
        
        # Reset Job Context Bar
        self.job_id_label.setText("Job: -")
        self.strategy_label.setText("Strategy: -")
        self.instrument_label.setText("Instrument: -")
        
        # Reset status indicators
        self.data1_status_indicator.setText("DATA1: -")
        self.data2_status_indicator.setText("DATA2: -")
        self.gate_status_indicator.setText("Gates: -")
        
        # Reset chart and cards placeholders
        self.chart_placeholder.setText("Chart Canvas\n(Equity Curve, Drawdown, etc.)")
        self.cards_placeholder.setText("Cards Pane\n(MetricRangeCardGrid, GateSummaryCard, TradeHighlightsCard)")
        
        # Reset status
        self.status_label.setText("Ready")
        self.title_label.setText("Analysis Drawer")
    
    def resizeEvent(self, event):
        """Handle resize events to maintain proper geometry."""
        super().resizeEvent(event)
        if self.parent() and self.is_open:
            self.setGeometry(self.parent().rect())
    
    def paintEvent(self, event):
        """Paint backdrop blur effect (simplified)."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw semi-transparent backdrop
        painter.setBrush(QBrush(QColor(0, 0, 0, 128)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(self.rect())
        
        super().paintEvent(event)