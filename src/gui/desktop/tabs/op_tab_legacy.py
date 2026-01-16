"""
OP (Operator Console) Tab - Phase C Professional CTA Desktop UI.

Implements Launch Pad + Job Tracker with actions wired to Supervisor API.
Layout: QSplitter horizontal with Launch Pad (left) and Job Tracker (right).
"""

# pylint: disable=no-name-in-module,c-extension-no-member

import logging
from typing import Optional, List, Dict, Any, cast, Protocol
from datetime import datetime
from PySide6.QtCore import (
    Qt, Signal, QTimer, QModelIndex, QAbstractTableModel, QAbstractItemModel,
    QUrl, QSize, QPersistentModelIndex, QEvent, QPoint, QRect
)  # pylint: disable=no-name-in-module
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QComboBox, QPushButton, QTableView, QSplitter,
    QGroupBox, QScrollArea, QSizePolicy,
    QStyledItemDelegate, QStyleOptionViewItem,
    QMessageBox, QSpacerItem, QLineEdit, QCheckBox,
    QTableWidget, QTableWidgetItem, QAbstractItemView
)  # pylint: disable=no-name-in-module
from PySide6.QtGui import QFont, QPainter, QBrush, QColor, QPen, QDesktopServices, QMouseEvent  # pylint: disable=no-name-in-module
from PySide6.QtWidgets import QToolTip

import json
from gui.desktop.widgets.log_viewer import LogViewerDialog
from gui.desktop.widgets.gate_summary_widget import GateSummaryWidget
from gui.desktop.widgets.explain_hub_widget import ExplainHubWidget
from gui.desktop.widgets.analysis_drawer_widget import AnalysisDrawerWidget
from gui.desktop.widgets.season_ssot_dialog import SeasonSSOTDialog
from gui.desktop.widgets.artifact_navigator import ArtifactNavigatorDialog, GateSummaryDialog
from gui.desktop.services.supervisor_client import (
    SupervisorClientError,
    get_registry_strategies, get_registry_instruments, get_registry_datasets,
    get_jobs, get_artifacts, get_strategy_report_v1,
    get_reveal_evidence_path, submit_job, get_wfs_policies
)
from ..state.active_run_state import active_run_state
from gui.services.timeframe_options import (
    get_timeframe_ids,
    get_default_timeframe,
    get_timeframe_registry
)
from gui.services.job_status_translator import translate_job_status
from gui.services.control_actions_gate import is_control_actions_enabled, is_abort_allowed, get_abort_button_tooltip, get_abort_attribution_summary
from gui.services.ui_action_evidence import write_abort_request_evidence, EvidenceWriteError, verify_evidence_write_possible
from gui.desktop.services.supervisor_client import abort_job
from gui.services.hybrid_bc_adapters import adapt_to_index, adapt_to_context, adapt_to_analysis
from gui.services.hybrid_bc_vms import JobIndexVM, JobContextVM, JobAnalysisVM
from gui.services.job_lifecycle_service import JobLifecycleService
from gui.services.dataset_resolver import DatasetResolver, DerivedDatasets, DatasetStatus

logger = logging.getLogger(__name__)


class _HasRect(Protocol):
    rect: QRect


class JobsTableModel(QAbstractTableModel):
    """Table model for displaying jobs from supervisor."""
    
    def __init__(self):
        super().__init__()
        self.all_jobs: List[Dict[str, Any]] = list()  # All jobs from API
        self.filtered_jobs: List[Dict[str, Any]] = list()  # Jobs after filtering
        self.headers = [
            "Job ID", "Strategy", "Instrument", "Timeframe",
            "Run Mode", "Season", "Status", "Created", "Finished", "Actions"
        ]
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self.refresh_data)
        self.refresh_interval = 5000  # 5 seconds default
        self.any_running = False
        
        # Filter criteria
        self.filter_status = "ALL"
        self.filter_strategy = "ALL"
        self.filter_instrument = "ALL"
        self.filter_season = "ALL"
        self.filter_search = ""
        
        # Lifecycle visibility
        self.lifecycle_service: Optional[JobLifecycleService] = None
        self.show_archived = False
    
    @property
    def jobs(self):
        """Backward-compatible property returning filtered_jobs."""
        return self.filtered_jobs
    
    def start_auto_refresh(self, interval: int = 5000):
        """Start automatic refresh timer."""
        self.refresh_interval = interval
        self.refresh_timer.start(self.refresh_interval)
    
    def stop_auto_refresh(self):
        """Stop automatic refresh timer."""
        self.refresh_timer.stop()
    
    def refresh_data(self):
        """Refresh job data from supervisor."""
        try:
            jobs = get_jobs(limit=50)
            self.set_jobs(jobs)
            
            # Check if any jobs are running
            self.any_running = any(
                job.get("status") in ["RUNNING", "PENDING", "STARTED"]
                for job in jobs
            )
            
        except SupervisorClientError as e:
            logger.error("Failed to refresh jobs: %s", e)
    
    def set_jobs(self, jobs: List[Dict[str, Any]]):
        """Set jobs data and update table."""
        self.beginResetModel()
        self.all_jobs = jobs
        self.apply_filters()
        self.endResetModel()
    
    def set_lifecycle_service(self, service: JobLifecycleService):
        """Set the lifecycle service for filtering archived/purged jobs."""
        self.lifecycle_service = service
    
    def set_show_archived(self, show: bool):
        """Set whether archived jobs should be shown."""
        if self.show_archived != show:
            self.show_archived = show
            self.beginResetModel()
            self.apply_filters()
            self.endResetModel()
    
    def apply_filters(self):
        """Apply current filters to all_jobs and update filtered_jobs."""
        self.filtered_jobs = list()
        
        # Get archived/purged job IDs if lifecycle service is available
        archived_ids = set()
        purged_ids = set()
        if self.lifecycle_service and not self.show_archived:
            archived_ids = set(self.lifecycle_service.get_job_ids_by_state("ARCHIVED"))
            purged_ids = set(self.lifecycle_service.get_job_ids_by_state("PURGED"))
        
        for job in self.all_jobs:
            job_id = job.get("job_id", "")
            
            # Lifecycle filter: exclude archived/purged jobs unless show_archived is True
            if not self.show_archived:
                if job_id in archived_ids or job_id in purged_ids:
                    continue
            
            # Status filter
            if self.filter_status != "ALL":
                job_status = job.get("status", "")
                if self.filter_status == "SUCCEEDED" and job_status != "SUCCEEDED":
                    continue
                elif self.filter_status == "RUNNING" and job_status != "RUNNING":
                    continue
                elif self.filter_status == "PENDING" and job_status != "PENDING":
                    continue
                elif self.filter_status == "FAILED" and job_status != "FAILED":
                    continue
                elif self.filter_status == "REJECTED" and job_status != "REJECTED":
                    continue
            
            # Strategy filter
            if self.filter_strategy != "ALL":
                job_strategy = job.get("strategy_name", job.get("strategy_id", ""))
                if job_strategy != self.filter_strategy:
                    continue
            
            # Instrument filter
            if self.filter_instrument != "ALL":
                job_instrument = job.get("instrument", "")
                if job_instrument != self.filter_instrument:
                    continue
            
            # Season filter
            if self.filter_season != "ALL":
                job_season = job.get("season", "")
                if job_season != self.filter_season:
                    continue
            
            # Text search
            if self.filter_search:
                search_lower = self.filter_search.lower()
                job_id_lower = job_id.lower()
                strategy = job.get("strategy_name", job.get("strategy_id", "")).lower()
                instrument = job.get("instrument", "").lower()
                if (search_lower not in job_id_lower and
                    search_lower not in strategy and
                    search_lower not in instrument):
                    continue
            
            self.filtered_jobs.append(job)
        
        # Check if any jobs are running (in filtered set)
        self.any_running = any(
            job.get("status") in ["RUNNING", "PENDING", "STARTED"]
            for job in self.filtered_jobs
        )
    
    def update_filter(self, status="ALL", strategy="ALL", instrument="ALL",
                     season="ALL", search=""):
        """Update filter criteria and reapply filters."""
        self.filter_status = status
        self.filter_strategy = strategy
        self.filter_instrument = instrument
        self.filter_season = season
        self.filter_search = search
        self.beginResetModel()
        self.apply_filters()
        self.endResetModel()
    
    def get_unique_values(self, field: str) -> List[str]:
        """Get unique values for a field from all_jobs."""
        values = set()
        for job in self.all_jobs:
            val = job.get(field)
            if val:
                values.add(str(val))
        return sorted(list(values))
    
    def rowCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:
        return len(self.filtered_jobs)
    
    def columnCount(self, parent: QModelIndex | QPersistentModelIndex = QModelIndex()) -> int:
        return len(self.headers)
    
    def data(self, index: QModelIndex | QPersistentModelIndex, role: int = int(Qt.ItemDataRole.DisplayRole)):
        if not index.isValid():
            return None
        
        row = index.row()
        col = index.column()
        
        if row >= len(self.filtered_jobs):
            return None
        
        job = self.filtered_jobs[row]
        
        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:  # Job ID
                job_id = job.get("job_id", "")
                return job_id[:8] + "..." if len(job_id) > 8 else job_id
            elif col == 1:  # Strategy
                return job.get("strategy_name", job.get("strategy_id", "Unknown"))
            elif col == 2:  # Instrument
                return job.get("instrument", "N/A")
            elif col == 3:  # Timeframe
                return job.get("timeframe", "N/A")
            elif col == 4:  # Run Mode
                run_mode = job.get("run_mode")
                if run_mode:
                    return run_mode.capitalize()
                return "N/A"
            elif col == 5:  # Season
                season = job.get("season")
                return season if season else "N/A"
            elif col == 6:  # Status
                status = job.get("status", "UNKNOWN")
                # Map SUCCEEDED to "Completed" for UI display only
                if status == "SUCCEEDED":
                    return "Completed"
                return status
            elif col == 7:  # Created (previously col 9)
                created = job.get("created_at", "")
                if created:
                    try:
                        dt = datetime.fromisoformat(created.replace('Z', '+00:00'))
                        return dt.strftime("%Y-%m-%d\n%H:%M:%S")
                    except (ValueError, AttributeError):
                        return created
                return ""
            elif col == 8:  # Finished (previously col 10)
                finished = job.get("finished_at", "")
                if finished:
                    try:
                        dt = datetime.fromisoformat(finished.replace('Z', '+00:00'))
                        return dt.strftime("%Y-%m-%d\n%H:%M:%S")
                    except (ValueError, AttributeError):
                        return finished
                return "—"
            elif col == 9:  # Actions column (previously col 11)
                return ""  # Actions column is handled by delegate
        
        elif role == Qt.ItemDataRole.TextAlignmentRole:
            if col in [7, 8]:  # Timestamps (Created, Finished)
                return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
            elif col == 9:  # Actions column
                return Qt.AlignmentFlag.AlignCenter
            else:
                return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        
        elif role == Qt.ItemDataRole.ForegroundRole:
            if col == 6:  # Status column
                status = job.get("status", "")
                # Phase E.1 color coding: amber for RUNNING, green for SUCCEEDED, red for FAILED/REJECTED
                if status == "SUCCEEDED":
                    return QColor("#4CAF50")  # green
                elif status in ["FAILED", "REJECTED"]:
                    return QColor("#F44336")  # red
                elif status == "RUNNING":
                    return QColor("#FF9800")  # amber
                elif status in ["PENDING", "STARTED"]:
                    return QColor("#FFC107")  # lighter amber
                else:
                    return QColor("#9A9A9A")  # gray
        
        elif role == Qt.ItemDataRole.FontRole:
            if col == 6:  # Status column
                font = QFont()
                font.setBold(True)
                return font
        
        elif role == Qt.ItemDataRole.ToolTipRole:
            if col == 6:  # Status column
                status = job.get("status", "")
                error_details = job.get("error_details")
                # Use translator to generate human-readable explanation
                explanation = translate_job_status(status, error_details)
                return explanation
        
        return None
    
    def headerData(self, section: int, orientation: Qt.Orientation, role: int = int(Qt.ItemDataRole.DisplayRole)):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            # Guard against missing headers attribute (should not happen, but defensive)
            if hasattr(self, 'headers') and section < len(self.headers):
                return self.headers[section]
        return None
    
    def get_job_at_row(self, row: int) -> Optional[Dict[str, Any]]:
        """Get job data at specified row."""
        if 0 <= row < len(self.filtered_jobs):
            return self.filtered_jobs[row]
        return None


