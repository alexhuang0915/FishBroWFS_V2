"""
Data Readiness Dialog - Read-only modal showing dataset readiness details.

This dialog shows dataset mapping details and missing dataset reasons.
It's read-only and follows zero-silent UI principles.
"""

import logging
from typing import Dict, Any, List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QWidget,
    QLabel, QPushButton, QDialogButtonBox, QTextEdit,
    QGroupBox, QScrollArea, QFrame
)

from gui.desktop.state.operation_state import DataReadinessSummary, operation_page_state
from gui.services.dataset_resolver import DatasetResolver

logger = logging.getLogger(__name__)


class DataReadinessDialog(QDialog):
    """Read-only dialog showing data readiness details."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.dataset_resolver = DatasetResolver()
        self.current_readiness: DataReadinessSummary = DataReadinessSummary()
        
        self.setup_ui()
        self.load_current_state()
    
    def setup_ui(self):
        """Initialize the UI with data readiness details."""
        self.setWindowTitle("Data Readiness Details")
        self.setMinimumSize(800, 600)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)
        
        # Title
        title_label = QLabel("Data Readiness Details")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #E6E6E6;")
        main_layout.addWidget(title_label)
        
        # Description
        desc_label = QLabel(
            "This view shows dataset readiness status and mapping details. "
            "All missing data reasons are shown (zero-silent UI)."
        )
        desc_label.setStyleSheet("color: #9A9A9A; font-size: 12px;")
        desc_label.setWordWrap(True)
        main_layout.addWidget(desc_label)
        
        # Create scroll area for content
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: #121212;
            }
        """)
        
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(8, 8, 8, 8)
        content_layout.setSpacing(16)
        
        # Status summary group
        status_group = QGroupBox("Status Summary")
        status_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 2px solid #555555;
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
        
        status_layout = QVBoxLayout(status_group)
        
        # DATA1 status
        data1_widget = self.create_status_widget("DATA1", "UNKNOWN", "#FFC107")
        status_layout.addWidget(data1_widget)
        
        # DATA2 status
        data2_widget = self.create_status_widget("DATA2", "UNKNOWN", "#FFC107")
        status_layout.addWidget(data2_widget)
        
        content_layout.addWidget(status_group)
        
        # Missing reasons group
        self.missing_reasons_group = QGroupBox("Missing Data Reasons")
        self.missing_reasons_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 2px solid #F44336;
                background-color: #1E1E1E;
                margin-top: 5px;
                padding-top: 8px;
                font-size: 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px 0 4px;
                color: #F44336;
            }
        """)
        
        missing_reasons_layout = QVBoxLayout(self.missing_reasons_group)
        self.missing_reasons_text = QTextEdit()
        self.missing_reasons_text.setReadOnly(True)
        self.missing_reasons_text.setStyleSheet("""
            QTextEdit {
                background-color: #121212;
                color: #E6E6E6;
                border: 1px solid #555555;
                font-family: monospace;
                font-size: 11px;
            }
        """)
        self.missing_reasons_text.setMaximumHeight(150)
        missing_reasons_layout.addWidget(self.missing_reasons_text)
        
        content_layout.addWidget(self.missing_reasons_group)
        
        # Dataset mapping group
        self.dataset_mapping_group = QGroupBox("Dataset Mapping")
        self.dataset_mapping_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 2px solid #4CAF50;
                background-color: #1E1E1E;
                margin-top: 5px;
                padding-top: 8px;
                font-size: 12px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px 0 4px;
                color: #4CAF50;
            }
        """)
        
        dataset_mapping_layout = QVBoxLayout(self.dataset_mapping_group)
        self.dataset_mapping_text = QTextEdit()
        self.dataset_mapping_text.setReadOnly(True)
        self.dataset_mapping_text.setStyleSheet("""
            QTextEdit {
                background-color: #121212;
                color: #E6E6E6;
                border: 1px solid #555555;
                font-family: monospace;
                font-size: 11px;
            }
        """)
        self.dataset_mapping_text.setMaximumHeight(200)
        dataset_mapping_layout.addWidget(self.dataset_mapping_text)
        
        content_layout.addWidget(self.dataset_mapping_group)
        
        # Build cache button (if applicable)
        self.build_cache_frame = QFrame()
        self.build_cache_frame.setStyleSheet("""
            QFrame {
                background-color: #1E1E1E;
                border: 1px solid #555555;
                border-radius: 4px;
            }
        """)
        
        build_cache_layout = QHBoxLayout(self.build_cache_frame)
        build_cache_layout.setContentsMargins(12, 8, 12, 8)
        
        build_cache_label = QLabel("Build missing data cache:")
        build_cache_label.setStyleSheet("color: #E6E6E6;")
        build_cache_layout.addWidget(build_cache_label)
        
        build_cache_layout.addStretch()
        
        self.build_cache_btn = QPushButton("Build Cache")
        self.build_cache_btn.setStyleSheet("""
            QPushButton {
                background-color: #1a237e;
                color: white;
                font-weight: bold;
                padding: 6px 12px;
                border-radius: 4px;
                border: 1px solid #283593;
            }
            QPushButton:hover {
                background-color: #283593;
            }
            QPushButton:disabled {
                background-color: #424242;
                color: #9e9e9e;
            }
        """)
        self.build_cache_btn.clicked.connect(self.on_build_cache)
        build_cache_layout.addWidget(self.build_cache_btn)
        
        content_layout.addWidget(self.build_cache_frame)
        
        content_layout.addStretch()
        
        # Set content widget to scroll area
        scroll.setWidget(content_widget)
        main_layout.addWidget(scroll)
        
        # Dialog buttons
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.button(QDialogButtonBox.StandardButton.Close).setText("Close")
        button_box.rejected.connect(self.reject)
        
        main_layout.addWidget(button_box)
    
    def create_status_widget(self, data_name: str, status: str, color: str) -> QWidget:
        """Create a status widget for DATA1/DATA2."""
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(8, 4, 8, 4)
        
        name_label = QLabel(f"{data_name}:")
        name_label.setStyleSheet(f"color: {color}; font-weight: bold;")
        layout.addWidget(name_label)
        
        status_label = QLabel(status)
        status_label.setStyleSheet(f"color: {color};")
        layout.addWidget(status_label)
        
        layout.addStretch()
        
        return widget
    
    def load_current_state(self):
        """Load current operation state."""
        current_state = operation_page_state.get_state()
        self.current_readiness = current_state.data_readiness
        
        # Update UI with current readiness
        self.update_ui_from_state()
        
        # Evaluate if build cache should be shown
        self.evaluate_build_cache_visibility()
    
    def update_ui_from_state(self):
        """Update UI components to reflect current readiness state."""
        # Update status colors based on readiness
        data1_color = self.get_status_color(self.current_readiness.data1_status)
        data2_color = self.get_status_color(self.current_readiness.data2_status)
        
        # Update missing reasons
        if self.current_readiness.missing_reasons:
            reasons_text = "\n".join(f"• {reason}" for reason in self.current_readiness.missing_reasons)
            self.missing_reasons_text.setText(reasons_text)
            self.missing_reasons_group.show()
        else:
            self.missing_reasons_text.setText("No missing data reasons.")
            self.missing_reasons_group.show()
        
        # Update dataset mapping
        if self.current_readiness.dataset_mapping:
            mapping_lines = []
            for key, dataset_id in self.current_readiness.dataset_mapping.items():
                mapping_lines.append(f"{key} → {dataset_id}")
            self.dataset_mapping_text.setText("\n".join(mapping_lines))
            self.dataset_mapping_group.show()
        else:
            self.dataset_mapping_text.setText("No dataset mapping available.")
            self.dataset_mapping_group.show()
    
    def get_status_color(self, status: str) -> str:
        """Get color for status."""
        status_lower = status.lower()
        if "ready" in status_lower or "complete" in status_lower:
            return "#4CAF50"  # Green
        elif "missing" in status_lower or "fail" in status_lower:
            return "#F44336"  # Red
        elif "partial" in status_lower or "warning" in status_lower:
            return "#FFC107"  # Yellow
        else:
            return "#9E9E9E"  # Gray
    
    def evaluate_build_cache_visibility(self):
        """Evaluate if build cache button should be shown."""
        # Check if there are missing data reasons
        has_missing_data = bool(self.current_readiness.missing_reasons)
        
        # Check if DATA1 or DATA2 status indicates missing data
        data1_missing = "missing" in self.current_readiness.data1_status.lower()
        data2_missing = "missing" in self.current_readiness.data2_status.lower()
        
        should_show = has_missing_data or data1_missing or data2_missing
        
        self.build_cache_frame.setVisible(should_show)
        self.build_cache_btn.setEnabled(should_show)
    
    def on_build_cache(self):
        """Handle Build Cache button click."""
        # Get current run intent
        current_state = operation_page_state.get_state()
        run_intent = current_state.run_intent
        
        # Check if we have enough information to build cache
        if not run_intent.strategies or not run_intent.instruments or not run_intent.timeframes:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self,
                "Incomplete Configuration",
                "Cannot build cache: Run intent is incomplete. "
                "Please configure strategies, instruments, and timeframes first."
            )
            return
        
        # Use the first selected strategy, instrument, and timeframe
        strategy_id = run_intent.strategies[0] if run_intent.strategies else None
        instrument_id = run_intent.instruments[0] if run_intent.instruments else None
        timeframe_id = run_intent.timeframes[0] if run_intent.timeframes else None
        mode = run_intent.mode or "backtest"
        
        if not strategy_id or not instrument_id or not timeframe_id:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self,
                "Missing Configuration",
                "Cannot build cache: Missing strategy, instrument, or timeframe selection."
            )
            return
        
        try:
            # This would trigger a cache build job
            # For now, just show a message
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(
                self,
                "Build Cache",
                f"Cache build requested for:\n"
                f"Strategy: {strategy_id}\n"
                f"Instrument: {instrument_id}\n"
                f"Timeframe: {timeframe_id}\n"
                f"Mode: {mode}\n\n"
                f"This would trigger a background job to prepare missing data."
            )
            
            # Update status
            self.current_readiness.data1_status = "BUILDING"
            self.current_readiness.data2_status = "BUILDING"
            self.current_readiness.missing_reasons = ["Cache build in progress..."]
            
            self.update_ui_from_state()
            self.build_cache_btn.setEnabled(False)
            
        except Exception as e:
            logger.error(f"Failed to build cache: {e}")
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(
                self,
                "Build Cache Failed",
                f"Failed to build cache: {e}"
            )