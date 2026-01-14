"""
Help Icon - Inline help system with info icons.

Features:
- Small info icon button
- Shows tooltip on hover
- Opens help dialog on click
- Can be placed next to any UI element
"""

from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtWidgets import (
    QWidget, QPushButton, QLabel, QVBoxLayout, QHBoxLayout,
    QDialog, QTextEdit, QSizePolicy
)
from PySide6.QtGui import QIcon, QFont, QColor, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtSvgWidgets import QSvgWidget


class HelpIcon(QPushButton):
    """
    Small info icon button for inline help.
    
    Shows tooltip on hover, opens help dialog on click.
    """
    
    def __init__(self, tooltip_text: str = "", help_text: str = "", parent=None):
        super().__init__(parent)
        self.tooltip_text = tooltip_text
        self.help_text = help_text
        
        # Configure button
        self.setFixedSize(16, 16)
        self.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                border-radius: 8px;
            }
            QPushButton:hover {
                background-color: #333333;
            }
            QPushButton:pressed {
                background-color: #444444;
            }
        """)
        
        # Set tooltip
        if tooltip_text:
            self.setToolTip(tooltip_text)
        
        # Create icon (simple "i" character)
        self.setText("i")
        self.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        
        # Connect click
        self.clicked.connect(self._show_help_dialog)
    
    def _show_help_dialog(self):
        """Show help dialog with detailed information."""
        if not self.help_text:
            return
        
        dialog = HelpDialog(self.help_text, self.tooltip_text, self)
        dialog.exec()


class HelpDialog(QDialog):
    """Dialog for displaying help information."""
    
    def __init__(self, help_text: str, title: str = "Help", parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(400, 300)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        
        # Title
        title_label = QLabel(title)
        title_label.setStyleSheet("""
            QLabel {
                font-weight: bold;
                font-size: 14px;
                color: #E6E6E6;
            }
        """)
        layout.addWidget(title_label)
        
        # Help text
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setPlainText(help_text)
        text_edit.setStyleSheet("""
            QTextEdit {
                background-color: #1E1E1E;
                color: #E6E6E6;
                border: 1px solid #444444;
                border-radius: 4px;
                font-size: 11px;
                padding: 8px;
            }
        """)
        layout.addWidget(text_edit)
        
        # Close button
        close_button = QPushButton("Close")
        close_button.setStyleSheet("""
            QPushButton {
                background-color: #424242;
                color: #E6E6E6;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #555555;
                border: 1px solid #666666;
            }
        """)
        close_button.clicked.connect(self.accept)
        layout.addWidget(close_button, 0, Qt.AlignmentFlag.AlignRight)


# Pre-defined help texts for common concepts
HELP_TEXTS = {
    "dataset_derivation": """
Dataset Derivation

In FishBroWFS_V2, datasets are NOT manually selected by users. Instead, they are automatically derived from your selections:

1. DATA1 (Primary): Derived from instrument + timeframe + mode
2. DATA2 (Secondary): Derived based on strategy dependency

How it works:
- Select an instrument (e.g., MNQ)
- Select a timeframe (e.g., 5m)  
- Select a run mode (e.g., Backtest)
- The system automatically maps these to appropriate dataset IDs

Benefits:
- Eliminates manual dataset selection errors
- Ensures data consistency
- Transparent mapping shown in real-time

The mapping uses registry rules defined in configs/registry/.
""",
    
    "data2_gate": """
DATA2 Gate (Hybrid BC v1.1)

The DATA2 gate automatically evaluates whether a secondary dataset is required and available:

Gate Rules (Option C - AUTO):
1. If strategy requires DATA2 and DATA2 is MISSING → BLOCKER (FAIL)
2. If strategy requires DATA2 and DATA2 is STALE → WARNING
3. If strategy ignores DATA2 → PASS (even if DATA2 missing)
4. If strategy has no dependency declaration → BLOCKER (safe default)

Strategy Dependency:
- Each strategy declares whether it requires secondary data
- Default is True (safe) if not specified
- Explicitly set to False for strategies that don't need DATA2

Gate Outcomes:
- PASS (Green): Can submit job
- WARNING (Amber): Can proceed with caution
- FAIL (Red): Blocked from submission
""",
    
    "date_range_override": """
Date Range Override

The system automatically derives date ranges from the selected dataset (DATA1), but you can override them:

Auto-derived Dates:
- Taken from DATA1 dataset metadata (min_date, max_date)
- Represents the full available date range for that dataset
- Ensures you don't request dates outside available data

Manual Override:
- Check "Override dates" to enable manual input
- Enter dates in YYYY-MM-DD format
- Validation ensures dates are within auto-derived range
- Useful for testing specific time periods

Best Practices:
- Use auto-derived dates for full backtesting
- Override only when testing specific market conditions
- Ensure overridden dates are within dataset range
""",
    
    "run_readiness": """
Run Readiness Panel

This panel shows the pre-flight status of your configuration:

1. DATA2 Gate Status:
   - PASS: Strategy doesn't need DATA2 or DATA2 is READY
   - WARNING: DATA2 is STALE (can proceed with caution)
   - FAIL: DATA2 is MISSING and strategy requires it

2. Strategy Dependency:
   - Shows whether the selected strategy requires DATA2
   - "Yes" means DATA2 gate evaluation matters
   - "No" means DATA2 status is ignored

3. DATA2 Status:
   - READY: Dataset is available and up-to-date
   - STALE: Dataset exists but may be outdated
   - MISSING: Dataset not found
   - UNKNOWN: Status cannot be determined

Submission Rules:
- FAIL gate blocks submission
- WARNING gate allows submission with confirmation
- PASS gate allows immediate submission
""",
    
    "card_selection": """
Card-Based Selection

The Launch Pad uses card-based selectors instead of traditional dropdowns:

Benefits:
- Visual representation of options
- Multi-select support for strategies/timeframes
- Search/filter capabilities
- Right-click context menus
- Better discoverability

Selection Modes:
- Strategies: Multi-select (choose one or more)
- Timeframes: Multi-select (choose one or more)
- Instruments: Single-select (choose one)
- Modes: Single-select (choose one)

Right-click Actions:
- Remove selection
- Copy ID to clipboard
- Open help (this dialog)

Search/Filter:
- Type in search box to filter cards
- Shows matching cards only
- Clear search to show all
"""
}