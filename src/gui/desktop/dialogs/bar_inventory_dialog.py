"""
BAR INVENTORY Dialog - Modal dialog for inspecting existing BAR assets.

Purpose: inspect existing BAR assets.
UI Contract: Modal dialog with read-only list or table.
Behavior Contract: No mutation. Close only.
"""

import logging
from typing import List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QLineEdit,
    QDialogButtonBox, QWidget, QGroupBox
)

from ..state.bar_prepare_state import bar_prepare_state

logger = logging.getLogger(__name__)


class BarInventoryDialog(QDialog):
    """Modal dialog for inspecting BAR inventory (read-only)."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("BAR INVENTORY - Existing BAR Assets")
        self.setMinimumSize(600, 400)
        
        self.setup_ui()
        self.setup_connections()
        self.populate_inventory()
    
    def setup_ui(self):
        """Initialize the UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        
        # Header
        header_label = QLabel("Inspect existing BAR assets (read-only):")
        header_label.setStyleSheet("font-weight: bold; color: #E6E6E6;")
        layout.addWidget(header_label)
        
        # Filter controls (optional)
        filter_layout = QHBoxLayout()
        filter_label = QLabel("Filter:")
        filter_label.setStyleSheet("color: #9A9A9A;")
        filter_layout.addWidget(filter_label)
        
        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("Filter by instrument, timeframe, or date...")
        self.filter_input.setStyleSheet("""
            QLineEdit {
                background-color: #2A2A2A;
                color: #E6E6E6;
                border: 1px solid #444444;
                border-radius: 4px;
                padding: 4px 8px;
            }
        """)
        filter_layout.addWidget(self.filter_input)
        layout.addLayout(filter_layout)
        
        # Inventory table
        self.inventory_table = QTableWidget()
        self.inventory_table.setColumnCount(5)
        self.inventory_table.setHorizontalHeaderLabels([
            "Instrument", "Timeframe", "Date Range", "Size", "Status"
        ])
        
        # Style the table
        self.inventory_table.setStyleSheet("""
            QTableWidget {
                background-color: #1E1E1E;
                color: #E6E6E6;
                border: 1px solid #444444;
                border-radius: 4px;
                gridline-color: #2A2A2A;
            }
            QHeaderView::section {
                background-color: #2A2A2A;
                color: #E6E6E6;
                padding: 6px;
                border: none;
                font-weight: bold;
            }
            QTableWidget::item {
                padding: 6px;
                border-bottom: 1px solid #2A2A2A;
            }
            QTableWidget::item:selected {
                background-color: #1A237E;
            }
        """)
        
        # Configure table headers
        header = self.inventory_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)  # Instrument
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)  # Timeframe
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)  # Date Range
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)  # Size
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)  # Status
        
        self.inventory_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.inventory_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.inventory_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)  # Read-only
        
        layout.addWidget(self.inventory_table)
        
        # Summary
        self.summary_label = QLabel("Loading inventory...")
        self.summary_label.setStyleSheet("color: #9A9A9A; font-size: 11px;")
        layout.addWidget(self.summary_label)
        
        # Button box (Close only)
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.button(QDialogButtonBox.StandardButton.Close).setText("Close")
        layout.addWidget(button_box)
    
    def setup_connections(self):
        """Connect signals and slots."""
        # Filter input
        self.filter_input.textChanged.connect(self.filter_inventory)
        
        # Button box
        button_box = self.findChild(QDialogButtonBox)
        if button_box:
            button_box.rejected.connect(self.reject)
    
    def populate_inventory(self):
        """Populate inventory table with BAR assets."""
        # Clear table
        self.inventory_table.setRowCount(0)

        state = bar_prepare_state.get_state()
        inventory_rows = []
        if state.bar_inventory_summary:
            if isinstance(state.bar_inventory_summary, list):
                inventory_rows = state.bar_inventory_summary
            elif isinstance(state.bar_inventory_summary, dict):
                inventory_rows = state.bar_inventory_summary.get("rows", [])

        if not inventory_rows:
            self.inventory_table.insertRow(0)
            self.inventory_table.setItem(0, 0, QTableWidgetItem("No inventory data available"))
            for col in range(1, 5):
                self.inventory_table.setItem(0, col, QTableWidgetItem("—"))
            self.summary_label.setText("No BAR inventory data available")
            return

        total_size = 0.0
        ready_count = 0

        for row, item in enumerate(inventory_rows):
            self.inventory_table.insertRow(row)

            if isinstance(item, dict):
                instr = str(item.get("instrument", "—"))
                tf = str(item.get("timeframe", "—"))
                date_range = str(item.get("date_range", "—"))
                size = str(item.get("size", "—"))
                status = str(item.get("status", "—"))
            else:
                instr, tf, date_range, size, status = item

            self.inventory_table.setItem(row, 0, QTableWidgetItem(instr))
            self.inventory_table.setItem(row, 1, QTableWidgetItem(tf))
            self.inventory_table.setItem(row, 2, QTableWidgetItem(date_range))
            self.inventory_table.setItem(row, 3, QTableWidgetItem(size))

            status_item = QTableWidgetItem(status)
            if status == "READY":
                status_item.setForeground(Qt.GlobalColor.green)
                ready_count += 1
            elif status == "PARTIAL":
                status_item.setForeground(Qt.GlobalColor.yellow)
            else:
                status_item.setForeground(Qt.GlobalColor.red)
            self.inventory_table.setItem(row, 4, status_item)

            try:
                total_size += float(str(size).split()[0])
            except Exception:
                pass

        self.summary_label.setText(
            f"{len(inventory_rows)} BAR assets, {ready_count} ready, "
            f"{len(inventory_rows) - ready_count} partial, total {total_size:.1f} MB"
        )
    
    def filter_inventory(self, text: str):
        """Filter inventory table based on search text."""
        filter_lower = text.lower().strip()
        
        for row in range(self.inventory_table.rowCount()):
            should_show = not filter_lower  # Show all if filter is empty
            
            if filter_lower:
                # Check if any cell in the row contains the filter text
                for col in range(self.inventory_table.columnCount()):
                    item = self.inventory_table.item(row, col)
                    if item and filter_lower in item.text().lower():
                        should_show = True
                        break
            
            self.inventory_table.setRowHidden(row, not should_show)
    
    def reject(self):
        """Handle dialog closure."""
        # No state changes - this dialog is read-only
        logger.info("BAR INVENTORY dialog closed")
        super().reject()