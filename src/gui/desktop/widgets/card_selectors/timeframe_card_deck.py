"""
Timeframe Card Deck - Multi-select card-based selector for timeframes.

Features:
- Multi-select card deck for timeframes
- Visual grouping by timeframe category (intraday, daily, etc.)
- Right-click context menu
- Info icons with timeframe explanations
"""

from typing import List, Dict, Any, Optional, Set
from PySide6.QtCore import Qt, Signal, QSize, QPoint
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QScrollArea,
    QLabel, QFrame, QPushButton, QLineEdit, QToolButton,
    QMenu, QSizePolicy, QSpacerItem, QGroupBox
)
from PySide6.QtGui import QFont, QIcon, QAction, QCursor

from gui.desktop.widgets.card_selectors.base_card import SelectableCard


class TimeframeCardDeck(QWidget):
    """
    Multi-select card deck for timeframe selection.
    
    Replaces the timeframe combobox with an explainable, card-based interface.
    Supports multi-selection with visual feedback and categorization.
    """
    
    # Signals
    selection_changed = Signal(list)  # List of selected timeframe IDs
    card_clicked = Signal(str, bool)  # timeframe_id, is_selected
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.timeframes: List[Dict[str, Any]] = []
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
        title_label = QLabel("Timeframes")
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
        self.search_edit.setPlaceholderText("Search timeframes...")
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
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(4, 4, 4, 4)
        self.cards_layout.setSpacing(12)
        
        # Create category groups
        self.intraday_group = self._create_category_group("Intraday (Minutes)")
        self.hourly_group = self._create_category_group("Hourly")
        self.daily_group = self._create_category_group("Daily")
        self.weekly_group = self._create_category_group("Weekly")
        self.other_group = self._create_category_group("Other")
        
        self.cards_layout.addWidget(self.intraday_group)
        self.cards_layout.addWidget(self.hourly_group)
        self.cards_layout.addWidget(self.daily_group)
        self.cards_layout.addWidget(self.weekly_group)
        self.cards_layout.addWidget(self.other_group)
        
        scroll.setWidget(self.cards_container)
        main_layout.addWidget(scroll)
        
        # Status label
        self.status_label = QLabel("No timeframes loaded")
        self.status_label.setStyleSheet("""
            QLabel {
                color: #9A9A9A;
                font-size: 10px;
                font-style: italic;
            }
        """)
        main_layout.addWidget(self.status_label)
        
    def _create_category_group(self, title: str) -> QGroupBox:
        """Create a category group for timeframes."""
        group = QGroupBox(title)
        group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 1px solid #444444;
                border-radius: 4px;
                margin-top: 10px;
                padding-top: 10px;
                background-color: #252525;
                color: #E6E6E6;
                font-size: 11px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px 0 4px;
                color: #B0B0B0;
            }
        """)
        
        layout = QGridLayout(group)
        layout.setContentsMargins(8, 16, 8, 8)
        layout.setHorizontalSpacing(8)
        layout.setVerticalSpacing(8)
        
        return group
    
    def setup_context_menu(self):
        """Setup right-click context menu for cards."""
        self.context_menu = QMenu(self)
        
        # Remove action
        self.remove_action = QAction("Remove from selection", self)
        self.remove_action.triggered.connect(self._handle_remove_action)
        
        # Copy ID action
        self.copy_id_action = QAction("Copy Timeframe ID", self)
        self.copy_id_action.triggered.connect(self._handle_copy_id_action)
        
        # Help action
        self.help_action = QAction("Open Help", self)
        self.help_action.triggered.connect(self._handle_help_action)
        
        self.context_menu.addAction(self.remove_action)
        self.context_menu.addAction(self.copy_id_action)
        self.context_menu.addSeparator()
        self.context_menu.addAction(self.help_action)
        
    def load_timeframes(self, timeframes: List[Dict[str, Any]]):
        """Load timeframes from registry data."""
        self.timeframes = timeframes
        self.cards.clear()
        
        # Clear all category groups
        for group in [self.intraday_group, self.hourly_group, self.daily_group, 
                     self.weekly_group, self.other_group]:
            layout = group.layout()
            while layout.count():
                child = layout.takeAt(0)
                if child.widget():
                    child.widget().setParent(None)
        
        if not timeframes:
            self.status_label.setText("No timeframes available")
            return
        
        # Create cards and categorize them
        for i, timeframe in enumerate(timeframes):
            timeframe_id = timeframe.get("id", "")
            timeframe_name = timeframe.get("name", "Unknown")
            description = timeframe.get("description", "")
            category = self._categorize_timeframe(timeframe_id)
            
            # Create card
            card = SelectableCard(
                title=timeframe_name,
                subtitle=timeframe_id,
                description=description,
                data={"id": timeframe_id, "name": timeframe_name, "category": category}
            )
            
            # Connect signals
            card.clicked.connect(self._handle_card_clicked)
            card.right_clicked.connect(self._handle_card_right_clicked)
            
            # Store card
            self.cards[timeframe_id] = card
            
            # Add to appropriate category group
            target_group = self._get_category_group(category)
            layout = target_group.layout()
            
            # Count cards in this group
            card_count = layout.count()
            row = card_count // 3
            col = card_count % 3
            layout.addWidget(card, row, col)
        
        # Hide empty groups
        self._update_group_visibility()
        
        # Update status
        self.status_label.setText(f"{len(timeframes)} timeframes loaded")
        
    def _categorize_timeframe(self, timeframe_id: str) -> str:
        """Categorize timeframe based on its ID."""
        timeframe_id_lower = timeframe_id.lower()
        
        if "m" in timeframe_id_lower and not "h" in timeframe_id_lower:
            # Check if it's minutes (e.g., "5m", "15m", "30m")
            try:
                minutes = int(timeframe_id_lower.replace("m", ""))
                if minutes < 60:
                    return "intraday"
            except ValueError:
                pass
        elif "h" in timeframe_id_lower:
            return "hourly"
        elif "d" in timeframe_id_lower:
            return "daily"
        elif "w" in timeframe_id_lower:
            return "weekly"
        
        return "other"
    
    def _get_category_group(self, category: str) -> QGroupBox:
        """Get the group box for a category."""
        groups = {
            "intraday": self.intraday_group,
            "hourly": self.hourly_group,
            "daily": self.daily_group,
            "weekly": self.weekly_group,
            "other": self.other_group
        }
        return groups.get(category, self.other_group)
    
    def _update_group_visibility(self):
        """Update group visibility based on whether they have cards."""
        for group in [self.intraday_group, self.hourly_group, self.daily_group,
                     self.weekly_group, self.other_group]:
            layout = group.layout()
            if layout.count() > 0:
                group.show()
            else:
                group.hide()
    
    def filter_cards(self, text: str):
        """Filter cards based on search text."""
        search_lower = text.lower().strip()
        
        for timeframe_id, card in self.cards.items():
            card_data = card.get_data()
            timeframe_name = card_data.get("name", "").lower()
            timeframe_id_lower = timeframe_id.lower()
            
            # Show/hide based on search
            if (not search_lower or 
                search_lower in timeframe_name or 
                search_lower in timeframe_id_lower):
                card.show()
            else:
                card.hide()
        
        # Update group visibility after filtering
        self._update_group_visibility_after_filter()
    
    def _update_group_visibility_after_filter(self):
        """Update group visibility after filtering."""
        for group in [self.intraday_group, self.hourly_group, self.daily_group,
                     self.weekly_group, self.other_group]:
            layout = group.layout()
            has_visible = False
            
            # Check if any card in this group is visible
            for i in range(layout.count()):
                item = layout.itemAt(i)
                if item and item.widget() and item.widget().isVisible():
                    has_visible = True
                    break
            
            if has_visible:
                group.show()
            else:
                group.hide()
    
    def _handle_card_clicked(self, card: SelectableCard):
        """Handle card click event."""
        card_data = card.get_data()
        timeframe_id = card_data.get("id", "")
        
        # Toggle selection
        if timeframe_id in self.selected_ids:
            self.selected_ids.remove(timeframe_id)
            card.set_selected(False)
        else:
            self.selected_ids.add(timeframe_id)
            card.set_selected(True)
        
        # Emit signals
        self.card_clicked.emit(timeframe_id, timeframe_id in self.selected_ids)
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
            timeframe_id = card_data.get("id", "")
            
            if timeframe_id in self.selected_ids:
                self.selected_ids.remove(timeframe_id)
                self.last_right_clicked_card.set_selected(False)
                
                # Emit signals
                self.selection_changed.emit(list(self.selected_ids))
                self._update_status()
        
    def _handle_copy_id_action(self):
        """Handle copy timeframe ID action."""
        if hasattr(self, 'last_right_clicked_card'):
            card_data = self.last_right_clicked_card.get_data()
            timeframe_id = card_data.get("id", "")
            
            # Copy to clipboard
            from PySide6.QtWidgets import QApplication
            clipboard = QApplication.clipboard()
            clipboard.setText(timeframe_id)
            
            # Show feedback
            self.status_label.setText(f"Copied: {timeframe_id}")
            
    def _handle_help_action(self):
        """Handle help action."""
        if hasattr(self, 'last_right_clicked_card'):
            card_data = self.last_right_clicked_card.get_data()
            timeframe_name = card_data.get("name", "Unknown")
            timeframe_id = card_data.get("id", "")
            category = card_data.get("category", "unknown")
            
            # Show help dialog
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(
                self,
                f"Help: {timeframe_name}",
                f"Timeframe ID: {timeframe_id}\n"
                f"Category: {category.capitalize()}\n\n"
                f"This timeframe determines the bar interval for analysis.\n"
                f"Select multiple timeframes to run the same strategy across different intervals."
            )
    
    def clear_selection(self):
        """Clear all selections."""
        for timeframe_id in list(self.selected_ids):
            if timeframe_id in self.cards:
                self.cards[timeframe_id].set_selected(False)
        
        self.selected_ids.clear()
        self.selection_changed.emit([])
        self._update_status()
    
    def get_selected_timeframes(self) -> List[Dict[str, Any]]:
        """Get selected timeframes data."""
        selected = []
        for timeframe in self.timeframes:
            if timeframe.get("id", "") in self.selected_ids:
                selected.append(timeframe)
        return selected
    
    def get_selected_ids(self) -> List[str]:
        """Get selected timeframe IDs."""
        return list(self.selected_ids)
    
    def set_selected_ids(self, timeframe_ids: List[str]):
        """Set selected timeframe IDs."""
        # Clear current selection
        for timeframe_id in list(self.selected_ids):
            if timeframe_id in self.cards:
                self.cards[timeframe_id].set_selected(False)
        
        self.selected_ids.clear()
        
        # Set new selection
        for timeframe_id in timeframe_ids:
            if timeframe_id in self.cards:
                self.cards[timeframe_id].set_selected(True)
                self.selected_ids.add(timeframe_id)
        
        self.selection_changed.emit(list(self.selected_ids))
        self._update_status()
    
    def _update_status(self):
        """Update status label."""
        count = len(self.selected_ids)
        if count == 0:
            self.status_label.setText("No timeframes selected")
        elif count == 1:
            self.status_label.setText("1 timeframe selected")
        else:
            self.status_label.setText(f"{count} timeframes selected")