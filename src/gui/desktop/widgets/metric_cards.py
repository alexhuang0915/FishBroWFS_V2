"""
Metric Cards Widgets for Professional CTA UI.

Provides MetricCard and MetricRow for displaying key metrics in a professional dashboard.
"""

from typing import Optional, List, Tuple
from PySide6.QtCore import Qt, QSize
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QFrame, QSizePolicy
)
from PySide6.QtGui import QFont, QPalette, QColor


class MetricCard(QFrame):
    """
    A single metric card displaying a title, big value, and optional subtitle.
    
    Features:
    - Title (small, muted)
    - Value (large, bold)
    - Subtitle (small, optional)
    - Professional styling with subtle borders
    """
    
    def __init__(
        self,
        title: str,
        value: str,
        subtitle: Optional[str] = None,
        value_color: Optional[str] = None,
        parent=None
    ):
        super().__init__(parent)
        self.title = title
        self.value = value
        self.subtitle = subtitle
        self.value_color = value_color
        
        self.setup_ui()
        self.apply_styling()
    
    def setup_ui(self):
        """Initialize the UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)
        
        # Title label (small, muted)
        self.title_label = QLabel(self.title)
        self.title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.title_label)
        
        # Value label (large, bold)
        self.value_label = QLabel(self.value)
        self.value_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.value_label)
        
        # Subtitle label (small, optional)
        if self.subtitle:
            self.subtitle_label = QLabel(self.subtitle)
            self.subtitle_label.setAlignment(Qt.AlignCenter)
            layout.addWidget(self.subtitle_label)
        
        # Set size policy
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
    
    def apply_styling(self):
        """Apply professional styling to the card."""
        # Base styling
        self.setFrameStyle(QFrame.StyledPanel | QFrame.Raised)
        
        # Title styling
        self.title_label.setStyleSheet("""
            QLabel {
                color: #9A9A9A;
                font-size: 11px;
                font-weight: 500;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }
        """)
        
        # Value styling
        value_style = f"""
            QLabel {{
                color: {self.value_color or '#E6E6E6'};
                font-size: 24px;
                font-weight: bold;
                font-family: 'Segoe UI', 'Roboto', sans-serif;
            }}
        """
        self.value_label.setStyleSheet(value_style)
        
        # Subtitle styling
        if hasattr(self, 'subtitle_label'):
            self.subtitle_label.setStyleSheet("""
                QLabel {
                    color: #9A9A9A;
                    font-size: 10px;
                    font-style: italic;
                }
            """)
        
        # Card styling
        self.setStyleSheet("""
            QFrame {
                background-color: #2A2A2A;
                border: 1px solid #444444;
                border-radius: 6px;
                padding: 2px;
            }
            QFrame:hover {
                border: 1px solid #3A8DFF;
                background-color: #2F2F2F;
            }
        """)
    
    def update_value(self, new_value: str, new_color: Optional[str] = None):
        """Update the displayed value and optionally its color."""
        self.value = new_value
        self.value_label.setText(new_value)
        
        if new_color:
            self.value_color = new_color
            self.value_label.setStyleSheet(f"""
                QLabel {{
                    color: {new_color};
                    font-size: 24px;
                    font-weight: bold;
                    font-family: 'Segoe UI', 'Roboto', sans-serif;
                }}
            """)
    
    def update_title(self, new_title: str):
        """Update the card title."""
        self.title = new_title
        self.title_label.setText(new_title)
    
    def update_subtitle(self, new_subtitle: Optional[str]):
        """Update the card subtitle."""
        self.subtitle = new_subtitle
        if hasattr(self, 'subtitle_label'):
            if new_subtitle:
                self.subtitle_label.setText(new_subtitle)
                self.subtitle_label.show()
            else:
                self.subtitle_label.hide()
        elif new_subtitle:
            # Create subtitle label if it doesn't exist
            self.subtitle_label = QLabel(new_subtitle)
            self.subtitle_label.setAlignment(Qt.AlignCenter)
            self.subtitle_label.setStyleSheet("""
                QLabel {
                    color: #9A9A9A;
                    font-size: 10px;
                    font-style: italic;
                }
            """)
            self.layout().addWidget(self.subtitle_label)


class MetricRow(QWidget):
    """
    A responsive row of MetricCard widgets arranged in a grid.
    
    Automatically arranges cards in a responsive grid layout.
    Supports 1-6 cards per row with proper spacing.
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.cards: List[MetricCard] = []
        self.setup_ui()
    
    def setup_ui(self):
        """Initialize the UI with a grid layout."""
        self.layout = QGridLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setHorizontalSpacing(8)
        self.layout.setVerticalSpacing(8)
    
    def add_card(self, card: MetricCard):
        """Add a card to the row."""
        self.cards.append(card)
        self._arrange_cards()
    
    def create_and_add_card(
        self,
        title: str,
        value: str,
        subtitle: Optional[str] = None,
        value_color: Optional[str] = None
    ) -> MetricCard:
        """Create a new card and add it to the row."""
        card = MetricCard(title, value, subtitle, value_color)
        self.add_card(card)
        return card
    
    def _arrange_cards(self):
        """Arrange cards in a responsive grid."""
        # Clear layout
        while self.layout.count():
            child = self.layout.takeAt(0)
            if child.widget():
                child.widget().setParent(None)
        
        # Determine grid dimensions
        num_cards = len(self.cards)
        if num_cards == 0:
            return
        
        # Simple arrangement: all in one row
        # For more than 4 cards, wrap to 2 rows
        if num_cards <= 4:
            cols = num_cards
            rows = 1
        else:
            cols = (num_cards + 1) // 2
            rows = 2
        
        # Place cards in grid
        for i, card in enumerate(self.cards):
            if rows == 1:
                row = 0
                col = i
            else:
                row = i // cols
                col = i % cols
            
            self.layout.addWidget(card, row, col)
    
    def clear_cards(self):
        """Remove all cards from the row."""
        for card in self.cards:
            card.setParent(None)
        self.cards.clear()
        self._arrange_cards()
    
    def set_card_count(self, count: int):
        """Set the number of cards (creates placeholder cards if needed)."""
        current_count = len(self.cards)
        
        if count > current_count:
            # Add placeholder cards
            for i in range(count - current_count):
                card = MetricCard(f"Metric {len(self.cards) + 1}", "-", "Loading...")
                self.add_card(card)
        elif count < current_count:
            # Remove excess cards
            for i in range(current_count - count):
                card = self.cards.pop()
                card.setParent(None)
            self._arrange_cards()
    
    def get_card(self, index: int) -> Optional[MetricCard]:
        """Get card at specified index."""
        if 0 <= index < len(self.cards):
            return self.cards[index]
        return None