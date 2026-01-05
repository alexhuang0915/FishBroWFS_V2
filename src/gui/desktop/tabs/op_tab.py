"""
OP (Operator Console) Tab - Desktop replacement for Qt Desktop UI OP tab.
Phase 17B: Card-based, Task-oriented UI with 4 fixed cards.

Provides 1:1 semantic parity with historical Desktop UI OP flow.
"""

import logging
from pathlib import Path
from typing import Optional, List, Set, Dict
import datetime

from PySide6.QtCore import Qt, Signal, Slot, QThread
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QComboBox, QPushButton, QTextEdit, QProgressBar,
    QGroupBox, QFrame, QSplitter, QSizePolicy, QCheckBox,
    QScrollArea, QLineEdit
)
from PySide6.QtGui import QFont

from ..worker import BacktestWorker, BuildWorker, ArtifactWorker
from ..artifact_validation import (
    is_artifact_dir_name,
    validate_artifact_dir,
    find_latest_valid_artifact,
)
from ..analysis import AnalysisWidget
from ..styles.state_styles import set_widget_state, DISABLED_REASONS
from ..widgets.cleanup_dialog import CleanupDialog

# Import new run index resolver
try:
    from research.run_index import find_best_run, get_run_diagnostics
    RUN_INDEX_AVAILABLE = True
except ImportError:
    RUN_INDEX_AVAILABLE = False
    find_best_run = None
    get_run_diagnostics = None

# Import new services for OPEN RUN and CHECK buttons
try:
    from ..services.run_index_service import list_runs, pick_last_run, get_run_summary
    from ..services.data_readiness_service import check_all, Readiness
    RUN_SERVICES_AVAILABLE = True
except ImportError:
    RUN_SERVICES_AVAILABLE = False
    list_runs = None
    pick_last_run = None
    get_run_summary = None
    check_all = None
    Readiness = None

logger = logging.getLogger(__name__)


