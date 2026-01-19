"""
Job Tracker Dialog - Read-only modal showing job tracking details.

This dialog shows job list, status, and details.
It's read-only and follows zero-silent UI principles.
"""

import logging
from typing import List, Dict, Any
from datetime import datetime

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QWidget,
    QLabel, QPushButton, QDialogButtonBox, QTextEdit,
    QGroupBox, QScrollArea, QFrame, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView
)

from gui.desktop.state.operation_state import JobTrackerSummary, operation_page_state
from gui.services.job_tracker import JobTracker
from gui.services.action_router_service import get_action_router_service

logger = logging.getLogger(__name__)


class JobTrackerDialog(QDialog):
    """Read-only dialog showing job tracking details."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self.job_tracker = JobTracker()
        self.current_summary: JobTrackerSummary = JobTrackerSummary()
        self.refresh_timer = QTimer()
        
        self.setup_ui()
        self.setup_refresh_timer()
        self.load_current_state()
    
    def setup_ui(self):
        """Initialize the UI with job tracking details."""
        self.setWindowTitle("Job Tracker Details")
        self.setMinimumSize(1000, 700)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)
        
        # Title
        title_label = QLabel("Job Tracker Details")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #E6E6E6;")
        main_layout.addWidget(title_label)
        
        # Description
        desc_label = QLabel(
            "This view shows job execution status and details. "
            "All job states are shown (zero-silent UI)."
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
        status_group = QGroupBox("Job Status Summary")
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
        
        status_layout = QHBoxLayout(status_group)
        
        # Create status widgets
        self.running_widget = self.create_status_counter("Running", "0", "#4CAF50")
        self.pending_widget = self.create_status_counter("Pending", "0", "#FFC107")
        self.completed_widget = self.create_status_counter("Completed", "0", "#2196F3")
        self.failed_widget = self.create_status_counter("Failed", "0", "#F44336")
        
        status_layout.addWidget(self.running_widget)
        status_layout.addWidget(self.pending_widget)
        status_layout.addWidget(self.completed_widget)
        status_layout.addWidget(self.failed_widget)
        status_layout.addStretch()
        
        content_layout.addWidget(status_group)
        
        # Job table group
        self.job_table_group = QGroupBox("Job List")
        self.job_table_group.setStyleSheet("""
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
        
        job_table_layout = QVBoxLayout(self.job_table_group)
        
        # Create job table
        self.job_table = QTableWidget()
        self.job_table.setColumnCount(6)
        self.job_table.setHorizontalHeaderLabels([
            "Job ID", "Status", "Strategy", "Instrument", "Timeframe", "Created"
        ])
        
        # Style the table
        self.job_table.setStyleSheet("""
            QTableWidget {
                background-color: #121212;
                color: #E6E6E6;
                border: 1px solid #555555;
                font-size: 11px;
            }
            QTableWidget::item {
                padding: 4px;
            }
            QHeaderView::section {
                background-color: #1E1E1E;
                color: #E6E6E6;
                font-weight: bold;
                padding: 4px;
                border: 1px solid #555555;
            }
        """)
        
        # Configure table behavior
        self.job_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.job_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.job_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.job_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.job_table.verticalHeader().setVisible(False)
        
        job_table_layout.addWidget(self.job_table)
        
        content_layout.addWidget(self.job_table_group)
        
        # Job details group
        self.job_details_group = QGroupBox("Job Details")
        self.job_details_group.setStyleSheet("""
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
        
        job_details_layout = QVBoxLayout(self.job_details_group)
        
        self.job_details_text = QTextEdit()
        self.job_details_text.setReadOnly(True)
        self.job_details_text.setStyleSheet("""
            QTextEdit {
                background-color: #121212;
                color: #E6E6E6;
                border: 1px solid #555555;
                font-family: monospace;
                font-size: 11px;
            }
        """)
        self.job_details_text.setMaximumHeight(200)
        job_details_layout.addWidget(self.job_details_text)
        
        content_layout.addWidget(self.job_details_group)
        
        # Action buttons frame
        action_frame = QFrame()
        action_frame.setStyleSheet("""
            QFrame {
                background-color: #1E1E1E;
                border: 1px solid #555555;
                border-radius: 4px;
            }
        """)
        
        action_layout = QHBoxLayout(action_frame)
        action_layout.setContentsMargins(12, 8, 12, 8)
        
        # Refresh button
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.setStyleSheet("""
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
        """)
        self.refresh_btn.clicked.connect(self.refresh_job_list)
        action_layout.addWidget(self.refresh_btn)
        
        # Cancel job button
        self.cancel_job_btn = QPushButton("Cancel Selected Job")
        self.cancel_job_btn.setStyleSheet("""
            QPushButton {
                background-color: #d32f2f;
                color: white;
                font-weight: bold;
                padding: 6px 12px;
                border-radius: 4px;
                border: 1px solid #b71c1c;
            }
            QPushButton:hover {
                background-color: #b71c1c;
            }
            QPushButton:disabled {
                background-color: #424242;
                color: #9e9e9e;
            }
        """)
        self.cancel_job_btn.clicked.connect(self.on_cancel_job)
        action_layout.addWidget(self.cancel_job_btn)
        
        # Clear completed button
        self.clear_completed_btn = QPushButton("Clear Completed Jobs")
        self.clear_completed_btn.setStyleSheet("""
            QPushButton {
                background-color: #616161;
                color: white;
                font-weight: bold;
                padding: 6px 12px;
                border-radius: 4px;
                border: 1px solid #424242;
            }
            QPushButton:hover {
                background-color: #424242;
            }
            QPushButton:disabled {
                background-color: #424242;
                color: #9e9e9e;
            }
        """)
        self.clear_completed_btn.clicked.connect(self.on_clear_completed)
        action_layout.addWidget(self.clear_completed_btn)
        
        action_layout.addStretch()
        
        content_layout.addWidget(action_frame)
        
        content_layout.addStretch()
        
        # Set content widget to scroll area
        scroll.setWidget(content_widget)
        main_layout.addWidget(scroll)
        
        # Dialog buttons
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        button_box.button(QDialogButtonBox.StandardButton.Close).setText("Close")
        button_box.rejected.connect(self.reject)
        
        main_layout.addWidget(button_box)
        
        # Connect table selection
        self.job_table.itemSelectionChanged.connect(self.on_job_selection_changed)
    
    def create_status_counter(self, label: str, count: str, color: str) -> QWidget:
        """Create a status counter widget."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 8, 12, 8)
        
        count_label = QLabel(count)
        count_label.setStyleSheet(f"""
            font-size: 24px;
            font-weight: bold;
            color: {color};
        """)
        count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(count_label)
        
        label_label = QLabel(label)
        label_label.setStyleSheet(f"""
            font-size: 12px;
            color: {color};
        """)
        label_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label_label)
        
        return widget
    
    def setup_refresh_timer(self):
        """Setup timer for automatic refresh."""
        self.refresh_timer.timeout.connect(self.refresh_job_list)
        self.refresh_timer.start(5000)  # Refresh every 5 seconds
    
    def load_current_state(self):
        """Load current operation state."""
        current_state = operation_page_state.get_state()
        self.current_summary = current_state.job_tracker
        
        # Update UI with current summary
        self.update_ui_from_state()
    
    def update_ui_from_state(self):
        """Update UI components to reflect current job tracker state."""
        # Update status counters
        self.update_status_counters()
        
        # Update job table
        self.update_job_table()
        
        # Update button states
        self.update_button_states()
    
    def update_status_counters(self):
        """Update status counter widgets."""
        # Get counts from current summary
        running_count = str(self.current_summary.running_jobs)
        pending_count = str(self.current_summary.pending_jobs)
        completed_count = str(self.current_summary.completed_jobs)
        failed_count = str(self.current_summary.failed_jobs)
        
        # Update count labels
        self.update_counter_widget(self.running_widget, running_count)
        self.update_counter_widget(self.pending_widget, pending_count)
        self.update_counter_widget(self.completed_widget, completed_count)
        self.update_counter_widget(self.failed_widget, failed_count)
    
    def update_counter_widget(self, widget: QWidget, count: str):
        """Update a counter widget's count."""
        layout = widget.layout()
        if layout and layout.count() > 0:
            count_label = layout.itemAt(0).widget()
            if isinstance(count_label, QLabel):
                count_label.setText(count)
    
    def update_job_table(self):
        """Update job table with current job list."""
        self.job_table.setRowCount(0)
        
        if not self.current_summary.job_list:
            return
        
        for i, job in enumerate(self.current_summary.job_list):
            self.job_table.insertRow(i)
            
            # Job ID
            job_id_item = QTableWidgetItem(job.get("job_id", "N/A"))
            job_id_item.setData(Qt.ItemDataRole.UserRole, job.get("job_id"))
            self.job_table.setItem(i, 0, job_id_item)
            
            # Status with color coding
            status = job.get("status", "UNKNOWN")
            status_item = QTableWidgetItem(status)
            status_color = self.get_status_color(status)
            status_item.setForeground(status_color)
            self.job_table.setItem(i, 1, status_item)
            
            # Strategy
            strategy_item = QTableWidgetItem(job.get("strategy_id", "N/A"))
            self.job_table.setItem(i, 2, strategy_item)
            
            # Instrument
            instrument_item = QTableWidgetItem(job.get("instrument_id", "N/A"))
            self.job_table.setItem(i, 3, instrument_item)
            
            # Timeframe
            timeframe_item = QTableWidgetItem(job.get("timeframe_id", "N/A"))
            self.job_table.setItem(i, 4, timeframe_item)
            
            # Created time
            created = job.get("created_at", "")
            if created:
                try:
                    # Try to format timestamp
                    if isinstance(created, (int, float)):
                        dt = datetime.fromtimestamp(created)
                        created_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                    else:
                        created_str = str(created)
                except:
                    created_str = str(created)
            else:
                created_str = "N/A"
            
            created_item = QTableWidgetItem(created_str)
            self.job_table.setItem(i, 5, created_item)
    
    def get_status_color(self, status: str):
        """Get color for job status."""
        from PySide6.QtGui import QColor
        
        status_lower = status.lower()
        if "running" in status_lower:
            return QColor("#4CAF50")  # Green
        elif "pending" in status_lower or "queued" in status_lower:
            return QColor("#FFC107")  # Yellow
        elif "completed" in status_lower or "success" in status_lower:
            return QColor("#2196F3")  # Blue
        elif "failed" in status_lower or "error" in status_lower:
            return QColor("#F44336")  # Red
        elif "cancelled" in status_lower or "canceled" in status_lower:
            return QColor("#9E9E9E")  # Gray
        else:
            return QColor("#E6E6E6")  # Default white
    
    def update_button_states(self):
        """Update button enabled states based on selection."""
        # Check if any job is selected
        selected_rows = self.job_table.selectionModel().selectedRows()
        has_selection = len(selected_rows) > 0
        
        # Check if selected job can be cancelled
        can_cancel = False
        if has_selection:
            row = selected_rows[0].row()
            status_item = self.job_table.item(row, 1)
            if status_item:
                status = status_item.text().lower()
                can_cancel = status in ["pending", "running", "queued"]
        
        self.cancel_job_btn.setEnabled(can_cancel)
        
        # Check if there are completed jobs to clear
        has_completed = self.current_summary.completed_jobs > 0
        self.clear_completed_btn.setEnabled(has_completed)
    
    def on_job_selection_changed(self):
        """Handle job selection change."""
        selected_rows = self.job_table.selectionModel().selectedRows()
        if not selected_rows:
            self.job_details_text.setText("No job selected.")
            self.update_button_states()
            return
        
        row = selected_rows[0].row()
        job_id_item = self.job_table.item(row, 0)
        if not job_id_item:
            self.job_details_text.setText("No job ID found.")
            return
        
        job_id = job_id_item.text()
        
        # Find job details
        job_details = None
        for job in self.current_summary.job_list:
            if job.get("job_id") == job_id:
                job_details = job
                break
        
        if not job_details:
            self.job_details_text.setText(f"Job {job_id} details not found.")
            return
        
        # Format job details
        details_text = self.format_job_details(job_details)
        self.job_details_text.setText(details_text)

        # Route job selection through ActionRouterService
        router = get_action_router_service()
        router.handle_action(f"internal://job/{job_id}")
        
        self.update_button_states()
    
    def format_job_details(self, job_details: Dict[str, Any]) -> str:
        """Format job details for display."""
        lines = []
        
        # Basic info
        lines.append(f"Job ID: {job_details.get('job_id', 'N/A')}")
        lines.append(f"Status: {job_details.get('status', 'UNKNOWN')}")
        lines.append(f"Strategy: {job_details.get('strategy_id', 'N/A')}")
        lines.append(f"Instrument: {job_details.get('instrument_id', 'N/A')}")
        lines.append(f"Timeframe: {job_details.get('timeframe_id', 'N/A')}")
        lines.append(f"Mode: {job_details.get('mode', 'N/A')}")
        
        # Timestamps
        created = job_details.get('created_at')
        if created:
            try:
                if isinstance(created, (int, float)):
                    dt = datetime.fromtimestamp(created)
                    created_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                else:
                    created_str = str(created)
                lines.append(f"Created: {created_str}")
            except:
                lines.append(f"Created: {created}")
        
        started = job_details.get('started_at')
        if started:
            try:
                if isinstance(started, (int, float)):
                    dt = datetime.fromtimestamp(started)
                    started_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                else:
                    started_str = str(started)
                lines.append(f"Started: {started_str}")
            except:
                lines.append(f"Started: {started}")
        
        completed = job_details.get('completed_at')
        if completed:
            try:
                if isinstance(completed, (int, float)):
                    dt = datetime.fromtimestamp(completed)
                    completed_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                else:
                    completed_str = str(completed)
                lines.append(f"Completed: {completed_str}")
            except:
                lines.append(f"Completed: {completed}")
        
        # Progress
        progress = job_details.get('progress')
        if progress is not None:
            lines.append(f"Progress: {progress}%")
        
        # Error info
        error = job_details.get('error')
        if error:
            lines.append(f"Error: {error}")
        
        # Additional metadata
        metadata = job_details.get('metadata', {})
        if metadata:
            lines.append("\nMetadata:")
            for key, value in metadata.items():
                lines.append(f"  {key}: {value}")
        
        return "\n".join(lines)
    
    def refresh_job_list(self):
        """Refresh job list from tracker."""
        try:
            # Get updated job list from tracker
            job_list = self.job_tracker.get_job_list()
            
            # Update current summary
            self.current_summary.job_list = job_list
            
            # Count statuses
            running = 0
            pending = 0
            completed = 0
            failed = 0
            
            for job in job_list:
                status = job.get('status', '').lower()
                if 'running' in status:
                    running += 1
                elif 'pending' in status or 'queued' in status:
                    pending += 1
                elif 'completed' in status or 'success' in status:
                    completed += 1
                elif 'failed' in status or 'error' in status:
                    failed += 1
            
            self.current_summary.running_jobs = running
            self.current_summary.pending_jobs = pending
            self.current_summary.completed_jobs = completed
            self.current_summary.failed_jobs = failed

            # Commit summary to SSOT on explicit refresh
            updated_summary = JobTrackerSummary(
                last_job_id=self.current_summary.last_job_id,
                last_job_status=self.current_summary.last_job_status,
                last_update_time=datetime.now(),
                total_jobs=len(job_list),
                running_jobs=running,
                pending_jobs=pending,
                completed_jobs=completed,
                failed_jobs=failed,
                job_list=job_list,
            )
            operation_page_state.update_state(job_tracker=updated_summary)
            
            # Update UI
            self.update_ui_from_state()
            
        except Exception as e:
            logger.error(f"Failed to refresh job list: {e}")
            self.job_details_text.setText(f"Failed to refresh job list: {e}")
    
    def on_cancel_job(self):
        """Handle cancel job button click."""
        selected_rows = self.job_table.selectionModel().selectedRows()
        if not selected_rows:
            return
        
        row = selected_rows[0].row()
        job_id_item = self.job_table.item(row, 0)
        if not job_id_item:
            return
        
        job_id = job_id_item.text()
        
        # Confirm cancellation
        from PySide6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self,
            "Confirm Cancellation",
            f"Are you sure you want to cancel job {job_id}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        try:
            # Cancel the job
            success = self.job_tracker.cancel_job(job_id)
            
            if success:
                # Refresh job list
                self.refresh_job_list()
                
                # Show success message
                QMessageBox.information(
                    self,
                    "Job Cancelled",
                    f"Job {job_id} has been cancelled."
                )
            else:
                QMessageBox.warning(
                    self,
                    "Cancellation Failed",
                    f"Failed to cancel job {job_id}."
                )
                
        except Exception as e:
            logger.error(f"Failed to cancel job {job_id}: {e}")
            QMessageBox.critical(
                self,
                "Cancellation Error",
                f"Error cancelling job {job_id}: {e}"
            )
    
    def on_clear_completed(self):
        """Handle clear completed jobs button click."""
        # Confirm clearing
        from PySide6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self,
            "Confirm Clear",
            "Are you sure you want to clear all completed jobs?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        
        if reply != QMessageBox.StandardButton.Yes:
            return
        
        try:
            # Clear completed jobs
            cleared_count = self.job_tracker.clear_completed_jobs()
            
            # Refresh job list
            self.refresh_job_list()
            
            # Show success message
            QMessageBox.information(
                self,
                "Jobs Cleared",
                f"Cleared {cleared_count} completed jobs."
            )
            
        except Exception as e:
            logger.error(f"Failed to clear completed jobs: {e}")
            QMessageBox.critical(
                self,
                "Clear Error",
                f"Error clearing completed jobs: {e}"
            )
    
    def closeEvent(self, event):
        """Handle dialog close event."""
        # Stop refresh timer
        self.refresh_timer.stop()
        super().closeEvent(event)