"""
OP (Operator Console) Tab - Phase C Professional CTA Desktop UI with Route 2 Card-Based Launch Pad.

Route 3 Cutover: This is now the canonical OP tab with ONLY card-based UI.
No legacy dropdowns - uses card-based selectors from Route 2.
"""

# pylint: disable=no-name-in-module,c-extension-no-member

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
from PySide6.QtCore import (
    Qt, Signal, QTimer, QModelIndex, QAbstractTableModel,
    QUrl, QSize, QPersistentModelIndex
)  # pylint: disable=no-name-in-module
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QPushButton, QTableView, QSplitter,
    QGroupBox, QScrollArea, QSizePolicy,
    QStyledItemDelegate, QStyleOptionViewItem,
    QMessageBox, QSpacerItem, QLineEdit, QCheckBox
)  # pylint: disable=no-name-in-module
from PySide6.QtGui import QFont, QPainter, QBrush, QColor, QPen, QDesktopServices  # pylint: disable=no-name-in-module

import json
from gui.desktop.widgets.log_viewer import LogViewerDialog
from gui.desktop.widgets.gate_summary_widget import GateSummaryWidget
from gui.desktop.widgets.explain_hub_widget import ExplainHubWidget
from gui.desktop.widgets.analysis_drawer_widget import AnalysisDrawerWidget
from gui.desktop.widgets.season_ssot_dialog import SeasonSSOTDialog
from gui.desktop.widgets.data_prepare_panel import DataPreparePanel

# Route 2 Card-Based Components
from gui.desktop.widgets.card_selectors import (
    StrategyCardDeck,
    TimeframeCardDeck,
    InstrumentCardList,
    ModePillCards,
    DerivedDatasetPanel,
    RunReadinessPanel,
    DateRangeSelector,
    HelpIcon
)

from gui.desktop.services.supervisor_client import (
    SupervisorClientError,
    get_registry_strategies, get_registry_instruments, get_registry_timeframes,
    get_jobs, get_artifacts, get_strategy_report_v1,
    get_reveal_evidence_path, submit_job
)
from gui.services.job_status_translator import translate_job_status
from gui.services.control_actions_gate import is_control_actions_enabled, is_abort_allowed
from gui.services.ui_action_evidence import write_abort_request_evidence, EvidenceWriteError
from gui.desktop.services.supervisor_client import abort_job
from gui.services.hybrid_bc_adapters import adapt_to_context
from gui.services.hybrid_bc_vms import JobContextVM
from gui.services.job_lifecycle_service import JobLifecycleService
from gui.services.dataset_resolver import DatasetResolver

logger = logging.getLogger(__name__)


