"""
Disabled Reason Banner – Unified disabled explanation with “Go to Fix” navigation.

Shows missing prerequisites and provides navigation buttons to fix them.
Used in OP tab, allocation tab, portfolio admission tab, etc.

Contract:
- Inputs: title (str), missing (dict[str,str]), actions (list[tuple[label:str, target:str]])
- Missing keys displayed in deterministic order (sorted by key)
- Hide when missing empty
- Navigation buttons emit signal with target string
"""

import logging
from typing import Dict, List, Tuple, Optional

from PySide6.QtCore import Qt, Signal, Slot  # type: ignore
from PySide6.QtWidgets import (  # type: ignore
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFrame, QSizePolicy
)
from PySide6.QtGui import QFont, QColor  # type: ignore

logger = logging.getLogger(__name__)


class DisabledReasonBanner(QWidget):
    """Banner that explains why a feature is disabled and provides navigation to fix."""
    
    # Signal emitted when a navigation action is clicked
    navigation_requested = Signal(str)  # target string
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_title = ""
        self.current_missing: Dict[str, str] = {}
        self.current_actions: List[Tuple[str, str]] = []
        
        self.setup_ui()
        self.hide()  # Hidden by default when no missing prerequisites
    
    def setup_ui(self):
        """Initialize the UI components."""
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        
        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(8)
        
        # Title label
        self.title_label = QLabel()
        self.title_label.setStyleSheet("""
            QLabel {
                color: #FF9800;
                font-weight: bold;
                font-size: 14px;
            }
        """)
        main_layout.addWidget(self.title_label)
        
        # Missing prerequisites list
        self.missing_layout = QVBoxLayout()
        self.missing_layout.setSpacing(4)
        main_layout.addLayout(self.missing_layout)
        
        # Actions (navigation buttons) layout
        self.actions_layout = QHBoxLayout()
        self.actions_layout.setSpacing(8)
        main_layout.addLayout(self.actions_layout)
        
        # Separator line at bottom
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setStyleSheet("background-color: #555555;")
        separator.setFixedHeight(1)
        main_layout.addWidget(separator)
    
    def update_banner(self,
                      title: str,
                      missing: Dict[str, str],
                      actions: List[Tuple[str, str]]):
        """Update banner with new title, missing prerequisites, and navigation actions."""
        self.current_title = title
        self.current_missing = missing
        self.current_actions = actions
        
        # Update title
        self.title_label.setText(title)
        
        # Clear existing missing items
        while self.missing_layout.count():
            item = self.missing_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        
        # Add missing items in deterministic order (sorted by key)
        if missing:
            for key in sorted(missing.keys()):
                reason = missing[key]
                item_widget = self._create_missing_item(key, reason)
                self.missing_layout.addWidget(item_widget)
        
        # Clear existing action buttons
        while self.actions_layout.count():
            item = self.actions_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        
        # Add navigation buttons
        if actions:
            for label, target in actions:
                button = self._create_action_button(label, target)
                self.actions_layout.addWidget(button)
            self.actions_layout.addStretch()
        
        # Show/hide based on missing
        if missing:
            self.show()
        else:
            self.hide()
    
    def _create_missing_item(self, key: str, reason: str) -> QWidget:
        """Create a widget for a single missing prerequisite."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        
        # Icon
        icon_label = QLabel("❌")
        icon_label.setStyleSheet("color: #F44336; font-size: 12px;")
        icon_label.setFixedSize(16, 16)
        layout.addWidget(icon_label)
        
        # Key label (bold)
        key_label = QLabel(f"{key}:")
        key_label.setStyleSheet("color: #E6E6E6; font-weight: bold; font-size: 11px;")
        key_label.setMinimumWidth(120)
        layout.addWidget(key_label)
        
        # Reason label
        reason_label = QLabel(reason)
        reason_label.setStyleSheet("color: #9e9e9e; font-size: 11px;")
        reason_label.setWordWrap(True)
        layout.addWidget(reason_label)
        
        layout.addStretch()
        return widget
    
    def _create_action_button(self, label: str, target: str) -> QPushButton:
        """Create a navigation button."""
        button = QPushButton(label)
        button.setStyleSheet("""
            QPushButton {
                background-color: #2a2a2a;
                color: #E6E6E6;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #3A8DFF;
                color: white;
                border: 1px solid #3A8DFF;
            }
            QPushButton:pressed {
                background-color: #2A7DFF;
            }
        """)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        
        # Connect signal with target
        button.clicked.connect(lambda checked, t=target: self.navigation_requested.emit(t))
        return button
    
    def clear(self):
        """Clear banner and hide."""
        self.update_banner("", {}, [])
        self.hide()