class ActionsDelegate(QStyledItemDelegate):
    """Delegate for rendering action buttons in the Actions column."""
    
    button_clicked = Signal(int, str)  # row, action_type
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.hovered_row = -1
        self.hovered_button = -1
    
    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex):
        """Paint action buttons."""
        # Draw default background
        super().paint(painter, option, index)
        
        # Get job data
        model = index.model()
        if not isinstance(model, JobsTableModel):
            return
        
        job = model.get_job_at_row(index.row())
        if not job:
            return
        
        # Get artifacts to determine which buttons are enabled
        artifacts = job.get("artifacts", {})
        links = artifacts.get("links", {})
        status = job.get("status", "")
        
        # Button definitions
        # Check if abort is allowed for this job
        abort_allowed = is_abort_allowed(status)
        
        buttons = [
            ("logs", "View Logs", links.get("stdout_tail_url") is not None),
            ("evidence", "Open Evidence", job.get("status") not in ["PENDING", "CREATED"]),
            ("report", "Open Report", links.get("strategy_report_v1_url") is not None),
            ("explain", "Explain Failure", status in ["FAILED", "REJECTED", "ABORTED"]),
            ("artifacts", "Artifacts", True),
            ("abort", "Abort", abort_allowed)
        ]
        
        # Calculate button positions
        button_width = 70
        button_height = 24
        button_spacing = 4
        total_width = len(buttons) * button_width + (len(buttons) - 1) * button_spacing
        opt = cast(_HasRect, option)
        rect = opt.rect
        start_x = rect.left() + (rect.width() - total_width) // 2
        
        painter.save()
        
        for i, (action_type, text, enabled) in enumerate(buttons):
            button_rect = rect.adjusted(
                start_x + i * (button_width + button_spacing),
                (rect.height() - button_height) // 2,
                start_x + i * (button_width + button_spacing) - rect.width() + button_width,
                (rect.height() - button_height) // 2 - rect.height() + button_height
            )
            
            # Determine button style
            if not enabled:
                # Disabled button
                painter.setBrush(QBrush(QColor("#555555")))
                painter.setPen(QPen(QColor("#333333")))
                text_color = QColor("#888888")
            elif self.hovered_row == index.row() and self.hovered_button == i:
                # Hovered button
                painter.setBrush(QBrush(QColor("#3A8DFF")))
                painter.setPen(QPen(QColor("#2A7DFF")))
                text_color = QColor("#FFFFFF")
            else:
                # Normal button
                painter.setBrush(QBrush(QColor("#2A2A2A")))
                painter.setPen(QPen(QColor("#555555")))
                text_color = QColor("#E6E6E6")
            
            # Draw button
            painter.drawRoundedRect(button_rect, 4, 4)
            
            # Draw text
            painter.setPen(text_color)
            painter.setFont(QFont("Arial", 9))
            painter.drawText(button_rect, Qt.AlignmentFlag.AlignCenter, text)
        
        painter.restore()
    
    def editorEvent(self, event: QEvent, model: QAbstractItemModel, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex) -> bool:
        """Handle mouse events on buttons."""
        opt = cast(_HasRect, option)
        rect = opt.rect
        
        if event.type() == QEvent.Type.MouseButtonPress:
            # Get job data
            job_model = index.model()
            if not isinstance(job_model, JobsTableModel):
                return False
            
            job = job_model.get_job_at_row(index.row())
            if not job:
                return False
            
            # Get artifacts
            artifacts = job.get("artifacts", {})
            links = artifacts.get("links", {})
            status = job.get("status", "")
            
            # Button definitions
            abort_allowed = is_abort_allowed(status)
            buttons = [
                ("logs", links.get("stdout_tail_url") is not None),
                ("evidence", job.get("status") not in ["PENDING", "CREATED"]),
                ("report", links.get("strategy_report_v1_url") is not None),
                ("explain", status in ["FAILED", "REJECTED", "ABORTED"]),
                ("artifacts", True),
                ("abort", abort_allowed)
            ]
            
            # Calculate button positions
            button_width = 70
            button_height = 24
            button_spacing = 4
            total_width = len(buttons) * button_width + (len(buttons) - 1) * button_spacing
            start_x = rect.left() + (rect.width() - total_width) // 2
            
            # Check which button was clicked
            for i, (action_type, enabled) in enumerate(buttons):
                button_rect = rect.adjusted(
                    start_x + i * (button_width + button_spacing),
                    (rect.height() - button_height) // 2,
                    start_x + i * (button_width + button_spacing) - rect.width() + button_width,
                    (rect.height() - button_height) // 2 - rect.height() + button_height
                )
                
                # Qt6 correctness: use QMouseEvent.position().toPoint()
                if isinstance(event, QMouseEvent):
                    pos = event.position().toPoint()
                    if button_rect.contains(pos) and enabled:
                        self.button_clicked.emit(index.row(), action_type)
                        return True
        
        elif event.type() == QEvent.Type.MouseMove:
            # Update hover state
            self.hovered_row = index.row()
            
            # Get job data
            job_model = index.model()
            if not isinstance(job_model, JobsTableModel):
                return False
            
            job = job_model.get_job_at_row(index.row())
            if not job:
                return False
            
            # Get artifacts
            artifacts = job.get("artifacts", {})
            links = artifacts.get("links", {})
            status = job.get("status", "")
            
            # Button definitions
            abort_allowed = is_abort_allowed(status)
            buttons = [
                ("logs", links.get("stdout_tail_url") is not None),
                ("evidence", job.get("status") not in ["PENDING", "CREATED"]),
                ("report", links.get("strategy_report_v1_url") is not None),
                ("explain", status in ["FAILED", "REJECTED", "ABORTED"]),
                ("artifacts", True),
                ("abort", abort_allowed)
            ]
            
            # Calculate button positions
            button_width = 70
            button_height = 24
            button_spacing = 4
            total_width = len(buttons) * button_width + (len(buttons) - 1) * button_spacing
            start_x = rect.left() + (rect.width() - total_width) // 2
            
            # Check which button is hovered
            self.hovered_button = -1
            tooltip_text = ""
            for i, (action_type, enabled) in enumerate(buttons):
                button_rect = rect.adjusted(
                    start_x + i * (button_width + button_spacing),
                    (rect.height() - button_height) // 2,
                    start_x + i * (button_width + button_spacing) - rect.width() + button_width,
                    (rect.height() - button_height) // 2 - rect.height() + button_height
                )
                
                # Qt6 correctness: use QMouseEvent.position().toPoint()
                if isinstance(event, QMouseEvent):
                    pos = event.position().toPoint()
                    if button_rect.contains(pos) and enabled:
                        self.hovered_button = i
                        
                        # Generate tooltip for abort button
                        if action_type == "abort":
                            tooltip_text = get_abort_button_tooltip(is_enabled=True, job_status=status)
                        elif action_type == "logs":
                            tooltip_text = "View job logs (stdout/stderr)"
                        elif action_type == "evidence":
                            tooltip_text = "Open evidence directory for this job"
                        elif action_type == "report":
                            tooltip_text = "Open strategy report (HTML)"
                        elif action_type == "explain":
                            tooltip_text = "Explain job failure (error details)"
                        
                        # Show tooltip
                        if tooltip_text:
                            # Convert button_rect to global coordinates
                            global_pos = event.globalPosition().toPoint()
                            QToolTip.showText(global_pos, tooltip_text, self.parent())
                        break
            
            # Trigger repaint
            model.dataChanged.emit(index, index)
            return True
        
        return False
    
    def sizeHint(self, option: QStyleOptionViewItem, index: QModelIndex | QPersistentModelIndex) -> QSize:
        """Provide size hint for the actions column."""
        return QSize(425, 32)  # Now 5 buttons (80px each + spacing)


