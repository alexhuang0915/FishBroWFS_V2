"""
Gate Explanation Dialog – shows detailed gate status, explanation, and raw evidence.
"""

import json
import logging
from typing import Any, Dict, Optional

from PySide6.QtCore import Qt, Signal, Slot  # type: ignore
from PySide6.QtWidgets import (  # type: ignore
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QPlainTextEdit, QLabel, QSizePolicy, QSpacerItem,
    QGroupBox, QCheckBox, QSplitter, QTextEdit
)
from PySide6.QtGui import QFont, QTextCursor, QKeySequence, QShortcut, QColor  # type: ignore

from gui.services.gate_summary_service import GateResult

logger = logging.getLogger(__name__)


class GateExplanationDialog(QDialog):
    """
    Dialog for displaying detailed gate explanation and raw evidence.
    
    Layout:
    - Header: gate name, status, timestamp
    - Explanation (plain text)
    - Collapsible raw evidence section (JSON pretty-printed)
    - Buttons: Close, Copy
    """
    
    # Signal emitted when dialog is closed
    closed = Signal()
    
    def __init__(
        self,
        gate_result: GateResult,
        parent=None
    ):
        super().__init__(parent)
        self.gate_result = gate_result
        self.setup_ui()
        self.setup_connections()
    
    def setup_ui(self):
        """Initialize the UI components."""
        self.setWindowTitle(f"Gate Explanation – {self.gate_result.gate_name}")
        self.setMinimumSize(700, 500)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(8)
        
        # Header with gate info
        header_layout = QHBoxLayout()
        
        gate_label = QLabel(f"Gate: {self.gate_result.gate_name}")
        gate_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #E6E6E6;")
        header_layout.addWidget(gate_label)
        
        header_layout.addSpacerItem(QSpacerItem(20, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
        
        # Status badge
        status_label = QLabel(self.gate_result.status.value)
        status_color = self._status_color(self.gate_result.status)
        status_label.setStyleSheet(f"""
            QLabel {{
                background-color: {status_color};
                color: #FFFFFF;
                font-weight: bold;
                padding: 4px 8px;
                border-radius: 4px;
                font-size: 12px;
            }}
        """)
        header_layout.addWidget(status_label)
        
        # Timestamp
        if self.gate_result.timestamp:
            ts_label = QLabel(self.gate_result.timestamp[:19].replace("T", " "))
            ts_label.setStyleSheet("color: #9A9A9A; font-size: 11px;")
            header_layout.addWidget(ts_label)
        
        main_layout.addLayout(header_layout)
        
        # Explanation section
        explanation_group = QGroupBox("Explanation")
        explanation_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 1px solid #555555;
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
        explanation_layout = QVBoxLayout(explanation_group)
        
        explanation_text = QTextEdit()
        explanation_text.setReadOnly(True)
        explanation_text.setPlainText(self.gate_result.message)
        explanation_text.setStyleSheet("""
            QTextEdit {
                background-color: #1E1E1E;
                color: #E6E6E6;
                border: none;
                font-size: 12px;
                padding: 4px;
            }
        """)
        explanation_text.setMaximumHeight(80)
        explanation_layout.addWidget(explanation_text)
        
        main_layout.addWidget(explanation_group)
        
        # Raw evidence section (collapsible)
        self.evidence_group = QGroupBox("Raw Evidence")
        self.evidence_group.setCheckable(True)
        self.evidence_group.setChecked(False)
        self.evidence_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 1px solid #555555;
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
        evidence_layout = QVBoxLayout(self.evidence_group)
        
        self.evidence_text = QPlainTextEdit()
        self.evidence_text.setReadOnly(True)
        self.evidence_text.setFont(QFont("Monospace", 9))
        self.evidence_text.setStyleSheet("""
            QPlainTextEdit {
                background-color: #1E1E1E;
                color: #E6E6E6;
                border: 1px solid #555555;
                border-radius: 4px;
                font-family: 'Consolas', 'Monaco', monospace;
                selection-background-color: #3A8DFF;
            }
        """)
        self.evidence_text.setPlaceholderText("Evidence will appear when expanded...")
        evidence_layout.addWidget(self.evidence_text)
        
        main_layout.addWidget(self.evidence_group)
        
        # Button panel
        button_layout = QHBoxLayout()
        
        # Copy button
        copy_btn = QPushButton("📋 Copy Evidence")
        copy_btn.setToolTip("Copy raw evidence JSON to clipboard")
        copy_btn.setMinimumWidth(120)
        button_layout.addWidget(copy_btn)
        self.copy_btn = copy_btn
        
        button_layout.addSpacerItem(QSpacerItem(20, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
        
        # Close button
        close_btn = QPushButton("Close")
        close_btn.setMinimumWidth(100)
        button_layout.addWidget(close_btn)
        self.close_btn = close_btn
        
        main_layout.addLayout(button_layout)
        
        # Populate evidence text when group is expanded
        self.evidence_group.toggled.connect(self._on_evidence_toggled)
    
    def setup_connections(self):
        """Connect signals and slots."""
        self.copy_btn.clicked.connect(self.copy_to_clipboard)
        self.close_btn.clicked.connect(self.accept)
        
        # Keyboard shortcuts
        QShortcut(QKeySequence.Copy, self).activated.connect(self.copy_to_clipboard)  # type: ignore
        QShortcut(QKeySequence.Close, self).activated.connect(self.accept)  # type: ignore
    
    def _status_color(self, status) -> str:
        """Return CSS color for status badge."""
        if status.value == "PASS":
            return "#4CAF50"
        elif status.value == "WARN":
            return "#FF9800"
        elif status.value == "FAIL":
            return "#F44336"
        else:
            return "#9E9E9E"
    
    def _on_evidence_toggled(self, checked: bool):
        """When evidence group is expanded, populate the text."""
        if checked and self.evidence_text.toPlainText() == "":
            evidence = self._format_evidence()
            self.evidence_text.setPlainText(evidence)
    
    def _format_evidence(self) -> str:
        """Format gate details as pretty JSON."""
        evidence = {
            "gate_id": self.gate_result.gate_id,
            "gate_name": self.gate_result.gate_name,
            "status": self.gate_result.status.value,
            "message": self.gate_result.message,
            "timestamp": self.gate_result.timestamp,
            "details": self.gate_result.details,
            "actions": self.gate_result.actions,
        }
        try:
            return json.dumps(evidence, indent=2, ensure_ascii=False)
        except (TypeError, ValueError):
            # Fallback to repr
            return repr(evidence)
    
    @Slot()
    def copy_to_clipboard(self):
        """Copy evidence JSON to clipboard."""
        evidence = self._format_evidence()
        from PySide6.QtWidgets import QApplication  # type: ignore
        QApplication.clipboard().setText(evidence)
        # Show temporary feedback
        self.copy_btn.setText("Copied!")
        from PySide6.QtCore import QTimer  # type: ignore
        QTimer.singleShot(1000, lambda: self.copy_btn.setText("📋 Copy Evidence"))
    
    def closeEvent(self, event):
        """Handle dialog close event."""
        self.closed.emit()
        super().closeEvent(event)
    
    @classmethod
    def show_for_gate(cls, gate_result: GateResult, parent=None):
        """
        Convenience method to create and show explanation for a gate.
        
        Args:
            gate_result: The gate result to explain
            parent: Parent widget
        """
        dialog = cls(gate_result, parent=parent)
        dialog.exec()