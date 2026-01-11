"""
Log Viewer Dialog for displaying stdout tail from supervisor jobs.
"""

import logging
from typing import Optional

from PySide6.QtCore import Qt, Signal, Slot  # type: ignore
from PySide6.QtWidgets import (  # type: ignore
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QPlainTextEdit, QLabel, QSizePolicy, QSpacerItem
)
from PySide6.QtGui import QFont, QTextCursor, QKeySequence, QShortcut  # type: ignore

from ...services.supervisor_client import get_stdout_tail, SupervisorClientError

logger = logging.getLogger(__name__)


class LogViewerDialog(QDialog):
    """
    Dialog for viewing job logs with refresh and copy functionality.
    
    Features:
    - Read-only text display with monospace font
    - Refresh button to fetch latest logs
    - Copy button to copy logs to clipboard
    - Auto-scroll to bottom on refresh
    """
    
    # Signal emitted when dialog is closed
    closed = Signal()
    
    # Type annotations for dynamically assigned attributes
    job_id: str
    title: str
    job_label: QLabel
    status_label: QLabel
    log_text: QPlainTextEdit
    refresh_btn: QPushButton
    copy_btn: QPushButton
    clear_btn: QPushButton
    close_btn: QPushButton
    
    def __init__(
        self,
        job_id: str,
        title: Optional[str] = None,
        parent=None
    ):
        super().__init__(parent)
        self.setProperty('job_id', job_id)
        setattr(self, 'job_id', job_id)
        self.setProperty('title', title or f"Logs - Job {job_id}")
        setattr(self, 'title', title or f"Logs - Job {job_id}")
        
        self.setup_ui()
        self.setup_connections()
        self.refresh_logs()
    
    def setup_ui(self):
        """Initialize the UI components."""
        self.setWindowTitle(self.title)
        self.setMinimumSize(800, 500)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(8)
        
        # Header with job info
        header_layout = QHBoxLayout()
        
        job_label = QLabel(f"Job ID: {self.job_id}")
        self.setProperty('job_label', job_label)
        setattr(self, 'job_label', job_label)
        self.job_label.setStyleSheet("font-weight: bold; color: #3A8DFF;")
        header_layout.addWidget(self.job_label)
        
        header_layout.addSpacerItem(QSpacerItem(20, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
        
        # Status label
        status_label = QLabel("Ready")
        self.setProperty('status_label', status_label)
        setattr(self, 'status_label', status_label)
        self.status_label.setStyleSheet("color: #9A9A9A; font-size: 11px;")
        header_layout.addWidget(self.status_label)
        
        main_layout.addLayout(header_layout)
        
        # Log text area
        log_text = QPlainTextEdit()
        self.setProperty('log_text', log_text)
        setattr(self, 'log_text', log_text)
        self.log_text.setReadOnly(True)
        self.log_text.setFont(QFont("Monospace", 10))
        self.log_text.setStyleSheet("""
            QPlainTextEdit {
                background-color: #1E1E1E;
                color: #E6E6E6;
                border: 1px solid #555555;
                border-radius: 4px;
                font-family: 'Consolas', 'Monaco', monospace;
                selection-background-color: #3A8DFF;
            }
        """)
        self.log_text.setPlaceholderText("Logs will appear here after refresh...")
        main_layout.addWidget(self.log_text, 1)  # Stretch factor 1
        
        # Button panel
        button_layout = QHBoxLayout()
        
        # Refresh button
        refresh_btn = QPushButton("🔄 Refresh")
        self.setProperty('refresh_btn', refresh_btn)
        setattr(self, 'refresh_btn', refresh_btn)
        self.refresh_btn.setToolTip("Fetch latest logs from supervisor")
        self.refresh_btn.setMinimumWidth(100)
        button_layout.addWidget(self.refresh_btn)
        
        # Copy button
        copy_btn = QPushButton("📋 Copy")
        self.setProperty('copy_btn', copy_btn)
        setattr(self, 'copy_btn', copy_btn)
        self.copy_btn.setToolTip("Copy logs to clipboard")
        self.copy_btn.setMinimumWidth(100)
        button_layout.addWidget(self.copy_btn)
        
        # Clear button (local only)
        clear_btn = QPushButton("🗑️ Clear View")
        self.setProperty('clear_btn', clear_btn)
        setattr(self, 'clear_btn', clear_btn)
        self.clear_btn.setToolTip("Clear displayed logs (does not affect supervisor)")
        self.clear_btn.setMinimumWidth(100)
        button_layout.addWidget(self.clear_btn)
        
        button_layout.addSpacerItem(QSpacerItem(20, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
        
        # Close button
        close_btn = QPushButton("Close")
        self.setProperty('close_btn', close_btn)
        setattr(self, 'close_btn', close_btn)
        self.close_btn.setMinimumWidth(100)
        button_layout.addWidget(self.close_btn)
        
        main_layout.addLayout(button_layout)
    
    def setup_connections(self):
        """Connect signals and slots."""
        self.refresh_btn.clicked.connect(self.refresh_logs)
        self.copy_btn.clicked.connect(self.copy_to_clipboard)
        self.clear_btn.clicked.connect(self.clear_display)
        self.close_btn.clicked.connect(self.accept)
        
        # Add keyboard shortcuts
        QShortcut(QKeySequence.Refresh, self).activated.connect(self.refresh_logs)  # type: ignore
        QShortcut(QKeySequence.Copy, self).activated.connect(self.copy_to_clipboard)  # type: ignore
        QShortcut(QKeySequence("Ctrl+L"), self).activated.connect(self.clear_display)
        QShortcut(QKeySequence.Close, self).activated.connect(self.accept)  # type: ignore
    
    @Slot()
    def refresh_logs(self):
        """Fetch and display latest logs from supervisor."""
        self.status_label.setText("Fetching logs...")
        self.refresh_btn.setEnabled(False)
        
        try:
            # Fetch logs from supervisor
            logs = get_stdout_tail(self.job_id, n=500)
            
            # Update display
            self.log_text.setPlainText(logs)
            
            # Scroll to bottom
            cursor = self.log_text.textCursor()
            cursor.movePosition(QTextCursor.End)  # type: ignore
            self.log_text.setTextCursor(cursor)
            
            self.status_label.setText(f"Loaded {len(logs.splitlines())} lines")
            
        except SupervisorClientError as e:
            error_msg = f"Failed to fetch logs: {e.message}"
            logger.error(error_msg)
            self.log_text.setPlainText(f"ERROR: {error_msg}\n\nCheck supervisor connection and job status.")
            self.status_label.setText("Error fetching logs")
            
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            logger.error(error_msg)
            self.log_text.setPlainText(f"ERROR: {error_msg}")
            self.status_label.setText("Error")
            
        finally:
            self.refresh_btn.setEnabled(True)
    
    @Slot()
    def copy_to_clipboard(self):
        """Copy current logs to clipboard."""
        logs = self.log_text.toPlainText()
        if logs:
            from PySide6.QtWidgets import QApplication  # type: ignore
            QApplication.clipboard().setText(logs)
            self.status_label.setText("Copied to clipboard")
    
    @Slot()
    def clear_display(self):
        """Clear the displayed logs (local only)."""
        self.log_text.clear()
        self.status_label.setText("Display cleared")
    
    def closeEvent(self, event):
        """Handle dialog close event."""
        self.closed.emit()
        super().closeEvent(event)
    
    @classmethod
    def show_for_job(cls, job_id: str, parent=None):
        """
        Convenience method to create and show log viewer for a job.
        
        Args:
            job_id: The job ID to show logs for
            parent: Parent widget
        """
        dialog = cls(job_id, parent=parent)
        dialog.exec()