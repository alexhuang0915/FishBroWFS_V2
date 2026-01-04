"""
Audit Tab - Forensic view of system events.
"""

import logging
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QGroupBox, QHeaderView, QMessageBox, QTextEdit,
    QSplitter, QFileDialog
)
from PySide6.QtGui import QFont

logger = logging.getLogger(__name__)


class AuditTab(QWidget):
    """Audit tab - chronological event log with forensic details."""
    
    # Signals for communication with main window
    log_signal = Signal(str)
    
    def __init__(self):
        super().__init__()
        self.setup_ui()
        self.setup_connections()
        self.refresh_audit()
    
    def setup_ui(self):
        """Initialize the UI components."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)
        
        # Header
        header_label = QLabel("Audit Trail - Forensic View")
        header_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        main_layout.addWidget(header_label)
        
        # Description
        desc_label = QLabel("Chronological event list from jobs.db + filesystem (no derived/cached state)")
        desc_label.setStyleSheet("font-size: 12px; color: #666;")
        main_layout.addWidget(desc_label)
        
        # Control buttons
        control_layout = QHBoxLayout()
        
        self.refresh_btn = QPushButton("🔄 Refresh")
        self.refresh_btn.setMinimumHeight(40)
        control_layout.addWidget(self.refresh_btn)
        
        self.export_btn = QPushButton("📤 Export to JSON")
        self.export_btn.setMinimumHeight(40)
        control_layout.addWidget(self.export_btn)
        
        self.clear_btn = QPushButton("🗑️ Clear Filter")
        self.clear_btn.setMinimumHeight(40)
        self.clear_btn.setEnabled(False)
        control_layout.addWidget(self.clear_btn)
        
        control_layout.addStretch()
        main_layout.addLayout(control_layout)
        
        # Create splitter for table/details
        splitter = QSplitter(Qt.Vertical)
        
        # Top panel: Audit table
        table_group = QGroupBox("Audit Events")
        table_layout = QVBoxLayout()
        
        self.audit_table = QTableWidget()
        self.audit_table.setColumnCount(5)
        self.audit_table.setHorizontalHeaderLabels([
            "Timestamp", "Event Type", "User/Actor", "Strategy ID", "Status"
        ])
        
        # Configure table with balanced column widths
        header = self.audit_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Interactive)  # Timestamp: 20-25%
        header.setSectionResizeMode(1, QHeaderView.Interactive)  # Event Type: 15-20%
        header.setSectionResizeMode(2, QHeaderView.Interactive)  # User/Actor: 20-25%
        header.setSectionResizeMode(3, QHeaderView.Interactive)  # Strategy ID: 20-25%
        header.setSectionResizeMode(4, QHeaderView.Interactive)  # Status: 10-15%
        
        # Set minimum sizes
        header.setMinimumSectionSize(60)
        
        # Set default sizes
        self.audit_table.setColumnWidth(0, 180)  # Timestamp
        self.audit_table.setColumnWidth(1, 120)  # Event Type
        self.audit_table.setColumnWidth(2, 150)  # User/Actor
        self.audit_table.setColumnWidth(3, 150)  # Strategy ID
        self.audit_table.setColumnWidth(4, 100)  # Status
        
        self.audit_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.audit_table.setSelectionMode(QTableWidget.SingleSelection)
        
        table_layout.addWidget(self.audit_table)
        table_group.setLayout(table_layout)
        
        # Bottom panel: Event details
        details_group = QGroupBox("Event Details")
        details_layout = QVBoxLayout()
        
        # Details text area
        self.details_text = QTextEdit()
        self.details_text.setReadOnly(True)
        self.details_text.setFont(QFont("Monospace", 10))
        self.details_text.setStyleSheet("""
            QTextEdit {
                background-color: #f8f8f8;
                border: 1px solid #ccc;
            }
        """)
        details_layout.addWidget(self.details_text)
        
        # Action buttons for details
        action_layout = QHBoxLayout()
        
        self.open_run_dir_btn = QPushButton("📁 Open Run Directory")
        self.open_run_dir_btn.setMinimumHeight(40)
        self.open_run_dir_btn.setEnabled(False)
        action_layout.addWidget(self.open_run_dir_btn)
        
        self.open_artifact_dir_btn = QPushButton("📦 Open Artifact Directory")
        self.open_artifact_dir_btn.setMinimumHeight(40)
        self.open_artifact_dir_btn.setEnabled(False)
        action_layout.addWidget(self.open_artifact_dir_btn)
        
        self.view_manifest_btn = QPushButton("📄 View Manifest.json")
        self.view_manifest_btn.setMinimumHeight(40)
        self.view_manifest_btn.setEnabled(False)
        action_layout.addWidget(self.view_manifest_btn)
        
        self.view_metrics_btn = QPushButton("📊 View Metrics.json")
        self.view_metrics_btn.setMinimumHeight(40)
        self.view_metrics_btn.setEnabled(False)
        action_layout.addWidget(self.view_metrics_btn)
        
        action_layout.addStretch()
        details_layout.addLayout(action_layout)
        
        details_group.setLayout(details_layout)
        
        # Add widgets to splitter
        splitter.addWidget(table_group)
        splitter.addWidget(details_group)
        splitter.setSizes([300, 200])
        
        main_layout.addWidget(splitter)
        
        # Status bar
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("font-size: 11px; color: #666;")
        main_layout.addWidget(self.status_label)
    
    def setup_connections(self):
        """Connect signals and slots."""
        self.refresh_btn.clicked.connect(self.refresh_audit)
        self.export_btn.clicked.connect(self.export_audit)
        self.clear_btn.clicked.connect(self.clear_filter)
        self.audit_table.itemSelectionChanged.connect(self.on_selection_changed)
        self.open_run_dir_btn.clicked.connect(self.open_run_directory)
        self.open_artifact_dir_btn.clicked.connect(self.open_artifact_directory)
        self.view_manifest_btn.clicked.connect(self.view_manifest)
        self.view_metrics_btn.clicked.connect(self.view_metrics)
    
    def log(self, message: str):
        """Append message to log."""
        self.log_signal.emit(message)
        self.status_label.setText(message)
    
    def refresh_audit(self):
        """Refresh audit data from jobs.db and filesystem."""
        self.log("Refreshing audit trail from jobs.db + filesystem...")
        
        # Clear table
        self.audit_table.setRowCount(0)
        
        try:
            # TODO: Replace with actual backend call to jobs.db
            # For now, use mock data
            events = self._get_mock_audit_events()
            
            self.audit_table.setRowCount(len(events))
            
            for row, event in enumerate(events):
                # Timestamp
                self.audit_table.setItem(row, 0, QTableWidgetItem(event["timestamp"]))
                
                # Event Type
                event_type_item = QTableWidgetItem(event["event_type"])
                # Color code by event type
                if event["event_type"] == "promote":
                    event_type_item.setForeground(Qt.darkGreen)
                elif event["event_type"] == "admit":
                    event_type_item.setForeground(Qt.darkBlue)
                elif event["event_type"] == "freeze":
                    event_type_item.setForeground(Qt.darkGray)
                elif event["event_type"] == "allocation_change":
                    event_type_item.setForeground(Qt.darkMagenta)
                self.audit_table.setItem(row, 1, event_type_item)
                
                # User/Actor
                self.audit_table.setItem(row, 2, QTableWidgetItem(event["actor"]))
                
                # Strategy ID
                self.audit_table.setItem(row, 3, QTableWidgetItem(event["strategy_id"]))
                
                # Status
                status_item = QTableWidgetItem(event["status"])
                if event["status"] == "SUCCESS":
                    status_item.setForeground(Qt.darkGreen)
                elif event["status"] == "FAILED":
                    status_item.setForeground(Qt.darkRed)
                elif event["status"] == "PENDING":
                    status_item.setForeground(Qt.darkYellow)
                self.audit_table.setItem(row, 4, status_item)
            
            self.log(f"Loaded {len(events)} audit events")
            
        except Exception as e:
            self.log(f"ERROR: Failed to refresh audit: {e}")
            QMessageBox.critical(self, "Audit Error", f"Failed to load audit events: {e}")
    
    def _get_mock_audit_events(self) -> List[Dict[str, Any]]:
        """Get mock audit events for development."""
        return [
            {
                "timestamp": "2026-01-03 11:45:23",
                "event_type": "promote",
                "actor": "operator@desktop",
                "strategy_id": "S1_baseline",
                "status": "SUCCESS",
                "details": {
                    "run_dir": "outputs/seasons/2026Q1/runs/artifact_20260103_123456",
                    "artifact_dir": "outputs/seasons/2026Q1/runs/artifact_20260103_123456",
                    "manifest_exists": True,
                    "metrics_exists": True,
                    "validation_result": "VALID"
                }
            },
            {
                "timestamp": "2026-01-03 11:30:15",
                "event_type": "admit",
                "actor": "research_auto",
                "strategy_id": "S2_momentum",
                "status": "SUCCESS",
                "details": {
                    "run_dir": "outputs/seasons/2026Q1/runs/run_20260103_112345",
                    "artifact_dir": "outputs/seasons/2026Q1/runs/artifact_20260103_112345",
                    "manifest_exists": True,
                    "metrics_exists": True,
                    "validation_result": "VALID"
                }
            },
            {
                "timestamp": "2026-01-03 11:15:42",
                "event_type": "freeze",
                "actor": "governance@desktop",
                "strategy_id": "S3_reversal",
                "status": "SUCCESS",
                "details": {
                    "run_dir": "outputs/seasons/2026Q1/runs/artifact_20260102_234567",
                    "artifact_dir": "outputs/seasons/2026Q1/runs/artifact_20260102_234567",
                    "manifest_exists": True,
                    "metrics_exists": True,
                    "reason": "Excessive drawdown"
                }
            },
            {
                "timestamp": "2026-01-03 10:55:18",
                "event_type": "allocation_change",
                "actor": "portfolio_manager",
                "strategy_id": "ALL",
                "status": "SUCCESS",
                "details": {
                    "changes": [
                        {"strategy": "S1_baseline", "old_weight": 35.0, "new_weight": 40.0},
                        {"strategy": "S2_momentum", "old_weight": 25.0, "new_weight": 30.0}
                    ],
                    "total_risk_budget": 125000.0
                }
            },
            {
                "timestamp": "2026-01-03 10:30:05",
                "event_type": "promote",
                "actor": "operator@desktop",
                "strategy_id": "SMA_cross",
                "status": "FAILED",
                "details": {
                    "run_dir": "outputs/seasons/2026Q1/runs/run_20260103_103005",
                    "artifact_dir": "outputs/seasons/2026Q1/runs/run_20260103_103005",
                    "manifest_exists": False,
                    "metrics_exists": True,
                    "validation_result": "INVALID_MISSING_MANIFEST",
                    "error": "manifest.json not found"
                }
            }
        ]
    
    def on_selection_changed(self):
        """Handle table selection change."""
        selected_rows = self.audit_table.selectionModel().selectedRows()
        if not selected_rows:
            self.details_text.clear()
            self.open_run_dir_btn.setEnabled(False)
            self.open_artifact_dir_btn.setEnabled(False)
            self.view_manifest_btn.setEnabled(False)
            self.view_metrics_btn.setEnabled(False)
            return
        
        row = selected_rows[0].row()
        
        # Get event data (from mock or actual data)
        events = self._get_mock_audit_events()
        if row < len(events):
            event = events[row]
            
            # Format details for display
            details_text = f"Event: {event['event_type']}\n"
            details_text += f"Timestamp: {event['timestamp']}\n"
            details_text += f"Actor: {event['actor']}\n"
            details_text += f"Strategy: {event['strategy_id']}\n"
            details_text += f"Status: {event['status']}\n\n"
            details_text += "Details:\n"
            details_text += json.dumps(event.get("details", {}), indent=2)
            
            self.details_text.setText(details_text)
            
            # Enable buttons based on event type and details
            has_run_dir = "run_dir" in event.get("details", {})
            has_artifact_dir = "artifact_dir" in event.get("details", {})
            has_manifest = event.get("details", {}).get("manifest_exists", False)
            has_metrics = event.get("details", {}).get("metrics_exists", False)
            
            self.open_run_dir_btn.setEnabled(has_run_dir)
            self.open_artifact_dir_btn.setEnabled(has_artifact_dir)
            self.view_manifest_btn.setEnabled(has_manifest)
            self.view_metrics_btn.setEnabled(has_metrics)
    
    def open_run_directory(self):
        """Open run directory in file explorer."""
        selected_rows = self.audit_table.selectionModel().selectedRows()
        if not selected_rows:
            return
        
        row = selected_rows[0].row()
        events = self._get_mock_audit_events()
        if row < len(events):
            run_dir = events[row].get("details", {}).get("run_dir", "")
            if run_dir:
                path = Path(run_dir)
                if path.exists():
                    # TODO: Open file explorer
                    self.log(f"Would open run directory: {run_dir}")
                    QMessageBox.information(self, "Open Directory", f"Run directory: {run_dir}")
                else:
                    QMessageBox.warning(self, "Directory Not Found", f"Directory does not exist: {run_dir}")
    
    def open_artifact_directory(self):
        """Open artifact directory in file explorer."""
        selected_rows = self.audit_table.selectionModel().selectedRows()
        if not selected_rows:
            return
        
        row = selected_rows[0].row()
        events = self._get_mock_audit_events()
        if row < len(events):
            artifact_dir = events[row].get("details", {}).get("artifact_dir", "")
            if artifact_dir:
                path = Path(artifact_dir)
                if path.exists():
                    # TODO: Open file explorer
                    self.log(f"Would open artifact directory: {artifact_dir}")
                    QMessageBox.information(self, "Open Directory", f"Artifact directory: {artifact_dir}")
                else:
                    QMessageBox.warning(self, "Directory Not Found", f"Directory does not exist: {artifact_dir}")
    
    def view_manifest(self):
        """View manifest.json content."""
        selected_rows = self.audit_table.selectionModel().selectedRows()
        if not selected_rows:
            return
        
        row = selected_rows[0].row()
        events = self._get_mock_audit_events()
        if row < len(events):
            artifact_dir = events[row].get("details", {}).get("artifact_dir", "")
            if artifact_dir:
                manifest_path = Path(artifact_dir) / "manifest.json"
                if manifest_path.exists():
                    try:
                        with open(manifest_path, 'r') as f:
                            manifest_content = json.load(f)
                        
                        # Show in dialog
                        dialog = QMessageBox(self)
                        dialog.setWindowTitle("manifest.json")
                        dialog.setText(f"File: {manifest_path}")
                        dialog.setDetailedText(json.dumps(manifest_content, indent=2))
                        dialog.setIcon(QMessageBox.Information)
                        dialog.exec()
                    except Exception as e:
                        QMessageBox.critical(self, "Error", f"Failed to read manifest.json: {e}")
                else:
                    QMessageBox.warning(self, "File Not Found", f"manifest.json not found at: {manifest_path}")
    
    def view_metrics(self):
        """View metrics.json content."""
        selected_rows = self.audit_table.selectionModel().selectedRows()
        if not selected_rows:
            return
        
        row = selected_rows[0].row()
        events = self._get_mock_audit_events()
        if row < len(events):
            artifact_dir = events[row].get("details", {}).get("artifact_dir", "")
            if artifact_dir:
                metrics_path = Path(artifact_dir) / "metrics.json"
                if metrics_path.exists():
                    try:
                        with open(metrics_path, 'r') as f:
                            metrics_content = json.load(f)
                        
                        # Show in dialog
                        dialog = QMessageBox(self)
                        dialog.setWindowTitle("metrics.json")
                        dialog.setText(f"File: {metrics_path}")
                        dialog.setDetailedText(json.dumps(metrics_content, indent=2))
                        dialog.setIcon(QMessageBox.Information)
                        dialog.exec()
                    except Exception as e:
                        QMessageBox.critical(self, "Error", f"Failed to read metrics.json: {e}")
                else:
                    QMessageBox.warning(self, "File Not Found", f"metrics.json not found at: {metrics_path}")
    
    def export_audit(self):
        """Export audit events to JSON file."""
        try:
            events = self._get_mock_audit_events()
            
            # Get save location
            file_path, _ = QFileDialog.getSaveFileName(
                self, "Export Audit Events", "audit_export.json", "JSON Files (*.json)"
            )
            
            if file_path:
                with open(file_path, 'w') as f:
                    json.dump(events, f, indent=2)
                
                self.log(f"Exported {len(events)} events to {file_path}")
                QMessageBox.information(self, "Export Successful", f"Exported {len(events)} events to {file_path}")
        
        except Exception as e:
            self.log(f"ERROR: Failed to export audit: {e}")
            QMessageBox.critical(self, "Export Error", f"Failed to export audit events: {e}")
    
    def clear_filter(self):
        """Clear any applied filters."""
        self.log("Filters cleared")
        # TODO: Implement actual filter clearing when filters are added