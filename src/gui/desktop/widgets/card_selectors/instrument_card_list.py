"""
Instrument Card List - Single-select card-based selector for instruments.

Features:
- Single-select card list for instruments
- Visual feedback for selected card
- Right-click context menu
- Info icons with instrument details
"""

from typing import List, Dict, Any, Optional
from PySide6.QtCore import Qt, Signal, QSize, QPoint
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QScrollArea,
    QLabel, QFrame, QPushButton, QLineEdit, QToolButton,
    QMenu, QSizePolicy, QSpacerItem
)
from PySide6.QtGui import QFont, QIcon, QAction, QCursor

from gui.desktop.widgets.card_selectors.base_card import SelectableCard


class InstrumentCardList(QWidget):
    """
    Single-select card list for instrument selection.
    
    Replaces the instrument combobox with an explainable, card-based interface.
    Supports single-selection with visual feedback.
    """
    
    # Signals
    selection_changed = Signal(str)  # Selected instrument ID (empty string if none)
    card_clicked = Signal(str, bool)  # instrument_id, is_selected
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.instruments: List[str] = []
        self.selected_id: str = ""
        self.cards: Dict[str, SelectableCard] = {}
        
        self.setup_ui()
        self.setup_context_menu()
        
    def setup_ui(self):
        """Initialize the UI components."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(8)
        
        # Header with title and search
        header_layout = QHBoxLayout()
        
        # Title
        title_label = QLabel("Instruments")
        title_label.setStyleSheet("""
            QLabel {
                font-weight: bold;
                font-size: 13px;
                color: #E6E6E6;
            }
        """)
        header_layout.addWidget(title_label)
        
        header_layout.addSpacerItem(QSpacerItem(20, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
        
        # Search box
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search instruments...")
        self.search_edit.setMaximumWidth(200)
        self.search_edit.setStyleSheet("""
            QLineEdit {
                background-color: #2A2A2A;
                border: 1px solid #444444;
                border-radius: 4px;
                padding: 4px 8px;
                color: #E6E6E6;
                font-size: 11px;
            }
            QLineEdit:focus {
                border: 1px solid #3A8DFF;
            }
        """)
        self.search_edit.textChanged.connect(self.filter_cards)
        header_layout.addWidget(self.search_edit)
        
        # Clear selection button
        self.clear_btn = QPushButton("Clear")
        self.clear_btn.setMaximumWidth(60)
        self.clear_btn.setStyleSheet("""
            QPushButton {
                background-color: #424242;
                color: #E6E6E6;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #555555;
                border: 1px solid #666666;
            }
            QPushButton:pressed {
                background-color: #333333;
            }
        """)
        self.clear_btn.clicked.connect(self.clear_selection)
        header_layout.addWidget(self.clear_btn)
        
        main_layout.addLayout(header_layout)
        
        # Scroll area for cards
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            QScrollArea > QWidget > QWidget {
                background-color: transparent;
            }
        """)
        
        # Cards container
        self.cards_container = QWidget()
        self.cards_layout = QGridLayout(self.cards_container)
        self.cards_layout.setContentsMargins(4, 4, 4, 4)
        self.cards_layout.setHorizontalSpacing(8)
        self.cards_layout.setVerticalSpacing(8)
        
        scroll.setWidget(self.cards_container)
        main_layout.addWidget(scroll)
        
        # Status label
        self.status_label = QLabel("No instruments loaded")
        self.status_label.setStyleSheet("""
            QLabel {
                color: #9A9A9A;
                font-size: 10px;
                font-style: italic;
            }
        """)
        main_layout.addWidget(self.status_label)
        
    def setup_context_menu(self):
        """Setup right-click context menu for cards."""
        self.context_menu = QMenu(self)
        
        # Select action (for non-selected cards)
        self.select_action = QAction("Select Instrument", self)
        self.select_action.triggered.connect(self._handle_select_action)
        
        # Deselect action (for selected cards)
        self.deselect_action = QAction("Deselect Instrument", self)
        self.deselect_action.triggered.connect(self._handle_deselect_action)
        
        # Copy ID action
        self.copy_id_action = QAction("Copy Instrument ID", self)
        self.copy_id_action.triggered.connect(self._handle_copy_id_action)
        
        # Help action
        self.help_action = QAction("Open Help", self)
        self.help_action.triggered.connect(self._handle_help_action)
        
        self.context_menu.addAction(self.select_action)
        self.context_menu.addAction(self.deselect_action)
        self.context_menu.addSeparator()
        self.context_menu.addAction(self.copy_id_action)
        self.context_menu.addSeparator()
        self.context_menu.addAction(self.help_action)
        
    def load_instruments(self, instruments: List[str]):
        """Load instruments from registry data."""
        self.instruments = instruments
        self.cards.clear()
        
        # Clear layout
        while self.cards_layout.count():
            child = self.cards_layout.takeAt(0)
            if child.widget():
                child.widget().setParent(None)
        
        if not instruments:
            self.status_label.setText("No instruments available")
            return
        
        # Create cards
        for i, instrument_id in enumerate(instruments):
            # Create a display name (capitalize, replace underscores)
            display_name = instrument_id.replace("_", " ").title()
            
            # Create card
            card = SelectableCard(
                title=display_name,
                subtitle=instrument_id,
                description=f"Trading instrument: {instrument_id}",
                data={"id": instrument_id, "name": display_name}
            )
            
            # Connect signals
            card.clicked.connect(self._handle_card_clicked)
            card.right_clicked.connect(self._handle_card_right_clicked)
            
            # Store card
            self.cards[instrument_id] = card
            
            # Add to layout (2 columns for instruments)
            row = i // 2
            col = i % 2
            self.cards_layout.addWidget(card, row, col)
        
        # Update status
        self.status_label.setText(f"{len(instruments)} instruments loaded")
        
    def filter_cards(self, text: str):
        """Filter cards based on search text."""
        search_lower = text.lower().strip()
        
        for instrument_id, card in self.cards.items():
            card_data = card.get_data()
            instrument_name = card_data.get("name", "").lower()
            instrument_id_lower = instrument_id.lower()
            
            # Show/hide based on search
            if (not search_lower or 
                search_lower in instrument_name or 
                search_lower in instrument_id_lower):
                card.show()
            else:
                card.hide()
        
        # Update layout
        self._rearrange_cards()
        
    def _rearrange_cards(self):
        """Rearrange visible cards in grid layout."""
        # Get visible cards
        visible_cards = []
        for instrument_id, card in self.cards.items():
            if card.isVisible():
                visible_cards.append((instrument_id, card))
        
        # Clear layout
        while self.cards_layout.count():
            child = self.cards_layout.takeAt(0)
            if child.widget():
                child.widget().setParent(None)
        
        # Add visible cards back in grid (2 columns)
        for i, (instrument_id, card) in enumerate(visible_cards):
            row = i // 2
            col = i % 2
            self.cards_layout.addWidget(card, row, col)
        
    def _handle_card_clicked(self, card: SelectableCard):
        """Handle card click event."""
        card_data = card.get_data()
        instrument_id = card_data.get("id", "")
        
        # Single-select: deselect previous if different
        if instrument_id != self.selected_id:
            # Deselect previous card
            if self.selected_id and self.selected_id in self.cards:
                self.cards[self.selected_id].set_selected(False)
            
            # Select new card
            self.selected_id = instrument_id
            card.set_selected(True)
            
            # Emit signals
            self.card_clicked.emit(instrument_id, True)
            self.selection_changed.emit(instrument_id)
        else:
            # Clicking the already selected card deselects it
            self.selected_id = ""
            card.set_selected(False)
            
            # Emit signals
            self.card_clicked.emit(instrument_id, False)
            self.selection_changed.emit("")
        
        # Update status
        self._update_status()
        
    def _handle_card_right_clicked(self, card: SelectableCard, pos: QPoint):
        """Handle card right-click event."""
        self.last_right_clicked_card = card
        self.context_menu.exec(QCursor.pos())
        
    def _handle_select_action(self):
        """Handle select action from context menu."""
        if hasattr(self, 'last_right_clicked_card'):
            card_data = self.last_right_clicked_card.get_data()
            instrument_id = card_data.get("id", "")
            
            # Select this instrument
            self._handle_card_clicked(self.last_right_clicked_card)
        
    def _handle_deselect_action(self):
        """Handle deselect action from context menu."""
        if hasattr(self, 'last_right_clicked_card'):
            card_data = self.last_right_clicked_card.get_data()
            instrument_id = card_data.get("id", "")
            
            # Only deselect if this is the currently selected card
            if instrument_id == self.selected_id:
                self.selected_id = ""
                self.last_right_clicked_card.set_selected(False)
                
                # Emit signals
                self.card_clicked.emit(instrument_id, False)
                self.selection_changed.emit("")
                self._update_status()
        
    def _handle_copy_id_action(self):
        """Handle copy instrument ID action."""
        if hasattr(self, 'last_right_clicked_card'):
            card_data = self.last_right_clicked_card.get_data()
            instrument_id = card_data.get("id", "")
            
            # Copy to clipboard
            from PySide6.QtWidgets import QApplication
            clipboard = QApplication.clipboard()
            clipboard.setText(instrument_id)
            
            # Show feedback
            self.status_label.setText(f"Copied: {instrument_id}")
            
    def _handle_help_action(self):
        """Handle help action."""
        if hasattr(self, 'last_right_clicked_card'):
            card_data = self.last_right_clicked_card.get_data()
            instrument_name = card_data.get("name", "Unknown")
            instrument_id = card_data.get("id", "")
            
            # Show help dialog
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(
                self,
                f"Help: {instrument_name}",
                f"Instrument ID: {instrument_id}\n\n"
                f"This is a trading instrument (e.g., futures contract, stock, forex pair).\n"
                f"Select one instrument to run your strategy on.\n\n"
                f"Note: Only one instrument can be selected at a time."
            )
    
    def clear_selection(self):
        """Clear selection."""
        if self.selected_id and self.selected_id in self.cards:
            self.cards[self.selected_id].set_selected(False)
        
        old_selected = self.selected_id
        self.selected_id = ""
        
        if old_selected:
            self.card_clicked.emit(old_selected, False)
        self.selection_changed.emit("")
        self._update_status()
    
    def get_selected_instrument(self) -> Optional[str]:
        """Get selected instrument ID."""
        return self.selected_id if self.selected_id else None
    
    def set_selected_instrument(self, instrument_id: str):
        """Set selected instrument ID."""
        # Clear current selection
        if self.selected_id and self.selected_id in self.cards:
            self.cards[self.selected_id].set_selected(False)
        
        # Set new selection
        if instrument_id and instrument_id in self.cards:
            self.cards[instrument_id].set_selected(True)
            self.selected_id = instrument_id
            
            # Emit signals
            self.card_clicked.emit(instrument_id, True)
            self.selection_changed.emit(instrument_id)
        else:
            self.selected_id = ""
            self.selection_changed.emit("")
        
        self._update_status()
    
    def _update_status(self):
        """Update status label."""
        if self.selected_id:
            self.status_label.setText(f"Selected: {self.selected_id}")
        else:
            self.status_label.setText("No instrument selected")