class OpTab(QWidget):
    """Operator Console tab - Route 3 Card-Based UI."""
    
    # Signals for communication with main window
    log_signal = Signal(str)
    switch_to_audit_tab = Signal(str)  # job_id for report
    progress_signal = Signal(int)  # progress updates
    artifact_state_changed = Signal(str, str, str)  # state, run_id, run_dir
    
    def __init__(self):
        super().__init__()
        self.job_lifecycle_service = JobLifecycleService()
        self.job_lifecycle_service.sync_index_with_filesystem()
        self.dataset_resolver = DatasetResolver()
        
        # Card-based components
        self.strategy_deck = None
        self.timeframe_deck = None
        self.instrument_list = None
        self.mode_pills = None
        self.dataset_panel = None
        self.date_range_selector = None
        self.run_readiness_panel = None
        
        # Data Prepare Panel (Explain Hub)
        self.data_prepare_panel = None
        
        self.setup_ui()
        self.setup_connections()
        self.load_registry_data()
    
    def setup_ui(self):
        """Initialize the UI with card-based components."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)
        
        # Gate Summary panel
        self.gate_summary_widget = GateSummaryWidget()
        main_layout.addWidget(self.gate_summary_widget)
        
        # Create main splitter
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #555555;
                width: 1px;
            }
            QSplitter::handle:hover {
                background-color: #3A8DFF;
            }
        """)
        
        # Left panel: Card-Based Launch Pad
        left_widget = QWidget()
        left_widget.setStyleSheet("background-color: #121212;")
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(4, 4, 4, 4)
        left_layout.setSpacing(8)
        
        # Launch Pad group
        launch_group = QGroupBox("Launch Pad (Card-Based)")
        launch_group.setStyleSheet("""
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
        
        # Scroll area for card components
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: #1E1E1E;
            }
        """)
        
        card_widget = QWidget()
        card_layout = QVBoxLayout(card_widget)
        card_layout.setContentsMargins(12, 12, 12, 12)
        card_layout.setSpacing(12)
        
        # Strategy Card Deck
        strategy_label = QLabel("Select Strategy (multi-select):")
        strategy_label.setStyleSheet("color: #E6E6E6; font-weight: bold;")
        card_layout.addWidget(strategy_label)
        
        self.strategy_deck = StrategyCardDeck()
        card_layout.addWidget(self.strategy_deck)
        
        # Timeframe Card Deck
        timeframe_label = QLabel("Select Timeframe (multi-select):")
        timeframe_label.setStyleSheet("color: #E6E6E6; font-weight: bold;")
        card_layout.addWidget(timeframe_label)
        
        self.timeframe_deck = TimeframeCardDeck()
        card_layout.addWidget(self.timeframe_deck)
        
        # Instrument Card List
        instrument_label = QLabel("Select Instrument (single-select):")
        instrument_label.setStyleSheet("color: #E6E6E6; font-weight: bold;")
        card_layout.addWidget(instrument_label)
        
        self.instrument_list = InstrumentCardList()
        card_layout.addWidget(self.instrument_list)
        
        # Mode Pills
        mode_label = QLabel("Select Mode (single-select):")
        mode_label.setStyleSheet("color: #E6E6E6; font-weight: bold;")
        card_layout.addWidget(mode_label)
        
        self.mode_pills = ModePillCards()
        card_layout.addWidget(self.mode_pills)
        
        # Derived Dataset Panel
        dataset_label = QLabel("Derived Datasets:")
        dataset_label.setStyleSheet("color: #E6E6E6; font-weight: bold;")
        card_layout.addWidget(dataset_label)
        
        self.dataset_panel = DerivedDatasetPanel()
        card_layout.addWidget(self.dataset_panel)
        
        # Date Range Selector
        date_label = QLabel("Date Range:")
        date_label.setStyleSheet("color: #E6E6E6; font-weight: bold;")
        card_layout.addWidget(date_label)
        
        self.date_range_selector = DateRangeSelector()
        card_layout.addWidget(self.date_range_selector)
        
        # Run Readiness Panel
        readiness_label = QLabel("Run Readiness:")
        readiness_label.setStyleSheet("color: #E6E6E6; font-weight: bold;")
        card_layout.addWidget(readiness_label)
        
        self.run_readiness_panel = RunReadinessPanel()
        card_layout.addWidget(self.run_readiness_panel)
        
        # RUN STRATEGY button
        self.run_button = QPushButton("RUN STRATEGY")
        self.run_button.setStyleSheet("""
            QPushButton {
                background-color: #1a237e;
                color: white;
                font-weight: bold;
                font-size: 14px;
                padding: 12px;
                border-radius: 6px;
                border: 2px solid #283593;
            }
            QPushButton:hover {
                background-color: #283593;
                border: 2px solid #3949ab;
            }
            QPushButton:pressed {
                background-color: #0d47a1;
            }
            QPushButton:disabled {
                background-color: #424242;
                color: #9e9e9e;
                border: 2px solid #616161;
            }
        """)
        self.run_button.setMinimumHeight(50)
        card_layout.addWidget(self.run_button)
        
        # Add stretch
        card_layout.addSpacerItem(QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))
        
        # Set card widget to scroll area
        scroll.setWidget(card_widget)
        
        # Add scroll area to launch group
        launch_layout = QVBoxLayout(launch_group)
        launch_layout.addWidget(scroll)
        
        # Add launch group to left panel
        left_layout.addWidget(launch_group)
        
        # Right panel: Explain Hub (Job Tracker)
        right_widget = QWidget()
        right_widget.setStyleSheet("background-color: #121212;")
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(4, 4, 4, 4)
        right_layout.setSpacing(8)
        
        # Explain Hub group
        explain_group = QGroupBox("Job Tracker & Explain Hub")
        explain_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 2px solid #1b5e20;
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
        
        # Create Data Prepare Panel for Explain Hub
        self.data_prepare_panel = DataPreparePanel()
        
        explain_layout = QVBoxLayout(explain_group)
        explain_layout.addWidget(self.data_prepare_panel)
        
        # Add explain group to right panel
        right_layout.addWidget(explain_group)
        
        # Add panels to splitter
        main_splitter.addWidget(left_widget)
        main_splitter.addWidget(right_widget)
        main_splitter.setSizes([400, 600])  # 40% left, 60% right
        
        # Add splitter to main layout
        main_layout.addWidget(main_splitter)
        
        # Status label
        self.status_label = QLabel("Ready - Card-Based Launch Pad Active")
        self.status_label.setStyleSheet("color: #9e9e9e; font-size: 10px;")
        main_layout.addWidget(self.status_label)
    
    def setup_connections(self):
        """Connect signals and slots."""
        # Connect RUN button
        self.run_button.clicked.connect(self.run_strategy)
        
        # Connect card selection changes to update dataset panel
        if self.strategy_deck:
            self.strategy_deck.selection_changed.connect(self.update_dataset_panel)
        if self.timeframe_deck:
            self.timeframe_deck.selection_changed.connect(self.update_dataset_panel)
        if self.instrument_list:
            self.instrument_list.selection_changed.connect(self.update_dataset_panel)
        if self.mode_pills:
            self.mode_pills.selection_changed.connect(self.update_dataset_panel)
    
    def load_registry_data(self):
        """Load registry data and populate card components."""
        try:
            # Load strategies
            strategies = get_registry_strategies()
            if self.strategy_deck and isinstance(strategies, list):
                self.strategy_deck.load_strategies(strategies)
            
            # Load instruments
            instruments = get_registry_instruments()
            if self.instrument_list and isinstance(instruments, list):
                self.instrument_list.load_instruments(instruments)
            
            # Load timeframes
            timeframes = get_registry_timeframes()
            if self.timeframe_deck and isinstance(timeframes, list):
                # Convert list of timeframe strings to list of dicts for the card deck
                timeframe_dicts = [{"id": tf, "name": tf.replace("_", " ").title()} for tf in timeframes]
                self.timeframe_deck.load_timeframes(timeframe_dicts)
            
            self.status_label.setText("Registry data loaded")
            
        except SupervisorClientError as e:
            self.status_label.setText(f"Failed to load registry: {e}")
            logger.error(f"Failed to load registry data: {e}")
    
    def update_dataset_panel(self):
        """Update dataset panel based on current selections."""
        try:
            # Get current selections
            selected_strategies = self.strategy_deck.get_selected_strategies() if self.strategy_deck else []
            selected_timeframes = self.timeframe_deck.get_selected_timeframes() if self.timeframe_deck else []
            selected_instrument = self.instrument_list.get_selected_instrument() if self.instrument_list else None
            selected_mode = self.mode_pills.get_selected_mode() if self.mode_pills else None
            
            # We need at least one strategy, one timeframe, and one instrument to derive datasets
            if not selected_strategies or not selected_timeframes or not selected_instrument:
                if self.dataset_panel:
                    self.dataset_panel.clear()
                if self.run_readiness_panel:
                    self.run_readiness_panel.clear()
                if self.data_prepare_panel:
                    self.data_prepare_panel.clear()
                return
            
            # Use the first selected strategy for dataset resolution
            strategy_id = selected_strategies[0].get('id') if selected_strategies else None
            timeframe_id = selected_timeframes[0].get('id') if selected_timeframes else None
            
            if strategy_id and timeframe_id and selected_instrument and selected_mode:
                # Derive datasets
                derived = self.dataset_resolver.resolve(
                    strategy_id=strategy_id,
                    instrument_id=selected_instrument,
                    timeframe_id=timeframe_id,
                    mode=selected_mode.lower(),
                    season=None  # TODO: Add season selection
                )
                
                # Update dataset panel (Launch Pad)
                if self.dataset_panel:
                    self.dataset_panel.update_data(derived)
                
                # Update data prepare panel (Explain Hub)
                if self.data_prepare_panel:
                    self.data_prepare_panel.set_datasets(derived)
                
                # Update run readiness panel
                if self.run_readiness_panel:
                    gate_status = self.dataset_resolver.evaluate_run_readiness_with_prepare_status(
                        strategy_id=strategy_id,
                        instrument_id=selected_instrument,
                        timeframe_id=timeframe_id,
                        mode=selected_mode.lower(),
                        season=None
                    )
                    self.run_readiness_panel.set_gate_status(gate_status)
                    
                    # Enable/disable run button based on gate status
                    if self.run_button:
                        self.run_button.setEnabled(gate_status.level != "FAIL")
            
        except Exception as e:
            logger.error(f"Failed to update dataset panel: {e}")
            # Just log the error, don't try to show it on UI panels
            # that don't have show_error method
    
    def run_strategy(self):
        """Submit a new strategy job."""
        # Get selections
        selected_strategies = self.strategy_deck.get_selected_strategies() if self.strategy_deck else []
        selected_timeframes = self.timeframe_deck.get_selected_timeframes() if self.timeframe_deck else []
        selected_instrument = self.instrument_list.get_selected_instrument() if self.instrument_list else None
        selected_mode = self.mode_pills.get_selected_mode() if self.mode_pills else None
        
        # Validate selections
        if not selected_strategies:
            QMessageBox.warning(self, "No Strategy", "Please select at least one strategy.")
            return
        
        if not selected_timeframes:
            QMessageBox.warning(self, "No Timeframe", "Please select at least one timeframe.")
            return
        
        if not selected_instrument:
            QMessageBox.warning(self, "No Instrument", "Please select an instrument.")
            return
        
        if not selected_mode:
            QMessageBox.warning(self, "No Mode", "Please select a run mode.")
            return
        
        # Use the first selected strategy
        strategy = selected_strategies[0]
        strategy_id = strategy.get('id')
        
        # Use the first selected timeframe
        timeframe = selected_timeframes[0]
        timeframe_id = timeframe.get('id')
        
        # Get date range if needed
        start_date = None
        end_date = None
        if self.date_range_selector and selected_mode.lower() in ['backtest', 'research']:
            date_range = self.date_range_selector.get_date_range()
            if date_range:
                start_date, end_date = date_range
        
        # Prepare job parameters
        params = {
            "strategy_id": strategy_id,
            "instrument": selected_instrument,
            "timeframe": timeframe_id,
            "run_mode": selected_mode.lower(),
            "season": "2026"
        }
        
        # Add date range if provided
        if start_date and end_date:
            params["start_date"] = start_date
            params["end_date"] = end_date
        
        try:
            # Submit job
            job_id = submit_job(params)
            
            # Show success message
            QMessageBox.information(
                self,
                "Job Submitted",
                f"Job {job_id} submitted successfully.\n"
                f"Strategy: {strategy_id}\n"
                f"Instrument: {selected_instrument}\n"
                f"Timeframe: {timeframe_id}\n"
                f"Mode: {selected_mode}"
            )
            
            # Update status
            self.status_label.setText(f"Job {job_id} submitted")
            
            # Emit signal to refresh job tracker
            self.log_signal.emit(f"Job {job_id} submitted")
            
        except SupervisorClientError as e:
            QMessageBox.critical(self, "Job Submission Failed", f"Failed to submit job: {e}")
            logger.error(f"Job submission failed: {e}")
    
    def refresh_job_list(self):
        """Refresh the job list in the tracker."""
        # This is a placeholder - in a real implementation, this would
        # update the job tracker widget with current jobs
        pass
    
    def show_analysis_drawer(self, job_id: str):
        """Show analysis drawer for a completed job."""
        try:
            drawer = AnalysisDrawerWidget(job_id, self)
            drawer.exec()
        except Exception as e:
            QMessageBox.warning(self, "Analysis Drawer Error", f"Cannot open analysis drawer: {e}")
            logger.error(f"Failed to open analysis drawer for job {job_id}: {e}")
    
    def show_season_ssot(self):
        """Show season SSOT dialog."""
        dialog = SeasonSSOTDialog(self)
        dialog.exec()
    
    def show_log_viewer(self):
        """Show log viewer dialog."""
        dialog = LogViewerDialog(self)
        dialog.exec()
    
    def show_explain_hub(self):
        """Show explain hub dialog."""
        dialog = ExplainHubWidget(self)
        dialog.exec()
    
    def on_job_selected(self, job_id: str):
        """Handle job selection in tracker."""
        # This would update UI to show details of selected job
        pass
    
    def on_abort_job(self, job_id: str):
        """Handle abort job request."""
        if not is_abort_allowed():
            QMessageBox.warning(self, "Abort Not Allowed", "Abort action is not currently allowed.")
            return
        
        try:
            abort_job(job_id)
            write_abort_request_evidence(job_id)
            QMessageBox.information(self, "Job Aborted", f"Job {job_id} aborted.")
            self.log_signal.emit(f"Job {job_id} aborted")
        except Exception as e:
            QMessageBox.critical(self, "Abort Failed", f"Failed to abort job: {e}")
            logger.error(f"Failed to abort job {job_id}: {e}")
    
    def on_view_report(self, job_id: str):
        """Handle view report request."""
        try:
            report = get_strategy_report_v1(job_id)
            if report:
                # Switch to audit tab with report
                self.switch_to_audit_tab.emit(job_id)
            else:
                QMessageBox.warning(self, "Report Not Available", f"No report available for job {job_id}")
        except Exception as e:
            QMessageBox.warning(self, "Report Error", f"Cannot retrieve report: {e}")
            logger.error(f"Failed to get report for job {job_id}: {e}")
    
    def on_reveal_evidence(self, job_id: str):
        """Handle reveal evidence request."""
        try:
            evidence_path = get_reveal_evidence_path(job_id)
            if evidence_path:
                QDesktopServices.openUrl(QUrl.fromLocalFile(evidence_path))
            else:
                QMessageBox.warning(self, "Evidence Not Found", f"No evidence found for job {job_id}")
        except Exception as e:
            QMessageBox.warning(self, "Evidence Error", f"Cannot reveal evidence: {e}")
            logger.error(f"Failed to reveal evidence for job {job_id}: {e}")
