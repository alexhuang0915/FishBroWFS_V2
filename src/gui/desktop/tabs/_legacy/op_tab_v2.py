"""
OP (Operator Console) Tab - Phase C Professional CTA Desktop UI with Route 2 Card-Based Launch Pad.

Implements Launch Pad + Job Tracker with actions wired to Supervisor API.
Layout: QSplitter horizontal with Launch Pad (left) and Job Tracker (right).

Route 2 Upgrade: Replaces dropdown-driven INPUT with card-based, explainable, data-aware workspace.
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
    QMessageBox, QSpacerItem, QLineEdit, QCheckBox
)  # pylint: disable=no-name-in-module
from PySide6.QtGui import QFont, QPainter, QBrush, QColor, QPen, QDesktopServices, QMouseEvent  # pylint: disable=no-name-in-module
from PySide6.QtWidgets import QToolTip

import json
from gui.desktop.widgets.log_viewer import LogViewerDialog
from gui.desktop.widgets.gate_summary_widget import GateSummaryWidget
from gui.desktop.widgets.explain_hub_widget import ExplainHubWidget
from gui.desktop.widgets.analysis_drawer_widget import AnalysisDrawerWidget
from gui.desktop.widgets.season_ssot_dialog import SeasonSSOTDialog

# Route 2 Card-Based Components
from gui.desktop.widgets.card_selectors import (
    StrategyCardDeck,
    TimeframeCardDeck,
    InstrumentCardList,
    ModePillCards,
    DerivedDatasetPanel,
    RunReadinessPanel
)

from gui.desktop.services.supervisor_client import (
    SupervisorClientError,
    get_registry_strategies, get_registry_instruments, get_registry_datasets,
    get_jobs, get_artifacts, get_strategy_report_v1,
    get_reveal_evidence_path, submit_job
)
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
            ("abort", "Abort", abort_allowed)
        ]
        
        # Calculate button positions
        button_width = 80
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
                painter.setBrush(Q