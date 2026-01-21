"""
Ops Tab - Centralized Job Monitor (SSOT Surface).
Matches GO AI Execution Spec Phase 3.
"""

import logging
from datetime import datetime
from PySide6.QtCore import Qt, Slot
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,    QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox, QLabel, 
    QLineEdit, QPushButton, QSplitter, QTextEdit, QComboBox,
    QAbstractItemView, QApplication, QMenu
)
from PySide6.QtGui import QAction, QKeyEvent
from ..state.job_store import job_store, JobRecord

logger = logging.getLogger(__name__)

class OpsTab(QWidget):
    """
    Ops / Jobs & Logs Tab.
    Provides the single surface for monitoring all observable UI jobs.
    """
    def __init__(self):
        super().__init__()
        self.setup_ui()
        self.setup_connections()
        self.refresh_job_list()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Title
        title = QLabel("SYSTEM OPERATIONS MONITOR")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #E6E6E6;")
        layout.addWidget(title)

        # Filters & Search Row
        filter_row = QHBoxLayout()
        filter_row.setSpacing(10)
        
        filter_row.addWidget(QLabel("Search:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Filter by ID, Type, or Summary...")
        self.search_input.setStyleSheet("background-color: #262626; color: #E6E6E6; padding: 4px;")
        filter_row.addWidget(self.search_input, 2)

        filter_row.addWidget(QLabel("Status:"))
        self.status_filter = QComboBox()
        self.status_filter.addItems(["All", "Queued", "Running", "Done", "Failed"])
        self.status_filter.setStyleSheet("background-color: #262626; color: #E6E6E6;")
        filter_row.addWidget(self.status_filter, 1)

        filter_row.addStretch(1)
        layout.addLayout(filter_row)

        # Main Splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setStyleSheet("""
            QSplitter::handle { background-color: #333333; width: 1px; }
            QSplitter::handle:hover { background-color: #3A8DFF; }
        """)

        # Left: Job List
        list_container = QGroupBox("Active & Historical Jobs")
        list_container.setStyleSheet("font-weight: bold; border: 1px solid #444444;")
        list_layout = QVBoxLayout(list_container)
        
        self.job_table = QTableWidget()
        self.job_table.setColumnCount(4)
        self.job_table.setHorizontalHeaderLabels(["ID", "Type", "Status", "Started At"])
        self.job_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.job_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.job_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.job_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.job_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.job_table.verticalHeader().setVisible(False)
        self.job_table.setStyleSheet("background-color: #121212; color: #E6E6E6; font-size: 11px;")
        
        list_layout.addWidget(self.job_table)
        splitter.addWidget(list_container)

        # Right: Detail & Logs
        detail_container = QGroupBox("Job Details")
        detail_container.setStyleSheet("font-weight: bold; border: 1px solid #444444;")
        detail_layout = QVBoxLayout(detail_container)
        detail_layout.setSpacing(10)

        # Fields
        self.id_field = self._add_field(detail_layout, "Job ID:", readonly=True, copy_btn=True)
        self.type_field = self._add_field(detail_layout, "Type:", readonly=True)
        self.status_label = QLabel("Status: —")
        self.status_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        detail_layout.addWidget(self.status_label)

        # Timeline
        self.timeline_label = QLabel("Timeline: —")
        self.timeline_label.setStyleSheet("color: #9A9A9A; font-size: 10px; font-family: monospace;")
        detail_layout.addWidget(self.timeline_label)

        self.progress_field = self._add_field(detail_layout, "Phase:", readonly=True)
        self.artifact_field = self._add_field(detail_layout, "Artifacts:", readonly=True, copy_btn=True)
        
        self.heartbeat_label = QLabel("Last Update: —")
        self.heartbeat_label.setStyleSheet("color: #777777; font-size: 10px;")
        detail_layout.addWidget(self.heartbeat_label)
        
        # Error Digest
        detail_layout.addWidget(QLabel("Error Digest / Summary:"))
        self.error_digest = QTextEdit()
        self.error_digest.setReadOnly(True)
        self.error_digest.setMaximumHeight(100)
        self.error_digest.setStyleSheet("background-color: #1A1A1A; color: #F44336; font-family: monospace;")
        detail_layout.addWidget(self.error_digest)

        detail_layout.addStretch()
        splitter.addWidget(detail_container)
        
        splitter.setSizes([400, 600])
        layout.addWidget(splitter)

    def _add_field(self, layout, label_text, readonly=False, copy_btn=False):
        row = QHBoxLayout()
        row.addWidget(QLabel(label_text), 1)
        edit = QLineEdit()
        edit.setReadOnly(readonly)
        edit.setStyleSheet("background-color: #262626; color: #E6E6E6;")
        row.addWidget(edit, 4)
        if copy_btn:
            btn = QPushButton("Copy")
            btn.setFixedWidth(50)
            btn.setStyleSheet("font-size: 10px; height: 20px;")
            btn.clicked.connect(lambda: QApplication.clipboard().setText(edit.text()))
            row.addWidget(btn)
        layout.addLayout(row)
        return edit

    def setup_connections(self):
        job_store.jobs_changed.connect(self.refresh_job_list)
        job_store.selected_changed.connect(self.focus_job)
        self.job_table.itemSelectionChanged.connect(self._on_selection_changed)
        self.job_table.customContextMenuRequested.connect(self._show_context_menu)
        self.search_input.textChanged.connect(self.refresh_job_list)
        self.status_filter.currentIndexChanged.connect(self.refresh_job_list)

    @Slot()
    def refresh_job_list(self):
        """Update the table from JobStore with filtering and search."""
        jobs = job_store.list_jobs()
        
        # Filtering
        status_filter = self.status_filter.currentText().lower()
        search_query = self.search_input.text().lower()
        
        filtered_jobs = []
        for job in jobs:
            if status_filter != "all" and job.status != status_filter:
                continue
            if search_query:
                match = (search_query in job.job_id.lower() or 
                         search_query in job.job_type.lower() or 
                         search_query in (job.summary or "").lower())
                if not match:
                    continue
            filtered_jobs.append(job)

        self.job_table.setRowCount(0)
        for row, job in enumerate(filtered_jobs):
            self.job_table.insertRow(row)
            self.job_table.setItem(row, 0, QTableWidgetItem(job.job_id))
            self.job_table.setItem(row, 1, QTableWidgetItem(job.job_type))
            self.job_table.setItem(row, 2, QTableWidgetItem(job.status))
            self.job_table.setItem(row, 3, QTableWidgetItem(job.created_at.strftime("%H:%M:%S")))
            
            # Highlight if selected
            current = job_store.get_selected()
            if current and current.job_id == job.job_id:
                self.job_table.selectRow(row)

    @Slot(str)
    def focus_job(self, job_id: str):
        """Update the detail view for a specific job with advanced UX."""
        job = next((j for j in job_store.list_jobs() if j.job_id == job_id), None)
        if not job:
            return

        self.id_field.setText(job.job_id)
        self.type_field.setText(job.job_type)
        self.status_label.setText(f"Status: {job.status.upper()}")
        self.progress_field.setText(job.progress_stage)
        self.artifact_field.setText(job.artifact_dir or "Pending...")
        self.error_digest.setPlainText(job.error_digest or job.summary or "No details.")

        # Heartbeat / Relative time
        now = datetime.now()
        delta = now - job.created_at
        self.heartbeat_label.setText(f"Started: {job.created_at.strftime('%H:%M:%S')} ({int(delta.total_seconds())}s ago)")

        # Timeline Visualization
        timeline = self._build_timeline(job.status)
        self.timeline_label.setText(f"Timeline: {timeline}")

        # Color coding status
        colors = {"queued": "#FFC107", "running": "#2196F3", "done": "#4CAF50", "failed": "#F44336"}
        self.status_label.setStyleSheet(f"font-weight: bold; color: {colors.get(job.status, '#9A9A9A')};")

    def _build_timeline(self, status: str) -> str:
        stages = ["Queued", "Running", "Complete"]
        if status == "failed":
            stages[2] = "FAILED"
            
        icons = []
        status_map = {
            "queued": 0,
            "running": 1,
            "done": 2,
            "failed": 2
        }
        current_idx = status_map.get(status, 0)
        
        for i, name in enumerate(stages):
            if i < current_idx:
                icons.append(f"● {name}")
            elif i == current_idx:
                icons.append(f"◎ {name}")
            else:
                icons.append(f"○ {name}")
        return " → ".join(icons)

    def _show_context_menu(self, position):
        menu = QMenu()
        copy_id = QAction("Copy Job ID", self)
        copy_id.triggered.connect(lambda: QApplication.clipboard().setText(self.id_field.text()))
        menu.addAction(copy_id)
        
        if self.artifact_field.text() != "Pending...":
            copy_art = QAction("Copy Artifact Dir", self)
            copy_art.triggered.connect(lambda: QApplication.clipboard().setText(self.artifact_field.text()))
            menu.addAction(copy_art)

        menu.addSeparator()

        copy_details = QAction("Copy Details (Summary)", self)
        details_text = f"Job: {self.id_field.text()} | {self.status_label.text()} | {self.timeline_label.text()}"
        copy_details.triggered.connect(lambda: QApplication.clipboard().setText(details_text))
        menu.addAction(copy_details)

        if self.error_digest.toPlainText():
            copy_error = QAction("Copy Error Digest", self)
            copy_error.triggered.connect(lambda: QApplication.clipboard().setText(self.error_digest.toPlainText()))
            menu.addAction(copy_error)

        menu.exec_(self.job_table.viewport().mapToGlobal(position))

    def keyPressEvent(self, event: QKeyEvent):
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_C:
            # Context-aware copy
            if self.job_table.hasFocus():
                selected = self.job_table.selectedItems()
                if selected:
                    QApplication.clipboard().setText(selected[0].text())
        super().keyPressEvent(event)

    def _on_selection_changed(self):
        selected = self.job_table.selectedItems()
        if selected:
            job_id = selected[0].text()
            job_store.set_selected(job_id)
