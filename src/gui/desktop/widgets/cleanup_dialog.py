"""
Cleanup Dialog - Safe deletion tools UI.

Provides user interface for cleanup operations with dry-run preview,
confirmation dialogs, and safety guardrails.
"""

import os
import logging
from pathlib import Path
from typing import Optional, List

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QComboBox, QCheckBox, QGroupBox,
    QListWidget, QListWidgetItem, QTextEdit, QTabWidget,
    QMessageBox, QLineEdit, QProgressBar, QWidget,
    QScrollArea, QFrame, QSizePolicy, QInputDialog
)

from ..services.cleanup_service import (
    CleanupService, CleanupScope, TimeRange, DeletePlan
)

logger = logging.getLogger(__name__)


class CleanupDialog(QDialog):
    """Dialog for safe cleanup operations."""
    
    # Signal emitted when cleanup is performed
    cleanup_performed = Signal(dict)  # audit event
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.service = CleanupService()
        self.current_plan: Optional[DeletePlan] = None
        
        self.setup_ui()
        self.setup_connections()
        
        # Set window properties
        self.setWindowTitle("Clean Up Data")
        self.setMinimumSize(800, 600)
    
    def setup_ui(self):
        """Initialize the UI components."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)
        
        # Header
        header_label = QLabel("Clean Up Data - Safe Deletion Tools")
        header_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #E6E6E6;")
        main_layout.addWidget(header_label)
        
        # Description
        desc_label = QLabel("Safely delete runs, artifacts, cache, and demo data with dry-run preview and audit logging.")
        desc_label.setStyleSheet("color: #A8A8A8; font-size: 11px;")
        desc_label.setWordWrap(True)
        main_layout.addWidget(desc_label)
        
        # Tab widget for different cleanup types
        self.tab_widget = QTabWidget()
        
        # Tab 1: Recent Runs
        self.create_runs_tab()
        
        # Tab 2: Published Results
        self.create_published_tab()
        
        # Tab 3: Cache Data
        self.create_cache_tab()
        
        # Tab 4: Demo Data (only visible in demo mode)
        self.create_demo_tab()
        
        # Tab 5: Trash Purge
        self.create_trash_tab()
        
        main_layout.addWidget(self.tab_widget)
        
        # Preview panel
        preview_group = QGroupBox("Dry-Run Preview")
        preview_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 1px solid #2A2A2A;
                border-radius: 3px;
                margin-top: 4px;
                padding-top: 6px;
                font-size: 11px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 6px;
                padding: 0 3px 0 3px;
                color: #E6E6E6;
            }
        """)
        preview_layout = QVBoxLayout()
        
        self.preview_text = QTextEdit()
        self.preview_text.setReadOnly(True)
        self.preview_text.setMaximumHeight(150)
        self.preview_text.setStyleSheet("""
            QTextEdit {
                background-color: #1E1E1E;
                color: #E6E6E6;
                border: 1px solid #2A2A2A;
                border-radius: 3px;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 10px;
            }
        """)
        preview_layout.addWidget(self.preview_text)
        
        preview_group.setLayout(preview_layout)
        main_layout.addWidget(preview_group)
        
        # Action buttons
        button_layout = QHBoxLayout()
        
        self.dry_run_btn = QPushButton("Dry Run Preview")
        self.dry_run_btn.setMinimumHeight(40)
        self.dry_run_btn.setStyleSheet("""
            QPushButton {
                background-color: #2A2A2A;
                color: #E6E6E6;
                border: 1px solid #2A2A2A;
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3A3A3A;
                border: 1px solid #3A3A3A;
            }
        """)
        button_layout.addWidget(self.dry_run_btn)
        
        self.execute_btn = QPushButton("Execute Clean Up")
        self.execute_btn.setMinimumHeight(40)
        self.execute_btn.setEnabled(False)
        self.execute_btn.setStyleSheet("""
            QPushButton {
                background-color: #2F80ED;
                color: white;
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:disabled {
                background-color: #2B2B2B;
                color: #666666;
                border: 1px solid #333333;
            }
            QPushButton:hover:enabled {
                background-color: #2A7DFF;
            }
        """)
        button_layout.addWidget(self.execute_btn)
        
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setMinimumHeight(40)
        button_layout.addWidget(self.cancel_btn)
        
        button_layout.addStretch()
        main_layout.addLayout(button_layout)
        
        # Status bar
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: #A8A8A8; font-size: 10px;")
        main_layout.addWidget(self.status_label)
    
    def create_runs_tab(self):
        """Create tab for cleaning up recent runs."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        # Season selection
        season_layout = QHBoxLayout()
        season_layout.addWidget(QLabel("Season:"))
        
        self.runs_season_cb = QComboBox()
        self.runs_season_cb.addItems(["2026Q1", "2025Q4", "2025Q3"])
        season_layout.addWidget(self.runs_season_cb)
        season_layout.addStretch()
        layout.addLayout(season_layout)
        
        # Time range
        time_layout = QHBoxLayout()
        time_layout.addWidget(QLabel("Time Range:"))
        
        self.runs_time_cb = QComboBox()
        self.runs_time_cb.addItems([
            "Last 1 hour",
            "Today",
            "Last 7 days",
            "All"
        ])
        self.runs_time_cb.setCurrentText("Last 7 days")
        time_layout.addWidget(self.runs_time_cb)
        time_layout.addStretch()
        layout.addLayout(time_layout)
        
        # Run types
        type_group = QGroupBox("Run Types to Delete")
        type_layout = QVBoxLayout()
        
        self.runs_completed_cb = QCheckBox("Completed")
        self.runs_completed_cb.setChecked(True)
        type_layout.addWidget(self.runs_completed_cb)
        
        self.runs_failed_cb = QCheckBox("Failed")
        self.runs_failed_cb.setChecked(True)
        type_layout.addWidget(self.runs_failed_cb)
        
        self.runs_unpublished_cb = QCheckBox("Unpublished")
        self.runs_unpublished_cb.setChecked(False)
        type_layout.addWidget(self.runs_unpublished_cb)
        
        type_group.setLayout(type_layout)
        layout.addWidget(type_group)
        
        # Safety note
        note_label = QLabel("Note: This will move selected runs to outputs/_trash. Published artifacts (artifact_*) are excluded unless explicitly selected.")
        note_label.setStyleSheet("color: #A8A8A8; font-size: 10px; font-style: italic;")
        note_label.setWordWrap(True)
        layout.addWidget(note_label)
        
        layout.addStretch()
        self.tab_widget.addTab(tab, "Delete Recent Runs")
    
    def create_published_tab(self):
        """Create tab for cleaning up published results."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        # Season selection
        season_layout = QHBoxLayout()
        season_layout.addWidget(QLabel("Season:"))
        
        self.published_season_cb = QComboBox()
        self.published_season_cb.addItems(["2026Q1", "2025Q4", "2025Q3"])
        season_layout.addWidget(self.published_season_cb)
        season_layout.addStretch()
        layout.addLayout(season_layout)
        
        # Artifact selection
        artifact_group = QGroupBox("Select Published Results")
        artifact_layout = QVBoxLayout()
        
        self.artifact_list = QListWidget()
        self.artifact_list.setSelectionMode(QListWidget.MultiSelection)
        self.artifact_list.setMaximumHeight(200)
        
        # Load available artifacts
        self.load_artifacts()
        
        artifact_layout.addWidget(self.artifact_list)
        
        # Select all/none buttons
        select_layout = QHBoxLayout()
        select_all_btn = QPushButton("Select All")
        select_all_btn.clicked.connect(self.artifact_list.selectAll)
        select_layout.addWidget(select_all_btn)
        
        select_none_btn = QPushButton("Select None")
        select_none_btn.clicked.connect(self.artifact_list.clearSelection)
        select_layout.addWidget(select_none_btn)
        
        select_layout.addStretch()
        artifact_layout.addLayout(select_layout)
        
        artifact_group.setLayout(artifact_layout)
        layout.addWidget(artifact_group)
        
        # Warning
        warning_label = QLabel("⚠️ Warning: Deleting published results cannot be undone. If artifact is referenced in Strategy Library, allocation will be affected.")
        warning_label.setStyleSheet("color: #FF4D4D; font-size: 11px; font-weight: bold;")
        warning_label.setWordWrap(True)
        layout.addWidget(warning_label)
        
        layout.addStretch()
        self.tab_widget.addTab(tab, "Delete Published Results")
    
    def create_cache_tab(self):
        """Create tab for cleaning up cache data."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        # Season selection
        season_layout = QHBoxLayout()
        season_layout.addWidget(QLabel("Season:"))
        
        self.cache_season_cb = QComboBox()
        self.cache_season_cb.addItems(["2026Q1", "2025Q4", "2025Q3"])
        season_layout.addWidget(self.cache_season_cb)
        season_layout.addStretch()
        layout.addLayout(season_layout)
        
        # Market selection
        market_layout = QHBoxLayout()
        market_layout.addWidget(QLabel("Market:"))
        
        self.cache_market_cb = QComboBox()
        # Would need to load actual markets
        self.cache_market_cb.addItems(["ES", "NQ", "RTY", "CL"])
        market_layout.addWidget(self.cache_market_cb)
        market_layout.addStretch()
        layout.addLayout(market_layout)
        
        # Cache type
        type_group = QGroupBox("Cache Types to Delete")
        type_layout = QVBoxLayout()
        
        self.cache_bars_cb = QCheckBox("Market Data Cache (bars)")
        self.cache_bars_cb.setChecked(True)
        type_layout.addWidget(self.cache_bars_cb)
        
        self.cache_features_cb = QCheckBox("Analysis Data Cache (features)")
        self.cache_features_cb.setChecked(True)
        type_layout.addWidget(self.cache_features_cb)
        
        type_group.setLayout(type_layout)
        layout.addWidget(type_group)
        
        # Note
        note_label = QLabel("Note: Cache will be rebuilt automatically when needed. This operation is safe.")
        note_label.setStyleSheet("color: #A8A8A8; font-size: 10px; font-style: italic;")
        note_label.setWordWrap(True)
        layout.addWidget(note_label)
        
        layout.addStretch()
        self.tab_widget.addTab(tab, "Clear Cached Data")
    
    def create_demo_tab(self):
        """Create tab for cleaning up demo data."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        # Check if demo mode is enabled
        demo_enabled = os.environ.get("FISHBRO_DESKTOP_DEMO") == "1"
        
        if not demo_enabled:
            label = QLabel("Demo cleanup is only available when FISHBRO_DESKTOP_DEMO=1 is set.")
            label.setStyleSheet("color: #A8A8A8; font-size: 12px;")
            label.setAlignment(Qt.AlignCenter)
            layout.addWidget(label)
        else:
            # Season selection
            season_layout = QHBoxLayout()
            season_layout.addWidget(QLabel("Season:"))
            
            self.demo_season_cb = QComboBox()
            self.demo_season_cb.addItems(["2026Q1", "2025Q4", "2025Q3"])
            season_layout.addWidget(self.demo_season_cb)
            season_layout.addStretch()
            layout.addLayout(season_layout)
            
            # Description
            desc_label = QLabel("Delete all demo-tagged runs and audit records. Use this to reset demo environment.")
            desc_label.setStyleSheet("color: #A8A8A8; font-size: 11px;")
            desc_label.setWordWrap(True)
            layout.addWidget(desc_label)
            
            # Warning
            warning_label = QLabel("⚠️ This will delete all demo data. Make sure you have exported any results you want to keep.")
            warning_label.setStyleSheet("color: #FFA500; font-size: 11px; font-weight: bold;")
            warning_label.setWordWrap(True)
            layout.addWidget(warning_label)
        
        layout.addStretch()
        self.tab_widget.addTab(tab, "Reset Demo Data")
    
    def create_trash_tab(self):
        """Create tab for permanently deleting trash."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)
        
        # Time range
        time_layout = QHBoxLayout()
        time_layout.addWidget(QLabel("Time Range:"))
        
        self.trash_time_cb = QComboBox()
        self.trash_time_cb.addItems([
            "Last 1 hour",
            "Today",
            "Last 7 days",
            "All"
        ])
        self.trash_time_cb.setCurrentText("All")
        time_layout.addWidget(self.trash_time_cb)
        time_layout.addStretch()
        layout.addLayout(time_layout)
        
        # Trash info
        trash_dir = Path("outputs") / "_trash"
        if trash_dir.exists():
            trash_items = list(trash_dir.iterdir())
            trash_count = len([item for item in trash_items if item.is_dir()])
            
            info_label = QLabel(f"Trash directory contains {trash_count} items.")
            info_label.setStyleSheet("color: #A8A8A8; font-size: 11px;")
            layout.addWidget(info_label)
        else:
            info_label = QLabel("Trash directory does not exist.")
            info_label.setStyleSheet("color: #A8A8A8; font-size: 11px;")
            layout.addWidget(info_label)
        
        # Extreme warning
        warning_label = QLabel("🚨 EXTREME WARNING: This will PERMANENTLY DELETE data from outputs/_trash. This action cannot be undone. Data will be lost forever.")
        warning_label.setStyleSheet("color: #FF4D4D; font-size: 12px; font-weight: bold;")
        warning_label.setWordWrap(True)
        layout.addWidget(warning_label)
        
        # Confirmation requirement
        confirm_layout = QHBoxLayout()
        confirm_layout.addWidget(QLabel("Type 'DELETE' to confirm:"))
        
        self.trash_confirm_edit = QLineEdit()
        self.trash_confirm_edit.setPlaceholderText("Type DELETE here")
        confirm_layout.addWidget(self.trash_confirm_edit)
        
        layout.addLayout(confirm_layout)
        
        layout.addStretch()
        self.tab_widget.addTab(tab, "Permanently Delete Trash")
    
    def setup_connections(self):
        """Connect signals and slots."""
        self.dry_run_btn.clicked.connect(self.on_dry_run)
        self.execute_btn.clicked.connect(self.on_execute)
        self.cancel_btn.clicked.connect(self.reject)
        
        # Tab change updates preview
        self.tab_widget.currentChanged.connect(self.clear_preview)
    
    def load_artifacts(self):
        """Load available artifacts into list."""
        self.artifact_list.clear()
        
        # Simplified - would need to scan actual artifact directories
        artifacts = [
            "artifact_20250103_123456",
            "artifact_20250102_234567",
            "artifact_20250101_345678",
            "artifact_20241231_456789"
        ]
        
        for artifact in artifacts:
            item = QListWidgetItem(artifact)
            self.artifact_list.addItem(item)
    
    def clear_preview(self):
        """Clear the preview text."""
        self.preview_text.clear()
        self.execute_btn.setEnabled(False)
        self.current_plan = None
        self.status_label.setText("Ready")
    
    def on_dry_run(self):
        """Perform dry-run preview based on current tab."""
        current_tab = self.tab_widget.currentIndex()
        
        try:
            if current_tab == 0:  # Recent Runs
                plan = self._dry_run_runs()
            elif current_tab == 1:  # Published Results
                plan = self._dry_run_published()
            elif current_tab == 2:  # Cache Data
                plan = self._dry_run_cache()
            elif current_tab == 3:  # Demo Data
                plan = self._dry_run_demo()
            elif current_tab == 4:  # Trash Purge
                plan = self._dry_run_trash()
            else:
                self.status_label.setText("Unknown tab")
                return
            
            self.current_plan = plan
            self._update_preview(plan)
            self.execute_btn.setEnabled(True)
            self.status_label.setText(f"Dry-run complete: {len(plan.items)} items to delete")
            
        except Exception as e:
            self.status_label.setText(f"Error: {str(e)}")
            QMessageBox.critical(self, "Dry-run Error", f"Failed to generate dry-run: {str(e)}")
    
    def _dry_run_runs(self) -> DeletePlan:
        """Build dry-run plan for recent runs."""
        season = self.runs_season_cb.currentText()
        time_range_str = self.runs_time_cb.currentText()
        
        # Map UI to TimeRange enum
        time_range_map = {
            "Last 1 hour": TimeRange.LAST_1_HOUR,
            "Today": TimeRange.TODAY,
            "Last 7 days": TimeRange.LAST_7_DAYS,
            "All": TimeRange.ALL
        }
        time_range = time_range_map.get(time_range_str, TimeRange.LAST_7_DAYS)
        
        # Build criteria - map UI checkboxes to run_types
        run_types = []
        if self.runs_completed_cb.isChecked():
            run_types.append("completed")
        if self.runs_failed_cb.isChecked():
            run_types.append("failed")
        if self.runs_unpublished_cb.isChecked():
            run_types.append("unpublished")
        
        criteria = {
            "season": season,
            "time_range": time_range,
            "run_types": run_types
        }
        
        return self.service.build_delete_plan(CleanupScope.RUNS, criteria)
    
    def _dry_run_published(self) -> DeletePlan:
        """Build dry-run plan for published results."""
        season = self.published_season_cb.currentText()
        
        # Get selected artifacts
        selected_items = self.artifact_list.selectedItems()
        artifact_ids = [item.text() for item in selected_items]
        
        if not artifact_ids:
            raise ValueError("No artifacts selected")
        
        criteria = {
            "season": season,
            "artifact_ids": artifact_ids
        }
        
        return self.service.build_delete_plan(CleanupScope.PUBLISHED, criteria)
    
    def _dry_run_cache(self) -> DeletePlan:
        """Build dry-run plan for cache data."""
        season = self.cache_season_cb.currentText()
        market = self.cache_market_cb.currentText()
        
        # Determine cache type
        if self.cache_bars_cb.isChecked() and self.cache_features_cb.isChecked():
            cache_type = "both"
        elif self.cache_bars_cb.isChecked():
            cache_type = "bars"
        elif self.cache_features_cb.isChecked():
            cache_type = "features"
        else:
            raise ValueError("Select at least one cache type")
        
        criteria = {
            "season": season,
            "market": market,
            "cache_type": cache_type
        }
        
        return self.service.build_delete_plan(CleanupScope.CACHE, criteria)
    
    def _dry_run_demo(self) -> DeletePlan:
        """Build dry-run plan for demo data."""
        # Check if demo mode is enabled
        if os.environ.get("FISHBRO_DESKTOP_DEMO") != "1":
            raise ValueError("Demo mode not enabled")
        
        season = self.demo_season_cb.currentText()
        
        criteria = {
            "season": season
        }
        
        return self.service.build_delete_plan(CleanupScope.DEMO, criteria)
    
    def _dry_run_trash(self) -> DeletePlan:
        """Build dry-run plan for trash purge."""
        time_range_str = self.trash_time_cb.currentText()
        
        # Map UI to TimeRange enum
        time_range_map = {
            "Last 1 hour": TimeRange.LAST_1_HOUR,
            "Today": TimeRange.TODAY,
            "Last 7 days": TimeRange.LAST_7_DAYS,
            "All": TimeRange.ALL
        }
        time_range = time_range_map.get(time_range_str, TimeRange.ALL)
        
        criteria = {
            "time_range": time_range
        }
        
        return self.service.build_delete_plan(CleanupScope.TRASH_PURGE, criteria)
    
    def _update_preview(self, plan: DeletePlan):
        """Update preview text with plan details."""
        text = f"DRY-RUN PREVIEW\n"
        text += f"Scope: {plan.scope.value}\n"
        text += f"Items to delete: {len(plan.items)}\n"
        text += f"Total size: {plan.total_size_bytes / (1024*1024):.2f} MB\n"
        
        # Show trash destination if available
        if plan.trash_path:
            text += f"Destination: {plan.trash_path}\n\n"
        else:
            text += f"Destination: outputs/_trash (to be created)\n\n"
        
        text += "Items:\n"
        for i, item in enumerate(plan.items[:10]):  # Show first 10 items
            text += f"  • {item}\n"
        
        if len(plan.items) > 10:
            text += f"  ... and {len(plan.items) - 10} more items\n"
        
        self.preview_text.setText(text)
    
    def on_execute(self):
        """Execute the cleanup operation."""
        if not self.current_plan:
            QMessageBox.warning(self, "No Plan", "Please run dry-run first")
            return
        
        # Special confirmation for dangerous operations
        if self.current_plan.scope == CleanupScope.PUBLISHED:
            confirm_text, ok = QInputDialog.getText(
                self, "Confirm Deletion",
                "Type 'DELETE' to confirm deletion of published results:"
            )
            if not ok or confirm_text != "DELETE":
                self.status_label.setText("Cancelled: confirmation failed")
                return
        
        elif self.current_plan.scope == CleanupScope.TRASH_PURGE:
            confirm_text = self.trash_confirm_edit.text()
            if confirm_text != "DELETE":
                QMessageBox.warning(
                    self, "Confirmation Required",
                    "You must type 'DELETE' in the confirmation field"
                )
                return
        
        # Execute the plan
        try:
            self.status_label.setText("Executing cleanup...")
            self.setEnabled(False)
            
            # Determine which execution method to use
            if self.current_plan.scope == CleanupScope.TRASH_PURGE:
                success, message = self.service.execute_purge_trash(self.current_plan)
            else:
                success, message = self.service.execute_soft_delete(self.current_plan)
            
            if success:
                # Emit signal for audit logging
                from datetime import datetime
                self.cleanup_performed.emit({
                    "scope": self.current_plan.scope.value,
                    "item_count": len(self.current_plan.items),
                    "timestamp": datetime.now().isoformat(),
                    "trash_destination": str(self.current_plan.trash_path) if self.current_plan.trash_path else "outputs/_trash"
                })
                
                QMessageBox.information(
                    self, "Cleanup Complete",
                    f"Cleanup completed successfully.\n{message}"
                )
                
                self.clear_preview()
                self.status_label.setText("Cleanup completed successfully")
            else:
                QMessageBox.warning(
                    self, "Cleanup Failed",
                    f"Cleanup failed: {message}"
                )
                self.status_label.setText(f"Failed: {message}")
            
        except Exception as e:
            QMessageBox.critical(self, "Execution Error", f"Failed to execute cleanup: {str(e)}")
            self.status_label.setText(f"Error: {str(e)}")
        finally:
            self.setEnabled(True)
