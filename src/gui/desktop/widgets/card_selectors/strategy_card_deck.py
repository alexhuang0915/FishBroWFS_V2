"""
Strategy Card Deck - Multi-select card-based selector for strategies.

Features:
- Multi-select card deck with search/filter
- Visual feedback for selected cards
- Right-click context menu (remove, copy ID, help)
- Info icons with hover help
- Integration with existing registry data
"""

from typing import List, Dict, Any, Optional, Set
from PySide6.QtCore import Qt, Signal, QSize, QPoint
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QScrollArea,
    QLabel, QFrame, QPushButton, QLineEdit, QToolButton,
    QMenu, QSizePolicy, QSpacerItem
)
from PySide6.QtGui import QFont, QIcon, QAction, QCursor

from gui.desktop.widgets.card_selectors.base_card import SelectableCard


class StrategyCardDeck(QWidget):
    """
    Multi-select card deck for strategy selection.
    
    Replaces the strategy combobox with an explainable, card-based interface.
    Supports multi-selection with visual feedback and search/filter capabilities.
    """
    
    # Signals
    selection_changed = Signal(list)  # List of selected strategy IDs
    card_clicked = Signal(str, bool)  # strategy_id, is_selected
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.strategies: List[Dict[str, Any]] = []
        self.selected_ids: Set[str] = set()
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
        title_label = QLabel("Strategies")
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
        self.search_edit.setPlaceholderText("Search strategies...")
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
        self.status_label = QLabel("No strategies loaded")
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
        
        # Remove action
        self.remove_action = QAction("Remove from selection", self)
        self.remove_action.triggered.connect(self._handle_remove_action)
        
        # Copy ID action
        self.copy_id_action = QAction("Copy Strategy ID", self)
        self.copy_id_action.triggered.connect(self._handle_copy_id_action)
        
        # Help action
        self.help_action = QAction("Open Help", self)
        self.help_action.triggered.connect(self._handle_help_action)
        
        self.context_menu.addAction(self.remove_action)
        self.context_menu.addAction(self.copy_id_action)
        self.context_menu.addSeparator()
        self.context_menu.addAction(self.help_action)
        
    def load_strategies(self, strategies: List[Dict[str, Any]]):
        """Load strategies from registry data."""
        self.strategies = strategies
        self.cards.clear()
        
        # Clear layout
        while self.cards_layout.count():
            child = self.cards_layout.takeAt(0)
            if child.widget():
                child.widget().setParent(None)
        
        if not strategies:
            self.status_label.setText("No strategies available")
            return
        
        # Create cards
        for i, strategy in enumerate(strategies):
            strategy_id = strategy.get("id", "")
            strategy_name = strategy.get("name", "Unknown")
            description = strategy.get("description", "")
            
            # Create card
            card = SelectableCard(
                title=strategy_name,
                subtitle=strategy_id,
                description=description,
                data={"id": strategy_id, "name": strategy_name}
            )
            
            # Connect signals
            card.clicked.connect(self._handle_card_clicked)
            card.right_clicked.connect(self._handle_card_right_clicked)
            
            # Store card
            self.cards[strategy_id] = card
            
            # Add to layout (3 columns)
            row = i // 3
            col = i % 3
            self.cards_layout.addWidget(card, row, col)
        
        # Update status
        self.status_label.setText(f"{len(strategies)} strategies loaded")
        
    def filter_cards(self, text: str):
        """Filter cards based on search text."""
        search_lower = text.lower().strip()
        
        for strategy_id, card in self.cards.items():
            card_data = card.get_data()
            strategy_name = card_data.get("name", "").lower()
            strategy_id_lower = strategy_id.lower()
            
            # Show/hide based on search
            if (not search_lower or 
                search_lower in strategy_name or 
                search_lower in strategy_id_lower):
                card.show()
            else:
                card.hide()
        
        # Update layout
        self._rearrange_cards()
        
    def _rearrange_cards(self):
        """Rearrange visible cards in grid layout."""
        # Get visible cards
        visible_cards = []
        for strategy_id, card in self.cards.items():
            if card.isVisible():
                visible_cards.append((strategy_id, card))
        
        # Clear layout
        while self.cards_layout.count():
            child = self.cards_layout.takeAt(0)
            if child.widget():
                child.widget().setParent(None)
        
        # Add visible cards back in grid (3 columns)
        for i, (strategy_id, card) in enumerate(visible_cards):
            row = i // 3
            col = i % 3
            self.cards_layout.addWidget(card, row, col)
        
    def _handle_card_clicked(self, card: SelectableCard):
        """Handle card click event."""
        card_data = card.get_data()
        strategy_id = card_data.get("id", "")
        
        # Toggle selection
        if strategy_id in self.selected_ids:
            self.selected_ids.remove(strategy_id)
            card.set_selected(False)
        else:
            self.selected_ids.add(strategy_id)
            card.set_selected(True)
        
        # Emit signals
        self.card_clicked.emit(strategy_id, strategy_id in self.selected_ids)
        self.selection_changed.emit(list(self.selected_ids))
        
        # Update status
        self._update_status()
        
    def _handle_card_right_clicked(self, card: SelectableCard, pos: QPoint):
        """Handle card right-click event."""
        self.last_right_clicked_card = card
        self.context_menu.exec(QCursor.pos())
        
    def _handle_remove_action(self):
        """Handle remove from selection action."""
        if hasattr(self, 'last_right_clicked_card'):
            card_data = self.last_right_clicked_card.get_data()
            strategy_id = card_data.get("id", "")
            
            if strategy_id in self.selected_ids:
                self.selected_ids.remove(strategy_id)
                self.last_right_clicked_card.set_selected(False)
                
                # Emit signals
                self.selection_changed.emit(list(self.selected_ids))
                self._update_status()
        
    def _handle_copy_id_action(self):
        """Handle copy strategy ID action."""
        if hasattr(self, 'last_right_clicked_card'):
            card_data = self.last_right_clicked_card.get_data()
            strategy_id = card_data.get("id", "")
            
            # Copy to clipboard
            from PySide6.QtWidgets import QApplication
            clipboard = QApplication.clipboard()
            clipboard.setText(strategy_id)
            
            # Show feedback
            self.status_label.setText(f"Copied: {strategy_id}")
            
    def _handle_help_action(self):
        """Handle help action."""
        if hasattr(self, 'last_right_clicked_card'):
            card_data = self.last_right_clicked_card.get_data()
            strategy_name = card_data.get("name", "Unknown")
            strategy_id = card_data.get("id", "")
            
            # Show help dialog (simplified for now)
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(
                self,
                f"Help: {strategy_name}",
                f"Strategy ID: {strategy_id}\n\n"
                f"This is a trading strategy. Select it to include in your run.\n"
                f"You can select multiple strategies for batch processing."
            )
    
    def clear_selection(self):
        """Clear all selections."""
        for strategy_id in list(self.selected_ids):
            if strategy_id in self.cards:
                self.cards[strategy_id].set_selected(False)
        
        self.selected_ids.clear()
        self.selection_changed.emit([])
        self._update_status()
    
    def get_selected_strategies(self) -> List[Dict[str, Any]]:
        """Get selected strategies data."""
        selected = []
        for strategy in self.strategies:
            if strategy.get("id", "") in self.selected_ids:
                selected.append(strategy)
        return selected
    
    def get_selected_ids(self) -> List[str]:
        """Get selected strategy IDs."""
        return list(self.selected_ids)
    
    def set_selected_ids(self, strategy_ids: List[str]):
        """Set selected strategy IDs."""
        # Clear current selection
        for strategy_id in list(self.selected_ids):
            if strategy_id in self.cards:
                self.cards[strategy_id].set_selected(False)
        
        self.selected_ids.clear()
        
        # Set new selection
        for strategy_id in strategy_ids:
            if strategy_id in self.cards:
                self.cards[strategy_id].set_selected(True)
                self.selected_ids.add(strategy_id)
        
        self.selection_changed.emit(list(self.selected_ids))
        self._update_status()
    
    def _update_status(self):
        """Update status label."""
        count = len(self.selected_ids)
        if count == 0:
            self.status_label.setText("No strategies selected")
        elif count == 1:
            self.status_label.setText("1 strategy selected")
        else:
            self.status_label.setText(f"{count} strategies selected")