"""
BAR PREPARE Tab - Page 1: State-Summary Page with Three Summary Panels.

This page shows three summary panels only. All selections happen inside modal dialogs.
State is committed only when user presses Confirm. Cancel must leave the main page completely unchanged.
"""

import logging
from typing import Optional, List, Dict, Any

from PySide6.QtCore import Qt, Signal, Slot, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QFrame, QSizePolicy, QSpacerItem, QProgressBar
)
from PySide6.QtGui import QFont

from ..state.bar_prepare_state import bar_prepare_state
from ..dialogs.raw_input_dialog import RawInputDialog
from ..dialogs.prepare_plan_dialog import PreparePlanDialog
from ..dialogs.bar_inventory_dialog import BarInventoryDialog
from ..services.supervisor_client import submit_job, SupervisorClientError

logger = logging.getLogger(__name__)


class SummaryPanel(QGroupBox):
    """Reusable summary panel for BAR PREPARE page."""
    
    def __init__(self, title: str, action_text: str, parent=None):
        super().__init__(title, parent)
        self.setup_ui(action_text)
        self.apply_styling()
    
    def setup_ui(self, action_text: str):
        """Initialize the UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)
        
        # Status row
        status_layout = QHBoxLayout()
        
        # Status icon
        self.status_icon = QLabel("○")
        self.status_icon.setStyleSheet("font-size: 16px;")
        status_layout.addWidget(self.status_icon)
        
        # Status text
        self.status_text = QLabel("Empty")
        self.status_text.setStyleSheet("color: #9A9A9A; font-size: 11px;")
        status_layout.addWidget(self.status_text)
        
        status_layout.addStretch()
        layout.addLayout(status_layout)
        
        # Summary text
        self.summary_label = QLabel("No selection")
        self.summary_label.setStyleSheet("color: #E6E6E6; font-size: 12px;")
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)
        
        # Action button
        self.action_btn = QPushButton(action_text)
        self.action_btn.setStyleSheet("""
            QPushButton {
                background-color: #2A2A2A;
                color: #E6E6E6;
                border: 1px solid #444444;
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #2F2F2F;
                border: 1px solid #555555;
            }
        """)
        layout.addWidget(self.action_btn)
    
    def apply_styling(self):
        """Apply panel styling."""
        self.setStyleSheet("""
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
    
    def update_status(self, icon: str, status: str, summary: str):
        """Update panel status."""
        self.status_icon.setText(icon)
        self.status_text.setText(status)
        self.summary_label.setText(summary)


