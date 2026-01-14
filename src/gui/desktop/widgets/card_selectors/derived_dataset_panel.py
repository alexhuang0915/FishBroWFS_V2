"""
Derived Dataset Panel - Read-only display for DATA1/DATA2 dataset mapping.

Features:
- Shows derived dataset IDs for DATA1 and DATA2
- Displays dataset status (READY, MISSING, STALE, UNKNOWN)
- Shows date ranges for datasets
- Visual status indicators (color-coded)
- Mapping reason explanation
"""

from typing import Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QFrame, QSizePolicy, QSpacerItem
)
from PySide6.QtGui import QFont, QColor

from gui.services.dataset_resolver import DerivedDatasets, DatasetStatus


class DerivedDatasetPanel(QWidget):
    """
    Read-only panel for displaying derived dataset mapping.
    
    Shows DATA1 and DATA2 dataset IDs, statuses, date ranges, and mapping reason.
    Users cannot manually select datasets - they are derived from instrument+timeframe+mode.
    """
    
    # Signals
    data_updated = Signal()  # Emitted when data is updated
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.derived_data: Optional[DerivedDatasets] = None
        
        self.setup_ui()
        
    def setup_ui(self):
        """Initialize the UI components."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(8)
        
        # Header
        header_layout = QHBoxLayout()
        
        # Title
        title_label = QLabel("Derived Datasets")
        title_label.setStyleSheet("""
            QLabel {
                font-weight: bold;
                font-size: 13px;
                color: #E6E6E6;
            }
        """)
        header_layout.addWidget(title_label)
        
        # Info icon/label
        info_label = QLabel("(Auto-derived from instrument+timeframe+mode)")
        info_label.setStyleSheet("""
            QLabel {
                color: #9A9A9A;
                font-size: 10px;
                font-style: italic;
            }
        """)
        header_layout.addWidget(info_label)
        
        header_layout.addSpacerItem(QSpacerItem(20, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
        
        main_layout.addLayout(header_layout)
        
        # Dataset cards container
        cards_container = QFrame()
        cards_container.setStyleSheet("""
            QFrame {
                background-color: #252525;
                border: 1px solid #444444;
                border-radius: 6px;
            }
        """)
        
        cards_layout = QGridLayout(cards_container)
        cards_layout.setContentsMargins(12, 12, 12, 12)
        cards_layout.setHorizontalSpacing(16)
        cards_layout.setVerticalSpacing(8)
        
        # DATA1 card
        data1_label = QLabel("DATA1 (Primary):")
        data1_label.setStyleSheet("""
            QLabel {
                font-weight: bold;
                font-size: 11px;
                color: #E6E6E6;
            }
        """)
        cards_layout.addWidget(data1_label, 0, 0)
        
        self.data1_id_label = QLabel("—")
        self.data1_id_label.setStyleSheet("""
            QLabel {
                font-family: monospace;
                font-size: 11px;
                color: #B0B0B0;
            }
        """)
        cards_layout.addWidget(self.data1_id_label, 0, 1)
        
        self.data1_status_label = QLabel("UNKNOWN")
        self.data1_status_label.setStyleSheet("""
            QLabel {
                font-weight: bold;
                font-size: 10px;
                color: #9E9E9E;
            }
        """)
        cards_layout.addWidget(self.data1_status_label, 0, 2)
        
        # DATA1 date range
        self.data1_date_label = QLabel("Date range: —")
        self.data1_date_label.setStyleSheet("""
            QLabel {
                color: #9A9A9A;
                font-size: 9px;
                font-style: italic;
            }
        """)
        cards_layout.addWidget(self.data1_date_label, 1, 1, 1, 2)
        
        # DATA2 card
        data2_label = QLabel("DATA2 (Secondary):")
        data2_label.setStyleSheet("""
            QLabel {
                font-weight: bold;
                font-size: 11px;
                color: #E6E6E6;
            }
        """)
        cards_layout.addWidget(data2_label, 2, 0)
        
        self.data2_id_label = QLabel("—")
        self.data2_id_label.setStyleSheet("""
            QLabel {
                font-family: monospace;
                font-size: 11px;
                color: #B0B0B0;
            }
        """)
        cards_layout.addWidget(self.data2_id_label, 2, 1)
        
        self.data2_status_label = QLabel("UNKNOWN")
        self.data2_status_label.setStyleSheet("""
            QLabel {
                font-weight: bold;
                font-size: 10px;
                color: #9E9E9E;
            }
        """)
        cards_layout.addWidget(self.data2_status_label, 2, 2)
        
        # DATA2 date range
        self.data2_date_label = QLabel("Date range: —")
        self.data2_date_label.setStyleSheet("""
            QLabel {
                color: #9A9A9A;
                font-size: 9px;
                font-style: italic;
            }
        """)
        cards_layout.addWidget(self.data2_date_label, 3, 1, 1, 2)
        
        main_layout.addWidget(cards_container)
        
        # Mapping reason
        self.mapping_reason_label = QLabel("Select instrument, timeframe, and mode to see dataset mapping.")
        self.mapping_reason_label.setWordWrap(True)
        self.mapping_reason_label.setStyleSheet("""
            QLabel {
                color: #9A9A9A;
                font-size: 10px;
                font-style: italic;
                padding: 4px;
            }
        """)
        main_layout.addWidget(self.mapping_reason_label)
        
        # Status summary
        self.status_summary_label = QLabel("Ready")
        self.status_summary_label.setStyleSheet("""
            QLabel {
                color: #4CAF50;
                font-size: 10px;
                font-weight: bold;
            }
        """)
        main_layout.addWidget(self.status_summary_label)
        
    def update_data(self, derived_data: Optional[DerivedDatasets]):
        """Update the panel with derived dataset data."""
        self.derived_data = derived_data
        
        if not derived_data:
            self._clear_display()
            return
        
        # Update DATA1
        if derived_data.data1_id:
            self.data1_id_label.setText(derived_data.data1_id)
            
            # Update status with color
            status_text = derived_data.data1_status.value
            status_color = self._get_status_color(derived_data.data1_status)
            self.data1_status_label.setText(status_text)
            self.data1_status_label.setStyleSheet(f"""
                QLabel {{
                    font-weight: bold;
                    font-size: 10px;
                    color: {status_color};
                }}
            """)
            
            # Update date range
            if derived_data.data1_min_date and derived_data.data1_max_date:
                date_text = f"{derived_data.data1_min_date} to {derived_data.data1_max_date}"
                self.data1_date_label.setText(f"Date range: {date_text}")
            else:
                self.data1_date_label.setText("Date range: Unknown")
        else:
            self.data1_id_label.setText("Not mapped")
            self.data1_status_label.setText("UNKNOWN")
            self.data1_status_label.setStyleSheet("""
                QLabel {
                    font-weight: bold;
                    font-size: 10px;
                    color: #9E9E9E;
                }
            """)
            self.data1_date_label.setText("Date range: —")
        
        # Update DATA2
        if derived_data.data2_id:
            self.data2_id_label.setText(derived_data.data2_id)
            
            # Update status with color
            status_text = derived_data.data2_status.value
            status_color = self._get_status_color(derived_data.data2_status)
            self.data2_status_label.setText(status_text)
            self.data2_status_label.setStyleSheet(f"""
                QLabel {{
                    font-weight: bold;
                    font-size: 10px;
                    color: {status_color};
                }}
            """)
            
            # Update date range
            if derived_data.data2_min_date and derived_data.data2_max_date:
                date_text = f"{derived_data.data2_min_date} to {derived_data.data2_max_date}"
                self.data2_date_label.setText(f"Date range: {date_text}")
            else:
                self.data2_date_label.setText("Date range: Unknown")
        else:
            self.data2_id_label.setText("Not required or not mapped")
            self.data2_status_label.setText("N/A")
            self.data2_status_label.setStyleSheet("""
                QLabel {
                    font-weight: bold;
                    font-size: 10px;
                    color: #9E9E9E;
                }
            """)
            self.data2_date_label.setText("Date range: —")
        
        # Update mapping reason
        self.mapping_reason_label.setText(derived_data.mapping_reason)
        
        # Update status summary
        self._update_status_summary(derived_data)
        
        # Emit signal
        self.data_updated.emit()
    
    def _get_status_color(self, status: DatasetStatus) -> str:
        """Get color for a dataset status."""
        color_map = {
            DatasetStatus.READY: "#4CAF50",    # green
            DatasetStatus.MISSING: "#F44336",  # red
            DatasetStatus.STALE: "#FF9800",    # amber
            DatasetStatus.UNKNOWN: "#9E9E9E",  # gray
        }
        return color_map.get(status, "#9E9E9E")
    
    def _update_status_summary(self, derived_data: DerivedDatasets):
        """Update the status summary label."""
        # Check if both datasets are ready
        data1_ready = derived_data.data1_status == DatasetStatus.READY
        data2_ready = derived_data.data2_status == DatasetStatus.READY
        
        if not derived_data.data1_id:
            self.status_summary_label.setText("DATA1 not mapped")
            self.status_summary_label.setStyleSheet("""
                QLabel {
                    color: #FF9800;
                    font-size: 10px;
                    font-weight: bold;
                }
            """)
        elif not data1_ready:
            self.status_summary_label.setText(f"DATA1 {derived_data.data1_status.value}")
            self.status_summary_label.setStyleSheet("""
                QLabel {
                    color: #FF9800;
                    font-size: 10px;
                    font-weight: bold;
                }
            """)
        elif derived_data.data2_id and not data2_ready:
            self.status_summary_label.setText(f"DATA2 {derived_data.data2_status.value}")
            self.status_summary_label.setStyleSheet("""
                QLabel {
                    color: #FF9800;
                    font-size: 10px;
                    font-weight: bold;
                }
            """)
        else:
            self.status_summary_label.setText("Datasets ready")
            self.status_summary_label.setStyleSheet("""
                QLabel {
                    color: #4CAF50;
                    font-size: 10px;
                    font-weight: bold;
                }
            """)
    
    def _clear_display(self):
        """Clear the display."""
        self.data1_id_label.setText("—")
        self.data1_status_label.setText("UNKNOWN")
        self.data1_status_label.setStyleSheet("""
            QLabel {
                font-weight: bold;
                font-size: 10px;
                color: #9E9E9E;
            }
        """)
        self.data1_date_label.setText("Date range: —")
        
        self.data2_id_label.setText("—")
        self.data2_status_label.setText("UNKNOWN")
        self.data2_status_label.setStyleSheet("""
            QLabel {
                font-weight: bold;
                font-size: 10px;
                color: #9E9E9E;
            }
        """)
        self.data2_date_label.setText("Date range: —")
        
        self.mapping_reason_label.setText("Select instrument, timeframe, and mode to see dataset mapping.")
        self.status_summary_label.setText("Ready")
        self.status_summary_label.setStyleSheet("""
            QLabel {
                color: #4CAF50;
                font-size: 10px;
                font-weight: bold;
            }
        """)
    
    def get_derived_data(self) -> Optional[DerivedDatasets]:
        """Get the current derived dataset data."""
        return self.derived_data
    
    def is_data_ready(self) -> bool:
        """Check if datasets are ready for submission."""
        if not self.derived_data:
            return False
        
        # DATA1 must be READY
        if self.derived_data.data1_status != DatasetStatus.READY:
            return False
        
        # DATA2 must be READY if it exists and is required
        if (self.derived_data.data2_id and 
            self.derived_data.data2_status != DatasetStatus.READY):
            return False
        
        return True