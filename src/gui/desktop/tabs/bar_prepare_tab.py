"""
BAR PREPARE Tab - Page 1: State-Summary Page with Three Summary Panels.

This page shows three summary panels only. All selections happen inside modal dialogs.
State is read-only until the inventory snapshot is refreshed.
"""

import json
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

from PySide6.QtCore import Qt, Signal, Slot, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QFrame, QSizePolicy, QSpacerItem, QProgressBar,
    QApplication
)
from PySide6.QtGui import QFont

from ..state.bar_prepare_state import bar_prepare_state
from ..dialogs.raw_input_dialog import RawInputDialog
from ..dialogs.prepare_plan_dialog import PreparePlanDialog
from ..dialogs.bar_inventory_dialog import BarInventoryDialog
from ..services.supervisor_client import (
    submit_job,
    get_job,
    get_artifacts,
    get_artifact_file,
    get_stdout_tail,
    SupervisorClientError,
    get_registry_instruments,
    get_registry_timeframes
)
from ..state.job_store import job_store, JobRecord
from ..utils.artifact_manifest import select_build_manifest_filename, parse_build_manifest
from ..utils.build_status import (
    derive_overall_status,
    extract_status_message,
    compute_stall_warning,
    TERMINAL_FAILURE,
)

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
        self._last_inventory_refresh: Optional[datetime] = None
        self._build_poll_timer: Optional[QTimer] = None
        self._build_last_update_at: Optional[datetime] = None
        self._build_last_change_at: Optional[datetime] = None
        self._build_last_message: str = ""
        self._build_last_status: str = ""
        self.setup_ui()
        self.setup_connections()
        self.refresh_summary()
        self.destroyed.connect(self._stop_build_polling)
    
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

        # Bottom Action - Refresh Inventory button
        self.refresh_inventory_btn = QPushButton("Refresh Inventory")
        self.refresh_inventory_btn.setStyleSheet("""
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
        self.refresh_inventory_btn.setMinimumHeight(50)
        left_layout.addWidget(self.refresh_inventory_btn)

        # Disabled reason (visible when refresh is blocked)
        self.refresh_disabled_reason = QLabel("")
        self.refresh_disabled_reason.setStyleSheet("color: #FFB74D; font-size: 11px;")
        self.refresh_disabled_reason.setWordWrap(True)
        self.refresh_disabled_reason.setVisible(False)
        left_layout.addWidget(self.refresh_disabled_reason)

        left_layout.addStretch()

        # Status monitor panels
        self.latest_job_panel = QGroupBox("LATEST PREPARE JOB")
        self.latest_job_panel.setVisible(False)
        self.latest_job_panel.setStyleSheet("""
            QGroupBox { border: 1px solid #3A8DFF; font-weight: bold; margin-top: 5px; padding-top: 10px; }
            QGroupBox::title { color: #3A8DFF; left: 8px; }
        """)
        latest_job_layout = QVBoxLayout(self.latest_job_panel)
        self.latest_job_label = QLabel("Status: —")
        self.latest_job_label.setStyleSheet("color: #E6E6E6; font-size: 11px;")
        latest_job_layout.addWidget(self.latest_job_label)
        
        open_ops_btn = QPushButton("OPEN IN OPS")
        open_ops_btn.setStyleSheet("""
            QPushButton { background-color: #1A2A3A; color: #3A8DFF; font-size: 10px; padding: 4px; border: 1px solid #3A8DFF; }
            QPushButton:hover { background-color: #2A3A4A; }
        """)
        open_ops_btn.clicked.connect(self._on_open_latest_job_in_ops)
        latest_job_layout.addWidget(open_ops_btn)
        
        right_layout.addWidget(self.latest_job_panel)

        self.bar_inventory_panel = SummaryPanel("BAR INVENTORY", "View ▼")
        right_layout.addWidget(self.bar_inventory_panel)

        # Registry mismatch warning panel
        self.registry_warning_panel = QFrame()
        self.registry_warning_panel.setStyleSheet("""
            QFrame {
                background-color: #2E1B1B;
                border: 1px solid #8B0000;
                border-radius: 4px;
                padding: 6px;
            }
        """)
        self.registry_warning_panel.setVisible(False)
        registry_warning_layout = QVBoxLayout(self.registry_warning_panel)
        registry_warning_layout.setContentsMargins(8, 8, 8, 8)
        registry_warning_layout.setSpacing(4)

        self.registry_warning_title = QLabel("⚠ Registry Mismatch")
        self.registry_warning_title.setStyleSheet("color: #FFB74D; font-weight: bold; font-size: 11px;")
        registry_warning_layout.addWidget(self.registry_warning_title)

        self.registry_warning_text = QLabel("")
        self.registry_warning_text.setStyleSheet("color: #FFCCBC; font-size: 10px;")
        self.registry_warning_text.setWordWrap(True)
        registry_warning_layout.addWidget(self.registry_warning_text)

        right_layout.addWidget(self.registry_warning_panel)

        # Status panel for refresh feedback
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

        self.refresh_status_label = QLabel("Status: Idle")
        self.refresh_status_label.setStyleSheet("color: #9e9e9e; font-size: 10px;")
        status_layout.addWidget(self.refresh_status_label)

        self.refresh_detail_label = QLabel("Refresh to capture current inventory snapshot.")
        self.refresh_detail_label.setStyleSheet("color: #BDBDBD; font-size: 11px;")
        self.refresh_detail_label.setWordWrap(True)
        status_layout.addWidget(self.refresh_detail_label)

        self.refresh_progress = QProgressBar()
        self.refresh_progress.setRange(0, 0)
        self.refresh_progress.setVisible(False)
        status_layout.addWidget(self.refresh_progress)

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

        self.build_last_update_label = QLabel("Last update: —")
        self.build_last_update_label.setStyleSheet("color: #9e9e9e; font-size: 10px;")
        build_layout.addWidget(self.build_last_update_label)

        self.build_stall_label = QLabel("")
        self.build_stall_label.setStyleSheet("color: #FFB74D; font-size: 10px;")
        self.build_stall_label.setWordWrap(True)
        build_layout.addWidget(self.build_stall_label)

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
        
        # Refresh inventory button
        self.refresh_inventory_btn.clicked.connect(self.handle_refresh_inventory)

        # Build all data button
        self.build_all_btn.clicked.connect(self.handle_build_all)

    def closeEvent(self, event):
        """Ensure timers are stopped when the tab is closed."""
        self._stop_build_polling()
        super().closeEvent(event)
    
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
        self.update_refresh_button(state)
        self._update_refresh_status(state)
        self._update_build_button_state(state)
        self._refresh_registry_mismatch(state)
    
    def update_refresh_button(self, state=None):
        """Update Refresh Inventory button enabled state."""
        if state is None:
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
        self.refresh_inventory_btn.setEnabled(is_ready)

        if reasons:
            self.refresh_disabled_reason.setText("Blocked: " + " ".join(reasons))
            self.refresh_disabled_reason.setVisible(True)
        else:
            self.refresh_disabled_reason.setVisible(False)
    
    def _update_build_button_state(self, state):
        """Update Build All Data button enabled state."""
        has_inputs = len(state.raw_inputs) > 0
        has_instruments = len(state.derived_instruments) > 0
        has_timeframes = len(state.prepare_plan.timeframes) > 0
        self.build_all_btn.setEnabled(has_inputs and has_instruments and has_timeframes)

    def _refresh_registry_mismatch(self, state):
        """Check registry mismatch and update warning panel."""
        try:
            registry_instruments = get_registry_instruments()
            registry_timeframes = get_registry_timeframes()
        except Exception as e:
            logger.warning(f"Failed to fetch registry: {e}")
            self.registry_warning_panel.setVisible(False)
            return

        # Convert to sets for comparison
        registry_instr_set = set(registry_instruments)
        registry_tf_set = set(registry_timeframes)

        derived_instr_set = set(state.derived_instruments)
        selected_tf_set = set(state.prepare_plan.timeframes)

        mismatches = []
        # Instrument mismatches
        missing_instruments = derived_instr_set - registry_instr_set
        if missing_instruments:
            mismatches.append(f"Instruments not in registry: {', '.join(sorted(missing_instruments)[:3])}")
        # Timeframe mismatches
        missing_timeframes = selected_tf_set - registry_tf_set
        if missing_timeframes:
            mismatches.append(f"Timeframes not in registry: {', '.join(sorted(missing_timeframes)[:3])}")

        if mismatches:
            self.registry_warning_text.setText("\n".join(mismatches))
            self.registry_warning_panel.setVisible(True)
        else:
            self.registry_warning_panel.setVisible(False)

    def _update_refresh_status(self, state):
        """Update refresh status panel from current state."""
        if self._last_inventory_refresh:
            timestamp = self._last_inventory_refresh.strftime("%H:%M:%S")
            self.refresh_status_label.setText(f"Status: Inventory refreshed at {timestamp}")
            self.refresh_detail_label.setText(
                f"{len(state.raw_inputs)} RAW files • "
                f"{len(state.derived_instruments)} derived instruments • "
                f"{len(state.prepare_plan.timeframes)} timeframes"
            )
        else:
            self.refresh_status_label.setText("Status: Idle")
            self.refresh_detail_label.setText("Refresh to capture current inventory snapshot.")
        self.refresh_progress.setVisible(False)
    
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
    def handle_refresh_inventory(self):
        """Handle Refresh Inventory button click."""
        state = bar_prepare_state.get_state()
        self._last_inventory_refresh = datetime.now()
        self.refresh_summary()
        self.log_signal.emit(
            f"BAR PREPARE inventory refreshed: "
            f"{len(state.raw_inputs)} raw files, "
            f"{len(state.derived_instruments)} derived instruments, "
            f"{len(state.prepare_plan.timeframes)} timeframes"
        )

    def _parse_timeframe_minutes(self, timeframe: str) -> Optional[int]:
        """Parse timeframe string like '60m', '1h', 'D', '15m' into minutes."""
        if not timeframe:
            return None
        tf = timeframe.strip().lower()
        # Handle special single-letter codes (registry may use "D" for daily)
        if tf == "d":
            return 1440
        if tf == "w":
            return 10080  # 7 days
        # Extract digits
        digits = "".join(ch for ch in tf if ch.isdigit())
        if not digits:
            # Could be "H1"? Not typical, but fallback
            return None
        value = int(digits)
        if tf.endswith("h"):
            return value * 60
        if tf.endswith("d"):
            return value * 1440
        # Assume minutes if no suffix (or suffix 'm')
        # Registry display names are like "15m", "30m", "60m", "120m", "240m"
        # Also "1h" is already caught above
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

        if reasons:
            self.build_status_label.setText("Status: Blocked")
            self.build_detail_label.setText("Blocked: " + " ".join(reasons))
            self.build_errors_label.setVisible(False)
            self.build_jobs_label.setVisible(False)
            self.build_progress.setVisible(False)
            self._reset_build_tracking()
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
            self._reset_build_tracking()
            return

        if not queue:
            self.build_detail_label.setText("No new data needs building.")
            self.build_detail_label.setStyleSheet("color: #4CAF50;")
            self.build_all_btn.setToolTip("No instruments selected or already up to date.")
            return

        self._build_queue = queue
        self._build_submitted: List[str] = []
        self._build_errors: List[str] = []
        self._build_status_by_job: Dict[str, str] = {}

        self.build_status_label.setText("Status: Submitting")
        self.build_detail_label.setText(f"Submitting {len(queue)} build jobs...")
        self.build_progress.setVisible(True)
        self.build_jobs_label.setVisible(False)
        self.build_errors_label.setVisible(False)
        self.build_all_btn.setEnabled(False)
        self._stop_build_polling()
        self._reset_build_tracking()

        self.log_signal.emit(f"BUILD ALL DATA requested: {len(queue)} jobs")
        QTimer.singleShot(0, self._submit_next_build_job)

    def _submit_next_build_job(self):
        """Submit build jobs sequentially to keep UI responsive."""
        if not getattr(self, "_build_queue", []):
            submitted_count = len(self._build_submitted)
            error_count = len(self._build_errors)
            if submitted_count:
                self.build_status_label.setText("Status: Running")
            else:
                self.build_status_label.setText("Status: Failed")
            self.build_detail_label.setText("Jobs submitted. Waiting for status updates...")
            if self._build_submitted:
                self.build_jobs_label.setText("Job IDs: " + ", ".join(self._build_submitted[:8]))
                self.build_jobs_label.setVisible(True)
            if error_count:
                self.build_errors_label.setText("Errors: " + " | ".join(self._build_errors[:3]))
                self.build_errors_label.setVisible(True)
            if submitted_count:
                now = datetime.now()
                self._build_last_update_at = now
                self._build_last_change_at = now
                self._build_last_status = "RUNNING"
                self._build_last_message = ""
                self.build_last_update_label.setText(f"Last update: {now.strftime('%H:%M:%S')}")
                self.build_stall_label.setText("")
                self.build_progress.setVisible(True)
                self._start_build_polling()
            else:
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
            
            # Register with UI JobStore (SSOT)
            job_store.upsert(JobRecord(
                job_id=job_id,
                job_type="prepare",
                created_at=datetime.now(),
                status="queued",
                summary=f"Prepare: {payload.get('dataset_id')} ({payload.get('timeframe_min')}m)"
            ))

            self._build_submitted.append(job_id)
            self._build_status_by_job[job_id] = "SUBMITTED"
            
            # Non-silent feedback (UX B3.2)
            self.build_detail_label.setText(f"Submitted {job_id[:8]}... Next job starting.")
            
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

    def _start_build_polling(self):
        """Start polling supervisor for build job status."""
        if self._build_poll_timer is None:
            self._build_poll_timer = QTimer(self)
            self._build_poll_timer.setInterval(2000)
            self._build_poll_timer.timeout.connect(self._poll_build_jobs)
        self._build_poll_timer.start()
        self.build_status_label.setText("Status: Running")
        self.build_progress.setVisible(True)

    def _stop_build_polling(self):
        """Stop polling supervisor for build job status."""
        if self._build_poll_timer and self._build_poll_timer.isActive():
            self._build_poll_timer.stop()

    def _reset_build_tracking(self):
        """Reset build tracking labels and timestamps."""
        self._build_last_update_at = None
        self._build_last_change_at = None
        self._build_last_message = ""
        self._build_last_status = ""
        self.build_last_update_label.setText("Last update: —")
        self.build_stall_label.setText("")

    def _update_build_stall_warning(self, now: datetime, threshold_seconds: int = 20):
        """Update stall warning if no status/message change recently."""
        warning = compute_stall_warning(self._build_last_change_at, now, threshold_seconds)
        self.build_stall_label.setText(warning)

    def _poll_build_jobs(self):
        """Poll supervisor for build job status and update UI."""
        if not getattr(self, "_build_submitted", []):
            self._stop_build_polling()
            return

        failures = []
        message = ""
        statuses = []
        for job_id in self._build_submitted:
            try:
                job = get_job(job_id)
                status = job.get("status") or job.get("state") or "UNKNOWN"
                self._build_status_by_job[job_id] = status
                statuses.append(status)

                failure_message = job.get("failure_message") or job.get("error_message") or ""
                if status in TERMINAL_FAILURE and failure_message:
                    failures.append(f"{job_id[:8]}: {failure_message}")
                    if not message:
                        message = failure_message

                if not message:
                    message = extract_status_message(job)

                # Sync to Global JobStore (SSOT)
                existing = next((j for j in job_store.list_jobs() if j.job_id == job_id), None)
                if existing:
                    display_status = status.upper()
                    if display_status in {"SUCCEEDED", "DONE"}: ssot_status = "done"
                    elif display_status in {"FAILED", "REJECTED", "ABORTED", "KILLED"}: ssot_status = "failed"
                    elif display_status in {"RUNNING"}: ssot_status = "running"
                    else: ssot_status = "queued"

                    job_store.upsert(JobRecord(
                        job_id=job_id,
                        job_type=existing.job_type,
                        created_at=existing.created_at,
                        status=ssot_status,
                        progress_stage=extract_status_message(job),
                        summary=existing.summary,
                        error_digest=failure_message
                    ))
            except SupervisorClientError as exc:
                failures.append(f"{job_id[:8]}: {exc.message or str(exc)}")
                self._build_status_by_job[job_id] = "UNKNOWN"
                statuses.append("UNKNOWN")
            except Exception as exc:
                failures.append(f"{job_id[:8]}: {str(exc)}")
                self._build_status_by_job[job_id] = "UNKNOWN"
                statuses.append("UNKNOWN")

        if not message and self._build_submitted:
            try:
                log_tail = get_stdout_tail(self._build_submitted[0], n=10)
                last_line = log_tail.strip().splitlines()[-1] if log_tail.strip() else ""
                if last_line:
                    message = last_line
            except Exception:
                pass

        overall_status = derive_overall_status(statuses)

        now = datetime.now()
        self._build_last_update_at = now
        self.build_last_update_label.setText(f"Last update: {now.strftime('%H:%M:%S')}")

        if overall_status != self._build_last_status or (message and message != self._build_last_message):
            self._build_last_change_at = now
            self._build_last_status = overall_status
            if message:
                self._build_last_message = message

        if message:
            self.build_detail_label.setText(f"Last message: {message}")
        else:
            self.build_detail_label.setText("Waiting for status update...")

        if failures:
            self.build_errors_label.setText("Errors: " + " | ".join(failures[:3]))
            self.build_errors_label.setVisible(True)
        else:
            self.build_errors_label.setVisible(False)

        self.build_status_label.setText(f"Status: {overall_status}")
        self._update_build_stall_warning(now)

        if overall_status in {"DONE", "FAILED"}:
            if not message and overall_status == "DONE":
                self.build_detail_label.setText("Build completed successfully.")
            self._stop_build_polling()
            self.build_progress.setVisible(False)
            self.build_all_btn.setEnabled(True)
            self._refresh_bar_inventory_from_manifests(self._build_submitted)
            self.refresh_summary()
            
            # Update Latest Job Panel (UX B2.1)
            if self._build_submitted:
                last_job_id = self._build_submitted[-1]
                self.latest_job_label.setText(f"ID: {last_job_id[:8]}... | Status: {overall_status}")
                self.latest_job_panel.setVisible(True)

    def _on_open_latest_job_in_ops(self):
        """Deep-link to Ops tab for the last submitted job."""
        if not self._build_submitted:
            return
        last_job_id = self._build_submitted[-1]
        from gui.services.action_router_service import get_action_router_service
        router = get_action_router_service()
        router.handle_action(f"internal://job/{last_job_id}")

    def _refresh_bar_inventory_from_manifests(self, job_ids: List[str]):
        """Refresh BAR inventory summary from build manifests."""
        rows: List[Dict[str, Any]] = []
        for job_id in job_ids:
            try:
                artifact_index = get_artifacts(job_id)
            except SupervisorClientError as exc:
                logger.warning("Failed to fetch artifacts for job %s: %s", job_id, exc)
                continue
            except Exception as exc:
                logger.warning("Failed to fetch artifacts for job %s: %s", job_id, exc)
                continue

            manifest_file = select_build_manifest_filename(artifact_index)
            if not manifest_file:
                continue

            try:
                raw = get_artifact_file(job_id, manifest_file)
                payload = json.loads(raw.decode("utf-8", errors="replace"))
            except Exception as exc:
                logger.warning("Failed to parse manifest for job %s: %s", job_id, exc)
                continue

            manifest_rows, _produced_path = parse_build_manifest(payload)
            rows.extend(manifest_rows)

        if rows:
            bar_prepare_state.update_state(bar_inventory_summary={"rows": rows})
            self._last_inventory_refresh = datetime.now()