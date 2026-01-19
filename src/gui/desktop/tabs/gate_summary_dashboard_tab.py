"""
Gate Summary Dashboard Tab (DP7) with Explain Hub Tabs (v2.2-B).

Cross-job gate summary matrix showing gate status across all jobs.
Provides a dashboard view of research → governance → admission workflow.
Includes Explain Hub Tabs (Narrative/Dev/Biz) for job explanation.
"""

import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

from PySide6.QtCore import Qt, Signal, Slot, QTimer  # type: ignore
from PySide6.QtWidgets import (  # type: ignore
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QGroupBox, QFrame, QScrollArea,
    QSizePolicy, QProgressBar, QTextEdit
)

from gui.services.cross_job_gate_summary_service import (
    get_cross_job_gate_summary_service,
    CrossJobGateSummaryMatrix,
    JobGateSummary,
)
from gui.services.action_router_service import get_action_router_service
from gui.desktop.widgets.gate_drawer import GateDrawer
from gui.desktop.widgets.sticky_verdict_bar import StickyVerdictBar
from gui.desktop.widgets.explain_hub_tabs import ExplainHubTabs
from gui.desktop.widgets.evidence_browser import EvidenceBrowserDialog
from gui.desktop.widgets.gate_explanation_dialog import GateExplanationDialog
from contracts.portfolio.gate_summary_schemas import GateStatus
from gui.desktop.state.decision_gate_state import decision_gate_state

logger = logging.getLogger(__name__)


