"""
PREPARE PLAN Dialog - Modal dialog for defining instrument × timeframe combinations.

Purpose: define instrument × timeframe combinations and preview artifacts.
UI Contract: Modal dialog with two multi-select sections and read-only preview.
Behavior Contract: Preview updates live inside dialog. No commit until Confirm.
Cancel must discard all dialog changes.
"""

import logging
from typing import List, Set

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QGroupBox, QTextEdit,
    QDialogButtonBox, QWidget, QSplitter, QFrame
)

from ..state.bar_prepare_state import bar_prepare_state
from gui.services.timeframe_options import get_timeframe_ids
from core.bars_contract import derive_instruments_from_raw

logger = logging.getLogger(__name__)


class MultiSelectList(QListWidget):
    """Reusable multi-select list widget."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSelectionMode(QListWidget.SelectionMode.NoSelection)
        self.setStyleSheet("""
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
    
    def get_selected_items(self) -> List[str]:
        """Get list of selected item texts."""
        selected = []
        for i in range(self.count()):
            item = self.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                selected.append(item.text())
        return selected
    
    def set_selected_items(self, selected_items: Set[str]):
        """Set selected items based on set of item texts."""
        for i in range(self.count()):
            item = self.item(i)
            if item.text() in selected_items:
                item.setCheckState(Qt.CheckState.Checked)
            else:
                item.setCheckState(Qt.CheckState.Unchecked)


