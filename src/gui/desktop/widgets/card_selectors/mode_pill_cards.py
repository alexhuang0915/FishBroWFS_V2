"""
Mode Pill Cards - Single-select pill-style cards for run modes.

Features:
- Single-select pill cards for run modes (Backtest, Research, Optimize, WFS)
- Visual feedback for selected mode
- Info icons with mode explanations
- Compact horizontal layout
"""

from typing import List, Dict, Any, Optional
from PySide6.QtCore import Qt, Signal, QSize, QPoint
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QToolButton,
    QSizePolicy, QSpacerItem
)
from PySide6.QtGui import QFont, QMouseEvent, QCursor


class ModePillCard(QFrame):
    """
    Pill-style card for run mode selection.
    
    Compact, pill-shaped card with mode name and description.
    """
    
    # Signals
    clicked = Signal(object)  # Emits self
    
    def __init__(
        self,
        mode_id: str,
        mode_name: str,
        description: str = "",
        parent=None
    ):
        super().__init__(parent)
        self.mode_id = mode_id
        self.mode_name = mode_name
        self.description = description
        self.is_selected = False
        
        self.setup_ui()
        self.apply_styling()
        
    def setup_ui(self):
        """Initialize the UI components."""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(8)
        
        # Mode name
        self.name_label = QLabel(self.mode_name)
        self.name_label.setStyleSheet("""
            QLabel {
                font-weight: bold;
                font-size: 11px;
                color: #E6E6E6;
            }
        """)
        layout.addWidget(self.name_label)
        
        # Info button
        self.info_btn = QToolButton()
        self.info_btn.setText("ⓘ")
        self.info_btn.setStyleSheet("""
            QToolButton {
                background-color: transparent;
                color: #9A9A9A;
                border: none;
                font-size: 9px;
                padding: 1px;
                min-width: 14px;
                min-height: 14px;
            }
            QToolButton:hover {
                color: #3A8DFF;
            }
        """)
        self.info_btn.setToolTip("Click for mode description")
        self.info_btn.clicked.connect(self._show_info)
        layout.addWidget(self.info_btn)
        
        # Set size policy
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        
    def apply_styling(self):
        """Apply styling based on selection state."""
        self._update_style()
        
    def _update_style(self):
        """Update styling based on selection state."""
        if self.is_selected:
            self.setStyleSheet("""
                QFrame {
                    background-color: #1A237E;
                    border: 2px solid #3A8DFF;
                    border-radius: 16px;
                }
                QFrame:hover {
                    background-color: #283593;
                    border: 2px solid #4A9DFF;
                }
            """)
        else:
            self.setStyleSheet("""
                QFrame {
                    background-color: #2A2A2A;
                    border: 1px solid #444444;
                    border-radius: 16px;
                }
                QFrame:hover {
                    background-color: #2F2F2F;
                    border: 1px solid #555555;
                }
            """)
    
    def mousePressEvent(self, event: QMouseEvent):
        """Handle mouse press events."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self)
        
        super().mousePressEvent(event)
    
    def set_selected(self, selected: bool):
        """Set selection state."""
        self.is_selected = selected
        self._update_style()
    
    def _show_info(self):
        """Show information about this mode."""
        # Emit a signal that parent can handle
        pass
    
    def sizeHint(self) -> QSize:
        """Provide size hint for the pill card."""
        return QSize(100, 32)


class ModePillCards(QWidget):
    """
    Single-select pill cards for run mode selection.
    
    Replaces the run mode combobox with an explainable, pill-based interface.
    """
    
    # Signals
    selection_changed = Signal(str)  # Selected mode ID
    card_clicked = Signal(str, bool)  # mode_id, is_selected
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.modes: List[Dict[str, Any]] = []
        self.selected_id: str = ""
        self.cards: Dict[str, ModePillCard] = {}
        
        self.setup_ui()
        
    def setup_ui(self):
        """Initialize the UI components."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(8)
        
        # Header with title
        header_layout = QHBoxLayout()
        
        # Title
        title_label = QLabel("Run Mode")
        title_label.setStyleSheet("""
            QLabel {
                font-weight: bold;
                font-size: 13px;
                color: #E6E6E6;
            }
        """)
        header_layout.addWidget(title_label)
        
        header_layout.addSpacerItem(QSpacerItem(20, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
        
        main_layout.addLayout(header_layout)
        
        # Cards container (horizontal layout)
        self.cards_container = QWidget()
        self.cards_layout = QHBoxLayout(self.cards_container)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(8)
        
        main_layout.addWidget(self.cards_container)
        
        # Status label
        self.status_label = QLabel("Select a run mode")
        self.status_label.setStyleSheet("""
            QLabel {
                color: #9A9A9A;
                font-size: 10px;
                font-style: italic;
            }
        """)
        main_layout.addWidget(self.status_label)
        
        # Load default modes
        self.load_default_modes()
        
    def load_default_modes(self):
        """Load default run modes."""
        default_modes = [
            {
                "id": "backtest",
                "name": "Backtest",
                "description": "Run strategy on historical data with fixed parameters."
            },
            {
                "id": "research",
                "name": "Research", 
                "description": "Explore parameter space and generate optimization candidates."
            },
            {
                "id": "optimize",
                "name": "Optimize",
                "description": "Optimize strategy parameters using research results."
            },
            {
                "id": "wfs",
                "name": "WFS",
                "description": "Walk-Forward Simulation - advanced out-of-sample testing."
            }
        ]
        
        self.load_modes(default_modes)
        
    def load_modes(self, modes: List[Dict[str, Any]]):
        """Load modes data."""
        self.modes = modes
        self.cards.clear()
        
        # Clear layout
        while self.cards_layout.count():
            child = self.cards_layout.takeAt(0)
            if child.widget():
                child.widget().setParent(None)
        
        if not modes:
            self.status_label.setText("No modes available")
            return
        
        # Create cards
        for mode in modes:
            mode_id = mode.get("id", "")
            mode_name = mode.get("name", "Unknown")
            description = mode.get("description", "")
            
            # Create card
            card = ModePillCard(
                mode_id=mode_id,
                mode_name=mode_name,
                description=description
            )
            
            # Connect signals
            card.clicked.connect(self._handle_card_clicked)
            
            # Store card
            self.cards[mode_id] = card
            
            # Add to layout
            self.cards_layout.addWidget(card)
        
        # Add stretch to push cards to left
        self.cards_layout.addSpacerItem(QSpacerItem(20, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
        
        # Update status
        self.status_label.setText(f"{len(modes)} modes available")
        
    def _handle_card_clicked(self, card: ModePillCard):
        """Handle card click event."""
        mode_id = card.mode_id
        
        # Single-select: deselect previous if different
        if mode_id != self.selected_id:
            # Deselect previous card
            if self.selected_id and self.selected_id in self.cards:
                self.cards[self.selected_id].set_selected(False)
            
            # Select new card
            self.selected_id = mode_id
            card.set_selected(True)
            
            # Emit signals
            self.card_clicked.emit(mode_id, True)
            self.selection_changed.emit(mode_id)
        else:
            # Clicking the already selected card does nothing (mode stays selected)
            # This is different from instruments where clicking deselects
            pass
        
        # Update status
        self._update_status()
        
        # Show mode description
        self._show_mode_description(mode_id)
    
    def _show_mode_description(self, mode_id: str):
        """Show mode description in status label."""
        mode = next((m for m in self.modes if m.get("id") == mode_id), None)
        if mode:
            description = mode.get("description", "")
            self.status_label.setText(f"{mode.get('name')}: {description}")
    
    def clear_selection(self):
        """Clear selection."""
        if self.selected_id and self.selected_id in self.cards:
            self.cards[self.selected_id].set_selected(False)
        
        old_selected = self.selected_id
        self.selected_id = ""
        
        if old_selected:
            self.card_clicked.emit(old_selected, False)
        self.selection_changed.emit("")
        
        self.status_label.setText("Select a run mode")
    
    def get_selected_mode(self) -> Optional[str]:
        """Get selected mode ID."""
        return self.selected_id if self.selected_id else None
    
    def set_selected_mode(self, mode_id: str):
        """Set selected mode ID."""
        # Clear current selection
        if self.selected_id and self.selected_id in self.cards:
            self.cards[self.selected_id].set_selected(False)
        
        # Set new selection
        if mode_id and mode_id in self.cards:
            self.cards[mode_id].set_selected(True)
            self.selected_id = mode_id
            
            # Emit signals
            self.card_clicked.emit(mode_id, True)
            self.selection_changed.emit(mode_id)
            
            # Update status with description
            self._show_mode_description(mode_id)
        else:
            self.selected_id = ""
            self.selection_changed.emit("")
            self.status_label.setText("Select a run mode")
    
    def _update_status(self):
        """Update status label (called from other methods)."""
        # Status is updated in _show_mode_description
        pass