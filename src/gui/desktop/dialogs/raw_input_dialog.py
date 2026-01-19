"""
RAW INPUT Dialog - Modal dialog for selecting raw data files.

Purpose: select raw data files for this prepare session.
UI Contract: Modal dialog with scrollable list of raw files.
Behavior Contract: Selections modify local dialog state only.
Main page state must NOT change while dialog is open.
"""

import logging
from typing import List, Set
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QLineEdit, QCheckBox,
    QDialogButtonBox, QWidget, QSizePolicy
)

from ..state.bar_prepare_state import bar_prepare_state
from core.paths import get_outputs_root
from ..services.supervisor_client import get_raw_files, SupervisorClientError
from core.bars_contract import derive_instruments_from_raw

logger = logging.getLogger(__name__)


class RawInputDialog(QDialog):
    """Modal dialog for selecting raw data files."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("RAW INPUT - Select Raw Data Files")
        self.setMinimumSize(500, 400)
        
        # Dialog-local state (isolated from main page)
        self.selected_files: Set[str] = set()
        
        # Load current state from SSOT
        self.load_current_state()
        
        self.setup_ui()
        self.setup_connections()
    
    def load_current_state(self):
        """Load current selection from SSOT into dialog-local state."""
        state = bar_prepare_state.get_state()
        self.selected_files = set(state.raw_inputs)
    
    def setup_ui(self):
        """Initialize the UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        
        # Header
        header_label = QLabel("Select raw data files for this prepare session:")
        header_label.setStyleSheet("font-weight: bold; color: #E6E6E6;")
        layout.addWidget(header_label)
        
        # Search/filter (optional)
        search_layout = QHBoxLayout()
        search_label = QLabel("Search:")
        search_label.setStyleSheet("color: #9A9A9A;")
        search_layout.addWidget(search_label)
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Filter raw files...")
        self.search_input.setStyleSheet("""
            QLineEdit {
                background-color: #2A2A2A;
                color: #E6E6E6;
                border: 1px solid #444444;
                border-radius: 4px;
                padding: 4px 8px;
            }
        """)
        search_layout.addWidget(self.search_input)
        layout.addLayout(search_layout)
        
        # File list
        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.file_list.setStyleSheet("""
            QListWidget {
                background-color: #1E1E1E;
                color: #E6E6E6;
                border: 1px solid #444444;
                border-radius: 4px;
            }
            QListWidget::item {
                padding: 6px;
                border-bottom: 1px solid #2A2A2A;
            }
            QListWidget::item:hover {
                background-color: #2A2A2A;
            }
        """)
        layout.addWidget(self.file_list)
        
        # Selection summary
        self.summary_label = QLabel("0 files selected")
        self.summary_label.setStyleSheet("color: #9A9A9A; font-size: 11px;")
        layout.addWidget(self.summary_label)
        
        # Button box
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | 
            QDialogButtonBox.StandardButton.Cancel
        )
        button_box.button(QDialogButtonBox.StandardButton.Ok).setText("Confirm")
        button_box.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancel")
        layout.addWidget(button_box)
        
        # Populate file list from available raw inputs
        self.populate_file_list()
        self.update_summary()
    
    def setup_connections(self):
        """Connect signals and slots."""
        # Search filter
        self.search_input.textChanged.connect(self.filter_file_list)
        
        # Button box
        button_box = self.findChild(QDialogButtonBox)
        if button_box:
            button_box.accepted.connect(self.accept)
            button_box.rejected.connect(self.reject)
    
    def populate_file_list(self):
        """Populate file list with available raw files."""
        self.file_list.clear()
        
        raw_files = self._discover_raw_files()
        if not raw_files:
            item = QListWidgetItem("No raw inputs discovered")
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.file_list.addItem(item)
            return

        for file_name in raw_files:
            item = QListWidgetItem(file_name)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            
            # Set check state based on dialog-local selection
            if file_name in self.selected_files:
                item.setCheckState(Qt.CheckState.Checked)
            else:
                item.setCheckState(Qt.CheckState.Unchecked)
            
            self.file_list.addItem(item)

    def _discover_raw_files(self) -> List[str]:
        """Discover raw input files via Supervisor API."""
        try:
            files = get_raw_files()
            logger.debug(f"Retrieved {len(files)} raw files from supervisor API")
            return sorted(files)
        except SupervisorClientError as e:
            logger.warning(f"Failed to fetch raw files from supervisor API: {e}")
            # Return empty list - UI will show "No raw inputs discovered"
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching raw files: {e}")
            return []
    
    def filter_file_list(self, text: str):
        """Filter file list based on search text."""
        search_lower = text.lower().strip()
        
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            item_text = item.text().lower()
            
            if not search_lower or search_lower in item_text:
                item.setHidden(False)
            else:
                item.setHidden(True)
    
    def update_summary(self):
        """Update selection summary."""
        count = len(self.selected_files)
        self.summary_label.setText(f"{count} file{'s' if count != 1 else ''} selected")
    
    def accept(self):
        """Handle dialog acceptance (Confirm)."""
        # Update dialog-local selection from checkboxes
        self.selected_files.clear()
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                self.selected_files.add(item.text())
        
        # Derive instruments from selected RAW files
        raw_files_list = list(self.selected_files)
        derivation_result = derive_instruments_from_raw(raw_files_list)
        
        # Commit to SSOT with both raw inputs and derived instruments
        bar_prepare_state.update_state(
            raw_inputs=raw_files_list,
            derived_instruments=derivation_result.instruments,
            confirmed=False,
        )
        
        logger.info(
            f"RAW INPUT confirmed: {len(self.selected_files)} files selected, "
            f"{len(derivation_result.instruments)} instruments derived"
        )
        super().accept()
    
    def reject(self):
        """Handle dialog rejection (Cancel)."""
        # No state changes - dialog-local state is discarded
        logger.info("RAW INPUT cancelled - no state changes")
        super().reject()