class PreparePlanDialog(QDialog):
    """Modal dialog for defining prepare plan."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PREPARE PLAN - Define Timeframe Combinations for Derived Instruments")
        self.setMinimumSize(700, 500)
        
        # Dialog-local state (isolated from main page)
        self.derived_instruments: List[str] = []  # Auto-derived from RAW files (read-only)
        self.selected_timeframes: Set[str] = set()
        
        # Load current state from SSOT
        self.load_current_state()
        
        self.setup_ui()
        self.setup_connections()
        self.update_preview()
    
    def load_current_state(self):
        """Load current selection from SSOT into dialog-local state."""
        state = bar_prepare_state.get_state()
        # Instruments are derived from RAW files, not selected
        self.derived_instruments = state.derived_instruments
        self.selected_timeframes = set(state.prepare_plan.timeframes)
    
    def setup_ui(self):
        """Initialize the UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        
        # Header
        header_label = QLabel("Define timeframe combinations for derived instruments and preview artifacts:")
        header_label.setStyleSheet("font-weight: bold; color: #E6E6E6;")
        layout.addWidget(header_label)
        
        # Create splitter for two sections
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #555555;
                width: 1px;
            }
        """)
        
        # Left panel: Selection sections
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(12)
        
        # Derived Instruments section (read-only)
        instruments_group = QGroupBox("Derived Instruments (from RAW files)")
        instruments_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 1px solid #444444;
                background-color: #1E1E1E;
                margin-top: 5px;
                padding-top: 8px;
                font-size: 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px 0 4px;
                color: #E6E6E6;
            }
        """)
        
        instruments_layout = QVBoxLayout(instruments_group)
        self.instruments_display = QTextEdit()
        self.instruments_display.setReadOnly(True)
        self.instruments_display.setMaximumHeight(120)
        self.instruments_display.setStyleSheet("""
            QTextEdit {
                background-color: #1E1E1E;
                color: #E6E6E6;
                border: 1px solid #444444;
                border-radius: 4px;
                font-family: monospace;
                font-size: 10px;
            }
        """)
        
        # Display derived instruments
        if self.derived_instruments:
            display_text = "\n".join(sorted(self.derived_instruments))
        else:
            display_text = "No RAW files selected. Use RAW INPUT dialog first."
        
        self.instruments_display.setText(display_text)
        instruments_layout.addWidget(self.instruments_display)
        left_layout.addWidget(instruments_group)
        
        # Timeframes section
        timeframes_group = QGroupBox("Timeframes (multi-select)")
        timeframes_group.setStyleSheet(instruments_group.styleSheet())
        
        timeframes_layout = QVBoxLayout(timeframes_group)
        self.timeframes_list = MultiSelectList()
        
        timeframes = self._load_timeframes()
        for tf in timeframes:
            item = QListWidgetItem(tf)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.timeframes_list.addItem(item)
        
        timeframes_layout.addWidget(self.timeframes_list)
        left_layout.addWidget(timeframes_group)
        
        # Right panel: Preview
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)
        
        preview_group = QGroupBox("Artifacts Preview (read-only)")
        preview_group.setStyleSheet(instruments_group.styleSheet())
        
        preview_layout = QVBoxLayout(preview_group)
        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setStyleSheet("""
            QTextEdit {
                background-color: #1E1E1E;
                color: #E6E6E6;
                border: 1px solid #444444;
                border-radius: 4px;
                font-family: monospace;
                font-size: 10px;
            }
        """)
        preview_layout.addWidget(self.preview_text)
        right_layout.addWidget(preview_group)
        
        # Add widgets to splitter
        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setSizes([350, 350])
        
        layout.addWidget(splitter)
        
        # Selection summary
        self.summary_label = QLabel("0 instruments × 0 timeframes = 0 artifacts")
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
        
        # Set initial selections from dialog-local state
        self.timeframes_list.set_selected_items(self.selected_timeframes)
    
    def setup_connections(self):
        """Connect signals and slots."""
        # Only timeframe selection changes trigger preview updates
        self.timeframes_list.itemChanged.connect(self.update_preview)
        
        # Button box
        button_box = self.findChild(QDialogButtonBox)
        if button_box:
            button_box.accepted.connect(self.accept)
            button_box.rejected.connect(self.reject)

    def _load_timeframes(self) -> List[str]:
        """Load timeframe ids from provider."""
        try:
            return list(get_timeframe_ids())
        except Exception as e:
            logger.error(f"Failed to load timeframes: {e}")
            return []
    
    def update_preview(self):
        """Update preview based on current selections."""
        # Update dialog-local state from UI
        self.selected_timeframes = set(self.timeframes_list.get_selected_items())
        
        # Generate artifacts preview using derived instruments
        artifacts = []
        for instr in sorted(self.derived_instruments):
            for tf in sorted(self.selected_timeframes):
                artifacts.append(f"{instr} {tf} .PARSET")
        
        # Update preview text
        if artifacts:
            preview_text = "\n".join(artifacts)
        else:
            if not self.derived_instruments:
                preview_text = "No RAW files selected. Use RAW INPUT dialog first."
            else:
                preview_text = "No artifacts - select timeframes"
        
        self.preview_text.setText(preview_text)
        
        # Update summary
        instr_count = len(self.derived_instruments)
        tf_count = len(self.selected_timeframes)
        artifact_count = len(artifacts)
        self.summary_label.setText(
            f"{instr_count} derived instrument{'s' if instr_count != 1 else ''} × "
            f"{tf_count} timeframe{'s' if tf_count != 1 else ''} = "
            f"{artifact_count} artifact{'s' if artifact_count != 1 else ''}"
        )
    
    def accept(self):
        """Handle dialog acceptance (Confirm)."""
        # Update dialog-local state from UI (already done in update_preview)
        
        # Generate artifacts preview list using derived instruments
        artifacts_preview = []
        for instr in sorted(self.derived_instruments):
            for tf in sorted(self.selected_timeframes):
                artifacts_preview.append(f"{instr} {tf} .PARSET")
        
        # Commit to SSOT - instruments list is empty (derived from RAW)
        bar_prepare_state.update_state(
            prepare_plan={
                "instruments": [],  # Instruments are derived, not selected
                "timeframes": list(self.selected_timeframes),
                "artifacts_preview": artifacts_preview
            },
            confirmed=False,
        )
        
        logger.info(
            f"PREPARE PLAN confirmed: {len(self.derived_instruments)} derived instruments, "
            f"{len(self.selected_timeframes)} timeframes"
        )
        super().accept()
    
    def reject(self):
        """Handle dialog rejection (Cancel)."""
        # No state changes - dialog-local state is discarded
        logger.info("PREPARE PLAN cancelled - no state changes")
        super().reject()