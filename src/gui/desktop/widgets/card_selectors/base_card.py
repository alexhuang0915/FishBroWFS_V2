"""
Base Selectable Card Component.

Reusable card widget for card-based selectors with selection state,
hover effects, and right-click context menu support.
"""

from typing import Any, Dict, Optional
from PySide6.QtCore import Qt, Signal, QPoint, QSize
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QToolButton, QSizePolicy, QSpacerItem
)
from PySide6.QtGui import QFont, QMouseEvent, QCursor


class SelectableCard(QFrame):
    """
    Selectable card widget with title, subtitle, description, and selection state.
    
    Features:
    - Click to select/deselect
    - Right-click context menu support
    - Hover effects
    - Info icon for help
    - Visual selection feedback
    """
    
    # Signals
    clicked = Signal(object)  # Emits self
    right_clicked = Signal(object, QPoint)  # Emits self, position
    
    def __init__(
        self,
        title: str,
        subtitle: str = "",
        description: str = "",
        data: Optional[Dict[str, Any]] = None,
        parent=None
    ):
        super().__init__(parent)
        self.title = title
        self.subtitle = subtitle
        self.description = description
        self.data = data or {}
        self.is_selected = False
        
        self.setup_ui()
        self.apply_styling()
        
    def setup_ui(self):
        """Initialize the UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)
        
        # Header row with title and info button
        header_layout = QHBoxLayout()
        
        # Title
        self.title_label = QLabel(self.title)
        self.title_label.setStyleSheet("""
            QLabel {
                font-weight: bold;
                font-size: 12px;
                color: #E6E6E6;
            }
        """)
        header_layout.addWidget(self.title_label)
        
        header_layout.addSpacerItem(QSpacerItem(10, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
        
        # Info button (optional)
        self.info_btn = QToolButton()
        self.info_btn.setText("ⓘ")
        self.info_btn.setStyleSheet("""
            QToolButton {
                background-color: transparent;
                color: #9A9A9A;
                border: none;
                font-size: 10px;
                padding: 2px;
                min-width: 16px;
                min-height: 16px;
            }
            QToolButton:hover {
                color: #3A8DFF;
            }
        """)
        self.info_btn.setToolTip("Click for more information")
        self.info_btn.clicked.connect(self._show_info)
        header_layout.addWidget(self.info_btn)
        
        layout.addLayout(header_layout)
        
        # Subtitle
        if self.subtitle:
            self.subtitle_label = QLabel(self.subtitle)
            self.subtitle_label.setStyleSheet("""
                QLabel {
                    color: #9A9A9A;
                    font-size: 10px;
                    font-family: monospace;
                }
            """)
            layout.addWidget(self.subtitle_label)
        
        # Description (truncated if too long)
        if self.description:
            # Truncate long descriptions
            display_desc = self.description
            if len(display_desc) > 100:
                display_desc = display_desc[:97] + "..."
            
            self.desc_label = QLabel(display_desc)
            self.desc_label.setWordWrap(True)
            self.desc_label.setStyleSheet("""
                QLabel {
                    color: #B0B0B0;
                    font-size: 10px;
                    font-style: italic;
                }
            """)
            layout.addWidget(self.desc_label)
        
        # Set size policy
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(180)
        self.setMaximumWidth(220)
        
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
                    border-radius: 6px;
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
                    border-radius: 6px;
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
        elif event.button() == Qt.MouseButton.RightButton:
            self.right_clicked.emit(self, event.globalPosition().toPoint())
        
        super().mousePressEvent(event)
    
    def set_selected(self, selected: bool):
        """Set selection state."""
        self.is_selected = selected
        self._update_style()
    
    def toggle_selection(self):
        """Toggle selection state."""
        self.is_selected = not self.is_selected
        self._update_style()
        return self.is_selected
    
    def get_data(self) -> Dict[str, Any]:
        """Get card data."""
        return self.data
    
    def set_data(self, data: Dict[str, Any]):
        """Set card data."""
        self.data = data
    
    def _show_info(self):
        """Show information about this card."""
        # This would typically open a help dialog
        # For now, just emit a signal that parent can handle
        pass
    
    def sizeHint(self) -> QSize:
        """Provide size hint for the card."""
        return QSize(200, 120)