class OpTab(QWidget):
    """Operator Console tab - card-based research and artifact building interface."""
    
    # Signals for communication with main window
    log_signal = Signal(str)
    progress_signal = Signal(int)
    artifact_state_changed = Signal(str, str, str)  # state, run_id, run_dir
    
    def __init__(self):
        super().__init__()
        self.worker: Optional[BacktestWorker] = None
        self.worker_thread: Optional[QThread] = None
        self.current_result: Optional[dict] = None
        
        # State machine for artifact tracking
        self.artifact_state = "NONE"  # NONE, BUILDING, READY, FAILED
        self.artifact_run_id: Optional[str] = None
        self.artifact_run_dir: Optional[str] = None
        
        # Context feeds selection
        self.selected_context_feeds: Set[str] = set()
        self.context_feed_checkboxes: Dict[str, QCheckBox] = {}
        
        # Data2 preparation tracking
        self.data2_prepared_feeds: Set[str] = set()  # Tracks which Data2 feeds have been prepared
        
        # Cache status tracking
        self.bars_cache_status = "UNKNOWN"
        self.features_cache_status = "UNKNOWN"
        
        # Run tracking for robust discovery
        self.job_start_time_iso: Optional[str] = None
        
        self.setup_ui()
        self.load_datasets()
        self.load_context_feeds()
        self.setup_connections()
        self.update_cache_status()
    
    def setup_ui(self):
        """Initialize the UI components with 4-card layout and analytics suite."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)
        
        # Create main splitter (left: cards, right: analytics + log)
        main_splitter = QSplitter(Qt.Horizontal)
        main_splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #555555;
                width: 1px;
            }
            QSplitter::handle:hover {
                background-color: #3A8DFF;
            }
        """)
        
        # Left panel (4 Cards) - 25-30% width
        left_widget = QWidget()
        left_widget.setStyleSheet("background-color: #121212;")
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(4, 4, 4, 4)
        left_layout.setSpacing(6)
        
        # CARD 1 — What to Run
        card1 = self.create_card_what_to_run()
        left_layout.addWidget(card1)
        
        # CARD 2 — Context Feeds (Optional)
        card2 = self.create_card_context_feeds()
        left_layout.addWidget(card2)
        
        # CARD 3 — Prepare Data
        card3 = self.create_card_prepare_data()
        left_layout.addWidget(card3)
        
        # CARD 4 — Run & Publish
        card4 = self.create_card_run_publish()
        left_layout.addWidget(card4)
        
        left_layout.addStretch()
        
        # Right panel (Analytics + Log) - 70-75% width
        right_splitter = QSplitter(Qt.Vertical)
        right_splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #555555;
                height: 1px;
            }
            QSplitter::handle:hover {
                background-color: #3A8DFF;
            }
        """)
        
        # Analytics Suite (top) - charts dominate
        analytics_widget = QWidget()
        analytics_widget.setStyleSheet("background-color: #121212;")
        analytics_layout = QVBoxLayout(analytics_widget)
        analytics_layout.setContentsMargins(4, 4, 4, 4)
        analytics_layout.setSpacing(4)
        
        analytics_label = QLabel("Analytics Suite")
        analytics_label.setStyleSheet("font-size: 12px; font-weight: bold; color: #E6E6E6;")
        analytics_layout.addWidget(analytics_label)
        
        # Create analysis widget
        self.analysis_widget = AnalysisWidget()
        analytics_layout.addWidget(self.analysis_widget)
        
        # Log view (bottom) - collapsible, secondary
        log_widget = QWidget()
        log_widget.setStyleSheet("background-color: #121212;")
        log_layout = QVBoxLayout(log_widget)
        log_layout.setContentsMargins(4, 4, 4, 4)
        log_layout.setSpacing(4)
        
        # Log header with CLEAR button
        log_header = QWidget()
        log_header_layout = QHBoxLayout(log_header)
        log_header_layout.setContentsMargins(0, 0, 0, 0)
        log_header_layout.setSpacing(4)
        
        log_label = QLabel("Execution Log")
        log_label.setStyleSheet("font-weight: bold; color: #9A9A9A; font-size: 11px;")
        log_header_layout.addWidget(log_label)
        
        log_header_layout.addStretch()
        
        # CLEAR button (per spec)
        self.clear_log_btn = QPushButton("CLEAR")
        self.clear_log_btn.setToolTip("Clear visible log buffer only (does not touch disk logs)")
        self.clear_log_btn.setStyleSheet("""
            QPushButton {
                background-color: #2A2A2A;
                color: #E6E6E6;
                border: 1px solid #555555;
                border-radius: 3px;
                padding: 2px 8px;
                font-size: 10px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3A3A3A;
                border: 1px solid #3A8DFF;
            }
        """)
        log_header_layout.addWidget(self.clear_log_btn)
        
        log_layout.addWidget(log_header)
        
        # Log text view
        log_frame = QFrame()
        log_frame.setFrameStyle(QFrame.StyledPanel)
        log_frame.setStyleSheet("""
            QFrame {
                background-color: #1E1E1E;
                border: 1px solid #555555;
                border-radius: 3px;
            }
        """)
        log_frame_layout = QVBoxLayout(log_frame)
        log_frame_layout.setContentsMargins(0, 0, 0, 0)
        
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setFont(QFont("Monospace", 9))
        self.log_view.setStyleSheet("""
            QTextEdit {
                background-color: #1E1E1E;
                color: #E6E6E6;
                border: none;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 9px;
            }
        """)
        log_frame_layout.addWidget(self.log_view)
        log_layout.addWidget(log_frame)
        
        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #555555;
                border-radius: 3px;
                background-color: #2A2A2A;
                height: 6px;
            }
            QProgressBar::chunk {
                background-color: #3A8DFF;
                border-radius: 2px;
            }
        """)
        log_layout.addWidget(self.progress_bar)
        
        right_splitter.addWidget(analytics_widget)
        right_splitter.addWidget(log_widget)
        right_splitter.setSizes([600, 200])  # Charts dominate
        
        main_splitter.addWidget(left_widget)
        main_splitter.addWidget(right_splitter)
        main_splitter.setSizes([480, 1440])  # 25% left, 75% right for 1920px total
        
        main_layout.addWidget(main_splitter)
    
    def create_card_what_to_run(self) -> QGroupBox:
        """Create Card 1: What to Run."""
        card = QGroupBox("What to Run")
        card.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 2px solid #1a237e;
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
        
        layout = QGridLayout()
        layout.setVerticalSpacing(6)
        layout.setHorizontalSpacing(10)
        
        # Research Template (was Strategy Family)
        strategy_label = QLabel("Research Template:")
        strategy_label.setToolTip("Select research template to run")
        strategy_label.setStyleSheet("color: #9A9A9A;")
        layout.addWidget(strategy_label, 0, 0)
        
        self.strategy_cb = QComboBox()
        self.strategy_cb.addItems(["S1", "S2", "S3"])
        self.strategy_cb.setToolTip("Research template for analysis")
        self.strategy_cb.setStyleSheet("""
            QComboBox {
                background-color: #2A2A2A;
                border: 1px solid #555555;
                border-radius: 3px;
                padding: 4px;
                color: #E6E6E6;
                font-size: 11px;
                min-height: 24px;
            }
            QComboBox:hover {
                border: 1px solid #3A8DFF;
            }
        """)
        layout.addWidget(self.strategy_cb, 0, 1)
        
        # Market
        primary_market_label = QLabel("Primary Market:")
        primary_market_label.setToolTip("Main market to analyze")
        primary_market_label.setStyleSheet("color: #9A9A9A;")
        layout.addWidget(primary_market_label, 1, 0)
        
        self.primary_market_cb = QComboBox()
        self.primary_market_cb.setToolTip("Select market for analysis")
        self.primary_market_cb.setStyleSheet("""
            QComboBox {
                background-color: #2A2A2A;
                border: 1px solid #555555;
                border-radius: 3px;
                padding: 4px;
                color: #E6E6E6;
                font-size: 11px;
                min-height: 24px;
            }
            QComboBox:hover {
                border: 1px solid #3A8DFF;
            }
        """)
        layout.addWidget(self.primary_market_cb, 1, 1)
        
        # Timeframes (Multi-select)
        timeframe_label = QLabel("Timeframes:")
        timeframe_label.setToolTip("Analysis intervals (multiple allowed)")
        timeframe_label.setStyleSheet("color: #9A9A9A;")
        layout.addWidget(timeframe_label, 2, 0)
        
        # Timeframe selection widget
        timeframe_widget = QWidget()
        timeframe_layout = QVBoxLayout(timeframe_widget)
        timeframe_layout.setContentsMargins(0, 0, 0, 0)
        timeframe_layout.setSpacing(4)
        
        # Timeframe checkboxes
        self.timeframe_checkboxes = {}
        timeframe_options = ["15m", "30m", "60m", "120m", "240m"]
        
        for tf in timeframe_options:
            cb = QCheckBox(tf)
            cb.setChecked(tf == "60m")  # Default to 60m
            cb.stateChanged.connect(self.on_timeframe_changed)
            self.timeframe_checkboxes[tf] = cb
            timeframe_layout.addWidget(cb)
        
        # Timeframe summary label
        self.timeframe_summary_label = QLabel("Selected: 60m")
        self.timeframe_summary_label.setStyleSheet("color: #2F80ED; font-size: 10px; font-weight: bold;")
        timeframe_layout.addWidget(self.timeframe_summary_label)
        
        layout.addWidget(timeframe_widget, 2, 1)
        
        # Add dummy tf_cb for backward compatibility with tests
        self.tf_cb = QComboBox()
        self.tf_cb.addItems(timeframe_options)
        self.tf_cb.setVisible(False)  # Hide it since we're using checkboxes
        
        # Season
        season_label = QLabel("Season:")
        season_label.setToolTip("Trading season")
        season_label.setStyleSheet("color: #9A9A9A;")
        layout.addWidget(season_label, 3, 0)
        
        self.season_label = QLabel("2026Q1")
        self.season_label.setStyleSheet("font-weight: bold; color: #E6E6E6;")
        self.season_label.setToolTip("Current season")
        layout.addWidget(self.season_label, 3, 1)
        
        # Date Range
        date_range_label = QLabel("Date Range:")
        date_range_label.setToolTip("(Optional) Custom date range")
        date_range_label.setStyleSheet("color: #9A9A9A;")
        layout.addWidget(date_range_label, 4, 0)
        
        self.date_range_label = QLabel("Auto (full history)")
        self.date_range_label.setStyleSheet("color: #9A9A9A;")
        self.date_range_label.setToolTip("Uses full available history")
        layout.addWidget(self.date_range_label, 4, 1)
        
        card.setLayout(layout)
        return card
    
    def create_card_context_feeds(self) -> QGroupBox:
        """Create Card 2: Context Feeds (Optional) with dropdown-style menu and checkboxes."""
        card = QGroupBox("Context Feeds (Optional)")
        card.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 2px solid #7b1fa2;
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
        
        layout = QVBoxLayout()
        layout.setSpacing(6)
        
        # Explanation label
        explanation_label = QLabel("Extra markets used only as features/filters; they are not traded directly.")
        explanation_label.setStyleSheet("color: #9A9A9A; font-style: italic; font-size: 10px;")
        explanation_label.setWordWrap(True)
        explanation_label.setToolTip("Context feeds provide market data for analysis context")
        layout.addWidget(explanation_label)
        
        # Selection summary (MANDATORY - always visible above selector)
        self.selected_feeds_label = QLabel("Context Feeds: None")
        self.selected_feeds_label.setStyleSheet("color: #3A8DFF; font-weight: bold; font-size: 11px;")
        layout.addWidget(self.selected_feeds_label)
        
        # Selection action buttons
        action_layout = QHBoxLayout()
        action_layout.setSpacing(4)
        
        self.select_all_feeds_btn = QPushButton("Select All")
        self.select_all_feeds_btn.setStyleSheet("""
            QPushButton {
                background-color: #2A2A2A;
                color: #E6E6E6;
                border: 1px solid #555555;
                border-radius: 3px;
                padding: 4px 8px;
                font-size: 10px;
            }
            QPushButton:hover {
                background-color: #3A3A3A;
                border: 1px solid #3A8DFF;
            }
        """)
        action_layout.addWidget(self.select_all_feeds_btn)
        
        self.select_none_feeds_btn = QPushButton("Select None")
        self.select_none_feeds_btn.setStyleSheet("""
            QPushButton {
                background-color: #2A2A2A;
                color: #E6E6E6;
                border: 1px solid #555555;
                border-radius: 3px;
                padding: 4px 8px;
                font-size: 10px;
            }
            QPushButton:hover {
                background-color: #3A3A3A;
                border: 1px solid #3A8DFF;
            }
        """)
        action_layout.addWidget(self.select_none_feeds_btn)
        
        action_layout.addStretch()
        layout.addLayout(action_layout)
        
        # Dropdown-style container for checkboxes
        dropdown_frame = QFrame()
        dropdown_frame.setFrameStyle(QFrame.StyledPanel)
        dropdown_frame.setStyleSheet("""
            QFrame {
                background-color: #2A2A2A;
                border: 1px solid #555555;
                border-radius: 3px;
                max-height: 120px;
            }
        """)
        
        dropdown_layout = QVBoxLayout(dropdown_frame)
        dropdown_layout.setContentsMargins(4, 4, 4, 4)
        dropdown_layout.setSpacing(3)
        
        # Container for checkboxes with scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(100)
        scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: #2A2A2A;
            }
            QScrollArea QWidget {
                background-color: #2A2A2A;
            }
        """)
        
        container = QWidget()
        self.context_feeds_layout = QVBoxLayout(container)
        self.context_feeds_layout.setSpacing(3)
        
        scroll.setWidget(container)
        dropdown_layout.addWidget(scroll)
        
        layout.addWidget(dropdown_frame)
        
        card.setLayout(layout)
        return card
    
    def create_card_prepare_data(self) -> QGroupBox:
        """Create Card 3: Prepare Data."""
        card = QGroupBox("Prepare Data")
        card.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 2px solid #0288d1;
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
        
        layout = QVBoxLayout()
        layout.setSpacing(6)
        
        # Explanation
        explanation_label = QLabel("Data readiness for analysis")
        explanation_label.setStyleSheet("color: #9A9A9A; font-style: italic; font-size: 10px;")
        explanation_label.setWordWrap(True)
        explanation_label.setToolTip("Data status indicates if analysis can proceed")
        layout.addWidget(explanation_label)
        
        status_frame = QFrame()
        status_frame.setFrameStyle(QFrame.StyledPanel)
        status_frame.setStyleSheet("background-color: #2A2A2A; border-radius: 3px;")
        status_layout = QGridLayout(status_frame)
        status_layout.setVerticalSpacing(6)
        status_layout.setHorizontalSpacing(10)
        
        # Market Data Status
        market_data_label = QLabel("Market Data:")
        market_data_label.setToolTip("Price data status")
        market_data_label.setStyleSheet("color: #9A9A9A;")
        status_layout.addWidget(market_data_label, 0, 0)
        
        self.bars_status_label = QLabel("Checking...")
        self.bars_status_label.setStyleSheet("font-weight: bold;")
        self.bars_status_label.setToolTip("Market data status: READY, NOT READY, UPDATING, or FAILED")
        status_layout.addWidget(self.bars_status_label, 0, 1)
        
        self.bars_timestamp_label = QLabel("")
        self.bars_timestamp_label.setStyleSheet("color: #9A9A9A; font-size: 10px;")
        status_layout.addWidget(self.bars_timestamp_label, 0, 2)
        
        # Analysis Data Status
        analysis_data_label = QLabel("Analysis Data:")
        analysis_data_label.setToolTip("Analysis indicators status")
        analysis_data_label.setStyleSheet("color: #9A9A9A;")
        status_layout.addWidget(analysis_data_label, 1, 0)
        
        self.features_status_label = QLabel("Checking...")
        self.features_status_label.setStyleSheet("font-weight: bold;")
        self.features_status_label.setToolTip("Analysis data status: READY, NOT READY, UPDATING, or FAILED")
        status_layout.addWidget(self.features_status_label, 1, 1)
        
        self.features_timestamp_label = QLabel("")
        self.features_timestamp_label.setStyleSheet("color: #9A9A9A; font-size: 10px;")
        status_layout.addWidget(self.features_timestamp_label, 1, 2)
        
        layout.addWidget(status_frame)
        
        # CHECK buttons row (read-only)
        check_buttons_layout = QHBoxLayout()
        check_buttons_layout.setSpacing(6)
        
        self.check_bars_btn = QPushButton("CHECK BARS")
        self.check_bars_btn.setMinimumHeight(32)
        self.check_bars_btn.setToolTip("Check if market data is ready (read-only)")
        self.check_bars_btn.setStyleSheet("""
            QPushButton {
                background-color: #2A2A2A;
                color: #E6E6E6;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 6px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover:enabled {
                background-color: #3A3A3A;
                border: 1px solid #3A8DFF;
            }
            QPushButton:disabled {
                background-color: #1A1A1A;
                color: #666666;
                border: 1px solid #333333;
            }
        """)
        check_buttons_layout.addWidget(self.check_bars_btn)
        
        self.check_features_btn = QPushButton("CHECK FEATURES")
        self.check_features_btn.setMinimumHeight(32)
        self.check_features_btn.setToolTip("Check if analysis data is ready (read-only)")
        self.check_features_btn.setStyleSheet("""
            QPushButton {
                background-color: #2A2A2A;
                color: #E6E6E6;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 6px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover:enabled {
                background-color: #3A3A3A;
                border: 1px solid #3A8DFF;
            }
            QPushButton:disabled {
                background-color: #1A1A1A;
                color: #666666;
                border: 1px solid #333333;
            }
        """)
        check_buttons_layout.addWidget(self.check_features_btn)
        
        self.check_all_btn = QPushButton("CHECK ALL")
        self.check_all_btn.setMinimumHeight(32)
        self.check_all_btn.setToolTip("Check both market and analysis data (read-only)")
        self.check_all_btn.setStyleSheet("""
            QPushButton {
                background-color: #2A2A2A;
                color: #E6E6E6;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 6px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover:enabled {
                background-color: #3A3A3A;
                border: 1px solid #3A8DFF;
            }
            QPushButton:disabled {
                background-color: #1A1A1A;
                color: #666666;
                border: 1px solid #333333;
            }
        """)
        check_buttons_layout.addWidget(self.check_all_btn)
        
        check_buttons_layout.addStretch()
        layout.addLayout(check_buttons_layout)
        
        # Buttons - only show when NOT READY
        buttons_layout = QHBoxLayout()
        
        self.prepare_bars_btn = QPushButton("Prepare Bars")
        self.prepare_bars_btn.setMinimumHeight(32)
        self.prepare_bars_btn.setToolTip("Prepare market data for analysis")
        self.prepare_bars_btn.setStyleSheet("""
            QPushButton {
                background-color: #3A8DFF;
                color: white;
                border-radius: 4px;
                padding: 6px;
                font-size: 11px;
                border: none;
            }
            QPushButton:disabled {
                background-color: #555555;
                color: #9A9A9A;
            }
            QPushButton:hover:enabled {
                background-color: #2A7DFF;
            }
        """)
        buttons_layout.addWidget(self.prepare_bars_btn)
        
        self.prepare_features_btn = QPushButton("Prepare Features")
        self.prepare_features_btn.setMinimumHeight(32)
        self.prepare_features_btn.setToolTip("Prepare analysis indicators")
        self.prepare_features_btn.setStyleSheet("""
            QPushButton {
                background-color: #3A8DFF;
                color: white;
                border-radius: 4px;
                padding: 6px;
                font-size: 11px;
                border: none;
            }
            QPushButton:disabled {
                background-color: #555555;
                color: #9A9A9A;
            }
            QPushButton:hover:enabled {
                background-color: #2A7DFF;
            }
        """)
        buttons_layout.addWidget(self.prepare_features_btn)
        
        self.prepare_all_btn = QPushButton("Prepare All")
        self.prepare_all_btn.setMinimumHeight(32)
        self.prepare_all_btn.setToolTip("Prepare all data for analysis")
        self.prepare_all_btn.setStyleSheet("""
            QPushButton {
                background-color: #3A8DFF;
                color: white;
                border-radius: 4px;
                padding: 6px;
                font-size: 11px;
                border: none;
            }
            QPushButton:disabled {
                background-color: #555555;
                color: #9A9A9A;
            }
            QPushButton:hover:enabled {
                background-color: #2A7DFF;
            }
        """)
        buttons_layout.addWidget(self.prepare_all_btn)
        
        # Force refresh button (danger color)
        self.force_rebuild_btn = QPushButton("Force Refresh")
        self.force_rebuild_btn.setMinimumHeight(32)
        self.force_rebuild_btn.setToolTip("Force refresh all data (requires confirmation)")
        self.force_rebuild_btn.setStyleSheet("""
            QPushButton {
                background-color: #FF3B3B;
                color: white;
                border-radius: 4px;
                padding: 6px;
                font-size: 11px;
                border: none;
            }
            QPushButton:hover:enabled {
                background-color: #FF2B2B;
            }
        """)
        buttons_layout.addWidget(self.force_rebuild_btn)
        
        layout.addLayout(buttons_layout)
        
        # Status note
        status_note_label = QLabel("READY: Analysis can proceed. NOT READY: Click Prepare. UPDATING: In progress. FAILED: Check logs.")
        status_note_label.setStyleSheet("color: #9A9A9A; font-size: 9px; font-style: italic;")
        status_note_label.setWordWrap(True)
        layout.addWidget(status_note_label)
        
        card.setLayout(layout)
        return card
    
    def create_card_run_publish(self) -> QGroupBox:
        """Create Card 4: Run & Publish."""
        card = QGroupBox("Run & Publish")
        card.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 2px solid #2e7d32;
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
        
        layout = QVBoxLayout()
        layout.setSpacing(8)
        
        # OPEN LAST RUN + OPEN... buttons row
        open_buttons_layout = QHBoxLayout()
        open_buttons_layout.setSpacing(6)
        
        self.open_last_run_btn = QPushButton("OPEN LAST RUN")
        self.open_last_run_btn.setMinimumHeight(32)
        self.open_last_run_btn.setToolTip("Open the most recent run for analysis")
        self.open_last_run_btn.setStyleSheet("""
            QPushButton {
                background-color: #2A2A2A;
                color: #E6E6E6;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 6px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover:enabled {
                background-color: #3A3A3A;
                border: 1px solid #3A8DFF;
            }
            QPushButton:disabled {
                background-color: #1A1A1A;
                color: #666666;
                border: 1px solid #333333;
            }
        """)
        open_buttons_layout.addWidget(self.open_last_run_btn)
        
        self.open_run_btn = QPushButton("OPEN...")
        self.open_run_btn.setMinimumHeight(32)
        self.open_run_btn.setToolTip("Select a run to open for analysis")
        self.open_run_btn.setStyleSheet("""
            QPushButton {
                background-color: #2A2A2A;
                color: #E6E6E6;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 6px;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover:enabled {
                background-color: #3A3A3A;
                border: 1px solid #3A8DFF;
            }
            QPushButton:disabled {
                background-color: #1A1A1A;
                color: #666666;
                border: 1px solid #333333;
            }
        """)
        open_buttons_layout.addWidget(self.open_run_btn)
        
        open_buttons_layout.addStretch()
        layout.addLayout(open_buttons_layout)
        
        self.run_research_btn = QPushButton("Run Research")
        self.run_research_btn.setMinimumHeight(48)
        font = self.run_research_btn.font()
        font.setPointSize(12)
        font.setBold(True)
        self.run_research_btn.setFont(font)
        self.run_research_btn.setStyleSheet("""
            QPushButton {
                background-color: #3A8DFF;
                color: white;
                border-radius: 4px;
                padding: 8px;
                border: none;
            }
            QPushButton:disabled {
                background-color: #555555;
                color: #9A9A9A;
            }
            QPushButton:hover:enabled {
                background-color: #2A7DFF;
            }
        """)
        layout.addWidget(self.run_research_btn)
        
        self.summary_panel = QFrame()
        self.summary_panel.setFrameStyle(QFrame.StyledPanel)
        self.summary_panel.setStyleSheet("""
            QFrame {
                background-color: #2A2A2A;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 8px;
            }
        """)
        summary_layout = QGridLayout(self.summary_panel)
        summary_layout.setVerticalSpacing(4)
        summary_layout.setHorizontalSpacing(10)
        
        summary_layout.addWidget(QLabel("Status:"), 0, 0)
        self.run_status_label = QLabel("-")
        self.run_status_label.setStyleSheet("font-weight: bold;")
        summary_layout.addWidget(self.run_status_label, 0, 1)
        
        summary_layout.addWidget(QLabel("Net Profit:"), 1, 0)
        self.net_profit_label = QLabel("-")
        summary_layout.addWidget(self.net_profit_label, 1, 1)
        
        summary_layout.addWidget(QLabel("Max Drawdown:"), 2, 0)
        self.max_dd_label = QLabel("-")
        summary_layout.addWidget(self.max_dd_label, 2, 1)
        
        summary_layout.addWidget(QLabel("Trades:"), 3, 0)
        self.trades_label = QLabel("-")
        summary_layout.addWidget(self.trades_label, 3, 1)
        
        summary_layout.addWidget(QLabel("Sharpe:"), 4, 0)
        self.sharpe_label = QLabel("-")
        summary_layout.addWidget(self.sharpe_label, 4, 1)
        
        summary_layout.addWidget(QLabel("Strategy:"), 5, 0)
        self.artifact_status_label = QLabel("NOT READY")
        self.artifact_status_label.setStyleSheet("font-weight: bold; color: #666;")
        summary_layout.addWidget(self.artifact_status_label, 5, 1)
        
        self.summary_panel.setVisible(False)
        layout.addWidget(self.summary_panel)
        
        self.publish_btn = QPushButton("Publish to Registry")
        self.publish_btn.setMinimumHeight(32)
        self.publish_btn.setToolTip("Publishing makes this run a governed strategy version available for allocation.")
        self.publish_btn.setStyleSheet("""
            QPushButton {
                background-color: #00FF88;
                color: #121212;
                border-radius: 4px;
                padding: 6px;
                font-size: 11px;
                font-weight: bold;
                border: none;
            }
            QPushButton:disabled {
                background-color: #555555;
                color: #9A9A9A;
            }
            QPushButton:hover:enabled {
                background-color: #00EE77;
            }
        """)
        layout.addWidget(self.publish_btn)
        
        # Clean Up button (smaller, less prominent)
        self.cleanup_btn = QPushButton("Clean Up...")
        self.cleanup_btn.setMinimumHeight(28)
        self.cleanup_btn.setToolTip("Safe deletion tools for runs, artifacts, and cache")
        self.cleanup_btn.setStyleSheet("""
            QPushButton {
                background-color: #2A2A2A;
                color: #E6E6E6;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 4px;
                font-size: 10px;
            }
            QPushButton:hover {
                background-color: #3A3A3A;
                border: 1px solid #3A8DFF;
            }
        """)
        layout.addWidget(self.cleanup_btn)
        
        card.setLayout(layout)
        return card
    
    def load_datasets(self):
        """Load dataset options from raw data directory for Primary Market dropdown."""
        raw_dir = Path("/home/fishbro/FishBroWFS_V2/FishBroData/raw")
        if not raw_dir.exists():
            self.log(f"ERROR: Raw data directory not found: {raw_dir}")
            return
        
        identifiers = set()
        for item in raw_dir.iterdir():
            if not item.is_file():
                continue
            
            name = item.name
            if name.endswith(" HOT-Minute-Trade.txt"):
                identifier = name[:-len(" HOT-Minute-Trade.txt")]
            elif name.endswith("_SUBSET.txt"):
                identifier = name[:-len("_SUBSET.txt")]
            else:
                identifier = name.split()[0] if ' ' in name else name.split('_')[0]
                identifier = identifier.rsplit('.', 1)[0] if '.' in identifier else identifier
            
            if identifier and '.' in identifier:
                identifiers.add(identifier)
        
        datasets = sorted(identifiers)
        self.primary_market_cb.clear()
        self.primary_market_cb.addItems(datasets)
        
        if datasets:
            self.log(f"Loaded {len(datasets)} datasets for Primary Market")
        else:
            self.log("WARNING: No datasets found in raw directory")
    
    def load_context_feeds(self):
        """Load available auxiliary datasets for Context Feeds."""
        raw_dir = Path("/home/fishbro/FishBroWFS_V2/FishBroData/raw")
        if not raw_dir.exists():
            return
        
        while self.context_feeds_layout.count():
            child = self.context_feeds_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        
        # Clear stored checkboxes
        self.context_feed_checkboxes = {}
        
        auxiliary_patterns = ["VX", "DX", "ZN", "6J", "ES", "NQ", "YM", "RTY"]
        auxiliary_datasets = []
        
        for item in raw_dir.iterdir():
            if not item.is_file():
                continue
            
            name = item.name
            for pattern in auxiliary_patterns:
                if pattern in name:
                    if name.endswith(" HOT-Minute-Trade.txt"):
                        identifier = name[:-len(" HOT-Minute-Trade.txt")]
                    elif name.endswith("_SUBSET.txt"):
                        identifier = name[:-len("_SUBSET.txt")]
                    else:
                        identifier = name.split()[0] if ' ' in name else name.split('_')[0]
                        identifier = identifier.rsplit('.', 1)[0] if '.' in identifier else identifier
                    
                    if identifier and '.' in identifier:
                        auxiliary_datasets.append(identifier)
                    break
        
        auxiliary_datasets = sorted(set(auxiliary_datasets))
        
        for dataset in auxiliary_datasets:
            cb = QCheckBox(dataset)
            cb.setStyleSheet("""
                QCheckBox {
                    padding: 3px;
                    color: #E6E6E6;
                }
                QCheckBox:hover {
                    background-color: #2A2A2A;
                }
                QCheckBox::indicator {
                    width: 14px;
                    height: 14px;
                }
                QCheckBox::indicator:checked {
                    border: 1px solid #2F80ED;
                    background-color: #2F80ED;
                }
            """)
            cb.stateChanged.connect(lambda state, ds=dataset: self.on_context_feed_changed(ds, state))
            self.context_feeds_layout.addWidget(cb)
            self.context_feed_checkboxes[dataset] = cb
        
        if not auxiliary_datasets:
            label = QLabel("No auxiliary datasets found")
            label.setStyleSheet("color: #888; font-style: italic;")
            self.context_feeds_layout.addWidget(label)
        
        # Update summary
        self.update_selected_feeds_summary()
    
    def on_timeframe_changed(self):
        """Handle timeframe checkbox state change."""
        selected_timeframes = []
        for tf, cb in self.timeframe_checkboxes.items():
            if cb.isChecked():
                selected_timeframes.append(tf)
        
        # Update summary label
        if selected_timeframes:
            if len(selected_timeframes) > 2:
                summary = f"Selected: {len(selected_timeframes)} timeframes ({', '.join(selected_timeframes[:2])}...)"
            else:
                summary = f"Selected: {', '.join(selected_timeframes)}"
        else:
            summary = "Selected: None"
        
        self.timeframe_summary_label.setText(summary)
        
        # Update cache status when timeframes change
        self.update_cache_status()
        
        self.log(f"Timeframes updated: {selected_timeframes}")
    
    def on_context_feed_changed(self, dataset: str, state: int):
        """Handle context feed checkbox state change."""
        if state == Qt.Checked:
            self.selected_context_feeds.add(dataset)
        else:
            self.selected_context_feeds.discard(dataset)
        
        # Changing Data2 selection marks Prepare as DIRTY (per spec)
        # Clear prepared status for this feed since selection changed
        if dataset in self.data2_prepared_feeds:
            self.data2_prepared_feeds.remove(dataset)
        
        self.update_selected_feeds_summary()
        self.update_run_analysis_button()  # Update button state
        self.log(f"Context feeds updated: {sorted(self.selected_context_feeds)}")
    
    def update_selected_feeds_summary(self):
        """Update the selected feeds summary label."""
        if self.selected_context_feeds:
            feeds_list = sorted(self.selected_context_feeds)
            if len(feeds_list) <= 3:
                # Show up to 3 feed names
                summary = f"Context Feeds: {', '.join(feeds_list)}"
            else:
                # Show count for more than 3
                summary = f"Context Feeds: {len(feeds_list)} selected"
            self.selected_feeds_label.setText(summary)
        else:
            self.selected_feeds_label.setText("Context Feeds: None")
    
    def filter_context_feeds(self):
        """Filter context feeds based on search text. (Deprecated - no search bar)"""
        # No search bar in Phase 18.7, keep all checkboxes visible
        for dataset, cb in self.context_feed_checkboxes.items():
            cb.setHidden(False)
    
    def select_all_context_feeds(self):
        """Select all visible context feeds."""
        for dataset, cb in self.context_feed_checkboxes.items():
            if not cb.isHidden():
                cb.setChecked(True)
    
    def select_none_context_feeds(self):
        """Deselect all context feeds."""
        for dataset, cb in self.context_feed_checkboxes.items():
            cb.setChecked(False)
    
    def update_cache_status(self):
        """Check and update data status for market and analysis data."""
        primary_market = self.primary_market_cb.currentText()
        if not primary_market:
            self.bars_status_label.setText("Select Market")
            self.bars_status_label.setStyleSheet("font-weight: bold; color: #9A9A9A;")
            self.features_status_label.setText("Select Market")
            self.features_status_label.setStyleSheet("font-weight: bold; color: #9A9A9A;")
            self.prepare_bars_btn.setEnabled(False)
            self.prepare_features_btn.setEnabled(False)
            self.prepare_all_btn.setEnabled(False)
            return
        
        season = "2026Q1"
        
        # Use new data readiness service if available
        if RUN_SERVICES_AVAILABLE and check_all:
            selected_timeframes = self.get_selected_timeframes()
            if not selected_timeframes:
                self.bars_status_label.setText("Select Timeframe")
                self.bars_status_label.setStyleSheet("font-weight: bold; color: #9A9A9A;")
                self.features_status_label.setText("Select Timeframe")
                self.features_status_label.setStyleSheet("font-weight: bold; color: #9A9A9A;")
                self.prepare_bars_btn.setEnabled(False)
                self.prepare_features_btn.setEnabled(False)
                self.prepare_all_btn.setEnabled(False)
                return
            
            # Use first selected timeframe for check
            timeframe_str = selected_timeframes[0]
            try:
                timeframe = int(timeframe_str.replace('m', ''))
            except ValueError:
                self.bars_status_label.setText("Invalid TF")
                self.bars_status_label.setStyleSheet("font-weight: bold; color: #9A9A9A;")
                self.features_status_label.setText("Invalid TF")
                self.features_status_label.setStyleSheet("font-weight: bold; color: #9A9A9A;")
                return
            
            outputs_root = Path("outputs")
            
            try:
                readiness = check_all(primary_market, timeframe, season, outputs_root)
                
                # Update bars status
                if readiness.bars_ready:
                    self.bars_cache_status = "READY"
                    self.bars_status_label.setText("READY")
                    self.bars_status_label.setStyleSheet("font-weight: bold; color: #29D38D;")
                    self.prepare_bars_btn.setEnabled(False)
                else:
                    self.bars_cache_status = "MISSING"
                    self.bars_status_label.setText("MISSING")
                    self.bars_status_label.setStyleSheet("font-weight: bold; color: #FF4D4D;")
                    self.prepare_bars_btn.setEnabled(True)
                
                # Update features status
                if readiness.features_ready:
                    self.features_cache_status = "READY"
                    self.features_status_label.setText("READY")
                    self.features_status_label.setStyleSheet("font-weight: bold; color: #29D38D;")
                    self.prepare_features_btn.setEnabled(False)
                else:
                    self.features_cache_status = "MISSING"
                    self.features_status_label.setText("MISSING")
                    self.features_status_label.setStyleSheet("font-weight: bold; color: #FF4D4D;")
                    self.prepare_features_btn.setEnabled(True)
                
                # Clear timestamps for now (could be added later)
                self.bars_timestamp_label.setText("")
                self.features_timestamp_label.setText("")
                
            except Exception as e:
                self.log(f"Error checking data readiness: {e}")
                # Fall back to legacy check
                self._legacy_cache_status_check(primary_market, season)
        else:
            # Legacy check
            self._legacy_cache_status_check(primary_market, season)
        
        self.prepare_all_btn.setEnabled(
            self.bars_cache_status == "MISSING" or
            self.features_cache_status == "MISSING"
        )
        
        # Update Run Analysis button state
        self.update_run_analysis_button()
    
    def _legacy_cache_status_check(self, primary_market: str, season: str):
        """Legacy cache status check using hardcoded paths."""
        # Check if ANY selected timeframe has bars ready
        selected_timeframes = self.get_selected_timeframes()
        bars_ready = False
        bars_timestamp = None
        
        if selected_timeframes:
            for tf in selected_timeframes:
                timeframe = int(tf.replace('m', ''))
                bars_path = Path("outputs") / "seasons" / season / "shared" / primary_market / f"{timeframe}m.npz"
                if bars_path.exists():
                    bars_ready = True
                    mtime = bars_path.stat().st_mtime
                    timestamp = datetime.datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M')
                    bars_timestamp = timestamp
                    break
        
        if bars_ready:
            self.bars_cache_status = "READY"
            self.bars_status_label.setText("READY")
            self.bars_status_label.setStyleSheet("font-weight: bold; color: #29D38D;")
            if bars_timestamp:
                self.bars_timestamp_label.setText(f"Updated: {bars_timestamp}")
            else:
                self.bars_timestamp_label.setText("")
            self.prepare_bars_btn.setEnabled(False)
        else:
            self.bars_cache_status = "MISSING"
            self.bars_status_label.setText("MISSING")
            self.bars_status_label.setStyleSheet("font-weight: bold; color: #FF4D4D;")
            self.bars_timestamp_label.setText("")
            self.prepare_bars_btn.setEnabled(True)
        
        features_dir = Path("outputs") / "seasons" / season / "shared" / primary_market / "features"
        if features_dir.exists() and any(features_dir.iterdir()):
            self.features_cache_status = "READY"
            self.features_status_label.setText("READY")
            self.features_status_label.setStyleSheet("font-weight: bold; color: #29D38D;")
            try:
                first_file = next(features_dir.iterdir())
                mtime = first_file.stat().st_mtime
                timestamp = datetime.datetime.fromtimestamp(mtime).strftime('%Y-%m-%d %H:%M')
                self.features_timestamp_label.setText(f"Updated: {timestamp}")
            except StopIteration:
                self.features_timestamp_label.setText("")
            self.prepare_features_btn.setEnabled(False)
        else:
            self.features_cache_status = "MISSING"
            self.features_status_label.setText("MISSING")
            self.features_status_label.setStyleSheet("font-weight: bold; color: #FF4D4D;")
            self.features_timestamp_label.setText("")
            self.prepare_features_btn.setEnabled(True)
    
    def get_selected_timeframes(self) -> List[str]:
        """Get list of selected timeframes."""
        selected = []
        for tf, cb in self.timeframe_checkboxes.items():
            if cb.isChecked():
                selected.append(tf)
        return selected
    
    def update_run_analysis_button(self):
        """Update Run Analysis button state based on readiness with Data2 gating."""
        primary_market = self.primary_market_cb.currentText()
        selected_timeframes = self.get_selected_timeframes()
        
        # Basic requirements
        basic_enabled = (primary_market != "" and
                        len(selected_timeframes) > 0)
        
        # Data2 (context feeds) gating logic
        # If Data2 selected, Prepare must be completed first
        data2_selected = len(self.selected_context_feeds) > 0
        
        # Check if all selected Data2 feeds have been prepared
        data2_prepared = True  # Assume prepared unless we find missing feeds
        if data2_selected:
            for feed in self.selected_context_feeds:
                if feed not in self.data2_prepared_feeds:
                    data2_prepared = False
                    break
        
        # Determine final enabled state
        if not basic_enabled:
            enabled = False
            reasons = []
            if not primary_market:
                reasons.append("Select a market")
            if not selected_timeframes:
                reasons.append("Select at least one timeframe")
            
            if reasons:
                self.run_research_btn.setToolTip(f"Prepare data first: {', '.join(reasons)}")
        elif data2_selected and not data2_prepared:
            # Data2 selected but not prepared
            enabled = False
            self.run_research_btn.setToolTip("Context feeds selected. Preparing required data...")
        else:
            # All requirements met
            enabled = True
            self.run_research_btn.setToolTip("Run analysis with selected parameters")
        
        self.run_research_btn.setEnabled(enabled)
    
    def setup_connections(self):
        """Connect signals and slots."""
        self.run_research_btn.clicked.connect(self.start_run)
        self.prepare_bars_btn.clicked.connect(self.start_prepare_bars)
        self.prepare_features_btn.clicked.connect(self.start_prepare_features)
        self.prepare_all_btn.clicked.connect(self.start_prepare_all)
        self.force_rebuild_btn.clicked.connect(self.start_force_rebuild)
        self.publish_btn.clicked.connect(self.publish_artifact)
        self.cleanup_btn.clicked.connect(self.open_cleanup_dialog)
        
        # New OPEN buttons
        self.open_last_run_btn.clicked.connect(self.open_last_run)
        self.open_run_btn.clicked.connect(self.open_run_dialog)
        
        # New CHECK buttons
        self.check_bars_btn.clicked.connect(self.check_bars)
        self.check_features_btn.clicked.connect(self.check_features)
        self.check_all_btn.clicked.connect(self.check_all)
        
        # Context feeds selection (no search bar in Phase 18.7)
        self.select_all_feeds_btn.clicked.connect(self.select_all_context_feeds)
        self.select_none_feeds_btn.clicked.connect(self.select_none_context_feeds)
        
        # CLEAR log button
        self.clear_log_btn.clicked.connect(self.clear_log_view)
        
        self.primary_market_cb.currentTextChanged.connect(self.update_cache_status)
    
    def clear_log_view(self):
        """Clear visible log buffer only (no side effects to disk logs)."""
        self.log_view.clear()
        self.log("Log view cleared (buffer only, disk logs untouched)")
    
    def log(self, message: str):
        """Append message to log view."""
        self.log_view.append(message)
        scrollbar = self.log_view.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        self.log_signal.emit(message)
    
    def get_txt_path_for_dataset(self, dataset_id: str) -> Optional[Path]:
        """Get the TXT file path for a given dataset identifier."""
        raw_dir = Path("/home/fishbro/FishBroWFS_V2/FishBroData/raw")
        if not raw_dir.exists():
            return None
        
        for item in raw_dir.iterdir():
            if not item.is_file():
                continue
            
            name = item.name
            if name.startswith(dataset_id):
                return item
        
        suffixes = [" HOT-Minute-Trade.txt", "_SUBSET.txt", ".txt"]
        for suffix in suffixes:
            candidate = raw_dir / f"{dataset_id}{suffix}"
            if candidate.exists():
                return candidate
        
        return None
    
    def start_prepare_bars(self):
        """Start building bars cache."""
        self._start_prepare(build_bars=True, build_features=False)
    
    def start_prepare_features(self):
        """Start building features cache."""
        self._start_prepare(build_bars=False, build_features=True)
    
    def start_prepare_all(self):
        """Start building both bars and features cache (idempotent - skips READY)."""
        # Determine what actually needs to be built
        build_bars = self.bars_cache_status == "MISSING"
        build_features = self.features_cache_status == "MISSING"
        
        if not build_bars and not build_features:
            self.log("All caches are READY. Nothing to prepare.")
            return
        
        self.log(f"Prepare All: bars={build_bars}, features={build_features}")
        self._start_prepare(build_bars=build_bars, build_features=build_features)
    
    def start_force_rebuild(self):
        """Start force rebuild with confirmation."""
        from PySide6.QtWidgets import QMessageBox
        
        reply = QMessageBox.question(
            self,
            "Confirm Force Rebuild",
            "Force rebuild will rebuild ALL caches even if READY.\nThis may take significant time.\n\nAre you sure?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.log("Starting force rebuild (ignoring READY status)")
            self._start_prepare(build_bars=True, build_features=True, force=True)
    
    def _start_prepare(self, build_bars: bool, build_features: bool, force: bool = False):
        """Common prepare worker setup."""
        if self.worker_thread and self.worker_thread.isRunning():
            self.log("WARNING: An operation is already in progress")
            return
        
        primary_market = self.primary_market_cb.currentText()
        if not primary_market:
            self.log("ERROR: No Primary Market selected")
            return
        
        txt_path = self.get_txt_path_for_dataset(primary_market)
        if not txt_path:
            self.log(f"ERROR: Could not find TXT file for dataset {primary_market}")
            return
        
        mode = "FULL"
        
        # Get selected context feeds
        context_feeds = list(self.selected_context_feeds)
        
        # Log what's being built
        if force:
            self.log(f"FORCE REBUILD: Building all caches for {primary_market}")
        else:
            if build_bars:
                self.log(f"Preparing market data for {primary_market}")
            if build_features:
                self.log(f"Preparing analysis data for {primary_market}")
        
        if context_feeds:
            self.log(f"Also preparing Data2 feeds: {context_feeds}")
        
        self.log(f"TXT path: {txt_path}")
        
        self.worker = BuildWorker(
            dataset=primary_market,
            txt_path=txt_path,
            build_bars=build_bars,
            build_features=build_features,
            mode=mode,
            context_feeds=context_feeds
        )
        self.worker_thread = QThread()
        
        self.worker.moveToThread(self.worker_thread)
        
        self.worker.log_signal.connect(self.log)
        self.worker.progress_signal.connect(self.update_progress_value)
        self.worker.finished_signal.connect(self.on_prepare_finished)
        self.worker.failed_signal.connect(self.on_prepare_failed)
        
        self.worker_thread.started.connect(self.worker.run)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)
        
        self.set_ui_locked(True)
        self.worker_thread.start()
        self.progress_bar.setRange(0, 0)
    
    def start_run(self):
        """Start a backtest run."""
        if self.worker_thread and self.worker_thread.isRunning():
            self.log("WARNING: A run is already in progress")
            return
        
        strategy = self.strategy_cb.currentText()
        primary_market = self.primary_market_cb.currentText()
        if not primary_market:
            self.log("ERROR: Primary Market is required")
            return
        
        selected_timeframes = self.get_selected_timeframes()
        if not selected_timeframes:
            self.log("ERROR: At least one timeframe is required")
            return
        
        # For now, run with first selected timeframe
        # TODO: Support multiple timeframe analysis
        try:
            timeframe = int(selected_timeframes[0].replace('m', ''))
        except ValueError:
            self.log("ERROR: Invalid timeframe")
            return
        
        self.log(f"Starting research: {strategy}, {primary_market}, {timeframe}m")
        self.log(f"Selected timeframes: {selected_timeframes}")
        self.log(f"Context feeds: {sorted(self.selected_context_feeds)}")
        
        # Capture job start time for robust run discovery
        import datetime
        self.job_start_time_iso = datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00', 'Z')
        self.log(f"Job start time: {self.job_start_time_iso}")
        
        self.worker = BacktestWorker(strategy, primary_market, timeframe, list(self.selected_context_feeds))
        self.worker_thread = QThread()
        
        self.worker.moveToThread(self.worker_thread)
        
        self.worker.log_signal.connect(self.log)
        self.worker.progress_signal.connect(self.update_progress_value)
        self.worker.finished_signal.connect(self.on_finished)
        self.worker.failed_signal.connect(self.on_failed)
        
        self.worker_thread.started.connect(self.worker.run)
        self.worker_thread.finished.connect(self.worker_thread.deleteLater)
        
        self.set_ui_locked(True)
        self.worker_thread.start()
        self.progress_bar.setRange(0, 0)
    
    @Slot(dict)
    def on_prepare_finished(self, payload: dict):
        """Handle successful completion of prepare."""
        self.log(f"Prepare completed successfully!")
        
        # Extract Data2 preparation results
        context_feeds = payload.get("context_feeds", [])
        result = payload.get("result", {})
        
        if context_feeds:
            # Mark all selected Data2 feeds as prepared
            for feed in context_feeds:
                self.data2_prepared_feeds.add(feed)
            
            # Log Data2 preparation summary
            data2_reports = result.get("data2_reports", {})
            if data2_reports:
                self.log(f"Data2 feeds auto-built: {list(data2_reports.keys())}")
            else:
                self.log(f"Data2 feeds already prepared: {context_feeds}")
            
            self.log(f"Data2 prepared feeds updated: {sorted(self.data2_prepared_feeds)}")
        
        # Log no_change status
        no_change = result.get("no_change", True)
        if no_change:
            self.log("Prepare: no change (all data already ready)")
        else:
            self.log("Prepare: data was built or updated")
        
        self.set_ui_locked(False)
        
        if self.worker_thread:
            self.worker_thread.quit()
            self.worker_thread.wait()
            self.worker_thread = None
            self.worker = None
        
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.update_cache_status()
        self.update_run_analysis_button()  # Update button state after Data2 preparation
    
    @Slot(str)
    def on_prepare_failed(self, error_msg: str):
        """Handle prepare failure."""
        self.log(f"Prepare failed: {error_msg}")
        
        self.set_ui_locked(False)
        
        if self.worker_thread:
            self.worker_thread.quit()
            self.worker_thread.wait()
            self.worker_thread = None
            self.worker = None
        
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.update_cache_status()
    
    @Slot(dict)
    def on_finished(self, payload: dict):
        """Handle successful completion of backtest."""
        self.current_result = payload
        self.log(f"Research completed successfully!")
        
        # Log run ID from payload or try to resolve it
        run_id_from_payload = payload.get('run_id', '')
        if run_id_from_payload:
            self.log(f"Run ID: {run_id_from_payload}")
        else:
            self.log(f"Run ID: (empty in payload, attempting to resolve...)")
            # Try to resolve run using run index
            if RUN_INDEX_AVAILABLE and find_best_run:
                try:
                    strategy = payload.get('strategy_id', self.strategy_cb.currentText())
                    dataset = payload.get('dataset_id', self.primary_market_cb.currentText())
                    season = payload.get('season', '2026Q1')
                    
                    # Get timeframe from selected timeframes
                    selected_timeframes = self.get_selected_timeframes()
                    timeframe = selected_timeframes[0] if selected_timeframes else "60m"
                    
                    best_run = find_best_run(
                        outputs_root=Path("outputs"),
                        season=season,
                        strategy_id=strategy,
                        dataset_id=dataset,
                        timeframe=timeframe,
                        created_after_iso=self.job_start_time_iso
                    )
                    
                    if best_run:
                        self.log(f"Resolved Run ID: {best_run.run_id}")
                        # Update payload with resolved run_id for consistency
                        payload['run_id'] = best_run.run_id
                        if 'artifact_path' not in payload and best_run.run_dir:
                            payload['artifact_path'] = best_run.run_dir
                    else:
                        self.log(f"WARNING: Could not resolve run ID for {strategy}/{dataset}/{timeframe}")
                except Exception as e:
                    self.log(f"ERROR during run resolution: {e}")
        
        self.summary_panel.setVisible(True)
        
        pnl = payload.get('pnl', 0)
        maxdd = payload.get('maxdd', 0)
        trades = payload.get('trades', 0)
        
        self.run_status_label.setText("SUCCESS")
        self.run_status_label.setStyleSheet("font-weight: bold; color: #4caf50;")
        self.net_profit_label.setText(f"{pnl:,.2f}")
        self.max_dd_label.setText(f"{maxdd:,.2f}")
        self.trades_label.setText(f"{trades}")
        
        sharpe = payload.get('metrics', {}).get('sharpe', None)
        if sharpe is not None:
            self.sharpe_label.setText(f"{sharpe:.2f}")
        else:
            self.sharpe_label.setText("-")
        
        self.scan_and_update_artifact_status()
        self.set_ui_locked(False)
        
        if self.worker_thread:
            self.worker_thread.quit()
            self.worker_thread.wait()
            self.worker_thread = None
            self.worker = None
        
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
    
    @Slot(str)
    def on_failed(self, error_msg: str):
        """Handle backtest failure."""
        self.log(f"Research failed: {error_msg}")
        self.current_result = None
        
        self.summary_panel.setVisible(True)
        self.run_status_label.setText("FAILED")
        self.run_status_label.setStyleSheet("font-weight: bold; color: #f44336;")
        self.net_profit_label.setText("-")
        self.max_dd_label.setText("-")
        self.trades_label.setText("-")
        self.sharpe_label.setText("-")
        
        self.scan_and_update_artifact_status()
        self.set_ui_locked(False)
        
        if self.worker_thread:
            self.worker_thread.quit()
            self.worker_thread.wait()
            self.worker_thread = None
            self.worker = None
        
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
    
    def scan_and_update_artifact_status(self):
        """Scan for latest valid artifact and update UI status."""
        if not self.current_result:
            self.update_artifact_status("NONE")
            return
        
        season = self.current_result.get("season", "2026Q1")
        
        # Try using the new run index resolver first
        if RUN_INDEX_AVAILABLE and find_best_run:
            try:
                strategy = self.current_result.get('strategy_id', self.strategy_cb.currentText())
                dataset = self.current_result.get('dataset_id', self.primary_market_cb.currentText())
                
                # Get timeframe from selected timeframes
                selected_timeframes = self.get_selected_timeframes()
                timeframe = selected_timeframes[0] if selected_timeframes else "60m"
                
                best_run = find_best_run(
                    outputs_root=Path("outputs"),
                    season=season,
                    strategy_id=strategy,
                    dataset_id=dataset,
                    timeframe=timeframe,
                    created_after_iso=self.job_start_time_iso
                )
                
                if best_run:
                    self.update_artifact_status("READY", best_run.run_id, best_run.run_dir)
                    self.log(f"Found strategy result via run index: {best_run.run_id}")
                    return
                else:
                    # No matching run found, provide diagnostic info
                    if RUN_INDEX_AVAILABLE and get_run_diagnostics:
                        diag = get_run_diagnostics(
                            outputs_root=Path("outputs"),
                            season=season,
                            strategy_id=strategy,
                            dataset_id=dataset,
                            timeframe=timeframe
                        )
                        self.log(f"No strategy result found. Diagnostics:")
                        self.log(f"  Total runs in season: {diag['total_runs']}")
                        self.log(f"  Status counts: {diag['status_counts']}")
                        self.log(f"  Matching runs: {diag['matching_runs']}")
                        self.log(f"  Newest 3 runs: {[(r['run_id'], r['status'], r['dataset_id']) for r in diag['newest_runs']]}")
                    else:
                        self.log(f"No strategy result found for {strategy}/{dataset}/{timeframe}")
                    
                    self.update_artifact_status("NONE")
                    return
                    
            except Exception as e:
                self.log(f"ERROR during run index scan: {e}")
                # Fall back to legacy scanning
        
        # Fall back to legacy artifact validation
        runs_dir = Path("outputs") / "seasons" / season / "runs"
        
        result = self.find_latest_valid_artifact(runs_dir)
        if result.get("ok"):
            artifact_dir = result["artifact_dir"]
            artifact_path = Path(artifact_dir)
            self.update_artifact_status("READY", artifact_path.name, str(artifact_path))
            self.log(f"Found strategy result via legacy scan: {artifact_path.name}")
        else:
            self.update_artifact_status("NONE")
            if result.get("reason") == "no_valid_artifact_found":
                self.log(f"No strategy result found in {runs_dir}")
    
    def update_artifact_status(self, state: str, run_id: Optional[str] = None, run_dir: Optional[str] = None):
        """Update artifact status and UI."""
        self.artifact_state = state
        if run_id:
            self.artifact_run_id = run_id
        if run_dir:
            self.artifact_run_dir = run_dir
        
        color_map = {
            "NONE": "#666",
            "BUILDING": "#ff9800",
            "READY": "#4caf50",
            "FAILED": "#f44336"
        }
        color = color_map.get(state, "#666")
        
        if state == "READY" and run_id:
            display_text = f"Artifact: READY ({run_id})"
        else:
            display_text = f"Artifact: {state}"
        
        self.artifact_status_label.setText(display_text)
        self.artifact_status_label.setStyleSheet(f"font-weight: bold; color: {color};")
        
        # Load artifact into analytics suite if ready
        if state == "READY" and run_dir:
            self.load_artifact_into_analytics(Path(run_dir))
        
        self.set_ui_locked(self.worker_thread is not None and self.worker_thread.isRunning())
        self.artifact_state_changed.emit(state, run_id or "", run_dir or "")
    
    def load_artifact_into_analytics(self, artifact_path: Path):
        """Load artifact data into analytics suite."""
        try:
            if hasattr(self, 'analysis_widget'):
                success = self.analysis_widget.load_artifact(artifact_path)
                if success:
                    self.log(f"Loaded artifact into analytics suite: {artifact_path.name}")
                else:
                    self.log(f"Failed to load artifact into analytics suite")
        except Exception as e:
            self.log(f"Error loading artifact into analytics: {e}")
    
    def set_ui_locked(self, locked: bool):
        """Lock or unlock UI controls."""
        # Apply state to all controls
        widgets = [
            self.strategy_cb,
            self.primary_market_cb,
            self.run_research_btn,
            self.prepare_bars_btn,
            self.prepare_features_btn,
            self.prepare_all_btn,
            self.force_rebuild_btn,
            self.publish_btn,
            self.open_last_run_btn,
            self.open_run_btn,
            self.check_bars_btn,
            self.check_features_btn,
            self.check_all_btn
        ]
        
        for widget in widgets:
            set_widget_state(widget, not locked)
        
        # Timeframe checkboxes
        for cb in self.timeframe_checkboxes.values():
            set_widget_state(cb, not locked)
        
        # Context feed checkboxes
        for i in range(self.context_feeds_layout.count()):
            child = self.context_feeds_layout.itemAt(i)
            if child and child.widget():
                set_widget_state(child.widget(), not locked)
        
        # Special handling for prepare buttons based on cache status
        if not locked:
            # Prepare buttons only enabled when MISSING
            set_widget_state(self.prepare_bars_btn, self.bars_cache_status == "MISSING")
            set_widget_state(self.prepare_features_btn, self.features_cache_status == "MISSING")
            set_widget_state(self.prepare_all_btn,
                           self.bars_cache_status == "MISSING" or self.features_cache_status == "MISSING")
            
            # Publish button only enabled when artifact READY
            set_widget_state(self.publish_btn, self.artifact_state == "READY")
            
            # OPEN and CHECK buttons always enabled when not locked
            set_widget_state(self.open_last_run_btn, True)
            set_widget_state(self.open_run_btn, True)
            set_widget_state(self.check_bars_btn, True)
            set_widget_state(self.check_features_btn, True)
            set_widget_state(self.check_all_btn, True)
            
            # Update Run Analysis button
            self.update_run_analysis_button()
        else:
            # When locked, all buttons are disabled
            for widget in widgets:
                set_widget_state(widget, False)
    
    @Slot(int)
    def update_progress_value(self, value: int):
        """Update progress bar with specific value."""
        if 0 <= value <= 100:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(value)
    
    def publish_artifact(self):
        """Publish artifact to registry."""
        if not self.current_result:
            self.log("ERROR: No result to publish")
            return

        if self.artifact_state != "READY":
            self.log(f"ERROR: Strategy result not ready (state: {self.artifact_state})")
            return

        if not self.artifact_run_id:
            self.log("ERROR: No artifact run_id")
            return
        
        self.log(f"Publishing strategy: {self.artifact_run_id}")
        self.log(f"Result directory: {self.artifact_run_dir}")
        self.log("Publishing would call portfolio.manager.onboard_strategy()")
        self.log("Publishing successful (placeholder)")
        self.publish_btn.setEnabled(False)
    
    # Artifact validation methods delegate to the shared module
    def is_artifact_dir_name(self, name: str) -> bool:
        """Canonical predicate: return True iff name starts with 'artifact_'."""
        from ..artifact_validation import is_artifact_dir_name
        return is_artifact_dir_name(name)
    
    def validate_artifact_dir(self, run_dir: Path) -> dict:
        """HARD CONTRACT: Validate artifact directory."""
        from ..artifact_validation import validate_artifact_dir
        return validate_artifact_dir(run_dir)
    
    def find_latest_valid_artifact(self, runs_dir: Path) -> dict:
        """Find the latest valid artifact directory in runs_dir."""
        from ..artifact_validation import find_latest_valid_artifact
        return find_latest_valid_artifact(runs_dir)
    
    def open_cleanup_dialog(self):
        """Open the cleanup dialog."""
        dialog = CleanupDialog(self)
        dialog.cleanup_performed.connect(self.on_cleanup_performed)
        dialog.exec()
    
    def on_cleanup_performed(self, audit_event: dict):
        """Handle cleanup completion."""
        scope = audit_event.get("scope", "unknown")
        item_count = audit_event.get("item_count", 0)
        self.log(f"Cleanup performed: {scope}, {item_count} items moved to trash")
        
        # Refresh cache status since cleanup might have affected data
        self.update_cache_status()
    
    # New button handlers for OPEN RUN and CHECK buttons
    
    def open_last_run(self):
        """Open the most recent run for analysis."""
        if not RUN_SERVICES_AVAILABLE or not pick_last_run:
            self.log("ERROR: Run index service not available")
            return
        
        season = "2026Q1"  # Current season
        outputs_root = Path("outputs")
        
        try:
            last_run = pick_last_run(season, outputs_root)
            if not last_run:
                self.log("No runs found to open")
                return
            
            self.log(f"Opening last run: {last_run.name}")
            self.open_run(last_run.path)
            
        except Exception as e:
            self.log(f"ERROR opening last run: {e}")
    
    def open_run_dialog(self):
        """Open a dialog to select a run."""
        if not RUN_SERVICES_AVAILABLE or not list_runs:
            self.log("ERROR: Run index service not available")
            return
        
        # For now, just log - in a real implementation, this would open a dialog
        # to select from list_runs(season, outputs_root)
        season = "2026Q1"
        outputs_root = Path("outputs")
        
        try:
            runs = list_runs(season, outputs_root)
            if not runs:
                self.log("No runs found to open")
                return
            
            self.log(f"Found {len(runs)} runs. Opening newest: {runs[0].name}")
            self.open_run(runs[0].path)
            
        except Exception as e:
            self.log(f"ERROR listing runs: {e}")
    
    def open_run(self, run_dir: Path):
        """Open a specific run directory for analysis."""
        if not run_dir.exists():
            self.log(f"ERROR: Run directory does not exist: {run_dir}")
            return
        
        # Load run summary
        if RUN_SERVICES_AVAILABLE and get_run_summary:
            summary, reason = get_run_summary(run_dir)
            if summary is None:
                self.log(f"Run has no summary data: {reason}")
                # Still try to load into analytics if possible
            else:
                self.log(f"Loaded run summary: {reason}")
        
        # Load into analytics suite
        try:
            if hasattr(self, 'analysis_widget'):
                success = self.analysis_widget.load_artifact(run_dir)
                if success:
                    self.log(f"Loaded run into analytics suite: {run_dir.name}")
                    
                    # Update artifact status based on what was loaded
                    # Use the new state classification
                    from ..state.active_run_state import active_run_state, RunStatus
                    
                    # Extract season from run_dir path (e.g., outputs/seasons/2026Q1/runs/run_ac8a71aa)
                    season = "2026Q1"  # Default, could parse from path
                    if "seasons" in str(run_dir):
                        try:
                            parts = str(run_dir).split("/")
                            season_idx = parts.index("seasons") + 1
                            if season_idx < len(parts):
                                season = parts[season_idx]
                        except (ValueError, IndexError):
                            pass
                    
                    # Update active run state
                    active_run_state.set_active_run(run_dir, season, run_dir.name)
                    
                    # Determine artifact state for UI
                    if active_run_state.status == RunStatus.NONE:
                        artifact_state = "NONE"
                    elif active_run_state.status == RunStatus.PARTIAL:
                        artifact_state = "PARTIAL"
                    else:  # READY or VERIFIED
                        artifact_state = "READY"
                    
                    self.update_artifact_status(artifact_state, run_dir.name, str(run_dir))
                    
                else:
                    # Only log failure, don't clear analytics if metrics.json exists
                    # Check if metrics.json exists to determine if this is a partial run
                    metrics_path = run_dir / "metrics.json"
                    if metrics_path.exists():
                        # This is a partial run - update KPI labels from metrics
                        self.log(f"Loaded partial run (metrics only): {run_dir.name}")
                        
                        # Try to load metrics to update KPI labels
                        try:
                            import json
                            with open(metrics_path, "r", encoding="utf-8") as f:
                                metrics = json.load(f)
                            
                            # Update KPI labels in summary panel
                            net_profit = metrics.get("net_profit", 0)
                            max_dd = metrics.get("max_dd", 0)
                            trades = metrics.get("trades", 0)
                            sharpe = metrics.get("sharpe", None)
                            
                            self.net_profit_label.setText(f"{net_profit:,.2f}")
                            self.max_dd_label.setText(f"{max_dd:,.2f}")
                            self.trades_label.setText(f"{trades}")
                            if sharpe is not None:
                                self.sharpe_label.setText(f"{sharpe:.2f}")
                            else:
                                self.sharpe_label.setText("-")
                            
                            # Show summary panel
                            self.summary_panel.setVisible(True)
                            self.run_status_label.setText("PARTIAL")
                            self.run_status_label.setStyleSheet("font-weight: bold; color: #ff9800;")
                            
                            # Update active run state
                            from ..state.active_run_state import active_run_state
                            season = "2026Q1"
                            active_run_state.set_active_run(run_dir, season, run_dir.name)
                            
                            # Update artifact status as PARTIAL
                            self.update_artifact_status("PARTIAL", run_dir.name, str(run_dir))
                            
                        except Exception as e:
                            self.log(f"Error loading metrics.json: {e}")
                            self.log(f"Failed to load run into analytics suite")
                            # Show N/A in analytics for truly invalid runs
                            self.analysis_widget.clear()
                    else:
                        self.log(f"Failed to load run into analytics suite")
                        # Show N/A in analytics for truly invalid runs
                        self.analysis_widget.clear()
        except Exception as e:
            self.log(f"Error loading run into analytics: {e}")
    
    def check_bars(self):
        """Check bars readiness and update status."""
        self._perform_check(check_type="bars")
    
    def check_features(self):
        """Check features readiness and update status."""
        self._perform_check(check_type="features")
    
    def check_all(self):
        """Check both bars and features readiness."""
        self._perform_check(check_type="all")
    
    def _perform_check(self, check_type: str = "all"):
        """Perform data readiness check and update UI."""
        primary_market = self.primary_market_cb.currentText()
        if not primary_market:
            self.log("Select a market first")
            return
        
        selected_timeframes = self.get_selected_timeframes()
        if not selected_timeframes:
            self.log("Select at least one timeframe first")
            return
        
        # Use first selected timeframe for check
        timeframe_str = selected_timeframes[0]
        try:
            timeframe = int(timeframe_str.replace('m', ''))
        except ValueError:
            self.log(f"Invalid timeframe: {timeframe_str}")
            return
        
        season = "2026Q1"
        outputs_root = Path("outputs")
        
        if not RUN_SERVICES_AVAILABLE or not check_all:
            # Fall back to existing update_cache_status
            self.log("Using legacy cache status check")
            self.update_cache_status()
            return
        
        try:
            if check_type == "bars":
                from ..services.data_readiness_service import check_bars as check_bars_func
                ready, reason = check_bars_func(primary_market, timeframe, season, outputs_root)
                self.log(f"Bars check: {'READY' if ready else 'NOT READY'} - {reason}")
                
                # Update UI status
                if ready:
                    self.bars_cache_status = "READY"
                    self.bars_status_label.setText("READY")
                    self.bars_status_label.setStyleSheet("font-weight: bold; color: #29D38D;")
                else:
                    self.bars_cache_status = "MISSING"
                    self.bars_status_label.setText("MISSING")
                    self.bars_status_label.setStyleSheet("font-weight: bold; color: #FF4D4D;")
                
            elif check_type == "features":
                from ..services.data_readiness_service import check_features as check_features_func
                ready, reason = check_features_func(primary_market, timeframe, season, outputs_root)
                self.log(f"Features check: {'READY' if ready else 'NOT READY'} - {reason}")
                
                # Update UI status
                if ready:
                    self.features_cache_status = "READY"
                    self.features_status_label.setText("READY")
                    self.features_status_label.setStyleSheet("font-weight: bold; color: #29D38D;")
                else:
                    self.features_cache_status = "MISSING"
                    self.features_status_label.setText("MISSING")
                    self.features_status_label.setStyleSheet("font-weight: bold; color: #FF4D4D;")
                    
            else:  # "all"
                readiness = check_all(primary_market, timeframe, season, outputs_root)
                self.log(f"Bars check: {'READY' if readiness.bars_ready else 'NOT READY'} - {readiness.bars_reason}")
                self.log(f"Features check: {'READY' if readiness.features_ready else 'NOT READY'} - {readiness.features_reason}")
                
                # Update UI status
                self.bars_cache_status = "READY" if readiness.bars_ready else "MISSING"
                self.features_cache_status = "READY" if readiness.features_ready else "MISSING"
                
                self.bars_status_label.setText("READY" if readiness.bars_ready else "MISSING")
                self.bars_status_label.setStyleSheet(
                    "font-weight: bold; color: #29D38D;" if readiness.bars_ready
                    else "font-weight: bold; color: #FF4D4D;"
                )
                
                self.features_status_label.setText("READY" if readiness.features_ready else "MISSING")
                self.features_status_label.setStyleSheet(
                    "font-weight: bold; color: #29D38D;" if readiness.features_ready
                    else "font-weight: bold; color: #FF4D4D;"
                )
            
            # Update prepare button states
            self.prepare_bars_btn.setEnabled(self.bars_cache_status == "MISSING")
            self.prepare_features_btn.setEnabled(self.features_cache_status == "MISSING")
            self.prepare_all_btn.setEnabled(
                self.bars_cache_status == "MISSING" or self.features_cache_status == "MISSING"
            )
            
        except Exception as e:
            self.log(f"ERROR during check: {e}")