class OpTab(QWidget):
    """Operator Console tab - Phase C Professional CTA UI."""
    
    # Signals for communication with main window
    log_signal = Signal(str)
    switch_to_audit_tab = Signal(str)  # job_id for report
    progress_signal = Signal(int)  # progress updates
    artifact_state_changed = Signal(str, str, str)  # state, run_id, run_dir
    
    def __init__(self):
        super().__init__()
        self.jobs_model = JobsTableModel()
        self.actions_delegate = ActionsDelegate()
        self.explain_hub = ExplainHubWidget()
        self.analysis_drawer = AnalysisDrawerWidget(self)
        self.selected_job_id: Optional[str] = None
        self.selected_job_context: Optional[JobContextVM] = None
        self.job_lifecycle_service = JobLifecycleService()
        self.job_lifecycle_service.sync_index_with_filesystem()
        self.jobs_model.set_lifecycle_service(self.job_lifecycle_service)
        self.dataset_resolver = DatasetResolver()
        self.policy_preview_error: Optional[str] = None
        
        self.setup_ui()
        self.setup_connections()
        self.load_registry_data()
        self.start_auto_refresh()
    
    def setup_ui(self):
        """Initialize the UI components with QSplitter layout."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)
        
        # Gate Summary panel
        self.gate_summary_widget = GateSummaryWidget()
        main_layout.addWidget(self.gate_summary_widget)
        
        # Control Actions Status Indicator (D1)
        from gui.services.control_actions_gate import get_control_actions_indicator_text, get_control_actions_indicator_tooltip
        primary_label, secondary_text = get_control_actions_indicator_text()
        
        self.control_actions_indicator = QGroupBox("Control Actions Status")
        self.control_actions_indicator.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 2px solid #5d4037;
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
        
        indicator_layout = QVBoxLayout(self.control_actions_indicator)
        indicator_layout.setContentsMargins(12, 12, 12, 12)
        indicator_layout.setSpacing(4)
        
        self.control_actions_primary_label = QLabel(primary_label)
        self.control_actions_primary_label.setStyleSheet("font-weight: bold; font-size: 13px;")
        indicator_layout.addWidget(self.control_actions_primary_label)
        
        self.control_actions_secondary_label = QLabel(secondary_text)
        self.control_actions_secondary_label.setStyleSheet("color: #9e9e9e; font-size: 11px;")
        indicator_layout.addWidget(self.control_actions_secondary_label)
        
        # Set tooltip
        tooltip_text = get_control_actions_indicator_tooltip()
        self.control_actions_indicator.setToolTip(tooltip_text)
        self.control_actions_primary_label.setToolTip(tooltip_text)
        self.control_actions_secondary_label.setToolTip(tooltip_text)
        
        main_layout.addWidget(self.control_actions_indicator)

        # Create main splitter
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #555555;
                width: 1px;
            }
            QSplitter::handle:hover {
                background-color: #3A8DFF;
            }
        """)
        
        # Left panel: Launch Pad
        left_widget = QWidget()
        left_widget.setStyleSheet("background-color: #121212;")
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(4, 4, 4, 4)
        left_layout.setSpacing(8)
        
        # Launch Pad group
        launch_group = QGroupBox("Launch Pad")
        launch_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 2px solid #1a237e;
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
        
        # Scroll area for form
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: #1E1E1E;
            }
        """)
        
        form_widget = QWidget()
        form_layout = QFormLayout(form_widget)
        form_layout.setContentsMargins(12, 12, 12, 12)
        form_layout.setSpacing(10)
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        
        # Strategy family combobox
        self.strategy_cb = QComboBox()
        self.strategy_cb.setToolTip("Select strategy family from registry")
        form_layout.addRow("Strategy:", self.strategy_cb)
        
        # DATA1 combobox (instruments)
        self.instrument_cb = QComboBox()
        self.instrument_cb.setToolTip("Select primary instrument")
        form_layout.addRow("Instrument:", self.instrument_cb)
        
        # Derived Dataset Mapping (replaces manual dataset selection)
        self.dataset_mapping_label = QLabel("Mapped to: (select instrument/timeframe)")
        self.dataset_mapping_label.setStyleSheet("color: #9e9e9e; font-style: italic; font-size: 11px;")
        self.dataset_mapping_label.setWordWrap(True)
        self.dataset_mapping_label.setToolTip("Dataset is derived from instrument+timeframe+mode. Users do NOT manually select datasets.")
        form_layout.addRow("Dataset Mapping:", self.dataset_mapping_label)
        
        # Timeframe combobox
        self.timeframe_cb = QComboBox()
        try:
            self.timeframe_cb.addItems(get_timeframe_ids())
            self.timeframe_cb.setCurrentText(get_default_timeframe())
        except Exception as e:
            logger.error("Failed to load timeframes from registry: %s", e)
            # Fallback to registry directly (should not happen if registry is valid)
            try:
                registry = get_timeframe_registry()
                self.timeframe_cb.addItems(registry.get_display_names())
                self.timeframe_cb.setCurrentText(registry.get_display_name(registry.default))
            except Exception as e2:
                logger.error("Fallback also failed: %s", e2)
                # Last resort: empty combobox
                self.timeframe_cb.addItems(list())
        self.timeframe_cb.setToolTip("Select timeframe")
        form_layout.addRow("Timeframe:", self.timeframe_cb)
        
        # Run mode combobox
        self.run_mode_cb = QComboBox()
        self.run_mode_cb.addItems(["Backtest", "Research", "Optimize", "WFS"])
        self.run_mode_cb.setToolTip("Select run mode")
        form_layout.addRow("Mode:", self.run_mode_cb)

        self.policy_selector = QComboBox()
        self.policy_selector.addItem("Default", "default")
        self.policy_selector.addItem("Red Team", "red_team")
        self.policy_selector.setToolTip("Select WFS policy (applies when mode=WFS)")
        self.policy_selector.setEnabled(False)
        form_layout.addRow("WFS Policy:", self.policy_selector)

        self.policy_preview_group = QGroupBox("Policy Preview")
        self.policy_preview_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 2px solid #0d47a1;
                background-color: #121212;
                margin-top: 5px;
                padding-top: 8px;
                font-size: 11px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px 0 4px;
                color: #E6E6E6;
            }
        """)

        preview_layout = QVBoxLayout()
        preview_layout.setContentsMargins(8, 8, 8, 8)
        preview_layout.setSpacing(4)

        self.policy_preview_status = QLabel("Loading policy registry...")
        self.policy_preview_status.setStyleSheet("color: #9e9e9e; font-size: 10px;")
        preview_layout.addWidget(self.policy_preview_status)

        preview_form = QFormLayout()
        preview_form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        preview_form.setFormAlignment(Qt.AlignmentFlag.AlignLeft)

        self.policy_name_value = QLabel("Not available")
        self.policy_name_value.setStyleSheet("color: #E6E6E6; font-weight: bold;")
        preview_form.addRow("Name:", self.policy_name_value)

        self.policy_version_value = QLabel("Not available")
        preview_form.addRow("Version:", self.policy_version_value)

        self.policy_hash_value = QLabel("Not available")
        self.policy_hash_value.setWordWrap(True)
        preview_form.addRow("Hash:", self.policy_hash_value)

        self.policy_modes_value = QLabel("Not available")
        preview_form.addRow("Modes:", self.policy_modes_value)

        self.policy_description_value = QLabel("Not available")
        self.policy_description_value.setWordWrap(True)
        preview_form.addRow("Description:", self.policy_description_value)

        preview_layout.addLayout(preview_form)

        self.policy_gates_table = QTableWidget(2, 4)
        self.policy_gates_table.setHorizontalHeaderLabels(["Gate", "Metric", "Op", "Threshold"])
        self.policy_gates_table.verticalHeader().setVisible(False)
        self.policy_gates_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.policy_gates_table.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.policy_gates_table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.policy_gates_table.setMinimumHeight(120)
        preview_layout.addWidget(self.policy_gates_table)

        self.policy_diff_label = QLabel("Diff vs default: pending")
        self.policy_diff_label.setWordWrap(True)
        self.policy_diff_label.setStyleSheet("color: #9e9e9e; font-size: 11px;")
        preview_layout.addWidget(self.policy_diff_label)

        self.policy_preview_group.setLayout(preview_layout)
        form_layout.addRow(self.policy_preview_group)

        self.start_date_edit = QLineEdit()
        self.start_date_edit.setPlaceholderText("YYYY-MM-DD")
        self.start_date_edit.setToolTip("Required for Backtest/Research")
        form_layout.addRow("Start Date:", self.start_date_edit)

        self.end_date_edit = QLineEdit()
        self.end_date_edit.setPlaceholderText("YYYY-MM-DD")
        self.end_date_edit.setToolTip("Required for Backtest/Research")
        form_layout.addRow("End Date:", self.end_date_edit)

        self.research_run_id_edit = QLineEdit()
        self.research_run_id_edit.setPlaceholderText("Job ID (from a prior Research run)")
        self.research_run_id_edit.setToolTip("Required for Optimize")
        form_layout.addRow("Research Run ID:", self.research_run_id_edit)
        
        # Season/context combobox
        self.season_cb = QComboBox()
        self.season_cb.addItems(["2026Q1", "2026Q2", "2025Q4", "Custom"])
        self.season_cb.setToolTip("Select trading season/context")
        form_layout.addRow("Season:", self.season_cb)
        
        # Add stretch to push button to bottom
        form_layout.addItem(QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))
        
        # RUN STRATEGY button (big)
        self.run_button = QPushButton("RUN STRATEGY")
        self.run_button.setStyleSheet("""
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
        self.run_button.setMinimumHeight(50)
        form_layout.addRow(self.run_button)
        
        # Season SSOT Management button
        self.season_ssot_button = QPushButton("Manage Seasons (SSOT)")
        self.season_ssot_button.setStyleSheet("""
            QPushButton {
                background-color: #4a148c;
                color: white;
                font-weight: bold;
                font-size: 12px;
                padding: 8px;
                border-radius: 4px;
                border: 1px solid #6a1b9a;
            }
            QPushButton:hover {
                background-color: #6a1b9a;
                border: 1px solid #8e24aa;
            }
            QPushButton:pressed {
                background-color: #38006b;
            }
        """)
        self.season_ssot_button.setMinimumHeight(40)
        form_layout.addRow(self.season_ssot_button)
        
        # Set form widget to scroll area
        scroll.setWidget(form_widget)
        
        # Add scroll area to launch group
        launch_layout = QVBoxLayout(launch_group)
        launch_layout.addWidget(scroll)
        
        # Add launch group to left panel
        left_layout.addWidget(launch_group)
        
        # Right panel: Explain Hub (Hybrid BC Layer 2)
        right_widget = QWidget()
        right_widget.setStyleSheet("background-color: #121212;")
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(4, 4, 4, 4)
        right_layout.setSpacing(8)
        
        # Explain Hub group
        explain_group = QGroupBox("Explain Hub")
        explain_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 2px solid #1b5e20;
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
        
        # Filter controls layout (moved from Job Tracker to top of Explain Hub)
        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(8)
        
        # Status filter
        filter_layout.addWidget(QLabel("Status:"))
        self.status_filter = QComboBox()
        self.status_filter.addItems(["ALL", "PENDING", "RUNNING", "SUCCEEDED", "FAILED", "REJECTED"])
        self.status_filter.setCurrentText("ALL")
        self.status_filter.setMaximumWidth(120)
        filter_layout.addWidget(self.status_filter)
        
        # Strategy filter
        filter_layout.addWidget(QLabel("Strategy:"))
        self.strategy_filter = QComboBox()
        self.strategy_filter.addItem("ALL")
        self.strategy_filter.setMaximumWidth(150)
        filter_layout.addWidget(self.strategy_filter)
        
        # Instrument filter
        filter_layout.addWidget(QLabel("Instrument:"))
        self.instrument_filter = QComboBox()
        self.instrument_filter.addItem("ALL")
        self.instrument_filter.setMaximumWidth(120)
        filter_layout.addWidget(self.instrument_filter)
        
        # Season filter
        filter_layout.addWidget(QLabel("Season:"))
        self.season_filter = QComboBox()
        self.season_filter.addItem("ALL")
        self.season_filter.setMaximumWidth(100)
        filter_layout.addWidget(self.season_filter)
        
        # Text search
        filter_layout.addWidget(QLabel("Search:"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Job ID, strategy...")
        self.search_edit.setMaximumWidth(200)
        filter_layout.addWidget(self.search_edit)
        
        # Clear filters button
        self.clear_filters_btn = QPushButton("Clear Filters")
        self.clear_filters_btn.setMaximumWidth(100)
        filter_layout.addWidget(self.clear_filters_btn)
        
        # Show Archived checkbox
        self.show_archived_cb = QCheckBox("Show Archived")
        self.show_archived_cb.setToolTip("Show archived jobs (normally hidden)")
        self.show_archived_cb.setMaximumWidth(120)
        filter_layout.addWidget(self.show_archived_cb)
        
        filter_layout.addStretch()
        
        # Create table view (Job Index - Hybrid BC Layer 1)
        self.jobs_table = QTableView()
        self.jobs_table.setModel(self.jobs_model)
        self.jobs_table.setItemDelegateForColumn(9, self.actions_delegate)  # Actions column is now column 9
        self.jobs_table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.jobs_table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.jobs_table.setAlternatingRowColors(True)
        self.jobs_table.setStyleSheet("""
            QTableView {
                background-color: #1E1E1E;
                alternate-background-color: #252525;
                gridline-color: #333333;
                color: #E6E6E6;
                font-size: 11px;
            }
            QTableView::item {
                padding: 4px;
            }
            QTableView::item:selected {
                background-color: #2a2a2a;
                color: #FFFFFF;
            }
            QHeaderView::section {
                background-color: #2a2a2a;
                color: #E6E6E6;
                padding: 6px;
                border: 1px solid #333333;
                font-weight: bold;
            }
        """)
        
        # Configure column widths
        self.jobs_table.horizontalHeader().setStretchLastSection(False)
        self.jobs_table.setColumnWidth(0, 80)   # Job ID
        self.jobs_table.setColumnWidth(1, 120)  # Strategy
        self.jobs_table.setColumnWidth(2, 80)   # Instrument
        self.jobs_table.setColumnWidth(3, 70)   # Timeframe
        self.jobs_table.setColumnWidth(4, 80)   # Run Mode
        self.jobs_table.setColumnWidth(5, 80)   # Season
        self.jobs_table.setColumnWidth(6, 90)   # Status
        self.jobs_table.setColumnWidth(7, 120)  # Created
        self.jobs_table.setColumnWidth(8, 120)  # Finished
        self.jobs_table.setColumnWidth(9, 500)  # Actions (now includes artifacts button)
        
        # Add table and Explain Hub to explain group
        explain_layout = QVBoxLayout(explain_group)
        explain_layout.addLayout(filter_layout)
        explain_layout.addWidget(self.jobs_table)
        explain_layout.addWidget(self.explain_hub)
        
        # Add explain group to right panel
        right_layout.addWidget(explain_group)
        
        # Add panels to splitter
        main_splitter.addWidget(left_widget)
        main_splitter.addWidget(right_widget)
        main_splitter.setSizes([350, 650])  # 35% left, 65% right
        
        # Add splitter to main layout
        main_layout.addWidget(main_splitter)
        
        # Status label
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: #9e9e9e; font-size: 10px;")
        main_layout.addWidget(self.status_label)
    
    def setup_connections(self):
        """Connect signals and slots."""
        # Connect action delegate button clicks
        self.actions_delegate.button_clicked.connect(self.handle_action_click)
        
        # Connect RUN button
        self.run_button.clicked.connect(self.run_strategy)
        
        # Connect Season SSOT button
        self.season_ssot_button.clicked.connect(self.open_season_ssot_dialog)

        self.run_mode_cb.currentTextChanged.connect(self._apply_mode_field_visibility)
        self._apply_mode_field_visibility(self.run_mode_cb.currentText())
        self.policy_selector.currentIndexChanged.connect(lambda _: self._update_policy_preview())
        
        # Connect model refresh signal to update status and filter dropdowns
        self.jobs_model.dataChanged.connect(self.update_refresh_status)
        self.jobs_model.dataChanged.connect(self.update_filter_dropdowns)
        
        # Connect season combobox change for custom input
        self.season_cb.currentTextChanged.connect(self.handle_season_change)
        
        # Connect filter widgets
        self.status_filter.currentTextChanged.connect(self.apply_filters)
        self.strategy_filter.currentTextChanged.connect(self.apply_filters)
        self.instrument_filter.currentTextChanged.connect(self.apply_filters)
        self.season_filter.currentTextChanged.connect(self.apply_filters)
        self.search_edit.textChanged.connect(self.apply_filters)
        self.clear_filters_btn.clicked.connect(self.clear_filters)
        # Connect Show Archived checkbox
        self.show_archived_cb.stateChanged.connect(self.handle_show_archived_changed)
        
        # Connect job table selection to update Explain Hub (Hybrid BC Layer 1 → Layer 2)
        self.jobs_table.selectionModel().selectionChanged.connect(self.handle_job_selection)
        
        # Connect Explain Hub's open analysis signal
        self.explain_hub.request_open_analysis.connect(self.handle_open_analysis_request)
        
        # Connect Explain Hub's lifecycle signals
        self.explain_hub.request_archive.connect(self.handle_archive_request)
        self.explain_hub.request_restore.connect(self.handle_restore_request)
        self.explain_hub.request_purge.connect(self.handle_purge_request)
        
        # Disable double-click bypass (Hybrid BC governance)
        self.jobs_table.doubleClicked.connect(self.block_double_click)
        
        # Connect Analysis Drawer close signal
        self.analysis_drawer.drawer_closed.connect(self.handle_drawer_closed)
        
        # Connect combobox changes to update derived dataset mapping
        self.strategy_cb.currentTextChanged.connect(self.update_derived_dataset_mapping)
        self.instrument_cb.currentTextChanged.connect(self.update_derived_dataset_mapping)
        self.timeframe_cb.currentTextChanged.connect(self.update_derived_dataset_mapping)
        self.run_mode_cb.currentTextChanged.connect(self.update_derived_dataset_mapping)
        self.season_cb.currentTextChanged.connect(self.update_derived_dataset_mapping)
    
    def update_derived_dataset_mapping(self):
        """Update the derived dataset mapping label based on current selections."""
        try:
            # Get current selections
            strategy_idx = self.strategy_cb.currentIndex()
            strategy_id = self.strategy_cb.itemData(strategy_idx) if strategy_idx >= 0 else None
            instrument = self.instrument_cb.currentText()
            timeframe = self.timeframe_cb.currentText()
            run_mode = self.run_mode_cb.currentText().lower()
            season = self.season_cb.currentText()
            
            # Check if we have enough information to derive datasets
            if not strategy_id or not instrument or not timeframe:
                self.dataset_mapping_label.setText("Mapped to: (select instrument/timeframe)")
                return
            
            # Derive datasets using the resolver
            derived = self.dataset_resolver.resolve(
                strategy_id=strategy_id,
                instrument_id=instrument,
                timeframe_id=timeframe,
                mode=run_mode,
                season=season if season != "Custom" else None
            )
            
            # Format the display text
            lines = []
            
            # DATA1 mapping
            if derived.data1_id:
                data1_status = derived.data1_status.value
                status_color = {
                    "READY": "#4CAF50",
                    "MISSING": "#F44336",
                    "STALE": "#FF9800",
                    "UNKNOWN": "#9E9E9E"
                }.get(data1_status, "#9E9E9E")
                lines.append(f"<span style='color: {status_color}'>DATA1: {derived.data1_id} ({data1_status})</span>")
            else:
                lines.append("<span style='color: #9E9E9E'>DATA1: Not mapped</span>")
            
            # DATA2 mapping
            if derived.data2_id:
                data2_status = derived.data2_status.value
                status_color = {
                    "READY": "#4CAF50",
                    "MISSING": "#F44336",
                    "STALE": "#FF9800",
                    "UNKNOWN": "#9E9E9E"
                }.get(data2_status, "#9E9E9E")
                lines.append(f"<span style='color: {status_color}'>DATA2: {derived.data2_id} ({data2_status})</span>")
            else:
                lines.append("<span style='color: #9E9E9E'>DATA2: Not required or not mapped</span>")
            
            # Add mapping reason
            lines.append(f"<span style='color: #9e9e9e; font-size: 10px;'>{derived.mapping_reason}</span>")
            
            # Set the label text with HTML formatting
            self.dataset_mapping_label.setText("<br>".join(lines))
            
        except Exception as e:
            logger.error(f"Failed to update derived dataset mapping: {e}")
            self.dataset_mapping_label.setText(f"<span style='color: #F44336'>Error: {str(e)}</span>")
    
    def load_registry_data(self):
        """Load registry data from supervisor API."""
        try:
            # Load strategies
            strategies = get_registry_strategies()
            self.strategy_cb.clear()
            if isinstance(strategies, list):
                for strategy in strategies:
                    if isinstance(strategy, dict):
                        self.strategy_cb.addItem(strategy.get("name", "Unknown"), strategy.get("id"))
                    else:
                        self.strategy_cb.addItem(str(strategy))
            else:
                self.strategy_cb.addItem("No strategies available")
            
            # Load instruments
            instruments = get_registry_instruments()
            self.instrument_cb.clear()
            if isinstance(instruments, list):
                for instrument in instruments:
                    self.instrument_cb.addItem(instrument)
            else:
                self.instrument_cb.addItem("No instruments available")
            
            # Note: Dataset selection is now derived, not manually selected
            # We no longer load datasets into a combobox
            
            self.status_label.setText("Registry data loaded")
            
            # Trigger initial dataset mapping update
            self.update_derived_dataset_mapping()
            
            # Load policy registry for preview
            try:
                policies = get_wfs_policies()
                active_run_state.set_policy_registry(policies)
                self.policy_preview_error = None
            except SupervisorClientError as e:
                self.policy_preview_error = str(e)
                self.policy_preview_status.setText("Policy preview unavailable")
            self._update_policy_preview()
            
        except SupervisorClientError as e:
            self.status_label.setText(f"Failed to load registry: {e}")
            logger.error(f"Failed to load registry data: {e}")
    
    def update_filter_dropdowns(self):
        """Update filter dropdowns with unique values from jobs."""
        if not self.jobs_model.all_jobs:
            return
        
        # Save current selections
        current_strategy = self.strategy_filter.currentText()
        current_instrument = self.instrument_filter.currentText()
        current_season = self.season_filter.currentText()
        
        # Update strategy filter
        self.strategy_filter.clear()
        self.strategy_filter.addItem("ALL")
        strategies = self.jobs_model.get_unique_values("strategy_name")
        for strategy in strategies:
            self.strategy_filter.addItem(strategy)
        if current_strategy in strategies:
            self.strategy_filter.setCurrentText(current_strategy)
        
        # Update instrument filter
        self.instrument_filter.clear()
        self.instrument_filter.addItem("ALL")
        instruments = self.jobs_model.get_unique_values("instrument")
        for instrument in instruments:
            self.instrument_filter.addItem(instrument)
        if current_instrument in instruments:
            self.instrument_filter.setCurrentText(current_instrument)
        
        # Update season filter
        self.season_filter.clear()
        self.season_filter.addItem("ALL")
        seasons = self.jobs_model.get_unique_values("season")
        for season in seasons:
            self.season_filter.addItem(season)
        if current_season in seasons:
            self.season_filter.setCurrentText(current_season)
    
    def start_auto_refresh(self):
        """Start automatic refresh of job data."""
        self.jobs_model.start_auto_refresh()
        self.update_refresh_status()
    
    def update_refresh_status(self):
        """Update status label with refresh info."""
        if self.jobs_model.any_running:
            interval = 1000  # 1 second when jobs are running
            status = "Auto-refresh: 1s (jobs running)"
        else:
            interval = 5000  # 5 seconds otherwise
            status = "Auto-refresh: 5s"
        
        # Update model interval if changed
        if interval != self.jobs_model.refresh_interval:
            self.jobs_model.stop_auto_refresh()
            self.jobs_model.start_auto_refresh(interval)
        
        self.status_label.setText(f"{status} | {len(self.jobs_model.jobs)} jobs")
    
    def handle_season_change(self, text):
        """Handle season combobox change."""
        if text == "Custom":
            # TODO: Show custom season input dialog
            pass
    
    def apply_filters(self):
        """Apply filters from UI widgets to model."""
        status = self.status_filter.currentText()
        strategy = self.strategy_filter.currentText()
        instrument = self.instrument_filter.currentText()
        season = self.season_filter.currentText()
        search = self.search_edit.text().strip()
        
        self.jobs_model.update_filter(
            status=status,
            strategy=strategy,
            instrument=instrument,
            season=season,
            search=search
        )
    
    def clear_filters(self):
        """Clear all filters."""
        self.status_filter.setCurrentText("ALL")
        self.strategy_filter.setCurrentText("ALL")
        self.instrument_filter.setCurrentText("ALL")
        self.season_filter.setCurrentText("ALL")
        self.search_edit.clear()
        # apply_filters will be triggered by the signals
    
    def handle_show_archived_changed(self, state: int):
        """Handle Show Archived checkbox state change."""
        show = state == Qt.CheckState.Checked.value
        self.jobs_model.set_show_archived(show)
        # Update status label
        if show:
            self.status_label.setText("Showing archived jobs")
        else:
            self.status_label.setText("Hiding archived jobs")
    
    def run_strategy(self):
        """Submit a new strategy job with duplicate job warning guardrail."""
        # Get form values
        strategy_idx = self.strategy_cb.currentIndex()
        strategy_id = self.strategy_cb.itemData(strategy_idx) if strategy_idx >= 0 else None
        
        if not strategy_id:
            QMessageBox.warning(self, "No Strategy", "Please select a strategy from the registry.")
            return
        
        instrument = self.instrument_cb.currentText()
        timeframe = self.timeframe_cb.currentText()
        run_mode = self.run_mode_cb.currentText().lower()
        season = self.season_cb.currentText()

        start_date = self.start_date_edit.text().strip()
        end_date = self.end_date_edit.text().strip()
        research_run_id = self.research_run_id_edit.text().strip()

        if run_mode in {"backtest", "research"}:
            missing = list()
            if not start_date:
                missing.append("Start Date")
            if not end_date:
                missing.append("End Date")
            if missing:
                QMessageBox.warning(
                    self,
                    "Missing Required Fields",
                    "Required fields missing: " + ", ".join(missing),
                )
                self.status_label.setText("Job submission blocked (missing required fields)")
                return

        if run_mode == "optimize" and not research_run_id:
            QMessageBox.warning(
                self,
                "Missing Required Fields",
                "Optimize requires Research Run ID (job_id of a prior Research run).",
            )
            self.status_label.setText("Job submission blocked (missing research_run_id)")
            return

        if run_mode == "wfs":
            QMessageBox.information(
                self,
                "Not Supported",
                "WFS submission is blocked until UI supports start_season/end_season.",
            )
            self.status_label.setText("Job submission blocked (WFS not supported in UI)")
            return
        
        # Derive datasets using the resolver
        try:
            derived = self.dataset_resolver.resolve(
                strategy_id=strategy_id,
                instrument_id=instrument,
                timeframe_id=timeframe,
                mode=run_mode,
                season=season if season != "Custom" else None
            )
            
            # Check DATA2 gate status
            gate_status = self.dataset_resolver.evaluate_data2_gate(
                strategy_id=strategy_id,
                instrument_id=instrument,
                timeframe_id=timeframe,
                mode=run_mode,
                season=season if season != "Custom" else None
            )
            
            # If DATA2 gate is FAIL, show warning and block submission
            if gate_status.level == "FAIL":
                QMessageBox.warning(
                    self,
                    "DATA2 Gate Failed",
                    f"Cannot submit job: {gate_status.detail}\n\n"
                    f"DATA2 status: {derived.data2_status.value}\n"
                    f"Strategy requires DATA2: {self._get_strategy_requires_data2(strategy_id)}"
                )
                self.status_label.setText("Job submission blocked (DATA2 gate failed)")
                return
                
            # If DATA2 gate is WARNING, show confirmation dialog
            if gate_status.level == "WARNING":
                reply = QMessageBox.warning(
                    self,
                    "DATA2 Gate Warning",
                    f"DATA2 is stale: {gate_status.detail}\n\n"
                    f"DATA2 dataset: {derived.data2_id or 'None'}\n"
                    f"Status: {derived.data2_status.value}\n\n"
                    "Submit job anyway?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )
                if reply != QMessageBox.StandardButton.Yes:
                    self.status_label.setText("Job submission cancelled (DATA2 warning)")
                    return
            
        except Exception as e:
            logger.error(f"Failed to derive datasets or evaluate DATA2 gate: {e}")
            QMessageBox.warning(
                self,
                "Dataset Resolution Error",
                f"Failed to derive datasets: {e}\n\n"
                "Job submission may fail due to missing dataset mapping."
            )
            # Continue with submission but log the error
        
        # Prepare job parameters
        params = {
            "strategy_id": strategy_id,
            "instrument": instrument,
            "timeframe": timeframe,
            "run_mode": run_mode,
            "season": season,
        }
        if run_mode == "wfs":
            policy_value = self.policy_selector.currentData()
            if policy_value:
                params["wfs_policy"] = policy_value
        
        # Add derived datasets to parameters if available
        try:
            if derived and derived.data1_id:
                params["dataset"] = derived.data1_id  # Use DATA1 as primary dataset
                # Note: DATA2 is derived by backend based on strategy dependency
        except Exception:
            # If dataset derivation failed, proceed without dataset parameter
            # Backend will handle missing dataset appropriately
            pass

        if run_mode in {"backtest", "research"}:
            params["start_date"] = start_date
            params["end_date"] = end_date

        if run_mode == "optimize":
            params["research_run_id"] = research_run_id
        
        # Guardrail A: Duplicate job warning
        try:
            # Check for recent identical successful jobs
            recent_jobs = get_jobs(limit=50)
            duplicate_job = None
            
            for job in recent_jobs:
                # Check if job is identical (same strategy, instrument, timeframe, season, run_mode)
                job_strategy = job.get("strategy_id") or job.get("strategy_name", "")
                job_instrument = job.get("instrument", "")
                job_timeframe = job.get("timeframe", "")
                job_season = job.get("season", "")
                job_run_mode = job.get("run_mode", "")
                job_status = job.get("status", "")
                
                # Convert timeframe to string for comparison
                if isinstance(job_timeframe, int):
                    job_timeframe_str = f"{job_timeframe}m"
                else:
                    job_timeframe_str = str(job_timeframe)
                
                # Compare parameters
                if (job_strategy == strategy_id and
                    job_instrument == instrument and
                    job_timeframe_str == timeframe and
                    job_season == season and
                    job_run_mode == run_mode and
                    job_status in ["QUEUED", "RUNNING", "SUCCEEDED"]):
                    
                    duplicate_job = job
                    break
            
            if duplicate_job:
                duplicate_job_id = duplicate_job.get("job_id", "")
                duplicate_job_status = duplicate_job.get("status", "UNKNOWN")
                short_id = duplicate_job_id[:8] + "..." if len(duplicate_job_id) > 8 else duplicate_job_id
                
                # Show confirmation dialog
                reply = QMessageBox.question(
                    self,
                    "Duplicate Job Warning",
                    f"A similar job is already {duplicate_job_status.lower()} (job_id={short_id}).\n\n"
                    f"Strategy: {strategy_id}\n"
                    f"Instrument: {instrument}\n"
                    f"Timeframe: {timeframe}\n"
                    f"Season: {season}\n"
                    f"Mode: {run_mode}\n\n"
                    "Run again anyway?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No  # Default to No (Cancel)
                )
                
                if reply == QMessageBox.StandardButton.No:
                    self.status_label.setText("Job submission cancelled (duplicate warning)")
                    self.log_signal.emit("Job submission cancelled due to duplicate warning")
                    return
        
        except SupervisorClientError as e:
            # If we can't check for duplicates, log but continue
            logger.warning(f"Failed to check for duplicate jobs: {e}")
        
        try:
            # Submit job via supervisor API
            response = submit_job(params)
            # Extract job_id from response dict (API returns {"ok": True, "job_id": "..."})
            job_id = response.get("job_id") if isinstance(response, dict) else response
            self.status_label.setText(f"Job submitted: {job_id[:8]}...")
            self.log_signal.emit(f"Submitted job {job_id} for strategy {strategy_id}")
            
            # Refresh job list immediately
            self.jobs_model.refresh_data()
            
        except SupervisorClientError as e:
            QMessageBox.critical(self, "Job Submission Failed", f"Failed to submit job: {e}")
            logger.error(f"Job submission failed: {e}")
    
    def handle_action_click(self, row: int, action_type: str):
        """Handle action button clicks from the table."""
        job = self.jobs_model.get_job_at_row(row)
        if not job:
            return
        
        job_id = job.get("job_id")
        if not job_id:
            return
        
        if action_type == "logs":
            self.view_logs(job_id)
        elif action_type == "evidence":
            self.open_evidence(job_id)
        elif action_type == "report":
            self.open_report(job_id)
        elif action_type == "explain":
            self.explain_failure(job_id, job)
        elif action_type == "artifacts":
            self.open_artifact_navigator(job_id, job)
        elif action_type == "abort":
            self.handle_abort_request(job_id, job, row)
    
    def open_artifact_navigator(self, job_id: str, job: Dict[str, Any]) -> None:
        """Launch the artifact navigator dialog for a job."""
        dialog = ArtifactNavigatorDialog(job_id, parent=self)
        dialog.open_gate_summary.connect(self._show_gate_summary_dialog)
        dialog.open_explain.connect(lambda jid: self.explain_failure(jid, job))
        dialog.exec()

    def _show_gate_summary_dialog(self) -> None:
        GateSummaryDialog(self).exec()
    
    def view_logs(self, job_id: str):
        """Open log viewer dialog for a job."""
        try:
            dialog = LogViewerDialog(job_id=job_id, parent=self)
            dialog.exec()
        except Exception as e:
            QMessageBox.critical(self, "Log Viewer Error", f"Failed to open logs: {e}")
            logger.error(f"Failed to open log viewer for job {job_id}: {e}")
    
    def open_evidence(self, job_id: str):
        """Open evidence folder for a job."""
        try:
            path_data = get_reveal_evidence_path(job_id)
            path = path_data.get("path") if isinstance(path_data, dict) else None
            if path:
                QDesktopServices.openUrl(QUrl.fromLocalFile(path))
                self.log_signal.emit(f"Opened evidence folder: {path}")
            else:
                QMessageBox.information(self, "No Evidence", "No evidence folder available for this job.")
        except SupervisorClientError as e:
            QMessageBox.critical(self, "Evidence Error", f"Failed to open evidence: {e}")
            logger.error(f"Failed to open evidence for job {job_id}: {e}")
    
    def open_report(self, job_id: str):
        """Open strategy report in Audit tab."""
        try:
            # Fetch report to ensure it exists
            report = get_strategy_report_v1(job_id)
            if report:
                # Signal main window to switch to Audit tab and load report
                self.switch_to_audit_tab.emit(job_id)
                self.log_signal.emit(f"Opening report for job {job_id}")
            else:
                QMessageBox.information(self, "No Report", "No strategy report available for this job.")
        except SupervisorClientError as e:
            QMessageBox.critical(self, "Report Error", f"Failed to open report: {e}")
            logger.error(f"Failed to open report for job {job_id}: {e}")

    def _apply_mode_field_visibility(self, mode_text: str) -> None:
        mode = (mode_text or "").strip().lower()
        needs_dates = mode in {"backtest", "research"}
        needs_research_run_id = mode == "optimize"
        needs_policy = mode == "wfs"

        self.start_date_edit.setEnabled(needs_dates)
        self.end_date_edit.setEnabled(needs_dates)
        self.research_run_id_edit.setEnabled(needs_research_run_id)
        self.policy_selector.setEnabled(needs_policy)
        if not needs_policy:
            self.policy_selector.setCurrentIndex(0)

        if not needs_dates:
            self.start_date_edit.setText("")
            self.end_date_edit.setText("")
        if not needs_research_run_id:
            self.research_run_id_edit.setText("")

    def _update_policy_preview(self) -> None:
        if not hasattr(self, "policy_preview_status"):
            return

        registry = active_run_state.policy_registry
        if not registry:
            msg = "Policy preview unavailable"
            if self.policy_preview_error:
                msg = f"Policy preview unavailable: {self.policy_preview_error}"
            self.policy_preview_status.setText(msg)
            self._clear_policy_preview_fields()
            return

        selector = self.policy_selector.currentData() or "default"
        entry = active_run_state.get_policy_entry(selector)
        if entry is None:
            self.policy_preview_status.setText("Unknown policy selection")
            self._clear_policy_preview_fields()
            return

        self.policy_preview_status.setText("Policy preview loaded")
        self.policy_name_value.setText(entry.get("name", "Unknown"))
        self.policy_version_value.setText(entry.get("version", "Unknown"))
        self.policy_hash_value.setText(entry.get("hash", "Unknown"))
        modes = entry.get("modes", {})
        mode_text = (
            f"Mode B enabled: {modes.get('mode_b_enabled', False)}; "
            f"Scoring guards: {modes.get('scoring_guards_enabled', False)}"
        )
        self.policy_modes_value.setText(mode_text)
        self.policy_description_value.setText(entry.get("description", ""))
        self._populate_policy_gates(entry.get("gates", {}))

        diff_text = self._compute_policy_diff(entry, active_run_state.default_policy_entry())
        self.policy_diff_label.setText(diff_text)

    def _clear_policy_preview_fields(self) -> None:
        self.policy_name_value.setText("Not available")
        self.policy_version_value.setText("Not available")
        self.policy_hash_value.setText("Not available")
        self.policy_modes_value.setText("Not available")
        self.policy_description_value.setText("Not available")
        self.policy_gates_table.setRowCount(0)
        self.policy_diff_label.setText("Diff vs default: pending")

    def _populate_policy_gates(self, gates: Dict[str, Dict[str, object]]) -> None:
        keys = list(gates.keys())
        self.policy_gates_table.setRowCount(len(keys))
        for row, gate_name in enumerate(keys):
            gate = gates.get(gate_name, {})
            self.policy_gates_table.setItem(row, 0, QTableWidgetItem(gate_name.replace("_", " ").title()))
            self.policy_gates_table.setItem(row, 1, QTableWidgetItem(str(gate.get("metric", ""))))
            self.policy_gates_table.setItem(row, 2, QTableWidgetItem(str(gate.get("op", ""))))
            self.policy_gates_table.setItem(row, 3, QTableWidgetItem(str(gate.get("threshold", ""))))

    def _compute_policy_diff(self, entry: Dict[str, Any], default: Optional[Dict[str, Any]]) -> str:
        if not default or entry.get("selector") == "default":
            return "No differences vs default."

        diffs = []
        entry_modes = entry.get("modes", {})
        default_modes = default.get("modes", {})
        for key in ("mode_b_enabled", "scoring_guards_enabled"):
            entry_val = entry_modes.get(key)
            default_val = default_modes.get(key)
            if entry_val != default_val:
                diffs.append(f"{key}: {default_val} -> {entry_val}")

        entry_gates = entry.get("gates", {})
        default_gates = default.get("gates", {})
        for gate_name in ("edge_gate", "cliff_gate"):
            entry_gate = entry_gates.get(gate_name, {})
            default_gate = default_gates.get(gate_name, {})
            for field in ("metric", "op", "threshold"):
                entry_val = entry_gate.get(field)
                default_val = default_gate.get(field)
                if entry_val != default_val:
                    diffs.append(f"{gate_name}.{field}: {default_val} -> {entry_val}")

        if not diffs:
            return "No differences vs default."

        return "Diff vs default:\n" + "\n".join(diffs)

    def explain_failure(self, job_id: str, job: Optional[Dict[str, Any]] = None):
        """Explain failure for a failed/rejected/aborted job."""
        try:
            # Fetch artifacts
            artifacts = get_artifacts(job_id)
            if not artifacts:
                QMessageBox.information(self, "No Artifacts",
                    f"No artifacts available for job {job_id[:8]}...")
                return
            
            # Extract failure explanation from policy_check.json and runtime_metrics.json
            explanation = self._extract_failure_explanation(artifacts)
            
            # Build header with semantic translation
            status = job.get("status") if job else None
            error_details = job.get("error_details") if job else None
            semantic = translate_job_status(status, error_details)
            
            # Start with semantic summary
            lines = [f"=== JOB STATUS ===",
                     f"Status: {status or 'UNKNOWN'}",
                     f"Explanation: {semantic}",
                     ""]
            
            # Add abort attribution summary if job is ABORTED (D3)
            if status == "ABORTED":
                attribution = get_abort_attribution_summary(status, error_details)
                if attribution:
                    lines.append("=== ABORT ATTRIBUTION ===")
                    lines.append(attribution)
                    lines.append("")
            
            # Add original artifact explanation
            lines.append(explanation)
            
            # If job has error_details, include them as pretty JSON
            if error_details and isinstance(error_details, dict):
                lines.append("\n=== ERROR DETAILS (JSON) ===")
                try:
                    pretty_json = json.dumps(error_details, indent=2, ensure_ascii=False)
                    lines.append(pretty_json)
                except Exception as e:
                    lines.append(f"Failed to format JSON: {e}")
                    lines.append(str(error_details))
            
            full_explanation = "\n".join(lines)
            
            # Show explanation dialog
            from PySide6.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QPushButton, QLabel  # type: ignore
            dialog = QDialog(self)
            dialog.setWindowTitle(f"Failure Explanation - {job_id[:8]}...")
            dialog.setMinimumSize(500, 400)
            
            layout = QVBoxLayout(dialog)
            layout.addWidget(QLabel(f"Job: {job_id}"))
            
            text_edit = QTextEdit()
            text_edit.setReadOnly(True)
            text_edit.setPlainText(full_explanation)
            text_edit.setStyleSheet("""
                QTextEdit {
                    background-color: #1E1E1E;
                    color: #E6E6E6;
                    font-family: monospace;
                    font-size: 11px;
                }
            """)
            layout.addWidget(text_edit)
            
            close_btn = QPushButton("Close")
            close_btn.clicked.connect(dialog.accept)
            layout.addWidget(close_btn)
            
            dialog.exec()
            
        except SupervisorClientError as e:
            QMessageBox.critical(self, "Explain Failure Error",
                f"Failed to fetch artifacts: {e}")
            logger.error(f"Failed to explain failure for job {job_id}: {e}")
        except Exception as e:
            QMessageBox.critical(self, "Explain Failure Error",
                f"Unexpected error: {e}")
            logger.error(f"Unexpected error explaining failure for job {job_id}: {e}")

    def handle_abort_request(self, job_id: str, job: dict, row: int):
        """Handle abort request for a job with confirmation dialog and safety gates."""
        # Double-check that abort is allowed (should already be checked by button enabled state)
        status = job.get("status", "")
        if not is_abort_allowed(status):
            QMessageBox.warning(
                self,
                "Abort Not Allowed",
                f"Cannot abort job {job_id[:8]}... (status: {status}). "
                "Only QUEUED or RUNNING jobs can be aborted, and control actions must be enabled."
            )
            return
        
        # Show confirmation dialog per Product Contract
        reply = QMessageBox.question(
            self,
            "Abort job?",
            f"Abort job {job_id[:8]}...?\n\n"
            f"Status: {status}\n"
            f"Strategy: {job.get('strategy_name', job.get('strategy_id', 'Unknown'))}\n"
            f"Instrument: {job.get('instrument', 'N/A')}\n\n"
            "This will request the supervisor to stop the job. "
            "Any partial results will be preserved.",
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Ok,
            QMessageBox.StandardButton.Cancel  # Default to Cancel (safe)
        )
        
        if reply != QMessageBox.StandardButton.Ok:
            # User cancelled
            self.log_signal.emit(f"Abort cancelled for job {job_id}")
            return
        
        # Disable the abort button immediately to prevent double-submit
        # We'll trigger a repaint of the table row
        index = self.jobs_model.index(row, 11)  # Actions column
        self.jobs_table.viewport().update(index)
        
        # Show feedback
        self.status_label.setText(f"Abort requested for {job_id[:8]}...")
        self.log_signal.emit(f"Requesting abort for job {job_id}")
        
        try:
            # Write audit evidence first (if this fails, abort should be blocked)
            try:
                evidence_path = write_abort_request_evidence(job_id, reason="user_requested")
                self.log_signal.emit(f"Abort evidence written: {evidence_path}")
            except EvidenceWriteError as e:
                QMessageBox.critical(
                    self,
                    "Evidence Write Failed",
                    f"Cannot write audit evidence: {e}\n\n"
                    "Abort request blocked for safety. Please check outputs directory permissions."
                )
                self.log_signal.emit(f"Abort blocked - evidence write failed: {e}")
                # Re-enable button by triggering repaint
                self.jobs_table.viewport().update(index)
                return
            
            # Call abort API
            try:
                response = abort_job(job_id)
                self.log_signal.emit(f"Abort API called for job {job_id}: {response}")
                self.status_label.setText(f"Abort requested for {job_id[:8]}... (waiting)")
                
                # Schedule a refresh after a short delay to update status
                QTimer.singleShot(2000, self.jobs_model.refresh_data)
                
            except SupervisorClientError as e:
                QMessageBox.critical(
                    self,
                    "Abort Request Failed",
                    f"Failed to send abort request: {e}\n\n"
                    "The job may have already finished or the supervisor may be unavailable."
                )
                self.log_signal.emit(f"Abort API failed for job {job_id}: {e}")
                # Re-enable button by triggering repaint
                self.jobs_table.viewport().update(index)
                
        except Exception as e:
            # Catch any unexpected errors
            logger.error(f"Unexpected error during abort for job {job_id}: {e}")
            QMessageBox.critical(
                self,
                "Unexpected Error",
                f"An unexpected error occurred: {e}"
            )
            # Re-enable button by triggering repaint
            self.jobs_table.viewport().update(index)

    def _extract_failure_explanation(self, artifacts: dict) -> str:
        """Extract failure explanation from artifacts."""
        lines = list()
        
        # Check policy_check.json
        policy_check = artifacts.get("policy_check")
        if policy_check:
            lines.append("=== POLICY CHECK ===")
            if isinstance(policy_check, dict):
                status = policy_check.get("status")
                if status:
                    lines.append(f"Status: {status}")
                gates = policy_check.get("gates", list())
                for gate in gates:
                    gate_name = gate.get("name", "Unknown")
                    gate_status = gate.get("status", "UNKNOWN")
                    gate_reason = gate.get("reason", "")
                    lines.append(f"  • {gate_name}: {gate_status}")
                    if gate_reason:
                        lines.append(f"    Reason: {gate_reason}")
            else:
                lines.append(f"Raw: {policy_check}")
        
        # Check runtime_metrics.json
        runtime_metrics = artifacts.get("runtime_metrics")
        if runtime_metrics:
            lines.append("\n=== RUNTIME METRICS ===")
            if isinstance(runtime_metrics, dict):
                error = runtime_metrics.get("error")
                if error:
                    lines.append(f"Error: {error}")
                exit_code = runtime_metrics.get("exit_code")
                if exit_code is not None:
                    lines.append(f"Exit Code: {exit_code}")
                signal = runtime_metrics.get("signal")
                if signal:
                    lines.append(f"Signal: {signal}")
            else:
                lines.append(f"Raw: {runtime_metrics}")
        
        # If no specific failure info found, provide generic message
        if len(lines) == 0:
            lines.append("No detailed failure information available in artifacts.")
            lines.append("Check the job logs for more details.")
        
        return "\n".join(lines)
    
    def handle_job_selection(self, selected, deselected):
        """Handle job selection change (Hybrid BC Layer 1 → Layer 2)."""
        indexes = selected.indexes()
        if not indexes:
            # No selection, clear Explain Hub
            self.selected_job_id = None
            self.selected_job_context = None
            self.explain_hub.clear()
            # Auto-close drawer if open (Hybrid BC governance)
            self.analysis_drawer.close()
            return
        
        # Get the first selected row
        index = indexes[0]
        row = index.row()
        job = self.jobs_model.get_job_at_row(row)
        if not job:
            return
        
        job_id = job.get("job_id")
        if not job_id:
            return
        
        # Update selected job
        self.selected_job_id = job_id
        
        try:
            # Fetch artifacts for context
            artifacts = get_artifacts(job_id)
            if not artifacts:
                # No artifacts yet, create minimal context
                context_data = {
                    "job_id": job_id,
                    "status": job.get("status", ""),
                    "note": job.get("note", ""),
                    "artifacts": {},
                    "gatekeeper": {"total_permutations": 0, "valid_candidates": 0, "plateau_check": "N/A"}
                }
            else:
                context_data = {
                    "job_id": job_id,
                    "status": job.get("status", ""),
                    "note": job.get("note", ""),
                    "artifacts": artifacts,
                    "gatekeeper": artifacts.get("gatekeeper", {"total_permutations": 0, "valid_candidates": 0, "plateau_check": "N/A"})
                }
            
            # Adapt raw data to JobContextVM
            context_vm = adapt_to_context(context_data)
            self.selected_job_context = context_vm
            
            # Update Explain Hub
            self.explain_hub.set_context(context_vm)
            
            # Auto-close drawer if open (Hybrid BC governance)
            self.analysis_drawer.close()
            
        except SupervisorClientError as e:
            logger.error(f"Failed to fetch artifacts for job {job_id}: {e}")
            # Show error in Explain Hub
            self.explain_hub.show_error(f"Failed to load job context: {e}")
    
    def handle_open_analysis_request(self, job_id: str):
        """Handle request to open analysis drawer (Hybrid BC Layer 2 → Layer 3)."""
        # Re-check valid_candidates > 0 (safety gate)
        if not self.selected_job_context:
            logger.warning(f"No context for job {job_id}, cannot open analysis")
            return
        
        if self.selected_job_context.gatekeeper.get("valid_candidates", 0) <= 0:
            logger.warning(f"Job {job_id} has no valid candidates, analysis blocked")
            # Show tooltip or status message
            self.status_label.setText(f"Analysis blocked: no valid candidates for job {job_id[:8]}...")
            return
        
        # Open drawer
        self.analysis_drawer.open_for_job(job_id)
        
        # Lazy-load analysis content
        QTimer.singleShot(100, lambda: self.load_analysis_content(job_id))
    
    def load_analysis_content(self, job_id: str):
        """Lazy-load analysis content for the drawer."""
        try:
            # Fetch artifacts for analysis
            artifacts = get_artifacts(job_id)
            if not artifacts:
                self.analysis_drawer.show_error("No artifacts available for analysis")
                return
            
            # Adapt to JobAnalysisVM (metrics allowed here)
            analysis_vm = adapt_to_analysis({
                "job_id": job_id,
                "artifacts": artifacts
            })
            
            # Load report widgets into drawer
            self.analysis_drawer.load_analysis(analysis_vm)
            
        except SupervisorClientError as e:
            logger.error(f"Failed to load analysis for job {job_id}: {e}")
            self.analysis_drawer.show_error(f"Failed to load analysis: {e}")
    
    def handle_archive_request(self, job_id: str):
        """Handle archive request from Explain Hub."""
        if not job_id:
            return
        
        # Confirm with user
        reply = QMessageBox.question(
            self,
            "Archive Job",
            f"Archive job {job_id[:8]}...?\n\n"
            "The job directory will be moved to outputs/jobs/_trash/.\n"
            "Archived jobs are hidden from the job list but can be restored later.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        try:
            # Call service
            result = self.job_lifecycle_service.archive_job(job_id)
            self.log_signal.emit(f"Archived job {job_id}: {result}")
            self.status_label.setText(f"Archived job {job_id[:8]}...")
            
            # Refresh job list (archived jobs should be hidden)
            self.jobs_model.refresh_data()
            
            # Update Explain Hub context (if this job is still selected)
            if self.selected_job_id == job_id:
                # Update lifecycle state in context VM
                if self.selected_job_context:
                    self.selected_job_context.lifecycle_state = "ARCHIVED"
                    self.explain_hub.set_context(self.selected_job_context)
            
            # Show success message
            QMessageBox.information(
                self,
                "Job Archived",
                f"Job {job_id[:8]}... has been archived.\n"
                "It will no longer appear in the job list unless you show archived jobs."
            )
            
        except Exception as e:
            logger.error(f"Failed to archive job {job_id}: {e}")
            QMessageBox.critical(
                self,
                "Archive Failed",
                f"Failed to archive job: {e}"
            )
    
    def handle_restore_request(self, job_id: str):
        """Handle restore request from Explain Hub."""
        if not job_id:
            return
        
        # Confirm with user
        reply = QMessageBox.question(
            self,
            "Restore Job",
            f"Restore job {job_id[:8]}...?\n\n"
            "The job directory will be moved back to outputs/jobs/.\n"
            "The job will reappear in the job list.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        try:
            # Call service
            result = self.job_lifecycle_service.restore_job(job_id)
            self.log_signal.emit(f"Restored job {job_id}: {result}")
            self.status_label.setText(f"Restored job {job_id[:8]}...")
            
            # Refresh job list (restored job should appear)
            self.jobs_model.refresh_data()
            
            # Update Explain Hub context (if this job is still selected)
            if self.selected_job_id == job_id:
                # Update lifecycle state in context VM
                if self.selected_job_context:
                    self.selected_job_context.lifecycle_state = "ACTIVE"
                    self.explain_hub.set_context(self.selected_job_context)
            
            # Show success message
            QMessageBox.information(
                self,
                "Job Restored",
                f"Job {job_id[:8]}... has been restored.\n"
                "It will now appear in the job list."
            )
            
        except Exception as e:
            logger.error(f"Failed to restore job {job_id}: {e}")
            QMessageBox.critical(
                self,
                "Restore Failed",
                f"Failed to restore job: {e}"
            )
    
    def handle_purge_request(self, job_id: str):
        """Handle purge request from Explain Hub."""
        if not job_id:
            return
        
        # Check if purge is enabled via environment variable
        import os
        if os.environ.get("ENABLE_PURGE_ACTION", "0") != "1":
            QMessageBox.warning(
                self,
                "Purge Disabled",
                "Purge action is disabled. Set ENABLE_PURGE_ACTION=1 to enable."
            )
            return
        
        # Strong warning confirmation
        reply = QMessageBox.warning(
            self,
            "PURGE JOB (IRREVERSIBLE)",
            f"⚠️  PURGE JOB {job_id[:8]}... ⚠️\n\n"
            "This will PERMANENTLY DELETE the job directory and all its artifacts.\n"
            "This action cannot be undone.\n\n"
            "Are you absolutely sure?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        # Second confirmation
        reply2 = QMessageBox.warning(
            self,
            "Final Confirmation",
            f"Type the job ID '{job_id}' to confirm permanent deletion:",
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel
        )
        if reply2 != QMessageBox.StandardButton.Ok:
            return
        
        try:
            # Call service
            result = self.job_lifecycle_service.purge_job(job_id)
            self.log_signal.emit(f"Purged job {job_id}: {result}")
            self.status_label.setText(f"Purged job {job_id[:8]}...")
            
            # Refresh job list (purged job should be gone)
            self.jobs_model.refresh_data()
            
            # Clear selection if this job was selected
            if self.selected_job_id == job_id:
                self.selected_job_id = None
                self.selected_job_context = None
                self.explain_hub.clear()
            
            # Show success message
            QMessageBox.information(
                self,
                "Job Purged",
                f"Job {job_id[:8]}... has been permanently deleted."
            )
            
        except Exception as e:
            logger.error(f"Failed to purge job {job_id}: {e}")
            QMessageBox.critical(
                self,
                "Purge Failed",
                f"Failed to purge job: {e}"
            )
    
    def block_double_click(self, index):
        """Block double-click bypass (Hybrid BC governance)."""
        # Simply ignore the double-click event
        # Optionally show a tooltip or status message
        self.status_label.setText("Double-click disabled. Use Explain Hub's 'Open Analysis Drawer' button.")
        # You could also play a beep or show a brief notification
        return
    
    def open_season_ssot_dialog(self):
        """Open Season SSOT management dialog."""
        try:
            dialog = SeasonSSOTDialog(parent=self)
            dialog.exec()
            self.log_signal.emit("Season SSOT dialog opened")
        except Exception as e:
            QMessageBox.critical(self, "Season SSOT Error", f"Failed to open Season SSOT dialog: {e}")
            logger.error(f"Failed to open Season SSOT dialog: {e}")
    
    def handle_drawer_closed(self):
        """Handle drawer closed event."""
        # Update status
        self.status_label.setText("Analysis drawer closed")
    
    def cleanup(self):
        """Clean up resources."""
        self.jobs_model.stop_auto_refresh()
        self.analysis_drawer.close()