class BarPrepareTab(QWidget):
    """BAR PREPARE tab - Page 1 with three summary panels."""
    
    # Signals for communication with main window
    log_signal = Signal(str)
    
    def __init__(self):
        super().__init__()
        self.setup_ui()
        self.setup_connections()
        self.refresh_summary()
    
    def setup_ui(self):
        """Initialize the UI with three summary panels."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 16, 16, 16)
        main_layout.setSpacing(16)
        
        # Title
        title_label = QLabel("BAR PREPARE")
        title_label.setStyleSheet("""
            QLabel {
                font-size: 18px;
                font-weight: bold;
                color: #E6E6E6;
            }
        """)
        main_layout.addWidget(title_label)
        
        # Description
        desc_label = QLabel("Configure raw data inputs and prepare plan. All selections happen in modal dialogs.")
        desc_label.setStyleSheet("color: #9A9A9A; font-size: 11px;")
        desc_label.setWordWrap(True)
        main_layout.addWidget(desc_label)
        
        # Add spacer
        main_layout.addSpacerItem(QSpacerItem(20, 20, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed))
        
        # Two-column layout: left = inputs, right = status monitor
        content_row = QHBoxLayout()
        content_row.setSpacing(16)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(12)

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(12)

        # Left: Input panels
        self.raw_input_panel = SummaryPanel("RAW INPUT", "Change ▼")
        left_layout.addWidget(self.raw_input_panel)

        self.prepare_plan_panel = SummaryPanel("PREPARE PLAN", "Change ▼")
        left_layout.addWidget(self.prepare_plan_panel)

        # Build All Data button
        self.build_all_btn = QPushButton("BUILD ALL DATA")
        self.build_all_btn.setStyleSheet("""
            QPushButton {
                background-color: #0d47a1;
                color: white;
                font-weight: bold;
                font-size: 13px;
                padding: 10px;
                border-radius: 6px;
                border: 2px solid #1565c0;
            }
            QPushButton:hover { background-color: #1565c0; }
            QPushButton:pressed { background-color: #0b3d8a; }
            QPushButton:disabled {
                background-color: #424242;
                color: #9e9e9e;
                border: 2px solid #616161;
            }
        """)
        self.build_all_btn.setMinimumHeight(44)
        left_layout.addWidget(self.build_all_btn)

        # Bottom Action - CONFIRM button
        self.confirm_btn = QPushButton("CONFIRM")
        self.confirm_btn.setStyleSheet("""
            QPushButton {
                background-color: #1a237e;
                color: white;
                font-weight: bold;
                font-size: 14px;
                padding: 12px;
                border-radius: 6px;
                border: 2px solid #283593;
            }
            QPushButton:hover {
                background-color: #283593;
                border: 2px solid #3949ab;
            }
            QPushButton:pressed {
                background-color: #0d47a1;
            }
            QPushButton:disabled {
                background-color: #424242;
                color: #9e9e9e;
                border: 2px solid #616161;
            }
        """)
        self.confirm_btn.setMinimumHeight(50)
        left_layout.addWidget(self.confirm_btn)

        # Disabled reason (visible when CONFIRM is blocked)
        self.confirm_disabled_reason = QLabel("")
        self.confirm_disabled_reason.setStyleSheet("color: #FFB74D; font-size: 11px;")
        self.confirm_disabled_reason.setWordWrap(True)
        self.confirm_disabled_reason.setVisible(False)
        left_layout.addWidget(self.confirm_disabled_reason)

        left_layout.addStretch()

        # Right: Status monitor panels
        self.bar_inventory_panel = SummaryPanel("BAR INVENTORY", "View ▼")
        right_layout.addWidget(self.bar_inventory_panel)

        # Status panel for confirm action feedback
        status_container = QFrame()
        status_container.setStyleSheet("""
            QFrame {
                background-color: #1E1E1E;
                border: 1px solid #333333;
                border-radius: 4px;
                padding: 6px;
            }
        """)
        status_layout = QVBoxLayout(status_container)
        status_layout.setContentsMargins(8, 8, 8, 8)
        status_layout.setSpacing(4)

        self.confirm_status_label = QLabel("Status: Idle")
        self.confirm_status_label.setStyleSheet("color: #9e9e9e; font-size: 10px;")
        status_layout.addWidget(self.confirm_status_label)

        self.confirm_detail_label = QLabel("No confirmation recorded yet.")
        self.confirm_detail_label.setStyleSheet("color: #BDBDBD; font-size: 11px;")
        self.confirm_detail_label.setWordWrap(True)
        status_layout.addWidget(self.confirm_detail_label)

        self.confirm_progress = QProgressBar()
        self.confirm_progress.setRange(0, 0)
        self.confirm_progress.setVisible(False)
        status_layout.addWidget(self.confirm_progress)

        right_layout.addWidget(status_container)

        # Build status panel
        build_status_group = QGroupBox("BUILD STATUS")
        build_status_group.setStyleSheet("""
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
        build_layout = QVBoxLayout(build_status_group)
        build_layout.setContentsMargins(8, 12, 8, 8)
        build_layout.setSpacing(6)

        self.build_status_label = QLabel("Status: Idle")
        self.build_status_label.setStyleSheet("color: #9e9e9e; font-size: 10px;")
        build_layout.addWidget(self.build_status_label)

        self.build_detail_label = QLabel("No build has been submitted yet.")
        self.build_detail_label.setStyleSheet("color: #BDBDBD; font-size: 11px;")
        self.build_detail_label.setWordWrap(True)
        build_layout.addWidget(self.build_detail_label)

        self.build_jobs_label = QLabel("")
        self.build_jobs_label.setStyleSheet("color: #64B5F6; font-size: 10px;")
        self.build_jobs_label.setWordWrap(True)
        self.build_jobs_label.setVisible(False)
        build_layout.addWidget(self.build_jobs_label)

        self.build_errors_label = QLabel("")
        self.build_errors_label.setStyleSheet("color: #FFB74D; font-size: 10px;")
        self.build_errors_label.setWordWrap(True)
        self.build_errors_label.setVisible(False)
        build_layout.addWidget(self.build_errors_label)

        self.build_progress = QProgressBar()
        self.build_progress.setRange(0, 0)
        self.build_progress.setVisible(False)
        build_layout.addWidget(self.build_progress)

        right_layout.addWidget(build_status_group)

        content_row.addWidget(left_widget, 3)
        content_row.addWidget(right_widget, 2)
        main_layout.addLayout(content_row)
    
    def setup_connections(self):
        """Connect signals and slots."""
        # Panel action buttons
        self.raw_input_panel.action_btn.clicked.connect(self.open_raw_input_dialog)
        self.prepare_plan_panel.action_btn.clicked.connect(self.open_prepare_plan_dialog)
        self.bar_inventory_panel.action_btn.clicked.connect(self.open_bar_inventory_dialog)
        
        # Confirm button
        self.confirm_btn.clicked.connect(self.handle_confirm)

        # Build all data button
        self.build_all_btn.clicked.connect(self.handle_build_all)
    
    def refresh_summary(self):
        """Refresh all summary panels based on current state."""
        state = bar_prepare_state.get_state()
        
        # RAW INPUT panel
        raw_count = len(state.raw_inputs)
        if raw_count == 0:
            self.raw_input_panel.update_status("○", "EMPTY", "No raw files selected")
        else:
            examples = ", ".join(state.raw_inputs[:3])
            if raw_count > 3:
                examples += f" (+{raw_count - 3} more)"
            self.raw_input_panel.update_status("✓", "SELECTED", f"{raw_count} files: {examples}")
        
        # PREPARE PLAN panel
        instr_count = len(state.derived_instruments)  # Use derived instruments, not selected
        tf_count = len(state.prepare_plan.timeframes)
        if instr_count == 0 or tf_count == 0:
            if instr_count == 0:
                self.prepare_plan_panel.update_status("○", "EMPTY", "No instruments derived from RAW files")
            else:
                self.prepare_plan_panel.update_status("○", "EMPTY", "No timeframes selected")
        else:
            artifact_count = len(state.prepare_plan.artifacts_preview)
            summary = f"{instr_count} derived instruments × {tf_count} timeframes → {artifact_count} artifacts"
            self.prepare_plan_panel.update_status("✓", "CONFIGURED", summary)
        
        # BAR INVENTORY panel (read-only)
        if state.bar_inventory_summary:
            # Simplified display - in real implementation would show actual counts
            self.bar_inventory_panel.update_status("📊", "AVAILABLE", "Existing BAR assets available for inspection")
        else:
            self.bar_inventory_panel.update_status("○", "EMPTY", "No BAR inventory loaded")
        
        # Update Confirm button state
        self.update_confirm_button()
        self._update_confirm_status_from_state(state)
        self._update_build_button_state(state)
    
    def update_confirm_button(self):
        """Update Confirm button enabled state."""
        state = bar_prepare_state.get_state()
        raw_selected = len(state.raw_inputs) > 0
        # Instruments are derived from RAW files, not selected
        instruments_derived = len(state.derived_instruments) > 0
        timeframes_selected = len(state.prepare_plan.timeframes) > 0

        reasons = []
        if not raw_selected:
            reasons.append("Select at least one RAW input file.")
        if not instruments_derived:
            reasons.append("No instruments derived from RAW inputs.")
        if not timeframes_selected:
            reasons.append("Select at least one timeframe in Prepare Plan.")

        is_ready = raw_selected and instruments_derived and timeframes_selected
        self.confirm_btn.setEnabled(is_ready)

        if reasons:
            self.confirm_disabled_reason.setText("Blocked: " + " ".join(reasons))
            self.confirm_disabled_reason.setVisible(True)
        else:
            self.confirm_disabled_reason.setVisible(False)
    
    def _update_build_button_state(self, state):
        """Update Build All Data button enabled state."""
        has_inputs = len(state.raw_inputs) > 0
        has_instruments = len(state.derived_instruments) > 0
        has_timeframes = len(state.prepare_plan.timeframes) > 0
        self.build_all_btn.setEnabled(has_inputs and has_instruments and has_timeframes and state.confirmed)

    def _update_confirm_status_from_state(self, state):
        """Update confirm status panel from current state."""
        if state.confirmed:
            self.confirm_status_label.setText("Status: Confirmed")
            self.confirm_detail_label.setText(
                f"Configuration confirmed at {state.last_updated.strftime('%H:%M:%S')}. "
                "Proceed to the next step to start the prepare pipeline."
            )
            self.confirm_btn.setText("CONFIRMED")
        else:
            self.confirm_status_label.setText("Status: Idle")
            self.confirm_detail_label.setText("No confirmation recorded yet.")
            self.confirm_btn.setText("CONFIRM")
        self.confirm_progress.setVisible(False)
    
    @Slot()
    def open_raw_input_dialog(self):
        """Open RAW INPUT dialog."""
        dialog = RawInputDialog(self)
        if dialog.exec():
            # Dialog was confirmed - state already updated by dialog
            self.refresh_summary()
            self.log_signal.emit("RAW INPUT selection confirmed")
        else:
            # Dialog was cancelled - no state change
            self.log_signal.emit("RAW INPUT selection cancelled")
    
    @Slot()
    def open_prepare_plan_dialog(self):
        """Open PREPARE PLAN dialog."""
        dialog = PreparePlanDialog(self)
        if dialog.exec():
            # Dialog was confirmed - state already updated by dialog
            self.refresh_summary()
            self.log_signal.emit("PREPARE PLAN configuration confirmed")
        else:
            # Dialog was cancelled - no state change
            self.log_signal.emit("PREPARE PLAN configuration cancelled")
    
    @Slot()
    def open_bar_inventory_dialog(self):
        """Open BAR INVENTORY dialog (read-only)."""
        dialog = BarInventoryDialog(self)
        dialog.exec()  # Read-only, no state changes
        self.log_signal.emit("BAR INVENTORY viewed")
    
    @Slot()
    def handle_confirm(self):
        """Handle CONFIRM button click."""
        state = bar_prepare_state.get_state()

        bar_prepare_state.update_state(confirmed=True)

        # Immediate UI feedback
        self.confirm_status_label.setText("Status: Confirmed")
        self.confirm_detail_label.setText(
            "Confirmation recorded. Next step can now start prepare execution."
        )
        self.confirm_progress.setVisible(False)
        
        # Log the confirmation
        self.log_signal.emit(f"BAR PREPARE confirmed: {len(state.raw_inputs)} raw files, "
                            f"{len(state.derived_instruments)} derived instruments, "
                            f"{len(state.prepare_plan.timeframes)} timeframes")
        
        # TODO: In a real implementation, this would trigger the actual prepare operation
        # For now, just show a message
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(
            self,
            "BAR PREPARE Confirmed",
            f"Configuration confirmed:\n"
            f"- {len(state.raw_inputs)} raw files\n"
            f"- {len(state.derived_instruments)} derived instruments\n"
            f"- {len(state.prepare_plan.timeframes)} timeframes\n\n"
            f"Prepare operation would now start...",
            QMessageBox.StandardButton.Ok
        )
        self.refresh_summary()

    def _parse_timeframe_minutes(self, timeframe: str) -> Optional[int]:
        """Parse timeframe string like '60m' or '1h' into minutes."""
        if not timeframe:
            return None
        tf = timeframe.strip().lower()
        digits = "".join(ch for ch in tf if ch.isdigit())
        if not digits:
            return None
        value = int(digits)
        if tf.endswith("h"):
            return value * 60
        if tf.endswith("d"):
            return value * 1440
        return value

    @Slot()
    def handle_build_all(self):
        """Submit BUILD_DATA jobs for all derived instruments and timeframes."""
        state = bar_prepare_state.get_state()
        reasons = []
        if not state.raw_inputs:
            reasons.append("Select RAW input files first.")
        if not state.derived_instruments:
            reasons.append("No instruments derived from RAW inputs.")
        if not state.prepare_plan.timeframes:
            reasons.append("Select timeframes in Prepare Plan.")
        if not state.confirmed:
            reasons.append("Confirm configuration before building data.")

        if reasons:
            self.build_status_label.setText("Status: Blocked")
            self.build_detail_label.setText("Blocked: " + " ".join(reasons))
            self.build_errors_label.setVisible(False)
            self.build_jobs_label.setVisible(False)
            self.build_progress.setVisible(False)
            return

        # Build submission queue
        queue: List[Dict[str, Any]] = []
        invalid_tfs = []
        for timeframe in state.prepare_plan.timeframes:
            tf_min = self._parse_timeframe_minutes(timeframe)
            if tf_min is None:
                invalid_tfs.append(timeframe)
                continue
            for instrument in state.derived_instruments:
                queue.append({
                    "job_type": "BUILD_DATA",
                    "dataset_id": instrument,
                    "timeframe_min": tf_min,
                    "mode": "FULL",
                    "force_rebuild": False
                })

        if invalid_tfs:
            self.build_status_label.setText("Status: Blocked")
            self.build_detail_label.setText(
                "Blocked: Invalid timeframe(s): " + ", ".join(invalid_tfs)
            )
            self.build_errors_label.setVisible(False)
            self.build_jobs_label.setVisible(False)
            self.build_progress.setVisible(False)
            return

        if not queue:
            self.build_status_label.setText("Status: Blocked")
            self.build_detail_label.setText("Blocked: No build jobs could be created.")
            self.build_errors_label.setVisible(False)
            self.build_jobs_label.setVisible(False)
            self.build_progress.setVisible(False)
            return

        self._build_queue = queue
        self._build_submitted: List[str] = []
        self._build_errors: List[str] = []

        self.build_status_label.setText("Status: Submitting")
        self.build_detail_label.setText(f"Submitting {len(queue)} build jobs...")
        self.build_progress.setVisible(True)
        self.build_jobs_label.setVisible(False)
        self.build_errors_label.setVisible(False)
        self.build_all_btn.setEnabled(False)

        self.log_signal.emit(f"BUILD ALL DATA requested: {len(queue)} jobs")
        QTimer.singleShot(0, self._submit_next_build_job)

    def _submit_next_build_job(self):
        """Submit build jobs sequentially to keep UI responsive."""
        if not getattr(self, "_build_queue", []):
            submitted_count = len(self._build_submitted)
            error_count = len(self._build_errors)
            self.build_status_label.setText("Status: Submitted")
            self.build_detail_label.setText(
                f"Submitted {submitted_count} build jobs."
            )
            if self._build_submitted:
                self.build_jobs_label.setText("Job IDs: " + ", ".join(self._build_submitted[:8]))
                self.build_jobs_label.setVisible(True)
            if error_count:
                self.build_errors_label.setText("Errors: " + " | ".join(self._build_errors[:3]))
                self.build_errors_label.setVisible(True)
            self.build_progress.setVisible(False)
            self.build_all_btn.setEnabled(True)
            self.refresh_summary()
            return

        payload = self._build_queue.pop(0)
        dataset_id = payload.get("dataset_id", "unknown")
        timeframe_min = payload.get("timeframe_min", "unknown")

        try:
            response = submit_job(payload)
            job_id = response.get("job_id")
            if not job_id:
                raise SupervisorClientError(message="No job_id in response", error_type="validation")
            self._build_submitted.append(job_id)
            self.build_detail_label.setText(
                f"Submitted {len(self._build_submitted)} / "
                f"{len(self._build_submitted) + len(self._build_queue)} jobs..."
            )
            self.log_signal.emit(f"BUILD_DATA submitted: {job_id} ({dataset_id}, {timeframe_min}m)")
        except SupervisorClientError as e:
            msg = f"{dataset_id}/{timeframe_min}m: {e.message or str(e)}"
            self._build_errors.append(msg)
            self.log_signal.emit(f"BUILD_DATA failed: {msg}")
        except Exception as e:
            msg = f"{dataset_id}/{timeframe_min}m: {str(e)}"
            self._build_errors.append(msg)
            self.log_signal.emit(f"BUILD_DATA failed: {msg}")

        QTimer.singleShot(0, self._submit_next_build_job)