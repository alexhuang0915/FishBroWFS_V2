"""
Explain Hub Widget for Hybrid BC v1.1 Shadow Adoption - Layer 2.

Displays job context information without performance metrics.
Only accepts JobContextVM (no raw dicts).
"""

from typing import Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QTextEdit, QScrollArea, QFrame, QSizePolicy
)
from PySide6.QtGui import QFont

from gui.services.hybrid_bc_vms import JobContextVM


class ExplainHubWidget(QWidget):
    """Explain Hub widget for Hybrid BC Layer 2."""
    
    # Signals
    request_open_analysis = Signal(str)  # job_id
    request_view_logs = Signal(str)
    request_open_evidence = Signal(str)
    request_explain_failure = Signal(str)
    request_abort = Signal(str)
    request_archive = Signal(str)  # job_id
    request_restore = Signal(str)  # job_id
    request_purge = Signal(str)   # job_id
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_job_id: Optional[str] = None
        self.current_vm: Optional[JobContextVM] = None
        
        self.setup_ui()
        
    def setup_ui(self):
        """Initialize UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(12)
        
        # Header section
        header_frame = QFrame()
        header_frame.setStyleSheet("""
            QFrame {
                background-color: #1a1a1a;
                border: 1px solid #333333;
                border-radius: 4px;
                padding: 8px;
            }
        """)
        header_layout = QVBoxLayout(header_frame)
        header_layout.setContentsMargins(8, 8, 8, 8)
        
        self.job_id_label = QLabel("No job selected")
        self.job_id_label.setStyleSheet("font-weight: bold; font-size: 14px; color: #E6E6E6;")
        header_layout.addWidget(self.job_id_label)
        
        self.status_badge = QLabel("")
        self.status_badge.setStyleSheet("""
            QLabel {
                padding: 2px 6px;
                border-radius: 3px;
                font-size: 11px;
                font-weight: bold;
            }
        """)
        header_layout.addWidget(self.status_badge)
        
        layout.addWidget(header_frame)
        
        # Full NOTE section (markdown)
        note_group = QGroupBox("NOTE")
        note_group.setStyleSheet("""
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
        note_layout = QVBoxLayout(note_group)
        self.note_text = QTextEdit()
        self.note_text.setReadOnly(True)
        self.note_text.setMaximumHeight(150)
        self.note_text.setStyleSheet("""
            QTextEdit {
                background-color: #252525;
                color: #CCCCCC;
                border: 1px solid #333333;
                font-family: monospace;
                font-size: 11px;
            }
        """)
        note_layout.addWidget(self.note_text)
        layout.addWidget(note_group)
        
        # Config snapshot card
        config_group = QGroupBox("Config Snapshot")
        config_group.setStyleSheet("""
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
        config_layout = QVBoxLayout(config_group)
        self.config_text = QTextEdit()
        self.config_text.setReadOnly(True)
        self.config_text.setMaximumHeight(200)
        self.config_text.setStyleSheet("""
            QTextEdit {
                background-color: #252525;
                color: #CCCCCC;
                border: 1px solid #333333;
                font-family: monospace;
                font-size: 10px;
            }
        """)
        config_layout.addWidget(self.config_text)
        layout.addWidget(config_group)
        
        # Health check card
        health_group = QGroupBox("Health Check")
        health_group.setStyleSheet("""
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
        health_layout = QVBoxLayout(health_group)
        
        self.health_summary_label = QLabel("No health data")
        self.health_summary_label.setStyleSheet("color: #9e9e9e; font-size: 11px;")
        health_layout.addWidget(self.health_summary_label)
        
        self.error_details_text = QTextEdit()
        self.error_details_text.setReadOnly(True)
        self.error_details_text.setMaximumHeight(150)
        self.error_details_text.setStyleSheet("""
            QTextEdit {
                background-color: #252525;
                color: #CCCCCC;
                border: 1px solid #333333;
                font-family: monospace;
                font-size: 10px;
            }
        """)
        self.error_details_text.hide()  # Collapsed by default
        health_layout.addWidget(self.error_details_text)
        
        layout.addWidget(health_group)
        
        # Gatekeeper card
        gatekeeper_group = QGroupBox("Gatekeeper")
        gatekeeper_group.setStyleSheet("""
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
        gatekeeper_layout = QVBoxLayout(gatekeeper_group)
        
        gatekeeper_stats_layout = QHBoxLayout()
        
        self.total_permutations_label = QLabel("Total: --")
        self.total_permutations_label.setStyleSheet("color: #9e9e9e; font-size: 11px;")
        gatekeeper_stats_layout.addWidget(self.total_permutations_label)
        
        self.valid_candidates_label = QLabel("Valid: --")
        self.valid_candidates_label.setStyleSheet("color: #9e9e9e; font-size: 11px;")
        gatekeeper_stats_layout.addWidget(self.valid_candidates_label)
        
        self.plateau_check_label = QLabel("Plateau: N/A")
        self.plateau_check_label.setStyleSheet("color: #9e9e9e; font-size: 11px;")
        gatekeeper_stats_layout.addWidget(self.plateau_check_label)
        
        gatekeeper_stats_layout.addStretch()
        gatekeeper_layout.addLayout(gatekeeper_stats_layout)
        
        layout.addWidget(gatekeeper_group)
        
        # Action bar
        action_frame = QFrame()
        action_frame.setStyleSheet("""
            QFrame {
                background-color: #1a1a1a;
                border: 1px solid #333333;
                border-radius: 4px;
                padding: 8px;
            }
        """)
        action_layout = QHBoxLayout(action_frame)
        action_layout.setContentsMargins(4, 4, 4, 4)
        
        # Primary button: Open Analysis Drawer
        self.open_analysis_btn = QPushButton("Open Analysis Drawer")
        self.open_analysis_btn.setStyleSheet("""
            QPushButton {
                background-color: #1a237e;
                color: white;
                font-weight: bold;
                padding: 8px 16px;
                border-radius: 4px;
                border: 1px solid #283593;
            }
            QPushButton:hover {
                background-color: #283593;
            }
            QPushButton:disabled {
                background-color: #424242;
                color: #9e9e9e;
                border: 1px solid #616161;
            }
        """)
        self.open_analysis_btn.clicked.connect(self._on_open_analysis)
        action_layout.addWidget(self.open_analysis_btn)
        
        # Secondary buttons
        self.view_logs_btn = QPushButton("Logs")
        self.view_logs_btn.setStyleSheet("""
            QPushButton {
                background-color: #2a2a2a;
                color: #E6E6E6;
                padding: 6px 12px;
                border-radius: 3px;
                border: 1px solid #444444;
            }
            QPushButton:hover {
                background-color: #3a3a3a;
            }
        """)
        self.view_logs_btn.clicked.connect(self._on_view_logs)
        action_layout.addWidget(self.view_logs_btn)
        
        self.open_evidence_btn = QPushButton("Evidence")
        self.open_evidence_btn.setStyleSheet("""
            QPushButton {
                background-color: #2a2a2a;
                color: #E6E6E6;
                padding: 6px 12px;
                border-radius: 3px;
                border: 1px solid #444444;
            }
            QPushButton:hover {
                background-color: #3a3a3a;
            }
        """)
        self.open_evidence_btn.clicked.connect(self._on_open_evidence)
        action_layout.addWidget(self.open_evidence_btn)
        
        self.explain_failure_btn = QPushButton("Explain")
        self.explain_failure_btn.setStyleSheet("""
            QPushButton {
                background-color: #2a2a2a;
                color: #E6E6E6;
                padding: 6px 12px;
                border-radius: 3px;
                border: 1px solid #444444;
            }
            QPushButton:hover {
                background-color: #3a3a3a;
            }
            QPushButton:disabled {
                background-color: #424242;
                color: #9e9e9e;
                border: 1px solid #616161;
            }
        """)
        self.explain_failure_btn.clicked.connect(self._on_explain_failure)
        action_layout.addWidget(self.explain_failure_btn)
        
        self.abort_btn = QPushButton("Abort")
        self.abort_btn.setStyleSheet("""
            QPushButton {
                background-color: #5d4037;
                color: white;
                padding: 6px 12px;
                border-radius: 3px;
                border: 1px solid #795548;
            }
            QPushButton:hover {
                background-color: #795548;
            }
            QPushButton:disabled {
                background-color: #424242;
                color: #9e9e9e;
                border: 1px solid #616161;
            }
        """)
        self.abort_btn.clicked.connect(self._on_abort)
        action_layout.addWidget(self.abort_btn)

        # Lifecycle buttons
        self.archive_btn = QPushButton("Archive")
        self.archive_btn.setStyleSheet("""
            QPushButton {
                background-color: #5d4037;
                color: white;
                padding: 6px 12px;
                border-radius: 3px;
                border: 1px solid #795548;
            }
            QPushButton:hover {
                background-color: #795548;
            }
            QPushButton:disabled {
                background-color: #424242;
                color: #9e9e9e;
                border: 1px solid #616161;
            }
        """)
        self.archive_btn.clicked.connect(self._on_archive)
        self.archive_btn.setToolTip("Move job to archive (outputs/jobs/_trash/)")
        action_layout.addWidget(self.archive_btn)

        self.restore_btn = QPushButton("Restore")
        self.restore_btn.setStyleSheet("""
            QPushButton {
                background-color: #2e7d32;
                color: white;
                padding: 6px 12px;
                border-radius: 3px;
                border: 1px solid #4caf50;
            }
            QPushButton:hover {
                background-color: #4caf50;
            }
            QPushButton:disabled {
                background-color: #424242;
                color: #9e9e9e;
                border: 1px solid #616161;
            }
        """)
        self.restore_btn.clicked.connect(self._on_restore)
        self.restore_btn.setToolTip("Restore job from archive to active")
        action_layout.addWidget(self.restore_btn)

        self.purge_btn = QPushButton("Purge")
        self.purge_btn.setStyleSheet("""
            QPushButton {
                background-color: #c62828;
                color: white;
                padding: 6px 12px;
                border-radius: 3px;
                border: 1px solid #d32f2f;
            }
            QPushButton:hover {
                background-color: #d32f2f;
            }
            QPushButton:disabled {
                background-color: #424242;
                color: #9e9e9e;
                border: 1px solid #616161;
            }
        """)
        self.purge_btn.clicked.connect(self._on_purge)
        self.purge_btn.setToolTip("Permanently delete archived job (requires ENABLE_PURGE_ACTION=1)")
        action_layout.addWidget(self.purge_btn)

        action_layout.addStretch()
        layout.addWidget(action_frame)
        
        # Add stretch at bottom
        layout.addStretch()
        
        # Initially disable all buttons
        self._update_button_states()
    
    def set_context(self, vm: JobContextVM) -> None:
        """Update widget with job context data."""
        self.current_vm = vm
        self.current_job_id = vm.job_id
        
        # Update header
        self.job_id_label.setText(f"Job: {vm.job_id}")
        
        # Update status badge
        status = vm.status if hasattr(vm, 'status') else "UNKNOWN"
        status_color = self._get_status_color(status)
        self.status_badge.setText(status)
        self.status_badge.setStyleSheet(f"""
            QLabel {{
                padding: 2px 6px;
                border-radius: 3px;
                font-size: 11px;
                font-weight: bold;
                background-color: {status_color};
                color: white;
            }}
        """)
        
        # Update NOTE
        self.note_text.setPlainText(vm.full_note or "No note available")
        
        # Update config snapshot
        if vm.config_snapshot:
            import json
            try:
                config_json = json.dumps(vm.config_snapshot, indent=2, ensure_ascii=False)
                self.config_text.setPlainText(config_json)
            except Exception:
                self.config_text.setPlainText(str(vm.config_snapshot))
        else:
            self.config_text.setPlainText("No config snapshot available")
        
        # Update health check
        if vm.health:
            self.health_summary_label.setText(vm.health.get('summary', 'No health summary'))
            error_details = vm.health.get('error_details_json')
            if error_details:
                try:
                    error_json = json.dumps(error_details, indent=2, ensure_ascii=False)
                    self.error_details_text.setPlainText(error_json)
                except Exception:
                    self.error_details_text.setPlainText(str(error_details))
            else:
                self.error_details_text.clear()
        else:
            self.health_summary_label.setText("No health data")
            self.error_details_text.clear()
        
        # Update gatekeeper
        if vm.gatekeeper:
            total = vm.gatekeeper.get('total_permutations', 0)
            valid = vm.gatekeeper.get('valid_candidates', 0)
            plateau = vm.gatekeeper.get('plateau_check', 'N/A')
            
            self.total_permutations_label.setText(f"Total: {total}")
            self.valid_candidates_label.setText(f"Valid: {valid}")
            self.plateau_check_label.setText(f"Plateau: {plateau}")
            
            # Color code for plateau
            if plateau == "Pass":
                self.plateau_check_label.setStyleSheet("color: #4CAF50; font-size: 11px;")
            elif plateau == "Fail":
                self.plateau_check_label.setStyleSheet("color: #F44336; font-size: 11px;")
            else:
                self.plateau_check_label.setStyleSheet("color: #9e9e9e; font-size: 11px;")
        else:
            self.total_permutations_label.setText("Total: --")
            self.valid_candidates_label.setText("Valid: --")
            self.plateau_check_label.setText("Plateau: N/A")
            self.plateau_check_label.setStyleSheet("color: #9e9e9e; font-size: 11px;")
        
        # Update button states
        self._update_button_states()
    
    def _update_button_states(self):
        """Update enabled/disabled state of buttons based on current VM."""
        has_vm = self.current_vm is not None
        has_job_id = self.current_job_id is not None
        
        # Open Analysis Drawer button enabled only if valid_candidates > 0
        if has_vm and self.current_vm.gatekeeper:
            valid_candidates = self.current_vm.gatekeeper.get('valid_candidates', 0)
            self.open_analysis_btn.setEnabled(valid_candidates > 0)
            if valid_candidates > 0:
                self.open_analysis_btn.setToolTip(f"Open analysis drawer ({valid_candidates} valid candidates)")
            else:
                self.open_analysis_btn.setToolTip("No valid candidates available for analysis")
        else:
            self.open_analysis_btn.setEnabled(False)
            self.open_analysis_btn.setToolTip("No job selected or gatekeeper data missing")
        
        # Other buttons
        self.view_logs_btn.setEnabled(has_job_id)
        self.open_evidence_btn.setEnabled(has_job_id)
        
        # Explain failure button only for failed/rejected/aborted jobs
        if has_vm:
            status = getattr(self.current_vm, 'status', '')
            self.explain_failure_btn.setEnabled(status in ['FAILED', 'REJECTED', 'ABORTED'])
        else:
            self.explain_failure_btn.setEnabled(False)
        
        # Abort button logic (should use existing control_actions_gate)
        if has_vm:
            from gui.services.control_actions_gate import is_abort_allowed
            status = getattr(self.current_vm, 'status', '')
            self.abort_btn.setEnabled(is_abort_allowed(status))
        else:
            self.abort_btn.setEnabled(False)
        
        # Lifecycle buttons
        if has_vm:
            lifecycle_state = getattr(self.current_vm, 'lifecycle_state', 'ACTIVE')
            # Archive button: enabled if job is ACTIVE
            self.archive_btn.setEnabled(lifecycle_state == 'ACTIVE')
            # Restore button: enabled if job is ARCHIVED
            self.restore_btn.setEnabled(lifecycle_state == 'ARCHIVED')
            # Purge button: enabled if job is ARCHIVED (environment variable check will be done by parent)
            self.purge_btn.setEnabled(lifecycle_state == 'ARCHIVED')
        else:
            self.archive_btn.setEnabled(False)
            self.restore_btn.setEnabled(False)
            self.purge_btn.setEnabled(False)
    
    def _get_status_color(self, status: str) -> str:
        """Get color for status badge."""
        status = status.upper()
        if status == "SUCCEEDED":
            return "#4CAF50"  # green
        elif status in ["FAILED", "REJECTED"]:
            return "#F44336"  # red
        elif status == "RUNNING":
            return "#FF9800"  # amber
        elif status in ["PENDING", "STARTED", "QUEUED"]:
            return "#FFC107"  # yellow
        else:
            return "#9A9A9A"  # gray for unknown status
    
    def _on_open_analysis(self):
        """Handle Open Analysis Drawer button click."""
        if self.current_job_id:
            # Re-check valid_candidates > 0 before emitting signal
            if self.current_vm and self.current_vm.gatekeeper:
                valid_candidates = self.current_vm.gatekeeper.get('valid_candidates', 0)
                if valid_candidates > 0:
                    self.request_open_analysis.emit(self.current_job_id)
                else:
                    # Should be disabled, but just in case
                    pass
    
    def _on_view_logs(self):
        """Handle View Logs button click."""
        if self.current_job_id:
            self.request_view_logs.emit(self.current_job_id)
    
    def _on_open_evidence(self):
        """Handle Open Evidence button click."""
        if self.current_job_id:
            self.request_open_evidence.emit(self.current_job_id)
    
    def _on_explain_failure(self):
        """Handle Explain Failure button click."""
        if self.current_job_id:
            self.request_explain_failure.emit(self.current_job_id)
    
    def _on_abort(self):
        """Handle Abort button click."""
        if self.current_job_id:
            self.request_abort.emit(self.current_job_id)

    def _on_archive(self):
        """Handle Archive button click."""
        if self.current_job_id:
            self.request_archive.emit(self.current_job_id)

    def _on_restore(self):
        """Handle Restore button click."""
        if self.current_job_id:
            self.request_restore.emit(self.current_job_id)

    def _on_purge(self):
        """Handle Purge button click."""
        if self.current_job_id:
            self.request_purge.emit(self.current_job_id)
    
    def show_error(self, message: str):
        """Display an error message in the widget."""
        self.current_vm = None
        self.current_job_id = None
        self.job_id_label.setText("Error loading job")
        self.status_badge.setText("ERROR")
        self.status_badge.setStyleSheet("""
            QLabel {
                padding: 2px 6px;
                border-radius: 3px;
                font-size: 11px;
                font-weight: bold;
                background-color: #F44336;
                color: white;
            }
        """)
        self.note_text.setPlainText(f"Error: {message}")
        self.config_text.clear()
        self.health_summary_label.setText(f"Failed to load job context: {message}")
        self.error_details_text.clear()
        self.total_permutations_label.setText("Total: --")
        self.valid_candidates_label.setText("Valid: --")
        self.plateau_check_label.setText("Plateau: N/A")
        self.plateau_check_label.setStyleSheet("color: #9e9e9e; font-size: 11px;")
        self._update_button_states()
    
    def clear(self):
        """Clear all displayed data."""
        self.current_vm = None
        self.current_job_id = None
        self.job_id_label.setText("No job selected")
        self.status_badge.setText("")
        self.status_badge.setStyleSheet("""
            QLabel {
                padding: 2px 6px;
                border-radius: 3px;
                font-size: 11px;
                font-weight: bold;
            }
        """)
        self.note_text.clear()
        self.config_text.clear()
        self.health_summary_label.setText("No health data")
        self.error_details_text.clear()
        self.total_permutations_label.setText("Total: --")
        self.valid_candidates_label.setText("Valid: --")
        self.plateau_check_label.setText("Plateau: N/A")
        self.plateau_check_label.setStyleSheet("color: #9e9e9e; font-size: 11px;")
        self._update_button_states()
