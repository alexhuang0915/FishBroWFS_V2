"""
Run Intent Dialog - Modal for configuring run intent.

This dialog contains all card-based selectors for configuring a run intent.
It operates on a draft copy of the operation state and only commits on Confirm.
"""

import logging
from typing import Optional, Dict, Any

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QWidget, QTabWidget,
    QLabel, QPushButton, QDialogButtonBox, QMessageBox
)

from gui.desktop.state.operation_state import RunIntent, operation_page_state
from gui.desktop.widgets.card_selectors import (
    StrategyCardDeck,
    TimeframeCardDeck,
    InstrumentCardList,
    ModePillCards,
    DateRangeSelector
)
from gui.desktop.services.supervisor_client import (
    get_registry_strategies, get_registry_instruments, get_registry_timeframes,
    SupervisorClientError
)

logger = logging.getLogger(__name__)


class RunIntentDialog(QDialog):
    """Dialog for configuring run intent with card-based selectors."""
    
    # Signal emitted when run intent is confirmed
    run_intent_confirmed = Signal(RunIntent)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Draft state (not committed until Confirm)
        self.draft_run_intent: RunIntent = RunIntent()
        
        # Card-based components
        self.strategy_deck: Optional[StrategyCardDeck] = None
        self.timeframe_deck: Optional[TimeframeCardDeck] = None
        self.instrument_list: Optional[InstrumentCardList] = None
        self.mode_pills: Optional[ModePillCards] = None
        self.date_range_selector: Optional[DateRangeSelector] = None
        
        self.setup_ui()
        self.setup_connections()
        self.load_registry_data()
        
        # Load current state into draft
        self.load_current_state()
    
    def setup_ui(self):
        """Initialize the UI with tabbed card selectors."""
        self.setWindowTitle("Configure Run Intent")
        self.setMinimumSize(1000, 700)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)
        
        # Title
        title_label = QLabel("Configure Run Intent")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #E6E6E6;")
        main_layout.addWidget(title_label)
        
        # Description
        desc_label = QLabel(
            "Configure your run intent using card-based selectors. "
            "Changes are not applied until you click Confirm."
        )
        desc_label.setStyleSheet("color: #9A9A9A; font-size: 12px;")
        desc_label.setWordWrap(True)
        main_layout.addWidget(desc_label)
        
        # Tab widget for different selector categories
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabPosition(QTabWidget.TabPosition.North)
        
        # Strategy tab
        strategy_tab = QWidget()
        strategy_layout = QVBoxLayout(strategy_tab)
        strategy_layout.setContentsMargins(8, 8, 8, 8)
        
        strategy_label = QLabel("Select Strategies (multi-select):")
        strategy_label.setStyleSheet("color: #E6E6E6; font-weight: bold; font-size: 14px;")
        strategy_layout.addWidget(strategy_label)
        
        self.strategy_deck = StrategyCardDeck()
        strategy_layout.addWidget(self.strategy_deck)
        
        strategy_layout.addStretch()
        self.tab_widget.addTab(strategy_tab, "Strategies")
        
        # Timeframe tab
        timeframe_tab = QWidget()
        timeframe_layout = QVBoxLayout(timeframe_tab)
        timeframe_layout.setContentsMargins(8, 8, 8, 8)
        
        timeframe_label = QLabel("Select Timeframes (multi-select):")
        timeframe_label.setStyleSheet("color: #E6E6E6; font-weight: bold; font-size: 14px;")
        timeframe_layout.addWidget(timeframe_label)
        
        self.timeframe_deck = TimeframeCardDeck()
        timeframe_layout.addWidget(self.timeframe_deck)
        
        timeframe_layout.addStretch()
        self.tab_widget.addTab(timeframe_tab, "Timeframes")
        
        # Instrument tab
        instrument_tab = QWidget()
        instrument_layout = QVBoxLayout(instrument_tab)
        instrument_layout.setContentsMargins(8, 8, 8, 8)
        
        instrument_label = QLabel("Select Instruments (multi-select):")
        instrument_label.setStyleSheet("color: #E6E6E6; font-weight: bold; font-size: 14px;")
        instrument_layout.addWidget(instrument_label)
        
        self.instrument_list = InstrumentCardList()
        instrument_layout.addWidget(self.instrument_list)
        
        instrument_layout.addStretch()
        self.tab_widget.addTab(instrument_tab, "Instruments")
        
        # Mode & Date tab
        mode_date_tab = QWidget()
        mode_date_layout = QVBoxLayout(mode_date_tab)
        mode_date_layout.setContentsMargins(8, 8, 8, 8)
        mode_date_layout.setSpacing(16)
        
        # Mode selection
        mode_label = QLabel("Select Run Mode (single-select):")
        mode_label.setStyleSheet("color: #E6E6E6; font-weight: bold; font-size: 14px;")
        mode_date_layout.addWidget(mode_label)
        
        self.mode_pills = ModePillCards()
        mode_date_layout.addWidget(self.mode_pills)
        
        # Date range selection
        date_label = QLabel("Date Range (for backtest/research modes):")
        date_label.setStyleSheet("color: #E6E6E6; font-weight: bold; font-size: 14px;")
        mode_date_layout.addWidget(date_label)
        
        self.date_range_selector = DateRangeSelector()
        mode_date_layout.addWidget(self.date_range_selector)
        
        mode_date_layout.addStretch()
        self.tab_widget.addTab(mode_date_tab, "Mode & Date")
        
        main_layout.addWidget(self.tab_widget)
        
        # Status label
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: #9A9A9A; font-size: 11px;")
        main_layout.addWidget(self.status_label)
        
        # Dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | 
            QDialogButtonBox.StandardButton.Cancel |
            QDialogButtonBox.StandardButton.Reset
        )
        button_box.button(QDialogButtonBox.StandardButton.Ok).setText("Confirm")
        button_box.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancel")
        button_box.button(QDialogButtonBox.StandardButton.Reset).setText("Reset")
        
        button_box.accepted.connect(self.on_confirm)
        button_box.rejected.connect(self.on_cancel)
        button_box.button(QDialogButtonBox.StandardButton.Reset).clicked.connect(self.on_reset)
        
        main_layout.addWidget(button_box)
    
    def setup_connections(self):
        """Connect signals and slots."""
        # Connect selection changes to update draft state
        if self.strategy_deck:
            self.strategy_deck.selection_changed.connect(self.on_strategy_selection_changed)
        
        if self.timeframe_deck:
            self.timeframe_deck.selection_changed.connect(self.on_timeframe_selection_changed)
        
        if self.instrument_list:
            self.instrument_list.selection_changed.connect(self.on_instrument_selection_changed)
        
        if self.mode_pills:
            self.mode_pills.selection_changed.connect(self.on_mode_selection_changed)
    
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
    
    def load_current_state(self):
        """Load current operation state into draft."""
        current_state = operation_page_state.get_state()
        self.draft_run_intent = current_state.run_intent
        
        # Update UI components to match draft state
        self.update_ui_from_draft()
    
    def update_ui_from_draft(self):
        """Update UI components to reflect draft state."""
        # Update strategy deck
        if self.strategy_deck and self.draft_run_intent.strategies:
            self.strategy_deck.set_selected_ids(self.draft_run_intent.strategies)
        
        # Update timeframe deck
        if self.timeframe_deck and self.draft_run_intent.timeframes:
            self.timeframe_deck.set_selected_ids(self.draft_run_intent.timeframes)
        
        # Update instrument list
        if self.instrument_list and self.draft_run_intent.instruments:
            self.instrument_list.set_selected_ids(self.draft_run_intent.instruments)
        
        # Update mode pills
        if self.mode_pills and self.draft_run_intent.mode:
            self.mode_pills.set_selected_mode(self.draft_run_intent.mode)
        
        # Update date range selector
        if self.date_range_selector:
            if self.draft_run_intent.start_date and self.draft_run_intent.end_date:
                self.date_range_selector.set_date_range(
                    self.draft_run_intent.start_date,
                    self.draft_run_intent.end_date
                )
    
    @Slot(list)
    def on_strategy_selection_changed(self, selected_strategy_ids: list):
        """Handle strategy selection changes."""
        self.draft_run_intent.strategies = selected_strategy_ids
        self.update_status()
    
    @Slot(list)
    def on_timeframe_selection_changed(self, selected_timeframe_ids: list):
        """Handle timeframe selection changes."""
        self.draft_run_intent.timeframes = selected_timeframe_ids
        self.update_status()
    
    @Slot(list)
    def on_instrument_selection_changed(self, selected_instrument_ids: list):
        """Handle instrument selection changes."""
        self.draft_run_intent.instruments = selected_instrument_ids
        self.update_status()
    
    @Slot(str)
    def on_mode_selection_changed(self, selected_mode: str):
        """Handle mode selection changes."""
        self.draft_run_intent.mode = selected_mode
        self.update_status()
        
        # Update date range selector visibility based on mode
        if self.date_range_selector:
            if selected_mode and selected_mode.lower() in ['backtest', 'research']:
                self.date_range_selector.setEnabled(True)
            else:
                self.date_range_selector.setEnabled(False)
    
    def update_status(self):
        """Update status label with current selection summary."""
        strategies_count = len(self.draft_run_intent.strategies)
        timeframes_count = len(self.draft_run_intent.timeframes)
        instruments_count = len(self.draft_run_intent.instruments)
        mode = self.draft_run_intent.mode or "Not selected"
        
        status_text = (
            f"Selected: {strategies_count} strategies, "
            f"{timeframes_count} timeframes, "
            f"{instruments_count} instruments, "
            f"Mode: {mode}"
        )
        self.status_label.setText(status_text)
    
    @Slot()
    def on_confirm(self):
        """Handle Confirm button click."""
        # Validate selections
        if not self.draft_run_intent.strategies:
            QMessageBox.warning(self, "No Strategy", "Please select at least one strategy.")
            return
        
        if not self.draft_run_intent.timeframes:
            QMessageBox.warning(self, "No Timeframe", "Please select at least one timeframe.")
            return
        
        if not self.draft_run_intent.instruments:
            QMessageBox.warning(self, "No Instrument", "Please select at least one instrument.")
            return
        
        if not self.draft_run_intent.mode:
            QMessageBox.warning(self, "No Mode", "Please select a run mode.")
            return
        
        # Get date range if needed
        if self.date_range_selector and self.draft_run_intent.mode.lower() in ['backtest', 'research']:
            date_range = self.date_range_selector.get_date_range()
            if date_range:
                self.draft_run_intent.start_date, self.draft_run_intent.end_date = date_range
        
        # Commit to SSOT on Confirm
        operation_page_state.update_state(
            run_intent=self.draft_run_intent,
            run_intent_confirmed=True,
        )

        # Emit signal with confirmed run intent (for backward compatibility)
        self.run_intent_confirmed.emit(self.draft_run_intent)
        
        # Close dialog
        self.accept()
    
    @Slot()
    def on_cancel(self):
        """Handle Cancel button click."""
        # Just close without committing changes
        self.reject()
    
    @Slot()
    def on_reset(self):
        """Handle Reset button click."""
        # Reset draft state to empty
        self.draft_run_intent = RunIntent()
        
        # Reset UI components
        if self.strategy_deck:
            self.strategy_deck.clear_selection()
        
        if self.timeframe_deck:
            self.timeframe_deck.clear_selection()
        
        if self.instrument_list:
            self.instrument_list.clear_selection()
        
        if self.mode_pills:
            self.mode_pills.clear_selection()
        
        if self.date_range_selector:
            self.date_range_selector.clear()
        
        self.update_status()