class GateSummaryDashboardTab(QWidget):
    """Dashboard tab showing cross-job gate summary matrix."""
    
    # Signal for logging
    log_signal = Signal(str)
    
    def __init__(self, enable_local_router: bool = True):
        super().__init__()
        self.service = get_cross_job_gate_summary_service()
        self.action_router = get_action_router_service()
        self.current_matrix: Optional[CrossJobGateSummaryMatrix] = None
        self.last_selected_job_id: Optional[str] = None
        self.enable_local_router = enable_local_router
        self.setup_ui()
        self.setup_refresh_timer()
        self.refresh_data()

    
    def setup_ui(self):
        """Initialize the UI with a sticky verdict bar and gate drawer."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        self.sticky_bar = StickyVerdictBar()
        self.sticky_bar.refresh_requested.connect(self.refresh_data)
        main_layout.addWidget(self.sticky_bar)

        expanded_widget = self._build_expanded_content()
        self.gate_drawer = GateDrawer(expanded_widget)
        main_layout.addWidget(self.gate_drawer)
        self.gate_drawer.set_collapsed(True)

    def _build_expanded_content(self) -> QWidget:
        """Build the expanded gate dashboard content (header + matrix + details)."""
        expanded_widget = QWidget()
        expanded_layout = QVBoxLayout(expanded_widget)
        expanded_layout.setContentsMargins(0, 0, 0, 0)
        expanded_layout.setSpacing(8)

        header_widget = QWidget()
        header_widget.setStyleSheet("background-color: #1E1E1E; border-radius: 4px; padding: 8px;")
        header_layout = QVBoxLayout(header_widget)

        self.title_label = QLabel("Gate Summary Dashboard")
        self.title_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #E6E6E6;")
        header_layout.addWidget(self.title_label)

        self.subtitle_label = QLabel("Cross-job gate status matrix (Research → Governance → Admission)")
        self.subtitle_label.setStyleSheet("color: #9A9A9A; font-size: 11px;")
        header_layout.addWidget(self.subtitle_label)

        stats_widget = QWidget()
        stats_layout = QHBoxLayout(stats_widget)
        stats_layout.setContentsMargins(0, 4, 0, 0)

        self.total_label = QLabel("Total: 0")
        self.pass_label = QLabel("PASS: 0")
        self.warn_label = QLabel("WARN: 0")
        self.fail_label = QLabel("FAIL: 0")
        self.unknown_label = QLabel("UNKNOWN: 0")

        for label in [
            self.total_label,
            self.pass_label,
            self.warn_label,
            self.fail_label,
            self.unknown_label,
        ]:
            label.setStyleSheet("font-size: 11px; padding: 2px 6px; border-radius: 3px;")
            stats_layout.addWidget(label)

        stats_layout.addStretch()

        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setEnabled(True)
        self.refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #2A2A2A;
                color: #E6E6E6;
                border: 1px solid #555555;
                border-radius: 3px;
                padding: 4px 8px;
                font-size: 10px;
            }
            QPushButton:hover:enabled {
                background-color: #3A3A3A;
                border: 1px solid #3A8DFF;
            }
        """)
        self.refresh_btn.clicked.connect(self.refresh_data)
        stats_layout.addWidget(self.refresh_btn)

        self.confirm_decision_btn = QPushButton("Confirm Decision Review")
        self.confirm_decision_btn.setEnabled(True)
        self.confirm_decision_btn.setStyleSheet("""
            QPushButton {
                background-color: #2A2A2A;
                color: #E6E6E6;
                border: 1px solid #555555;
                border-radius: 3px;
                padding: 4px 8px;
                font-size: 10px;
            }
            QPushButton:hover:enabled {
                background-color: #3A3A3A;
                border: 1px solid #3A8DFF;
            }
        """)
        self.confirm_decision_btn.clicked.connect(self.confirm_decision_review)
        stats_layout.addWidget(self.confirm_decision_btn)

        header_layout.addWidget(stats_widget)
        expanded_layout.addWidget(header_widget)

        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(8)

        matrix_group = QGroupBox("Gate Status Matrix")
        matrix_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 2px solid #0288d1;
                background-color: #1E1E1E;
                margin-top: 5px;
                padding-top: 8px;
                font-size: 11px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px 0 4px;
                color: #E6E6E6;
            }
        """)
        matrix_layout = QVBoxLayout()

        self.table_widget = QTableWidget()
        self.table_widget.setColumnCount(7)
        self.table_widget.setHorizontalHeaderLabels([
            "Job ID", "Gate Status", "Strategy", "Instrument", "Timeframe", "Actions", "Admission"
        ])
        self.table_widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table_widget.horizontalHeader().setStyleSheet("""
            QHeaderView::section {
                background-color: #2A2A2A;
                color: #E6E6E6;
                font-weight: bold;
                padding: 4px;
                border: none;
            }
        """)
        self.table_widget.setStyleSheet("""
            QTableWidget {
                background-color: #1E1E1E;
                color: #E6E6E6;
                border: none;
                gridline-color: #333333;
                font-size: 10px;
            }
            QTableWidget::item {
                padding: 4px;
                border-bottom: 1px solid #333333;
            }
            QTableWidget::item:selected {
                background-color: #3A3A3A;
                color: #E6E6E6;
            }
        """)
        self.table_widget.setAlternatingRowColors(True)
        self.table_widget.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_widget.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)

        matrix_layout.addWidget(self.table_widget)
        matrix_group.setLayout(matrix_layout)
        content_layout.addWidget(matrix_group, 70)

        self.table_widget.cellClicked.connect(self.on_table_cell_clicked)

        explain_group = QGroupBox("Explain Hub")
        explain_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 2px solid #7b1fa2;
                background-color: #1E1E1E;
                margin-top: 5px;
                padding-top: 8px;
                font-size: 11px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px 0 4px;
                color: #E6E6E6;
            }
        """)
        explain_layout = QVBoxLayout()

        # Create Explain Hub Tabs widget
        self.explain_hub_tabs = ExplainHubTabs()
        explain_layout.addWidget(self.explain_hub_tabs)
        
        # Connect action signals
        self.explain_hub_tabs.action_requested.connect(self._handle_explain_hub_action)
        
        explain_group.setLayout(explain_layout)
        content_layout.addWidget(explain_group, 30)

        details_group = QGroupBox("Job Details")
        details_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 2px solid #455A64;
                background-color: #1E1E1E;
                margin-top: 5px;
                padding-top: 8px;
                font-size: 11px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px 0 4px;
                color: #E6E6E6;
            }
        """)
        details_layout = QVBoxLayout()
        self.details_text = QTextEdit()
        self.details_text.setReadOnly(True)
        self.details_text.setStyleSheet("""
            QTextEdit {
                background-color: #121212;
                color: #E6E6E6;
                border: 1px solid #333333;
                font-family: monospace;
                font-size: 10px;
            }
        """)
        details_layout.addWidget(self.details_text)
        details_group.setLayout(details_layout)
        content_layout.addWidget(details_group, 20)

        expanded_layout.addWidget(content_widget)

        self.table_widget.itemSelectionChanged.connect(self.on_table_selection_changed)

        return expanded_widget
    
    def setup_refresh_timer(self):
        """Setup timer for automatic refresh."""
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.refresh_data)
        self.refresh_timer.start(30000)  # 30 seconds
    
    def refresh_data(self):
        """Refresh the dashboard data."""
        try:
            self.log_signal.emit("Refreshing gate summary dashboard...")
            
            # Fetch matrix data
            self.current_matrix = self.service.build_matrix()
            
            # Update stats
            self.update_stats()
            
            # Update table
            self.update_table()
            
            self.log_signal.emit(f"Dashboard refreshed: {self.current_matrix.summary_stats['total']} jobs")
            
        except Exception as e:
            logger.error(f"Failed to refresh dashboard: {e}")
            self.log_signal.emit(f"Error refreshing dashboard: {e}")
    
    def update_stats(self):
        """Update statistics labels."""
        if not self.current_matrix:
            return
        
        stats = self.current_matrix.summary_stats or {}
        total = self._safe_int(stats.get("total", 0))
        passed = self._safe_int(stats.get("pass", 0))
        warned = self._safe_int(stats.get("warn", 0))
        failed = self._safe_int(stats.get("fail", 0))
        unknown = self._safe_int(stats.get("unknown", 0))
        
        # Update labels with colors
        self.total_label.setText(f"Total: {total}")
        self.total_label.setStyleSheet("font-size: 11px; padding: 2px 6px; border-radius: 3px; background-color: #2A2A2A; color: #E6E6E6;")
        
        self.pass_label.setText(f"PASS: {passed}")
        self.pass_label.setStyleSheet("font-size: 11px; padding: 2px 6px; border-radius: 3px; background-color: #2E7D32; color: #E6E6E6;")
        
        self.warn_label.setText(f"WARN: {warned}")
        self.warn_label.setStyleSheet("font-size: 11px; padding: 2px 6px; border-radius: 3px; background-color: #F57C00; color: #E6E6E6;")
        
        self.fail_label.setText(f"FAIL: {failed}")
        self.fail_label.setStyleSheet("font-size: 11px; padding: 2px 6px; border-radius: 3px; background-color: #C62828; color: #E6E6E6;")
        
        self.unknown_label.setText(f"UNKNOWN: {unknown}")
        self.unknown_label.setStyleSheet("font-size: 11px; padding: 2px 6px; border-radius: 3px; background-color: #616161; color: #E6E6E6;")

        overall_status = "FAIL" if failed > 0 else "WARN" if warned > 0 else "PASS" if passed > 0 else "UNKNOWN"
        self.sticky_bar.set_overall_text(f"Overall: {overall_status}")
        self.sticky_bar.set_status_text(f"Jobs: {total}")

        if hasattr(self, "gate_drawer"):
            self.gate_drawer.set_summary_counts(
                fail=failed,
                warn=warned,
                ok=passed,
                total=total,
            )

    @staticmethod
    def _safe_int(value: Any) -> int:
        """Safely coerce a value to int for UI display."""
        try:
            return int(value)
        except Exception:
            return 0
    
    def update_table(self):
        """Update the table with job data."""
        if not self.current_matrix:
            self.table_widget.setRowCount(0)
            return
        
        jobs = self.current_matrix.jobs
        self.table_widget.setRowCount(len(jobs))
        
        for row, job_summary in enumerate(jobs):
            # Job ID
            job_id_item = QTableWidgetItem(job_summary.job_id[:12] + "..." if len(job_summary.job_id) > 12 else job_summary.job_id)
            job_id_item.setData(Qt.ItemDataRole.UserRole, job_summary.job_id)  # Store full ID
            self.table_widget.setItem(row, 0, job_id_item)
            
            # Gate Status
            status = job_summary.gate_summary.overall_status
            status_item = QTableWidgetItem(status.value)
            # Color coding
            if status == GateStatus.PASS:
                status_item.setForeground(Qt.GlobalColor.green)
            elif status == GateStatus.WARN:
                status_item.setForeground(Qt.GlobalColor.yellow)
            elif status == GateStatus.REJECT:
                status_item.setForeground(Qt.GlobalColor.red)
            else:
                status_item.setForeground(Qt.GlobalColor.gray)
            self.table_widget.setItem(row, 1, status_item)
            
            # Strategy
            job_data = job_summary.job_data
            strategy = job_data.get("strategy_id", job_data.get("strategy", "N/A"))
            strategy_item = QTableWidgetItem(strategy)
            self.table_widget.setItem(row, 2, strategy_item)
            
            # Instrument
            instrument = job_data.get("instrument", "N/A")
            instrument_item = QTableWidgetItem(instrument)
            self.table_widget.setItem(row, 3, instrument_item)
            
            # Timeframe
            timeframe = job_data.get("timeframe", "N/A")
            timeframe_item = QTableWidgetItem(timeframe)
            self.table_widget.setItem(row, 4, timeframe_item)
            
            # Actions (clickable links)
            actions_item = QTableWidgetItem("Gate Summary")
            actions_item.setForeground(Qt.GlobalColor.cyan)
            actions_item.setData(Qt.ItemDataRole.UserRole, "gate_summary")
            self.table_widget.setItem(row, 5, actions_item)
            
            # Admission (clickable link)
            admission_item = QTableWidgetItem("Admission")
            admission_item.setForeground(Qt.GlobalColor.cyan)
            admission_item.setData(Qt.ItemDataRole.UserRole, "admission")
            self.table_widget.setItem(row, 6, admission_item)
    
    def on_table_cell_clicked(self, row: int, column: int):
        """Handle table cell click for action columns."""
        if column not in [5, 6]:  # Actions or Admission columns
            return
        
        # Get job ID from first column
        job_id_item = self.table_widget.item(row, 0)
        if not job_id_item:
            return
        
        job_id = job_id_item.data(Qt.ItemDataRole.UserRole)
        if not job_id:
            job_id = job_id_item.text()
        self.last_selected_job_id = job_id
        
        # Handle based on column
        if column == 5:  # Actions (Gate Summary)
            self.action_router.handle_action(
                "gate_summary",
                context={"job_id": job_id}
            )
        elif column == 6:  # Admission
            self.action_router.handle_action(
                f"job_admission://{job_id}",
                context={"job_id": job_id}
            )

    def confirm_decision_review(self):
        """Confirm decision gate review for the selected job."""
        decision_gate_state.update_state(
            reviewed_job_id=self.last_selected_job_id,
            confirmed=True,
        )
        self.log_signal.emit("Decision gate review confirmed")
    
    def on_table_selection_changed(self):
        """Handle table selection change to update Explain Hub Tabs."""
        selected_items = self.table_widget.selectedItems()
        if not selected_items:
            self.explain_hub_tabs.clear()
            if hasattr(self, "details_text"):
                self.details_text.setText("")
            return
        
        # Get the selected row
        row = selected_items[0].row()
        
        # Get job ID from first column
        job_id_item = self.table_widget.item(row, 0)
        if not job_id_item:
            return
        
        job_id = job_id_item.data(Qt.ItemDataRole.UserRole)
        if not job_id:
            job_id = job_id_item.text()
        
        # Find job summary
        job_summary = None
        if self.current_matrix:
            for js in self.current_matrix.jobs:
                if js.job_id == job_id:
                    job_summary = js
                    break
        
        if not job_summary:
            self.explain_hub_tabs.clear()
            # Show error in Explain Hub
            self.explain_hub_tabs._show_error(f"Job {job_id} not found in current matrix")
            if hasattr(self, "details_text"):
                self.details_text.setText(f"Job {job_id} not found.")
            return
        
        # Update Explain Hub Tabs with job data
        self.explain_hub_tabs.update_for_job(job_id, job_summary)
        if hasattr(self, "details_text"):
            self.details_text.setText(self.build_job_details(job_summary))
    
    def build_job_details(self, job_summary: JobGateSummary) -> str:
        """Build detailed text for a job."""
        lines = []
        
        # Basic info
        lines.append(f"Job ID: {job_summary.job_id}")
        lines.append(f"Fetched at: {job_summary.fetched_at.isoformat()}")
        lines.append("")
        
        # Job data
        lines.append("=== Job Data ===")
        job_data = job_summary.job_data
        for key, value in job_data.items():
            if key not in ["_id", "created_at", "updated_at"]:  # Skip internal fields
                lines.append(f"  {key}: {value}")
        
        lines.append("")
        
        # Gate summary
        lines.append("=== Gate Summary ===")
        gate_summary = job_summary.gate_summary
        lines.append(f"Overall Status: {gate_summary.overall_status.value}")
        lines.append(f"Overall Message: {gate_summary.overall_message}")
        lines.append(f"Total Gates: {gate_summary.total_gates}")
        
        # Counts
        if gate_summary.counts:
            lines.append("Gate Counts:")
            for status, count in gate_summary.counts.items():
                lines.append(f"  {status}: {count}")
        
        lines.append("")
        
        # Individual gates (first 5)
        lines.append("=== Gates (first 5) ===")
        for i, gate in enumerate(gate_summary.gates[:5]):
            lines.append(f"{i+1}. {gate.gate_name} ({gate.gate_id})")
            lines.append(f"   Status: {gate.status.value}")
            lines.append(f"   Message: {gate.message}")
            if gate.reason_codes:
                lines.append(f"   Reason Codes: {', '.join(gate.reason_codes)}")
            lines.append("")
        
        if len(gate_summary.gates) > 5:
            lines.append(f"... and {len(gate_summary.gates) - 5} more gates")
        
        return "\n".join(lines)
    
    def _handle_explain_hub_action(self, target: str, context: Dict[str, Any]):
        """
        Handle action requests from ExplainHubTabs.
        
        Args:
            target: Action target string (e.g., "gate_explain://job123", "evidence://job123")
            context: Action context dictionary with job_id, source, etc.
        """
        logger.info(f"Handling ExplainHub action: {target} with context: {context}")
        self.log_signal.emit(f"Handling ExplainHub action: {target}")
        
        # Extract job_id from context or target
        job_id = context.get("job_id")
        if not job_id:
            # Try to extract from target pattern
            if "://" in target:
                job_id = target.split("://")[1]
        
        # Handle different action types
        if target.startswith("gate_explain://"):
            self._handle_gate_explain_action(job_id, context)
        elif target.startswith("evidence://"):
            self._handle_evidence_action(job_id, context)
        elif target.startswith("artifact://"):
            self._handle_artifact_action(job_id, context)
        elif target.startswith("internal://"):
            self._handle_internal_action(target, context)
        else:
            # Route through ActionRouterService for standard actions
            self._route_through_action_router(target, context)
    
    def _handle_gate_explain_action(self, job_id: str, context: Dict[str, Any]):
        """Handle gate explanation action."""
        logger.info(f"Opening gate explanation for job: {job_id}")
        
        # Find job summary
        job_summary = self._find_job_summary(job_id)
        if not job_summary:
            self.log_signal.emit(f"Job {job_id} not found for gate explanation")
            return
        
        # Get gate summary
        gate_summary = job_summary.gate_summary
        
        # Show gate explanation dialog
        try:
            # For now, show explanation for first gate
            # In future, could show a selection dialog or use specific gate from context
            if gate_summary.gates:
                # Use first gate for demonstration
                gate_result = gate_summary.gates[0]
                dialog = GateExplanationDialog(gate_result, parent=self)
                dialog.exec()
                self.log_signal.emit(f"Opened gate explanation for {gate_result.gate_name}")
            else:
                self.log_signal.emit(f"No gates found for job {job_id}")
        except Exception as e:
            logger.error(f"Failed to open gate explanation: {e}")
            self.log_signal.emit(f"Error opening gate explanation: {e}")
    
    def _handle_evidence_action(self, job_id: str, context: Dict[str, Any]):
        """Handle evidence viewer action."""
        logger.info(f"Opening evidence viewer for job: {job_id}")
        local_context = dict(context or {})
        local_context["local_only"] = True
        handled = self.action_router.handle_action(f"evidence://{job_id}", local_context)
        if not handled:
            self._open_evidence_dialog(job_id)

    def _open_evidence_dialog(self, job_id: str) -> None:
        """Open evidence browser dialog locally."""
        try:
            dialog = EvidenceBrowserDialog(job_id, parent=self)
            dialog.exec()
            self.log_signal.emit(f"Opened evidence browser for job {job_id}")
        except Exception as e:
            logger.error(f"Failed to open evidence browser: {e}")
            self.log_signal.emit(f"Error opening evidence browser: {e}")
    
    def _handle_artifact_action(self, job_id: str, context: Dict[str, Any]):
        """Handle artifact navigator action."""
        logger.info(f"Opening artifact navigator for job: {job_id}")
        self.log_signal.emit("Opening artifact navigator")
        
        # Route through ActionRouterService
        self._route_through_action_router(f"artifact://{job_id}", context)
    
    def _handle_internal_action(self, target: str, context: Dict[str, Any]):
        """Handle internal navigation action."""
        logger.info(f"Handling internal navigation: {target}")
        self.log_signal.emit("Handling internal navigation")
        
        # Route through ActionRouterService
        self._route_through_action_router(target, context)
    
    def _route_through_action_router(self, target: str, context: Dict[str, Any]):
        """Route action through ActionRouterService."""
        try:
            success = self.action_router.handle_action(target, context)
            if success:
                logger.info(f"ActionRouterService handled action: {target}")
                self.log_signal.emit(f"Action handled: {target}")
            else:
                logger.warning(f"ActionRouterService failed to handle action: {target}")
                self.log_signal.emit(f"Action failed: {target}")
        except Exception as e:
            logger.error(f"Error routing action {target}: {e}")
            self.log_signal.emit(f"Error routing action: {e}")
    
    def _find_job_summary(self, job_id: str) -> Optional[JobGateSummary]:
        """Find job summary by ID in current matrix."""
        if not self.current_matrix:
            return None
        
        for job_summary in self.current_matrix.jobs:
            if job_summary.job_id == job_id:
                return job_summary
        
        return None
    
    @Slot(str)
    def log(self, message: str):
        """Log a message."""
        self.log_signal.emit(message)