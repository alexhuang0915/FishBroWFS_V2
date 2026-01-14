"""
Data Prepare Panel for Explain Hub (Layer 2).

Implements Route 4: Data Prepare as First-Class Citizen.
Shows DATA1/DATA2 status with action buttons for explicit preparation.
"""

import logging
from typing import Optional, Dict, Any
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGroupBox, QFrame, QProgressBar, QSizePolicy
)
from PySide6.QtGui import QFont

from gui.services.dataset_resolver import DerivedDatasets, DatasetStatus
from gui.services.data_prepare_service import (
    get_data_prepare_service, PrepareStatus, PrepareResult
)

logger = logging.getLogger(__name__)


class DataPreparePanel(QWidget):
    """
    Panel for data preparation status and actions.
    
    Shows per dataset (DATA1, DATA2):
    - Dataset name (derived mapping)
    - Status badge
    - Last updated time (if available)
    - Reason text
    - Action button (Build Cache / Rebuild Cache)
    - Progress indicator when PREPARING
    - Result message on completion/failure
    """
    
    # Signals
    prepare_requested = Signal(str)  # dataset_key
    prepare_cancelled = Signal(str)  # dataset_key
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_datasets: Optional[DerivedDatasets] = None
        self.data_prepare_service = get_data_prepare_service()
        
        # Connect service signals
        self.data_prepare_service.progress.connect(self._on_prepare_progress)
        self.data_prepare_service.finished.connect(self._on_prepare_finished)
        self.data_prepare_service.status_changed.connect(self._on_status_changed)
        
        self.setup_ui()
        self._update_timer = QTimer()
        self._update_timer.timeout.connect(self._refresh_status)
        self._update_timer.start(1000)  # Refresh every second
        
    def setup_ui(self):
        """Initialize UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        
        # Title
        title_label = QLabel("Data Prepare")
        title_label.setStyleSheet("font-weight: bold; font-size: 13px; color: #E6E6E6;")
        layout.addWidget(title_label)
        
        # DATA1 panel
        self.data1_group = self._create_dataset_group("DATA1")
        layout.addWidget(self.data1_group)
        
        # DATA2 panel  
        self.data2_group = self._create_dataset_group("DATA2")
        layout.addWidget(self.data2_group)
        
        # Info label
        self.info_label = QLabel("Select strategy/instrument/timeframe to see dataset status")
        self.info_label.setStyleSheet("color: #9e9e9e; font-size: 10px; font-style: italic;")
        self.info_label.setWordWrap(True)
        layout.addWidget(self.info_label)
        
        # Add stretch
        layout.addStretch()
        
        # Initially hide dataset groups
        self.data1_group.hide()
        self.data2_group.hide()
    
    def _create_dataset_group(self, dataset_key: str) -> QGroupBox:
        """Create a group box for a dataset."""
        group = QGroupBox(dataset_key)
        group.setStyleSheet("""
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
        
        group_layout = QVBoxLayout(group)
        group_layout.setContentsMargins(8, 16, 8, 8)
        group_layout.setSpacing(6)
        
        # Dataset ID and mapping
        id_frame = QFrame()
        id_layout = QHBoxLayout(id_frame)
        id_layout.setContentsMargins(0, 0, 0, 0)
        
        self._add_widget_to_group(dataset_key, "id_label", QLabel("Dataset: --"), id_layout)
        id_layout.addStretch()
        group_layout.addWidget(id_frame)
        
        # Status row
        status_frame = QFrame()
        status_layout = QHBoxLayout(status_frame)
        status_layout.setContentsMargins(0, 0, 0, 0)
        
        self._add_widget_to_group(dataset_key, "status_label", QLabel("Status:"), status_layout)
        self._add_widget_to_group(dataset_key, "status_badge", QLabel("UNKNOWN"), status_layout)
        status_layout.addStretch()
        group_layout.addWidget(status_frame)
        
        # Reason text
        self._add_widget_to_group(dataset_key, "reason_label", QLabel(""), group_layout)
        
        # Date range (if available)
        date_frame = QFrame()
        date_layout = QHBoxLayout(date_frame)
        date_layout.setContentsMargins(0, 0, 0, 0)
        
        self._add_widget_to_group(dataset_key, "date_label", QLabel("Date range: --"), date_layout)
        date_layout.addStretch()
        group_layout.addWidget(date_frame)
        
        # Action button
        self._add_widget_to_group(dataset_key, "action_btn", QPushButton(), group_layout)
        
        # Progress bar (hidden by default)
        self._add_widget_to_group(dataset_key, "progress_bar", QProgressBar(), group_layout)
        
        # Result message (hidden by default)
        self._add_widget_to_group(dataset_key, "result_label", QLabel(""), group_layout)
        
        return group
    
    def _add_widget_to_group(self, dataset_key: str, widget_name: str, widget, layout):
        """Add widget to layout and store reference with dataset_key prefix."""
        attr_name = f"{dataset_key.lower()}_{widget_name}"
        setattr(self, attr_name, widget)
        layout.addWidget(widget)
        return widget
    
    def set_datasets(self, datasets: DerivedDatasets):
        """Update panel with current dataset information."""
        self.current_datasets = datasets
        
        # Show/hide groups based on dataset availability
        has_data1 = datasets.data1_id is not None
        has_data2 = datasets.data2_id is not None
        
        self.data1_group.setVisible(has_data1)
        self.data2_group.setVisible(has_data2)
        
        # Update DATA1
        if has_data1:
            self._update_dataset_panel("DATA1", datasets)
        
        # Update DATA2
        if has_data2:
            self._update_dataset_panel("DATA2", datasets)
        
        # Update info label
        if has_data1 or has_data2:
            self.info_label.setText(datasets.mapping_reason)
        else:
            self.info_label.setText("No datasets derived from current selection")
    
    def _update_dataset_panel(self, dataset_key: str, datasets: DerivedDatasets):
        """Update a specific dataset panel."""
        # Get dataset info
        if dataset_key == "DATA1":
            dataset_id = datasets.data1_id
            dataset_status = datasets.data1_status
            min_date = datasets.data1_min_date
            max_date = datasets.data1_max_date
        else:  # DATA2
            dataset_id = datasets.data2_id
            dataset_status = datasets.data2_status
            min_date = datasets.data2_min_date
            max_date = datasets.data2_max_date
        
        # Get prepare status from service
        prepare_status = self.data_prepare_service.get_prepare_status(dataset_key)
        prepare_result = self.data_prepare_service.get_prepare_result(dataset_key)
        
        # Update UI elements
        id_label = getattr(self, f"{dataset_key.lower()}_id_label")
        status_badge = getattr(self, f"{dataset_key.lower()}_status_badge")
        reason_label = getattr(self, f"{dataset_key.lower()}_reason_label")
        date_label = getattr(self, f"{dataset_key.lower()}_date_label")
        action_btn = getattr(self, f"{dataset_key.lower()}_action_btn")
        progress_bar = getattr(self, f"{dataset_key.lower()}_progress_bar")
        result_label = getattr(self, f"{dataset_key.lower()}_result_label")
        
        # Dataset ID
        id_label.setText(f"Dataset: {dataset_id or 'Unknown'}")
        
        # Status badge
        if prepare_status == PrepareStatus.PREPARING:
            display_status = "PREPARING"
            status_color = "#FF9800"  # amber
        elif prepare_status == PrepareStatus.FAILED:
            display_status = "FAILED"
            status_color = "#F44336"  # red
        elif prepare_status == PrepareStatus.READY:
            display_status = "READY"
            status_color = "#4CAF50"  # green
        else:
            # Use resolver status
            display_status = dataset_status.value
            status_color = self._get_status_color(dataset_status)
        
        status_badge.setText(display_status)
        status_badge.setStyleSheet(f"""
            QLabel {{
                padding: 2px 6px;
                border-radius: 3px;
                font-size: 10px;
                font-weight: bold;
                background-color: {status_color};
                color: white;
            }}
        """)
        
        # Reason text
        reason_text = self._get_reason_text(dataset_key, dataset_status, prepare_status, prepare_result)
        reason_label.setText(reason_text)
        reason_label.setStyleSheet("color: #9e9e9e; font-size: 10px;")
        reason_label.setWordWrap(True)
        
        # Date range
        if min_date and max_date:
            date_label.setText(f"Date range: {min_date} to {max_date}")
        else:
            date_label.setText("Date range: Unknown")
        date_label.setStyleSheet("color: #9e9e9e; font-size: 9px;")
        
        # Action button
        self._update_action_button(dataset_key, dataset_status, prepare_status, action_btn)
        
        # Progress bar
        if prepare_status == PrepareStatus.PREPARING:
            progress_bar.show()
            progress_bar.setRange(0, 100)
            # Progress will be updated via signal
        else:
            progress_bar.hide()
        
        # Result message
        if prepare_result and prepare_result.message:
            result_label.setText(prepare_result.message)
            result_label.setStyleSheet("color: #9e9e9e; font-size: 9px; font-style: italic;")
            result_label.setWordWrap(True)
            result_label.show()
        else:
            result_label.hide()
    
    def _get_reason_text(self, dataset_key: str, dataset_status: DatasetStatus, 
                         prepare_status: PrepareStatus, prepare_result: Optional[PrepareResult]) -> str:
        """Get reason text for dataset status."""
        if prepare_status == PrepareStatus.PREPARING:
            return f"Building cache for {dataset_key}..."
        elif prepare_status == PrepareStatus.FAILED:
            if prepare_result and prepare_result.message:
                return f"Preparation failed: {prepare_result.message}"
            else:
                return f"Preparation failed for {dataset_key}"
        elif prepare_status == PrepareStatus.READY:
            return f"{dataset_key} cache is ready"
        
        # Use resolver status
        if dataset_status == DatasetStatus.READY:
            return f"{dataset_key} cache is ready"
        elif dataset_status == DatasetStatus.STALE:
            return f"{dataset_key} cache is stale (older than threshold)"
        elif dataset_status == DatasetStatus.MISSING:
            return f"{dataset_key} cache not found"
        elif dataset_status == DatasetStatus.UNKNOWN:
            return f"{dataset_key} status unknown"
        else:
            return f"{dataset_key} status: {dataset_status.value}"
    
    def _get_status_color(self, dataset_status: DatasetStatus) -> str:
        """Get color for dataset status badge."""
        if dataset_status == DatasetStatus.READY:
            return "#4CAF50"  # green
        elif dataset_status == DatasetStatus.STALE:
            return "#FF9800"  # amber
        elif dataset_status == DatasetStatus.MISSING:
            return "#F44336"  # red
        else:  # UNKNOWN
            return "#9A9A9A"  # gray
    
    def _update_action_button(self, dataset_key: str, dataset_status: DatasetStatus,
                             prepare_status: PrepareStatus, action_btn: QPushButton):
        """Update action button based on dataset status."""
        # Disconnect previous connections
        try:
            action_btn.clicked.disconnect()
        except:
            pass
        
        if prepare_status == PrepareStatus.PREPARING:
            # Cancel button
            action_btn.setText("Cancel")
            action_btn.setStyleSheet("""
                QPushButton {
                    background-color: #5d4037;
                    color: white;
                    padding: 4px 8px;
                    border-radius: 3px;
                    border: 1px solid #795548;
                    font-size: 10px;
                }
                QPushButton:hover {
                    background-color: #795548;
                }
            """)
            action_btn.clicked.connect(lambda: self._on_cancel_prepare(dataset_key))
            action_btn.setEnabled(True)
            
        elif prepare_status == PrepareStatus.FAILED:
            # Retry button
            action_btn.setText("Retry")
            action_btn.setStyleSheet("""
                QPushButton {
                    background-color: #c62828;
                    color: white;
                    padding: 4px 8px;
                    border-radius: 3px;
                    border: 1px solid #d32f2f;
                    font-size: 10px;
                }
                QPushButton:hover {
                    background-color: #d32f2f;
                }
            """)
            action_btn.clicked.connect(lambda: self._on_prepare_request(dataset_key))
            action_btn.setEnabled(True)
            
        elif dataset_status in [DatasetStatus.MISSING, DatasetStatus.UNKNOWN]:
            # Build Cache button
            action_btn.setText("Build Cache")
            action_btn.setStyleSheet("""
                QPushButton {
                    background-color: #1a237e;
                    color: white;
                    padding: 4px 8px;
                    border-radius: 3px;
                    border: 1px solid #283593;
                    font-size: 10px;
                }
                QPushButton:hover {
                    background-color: #283593;
                }
            """)
            action_btn.clicked.connect(lambda: self._on_prepare_request(dataset_key))
            action_btn.setEnabled(True)
            
        elif dataset_status == DatasetStatus.STALE:
            # Rebuild Cache button
            action_btn.setText("Rebuild Cache")
            action_btn.setStyleSheet("""
                QPushButton {
                    background-color: #FF9800;
                    color: white;
                    padding: 4px 8px;
                    border-radius: 3px;
                    border: 1px solid #FFB74D;
                    font-size: 10px;
                }
                QPushButton:hover {
                    background-color: #FFB74D;
                }
            """)
            action_btn.clicked.connect(lambda: self._on_prepare_request(dataset_key))
            action_btn.setEnabled(True)
            
        else:  # READY or other
            action_btn.setText("Ready")
            action_btn.setStyleSheet("""
                QPushButton {
                    background-color: #424242;
                    color: #9e9e9e;
                    padding: 4px 8px;
                    border-radius: 3px;
                    border: 1px solid #616161;
                    font-size: 10px;
                }
            """)
            action_btn.setEnabled(False)
    
    def _on_prepare_request(self, dataset_key: str):
        """Handle prepare request button click."""
        if not self.current_datasets:
            return
        
        logger.info(f"Prepare requested for {dataset_key}")
        self.prepare_requested.emit(dataset_key)
        
        # Call service
        self.data_prepare_service.prepare(dataset_key, self.current_datasets)
    
    def _on_cancel_prepare(self, dataset_key: str):
        """Handle cancel prepare button click."""
        logger.info(f"Cancel prepare requested for {dataset_key}")
        self.prepare_cancelled.emit(dataset_key)
        
        # Call service
        self.data_prepare_service.cancel_preparation(dataset_key)
    
    def _on_prepare_progress(self, dataset_key: str, percent: int):
        """Handle prepare progress update."""
        if not self.current_datasets:
            return
        
        # Update progress bar
        progress_bar = getattr(self, f"{dataset_key.lower()}_progress_bar", None)
        if progress_bar:
            progress_bar.setValue(percent)
    
    def _on_prepare_finished(self, dataset_key: str, success: bool, message: str):
        """Handle prepare completion."""
        if not self.current_datasets:
            return
        
        # Refresh status
        self._refresh_status()
    
    def _on_status_changed(self, dataset_key: str, new_status: str):
        """Handle dataset status change."""
        if not self.current_datasets:
            return
        
        # Refresh status
        self._refresh_status()
    
    def _refresh_status(self):
        """Refresh dataset status from service."""
        if self.current_datasets:
            self.set_datasets(self.current_datasets)
    
    def clear(self):
        """Clear all displayed data."""
        self.current_datasets = None
        self.data1_group.hide()
        self.data2_group.hide()
        self.info_label.setText("Select strategy/instrument/timeframe to see dataset status")