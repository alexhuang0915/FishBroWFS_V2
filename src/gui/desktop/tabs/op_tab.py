"""
OP (Operator Console) Tab - Phase C Professional CTA Desktop UI.

Implements Launch Pad + Job Tracker with actions wired to Supervisor API.
Layout: QSplitter horizontal with Launch Pad (left) and Job Tracker (right).
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime
import time

from PySide6.QtCore import Qt, Signal, Slot, QThread, QTimer, QModelIndex, QAbstractTableModel, QUrl, QSize
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout,
    QLabel, QComboBox, QPushButton, QTableView, QSplitter,
    QGroupBox, QScrollArea, QHeaderView, QSizePolicy,
    QStyledItemDelegate, QStyleOptionViewItem, QStyle,
    QApplication, QMessageBox, QSpacerItem, QLineEdit
)
from PySide6.QtGui import QFont, QPainter, QBrush, QColor, QAction, QPen, QDesktopServices

from ..widgets.log_viewer import LogViewerDialog
from ...services.supervisor_client import (
    get_client, SupervisorClientError,
    get_registry_strategies, get_registry_instruments, get_registry_datasets,
    get_jobs, get_job, get_artifacts, get_strategy_report_v1,
    get_stdout_tail, get_reveal_evidence_path, submit_job
)

logger = logging.getLogger(__name__)


class JobsTableModel(QAbstractTableModel):
    """Table model for displaying jobs from supervisor."""
    
    def __init__(self):
        super().__init__()
        self.all_jobs: List[Dict[str, Any]] = []  # All jobs from API
        self.filtered_jobs: List[Dict[str, Any]] = []  # Jobs after filtering
        self.headers = [
            "Job ID", "Strategy", "Instrument", "Timeframe",
            "Run Mode", "Season", "Status", "Duration", "Score",
            "Created", "Finished", "Actions"
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
            logger.error(f"Failed to refresh jobs: {e}")
    
    def set_jobs(self, jobs: List[Dict[str, Any]]):
        """Set jobs data and update table."""
        self.beginResetModel()
        self.all_jobs = jobs
        self.apply_filters()
        self.endResetModel()
    
    def apply_filters(self):
        """Apply current filters to all_jobs and update filtered_jobs."""
        self.filtered_jobs = []
        for job in self.all_jobs:
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
                job_id = job.get("job_id", "").lower()
                strategy = job.get("strategy_name", job.get("strategy_id", "")).lower()
                instrument = job.get("instrument", "").lower()
                if (search_lower not in job_id and
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
    
    def rowCount(self, parent=QModelIndex()):
        return len(self.filtered_jobs)
    
    def columnCount(self, parent=QModelIndex()):
        return len(self.headers)
    
    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        
        row = index.row()
        col = index.column()
        
        if row >= len(self.filtered_jobs):
            return None
        
        job = self.filtered_jobs[row]
        
        if role == Qt.DisplayRole:
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
            elif col == 7:  # Duration
                duration = job.get("duration_seconds")
                if duration is not None:
                    if duration < 60:
                        return f"{duration:.1f}s"
                    elif duration < 3600:
                        return f"{duration/60:.1f}m"
                    else:
                        return f"{duration/3600:.1f}h"
                return "—"
            elif col == 8:  # Score
                score = job.get("score")
                if score is not None:
                    return f"{score:.3f}"
                return "—"
            elif col == 9:  # Created
                created = job.get("created_at", "")
                if created:
                    try:
                        dt = datetime.fromisoformat(created.replace('Z', '+00:00'))
                        return dt.strftime("%Y-%m-%d\n%H:%M:%S")
                    except (ValueError, AttributeError):
                        return created
                return ""
            elif col == 10:  # Finished
                finished = job.get("finished_at", "")
                if finished:
                    try:
                        dt = datetime.fromisoformat(finished.replace('Z', '+00:00'))
                        return dt.strftime("%Y-%m-%d\n%H:%M:%S")
                    except (ValueError, AttributeError):
                        return finished
                return "—"
        
        elif role == Qt.TextAlignmentRole:
            if col in [9, 10]:  # Timestamps
                return Qt.AlignLeft | Qt.AlignTop
            elif col == 11:  # Actions column
                return Qt.AlignCenter
            elif col in [7, 8]:  # Duration, Score
                return Qt.AlignRight | Qt.AlignVCenter
            else:
                return Qt.AlignLeft | Qt.AlignVCenter
        
        elif role == Qt.ForegroundRole:
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
            elif col == 8:  # Score column
                score = job.get("score")
                if score is not None:
                    if score > 0:
                        return QColor("#4CAF50")  # green for positive
                    elif score < 0:
                        return QColor("#F44336")  # red for negative
                return None
        
        elif role == Qt.FontRole:
            if col == 6:  # Status column
                font = QFont()
                font.setBold(True)
                return font
        
        return None
    
    def headerData(self, section: int, orientation: Qt.Orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            if section < len(self.headers):
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
    
    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
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
        buttons = [
            ("logs", "View Logs", links.get("stdout_tail_url") is not None),
            ("evidence", "Open Evidence", job.get("status") not in ["PENDING", "CREATED"]),
            ("report", "Open Report", links.get("strategy_report_v1_url") is not None),
            ("explain", "Explain Failure", status in ["FAILED", "REJECTED"])
        ]
        
        # Calculate button positions
        button_width = 80
        button_height = 24
        button_spacing = 4
        total_width = len(buttons) * button_width + (len(buttons) - 1) * button_spacing
        start_x = option.rect.left() + (option.rect.width() - total_width) // 2
        
        painter.save()
        
        for i, (action_type, text, enabled) in enumerate(buttons):
            button_rect = option.rect.adjusted(
                start_x + i * (button_width + button_spacing),
                (option.rect.height() - button_height) // 2,
                start_x + i * (button_width + button_spacing) - option.rect.width() + button_width,
                (option.rect.height() - button_height) // 2 - option.rect.height() + button_height
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
            painter.drawText(button_rect, Qt.AlignCenter, text)
        
        painter.restore()
    
    def editorEvent(self, event, model, option, index):
        """Handle mouse events on buttons."""
        if event.type() == event.Type.MouseButtonPress:
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
            buttons = [
                ("logs", links.get("stdout_tail_url") is not None),
                ("evidence", job.get("status") not in ["PENDING", "CREATED"]),
                ("report", links.get("strategy_report_v1_url") is not None),
                ("explain", status in ["FAILED", "REJECTED"])
            ]
            
            # Calculate button positions
            button_width = 80
            button_height = 24
            button_spacing = 4
            total_width = len(buttons) * button_width + (len(buttons) - 1) * button_spacing
            start_x = option.rect.left() + (option.rect.width() - total_width) // 2
            
            # Check which button was clicked
            for i, (action_type, enabled) in enumerate(buttons):
                button_rect = option.rect.adjusted(
                    start_x + i * (button_width + button_spacing),
                    (option.rect.height() - button_height) // 2,
                    start_x + i * (button_width + button_spacing) - option.rect.width() + button_width,
                    (option.rect.height() - button_height) // 2 - option.rect.height() + button_height
                )
                
                if button_rect.contains(event.pos()) and enabled:
                    self.button_clicked.emit(index.row(), action_type)
                    return True
        
        elif event.type() == event.Type.MouseMove:
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
            buttons = [
                ("logs", links.get("stdout_tail_url") is not None),
                ("evidence", job.get("status") not in ["PENDING", "CREATED"]),
                ("report", links.get("strategy_report_v1_url") is not None),
                ("explain", status in ["FAILED", "REJECTED"])
            ]
            
            # Calculate button positions
            button_width = 80
            button_height = 24
            button_spacing = 4
            total_width = len(buttons) * button_width + (len(buttons) - 1) * button_spacing
            start_x = option.rect.left() + (option.rect.width() - total_width) // 2
            
            # Check which button is hovered
            self.hovered_button = -1
            for i, (_, enabled) in enumerate(buttons):
                button_rect = option.rect.adjusted(
                    start_x + i * (button_width + button_spacing),
                    (option.rect.height() - button_height) // 2,
                    start_x + i * (button_width + button_spacing) - option.rect.width() + button_width,
                    (option.rect.height() - button_height) // 2 - option.rect.height() + button_height
                )
                
                if button_rect.contains(event.pos()) and enabled:
                    self.hovered_button = i
                    break
            
            # Trigger repaint
            model.dataChanged.emit(index, index)
            return True
        
        return False
    
    def sizeHint(self, option, index):
        """Provide size hint for the actions column."""
        return QSize(340, 32)  # Wider for 4 buttons


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
        
        self.setup_ui()
        self.setup_connections()
        self.load_registry_data()
        self.start_auto_refresh()
    
    def setup_ui(self):
        """Initialize the UI components with QSplitter layout."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)
        
        # Create main splitter
        main_splitter = QSplitter(Qt.Horizontal)
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
        form_layout.setLabelAlignment(Qt.AlignRight)
        
        # Strategy family combobox
        self.strategy_cb = QComboBox()
        self.strategy_cb.setToolTip("Select strategy family from registry")
        form_layout.addRow("Strategy:", self.strategy_cb)
        
        # DATA1 combobox (instruments)
        self.instrument_cb = QComboBox()
        self.instrument_cb.setToolTip("Select primary instrument")
        form_layout.addRow("Instrument:", self.instrument_cb)
        
        # DATA2 combobox (datasets)
        self.dataset_cb = QComboBox()
        self.dataset_cb.setToolTip("Select dataset (optional)")
        form_layout.addRow("Dataset:", self.dataset_cb)
        
        # Timeframe combobox
        self.timeframe_cb = QComboBox()
        self.timeframe_cb.addItems(["15m", "30m", "60m", "120m", "240m", "1D"])
        self.timeframe_cb.setCurrentText("60m")
        self.timeframe_cb.setToolTip("Select timeframe")
        form_layout.addRow("Timeframe:", self.timeframe_cb)
        
        # Run mode combobox
        self.run_mode_cb = QComboBox()
        self.run_mode_cb.addItems(["Backtest", "Research", "Optimize", "WFS"])
        self.run_mode_cb.setToolTip("Select run mode")
        form_layout.addRow("Mode:", self.run_mode_cb)
        
        # Season/context combobox
        self.season_cb = QComboBox()
        self.season_cb.addItems(["2026Q1", "2026Q2", "2025Q4", "Custom"])
        self.season_cb.setToolTip("Select trading season/context")
        form_layout.addRow("Season:", self.season_cb)
        
        # Add stretch to push button to bottom
        form_layout.addItem(QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding))
        
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
        
        # Set form widget to scroll area
        scroll.setWidget(form_widget)
        
        # Add scroll area to launch group
        launch_layout = QVBoxLayout(launch_group)
        launch_layout.addWidget(scroll)
        
        # Add launch group to left panel
        left_layout.addWidget(launch_group)
        
        # Right panel: Job Tracker
        right_widget = QWidget()
        right_widget.setStyleSheet("background-color: #121212;")
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(4, 4, 4, 4)
        right_layout.setSpacing(8)
        
        # Job Tracker group
        tracker_group = QGroupBox("Job Tracker")
        tracker_group.setStyleSheet("""
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
        
        # Filter controls layout
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
        
        filter_layout.addStretch()
        
        # Create table view
        self.jobs_table = QTableView()
        self.jobs_table.setModel(self.jobs_model)
        self.jobs_table.setItemDelegateForColumn(11, self.actions_delegate)
        self.jobs_table.setSelectionBehavior(QTableView.SelectRows)
        self.jobs_table.setSelectionMode(QTableView.SingleSelection)
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
        self.jobs_table.setColumnWidth(7, 80)   # Duration
        self.jobs_table.setColumnWidth(8, 70)   # Score
        self.jobs_table.setColumnWidth(9, 120)  # Created
        self.jobs_table.setColumnWidth(10, 120) # Finished
        self.jobs_table.setColumnWidth(11, 320) # Actions (wider for 4 buttons)
        
        # Add table to tracker group
        tracker_layout = QVBoxLayout(tracker_group)
        tracker_layout.addLayout(filter_layout)
        tracker_layout.addWidget(self.jobs_table)
        
        # Add tracker group to right panel
        right_layout.addWidget(tracker_group)
        
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
            
            # Load datasets
            datasets = get_registry_datasets()
            self.dataset_cb.clear()
            self.dataset_cb.addItem("None")
            if isinstance(datasets, list):
                for dataset in datasets:
                    self.dataset_cb.addItem(dataset)
            
            self.status_label.setText("Registry data loaded")
            
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
    
    def run_strategy(self):
        """Submit a new strategy job with duplicate job warning guardrail."""
        # Get form values
        strategy_idx = self.strategy_cb.currentIndex()
        strategy_id = self.strategy_cb.itemData(strategy_idx) if strategy_idx >= 0 else None
        
        if not strategy_id:
            QMessageBox.warning(self, "No Strategy", "Please select a strategy from the registry.")
            return
        
        instrument = self.instrument_cb.currentText()
        dataset = self.dataset_cb.currentText() if self.dataset_cb.currentText() != "None" else None
        timeframe = self.timeframe_cb.currentText()
        run_mode = self.run_mode_cb.currentText().lower()
        season = self.season_cb.currentText()
        
        # Prepare job parameters
        params = {
            "strategy_id": strategy_id,
            "instrument": instrument,
            "timeframe": timeframe,
            "run_mode": run_mode,
            "season": season,
        }
        
        if dataset:
            params["dataset"] = dataset
        
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
                    job_status == "SUCCEEDED"):
                    
                    duplicate_job = job
                    break
            
            if duplicate_job:
                duplicate_job_id = duplicate_job.get("job_id", "")
                short_id = duplicate_job_id[:8] + "..." if len(duplicate_job_id) > 8 else duplicate_job_id
                
                # Show confirmation dialog
                reply = QMessageBox.question(
                    self,
                    "Duplicate Job Warning",
                    f"A similar job succeeded recently (job_id={short_id}).\n\n"
                    f"Strategy: {strategy_id}\n"
                    f"Instrument: {instrument}\n"
                    f"Timeframe: {timeframe}\n"
                    f"Season: {season}\n"
                    f"Mode: {run_mode}\n\n"
                    "Run again anyway?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No  # Default to No (Cancel)
                )
                
                if reply == QMessageBox.No:
                    self.status_label.setText("Job submission cancelled (duplicate warning)")
                    self.log_signal.emit("Job submission cancelled due to duplicate warning")
                    return
        
        except SupervisorClientError as e:
            # If we can't check for duplicates, log but continue
            logger.warning(f"Failed to check for duplicate jobs: {e}")
        
        try:
            # Submit job via supervisor API
            job_id = submit_job(params)
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
            self.explain_failure(job_id)
    
    def view_logs(self, job_id: str):
        """Open log viewer dialog for a job."""
        try:
            dialog = LogViewerDialog(job_id, self)
            dialog.exec()
        except Exception as e:
            QMessageBox.critical(self, "Log Viewer Error", f"Failed to open logs: {e}")
            logger.error(f"Failed to open log viewer for job {job_id}: {e}")
    
    def open_evidence(self, job_id: str):
        """Open evidence folder for a job."""
        try:
            path = get_reveal_evidence_path(job_id)
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
            QMessageBox.critical(self, "Report Error", f"Failed to fetch report: {e}")
            logger.error(f"Failed to fetch report for job {job_id}: {e}")

    def explain_failure(self, job_id: str):
        """Explain failure for a failed/rejected job."""
        try:
            # Fetch artifacts
            artifacts = get_artifacts(job_id)
            if not artifacts:
                QMessageBox.information(self, "No Artifacts",
                    f"No artifacts available for job {job_id[:8]}...")
                return
            
            # Extract failure explanation from policy_check.json and runtime_metrics.json
            explanation = self._extract_failure_explanation(artifacts)
            
            # Show explanation dialog
            from PySide6.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QPushButton, QLabel
            dialog = QDialog(self)
            dialog.setWindowTitle(f"Failure Explanation - {job_id[:8]}...")
            dialog.setMinimumSize(500, 400)
            
            layout = QVBoxLayout(dialog)
            layout.addWidget(QLabel(f"Job: {job_id}"))
            
            text_edit = QTextEdit()
            text_edit.setReadOnly(True)
            text_edit.setPlainText(explanation)
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

    def _extract_failure_explanation(self, artifacts: dict) -> str:
        """Extract failure explanation from artifacts."""
        lines = []
        
        # Check policy_check.json
        policy_check = artifacts.get("policy_check")
        if policy_check:
            lines.append("=== POLICY CHECK ===")
            if isinstance(policy_check, dict):
                status = policy_check.get("status")
                if status:
                    lines.append(f"Status: {status}")
                gates = policy_check.get("gates", [])
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
    
    def cleanup(self):
        """Clean up resources."""
        self.jobs_model.stop_auto_refresh()
