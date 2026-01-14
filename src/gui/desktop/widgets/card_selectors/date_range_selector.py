"""
Date Range Selector - Auto-derived date range with optional override.

Features:
- Shows auto-derived date range from dataset (DATA1)
- Allows manual override with date pickers
- Visual indication of whether date range is auto-derived or manually overridden
- Validation for date format and logical order
"""

from typing import Optional, Tuple
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QFrame, QSizePolicy, QSpacerItem,
    QLineEdit, QPushButton, QCheckBox
)
from PySide6.QtGui import QFont, QColor

from gui.services.dataset_resolver import DerivedDatasets


class DateRangeSelector(QWidget):
    """
    Date range selector with auto-derived dates and optional override.
    
    Shows date range derived from DATA1 dataset, with option to manually override.
    """
    
    # Signals
    date_range_changed = Signal(str, str)  # start_date, end_date (ISO format)
    override_changed = Signal(bool)  # Whether override is enabled
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.auto_start_date: Optional[str] = None
        self.auto_end_date: Optional[str] = None
        self.is_override_enabled = False
        
        self.setup_ui()
        
    def setup_ui(self):
        """Initialize the UI components."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(8)
        
        # Header
        header_layout = QHBoxLayout()
        
        # Title
        title_label = QLabel("Date Range")
        title_label.setStyleSheet("""
            QLabel {
                font-weight: bold;
                font-size: 13px;
                color: #E6E6E6;
            }
        """)
        header_layout.addWidget(title_label)
        
        # Info label
        self.info_label = QLabel("(Auto-derived from DATA1)")
        self.info_label.setStyleSheet("""
            QLabel {
                color: #9A9A9A;
                font-size: 10px;
                font-style: italic;
            }
        """)
        header_layout.addWidget(self.info_label)
        
        header_layout.addSpacerItem(QSpacerItem(20, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
        
        main_layout.addLayout(header_layout)
        
        # Date range container
        container = QFrame()
        container.setStyleSheet("""
            QFrame {
                background-color: #252525;
                border: 1px solid #444444;
                border-radius: 6px;
            }
        """)
        
        grid_layout = QGridLayout(container)
        grid_layout.setContentsMargins(12, 12, 12, 12)
        grid_layout.setHorizontalSpacing(12)
        grid_layout.setVerticalSpacing(8)
        
        # Auto-derived dates display
        auto_label = QLabel("Auto-derived:")
        auto_label.setStyleSheet("""
            QLabel {
                font-weight: bold;
                font-size: 11px;
                color: #E6E6E6;
            }
        """)
        grid_layout.addWidget(auto_label, 0, 0)
        
        self.auto_dates_label = QLabel("—")
        self.auto_dates_label.setStyleSheet("""
            QLabel {
                color: #B0B0B0;
                font-size: 11px;
                font-style: italic;
            }
        """)
        grid_layout.addWidget(self.auto_dates_label, 0, 1, 1, 2)
        
        # Override checkbox
        self.override_checkbox = QCheckBox("Override dates")
        self.override_checkbox.setStyleSheet("""
            QCheckBox {
                color: #E6E6E6;
                font-size: 11px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
            }
        """)
        self.override_checkbox.stateChanged.connect(self._handle_override_changed)
        grid_layout.addWidget(self.override_checkbox, 1, 0)
        
        # Manual date inputs (initially disabled)
        start_label = QLabel("Start:")
        start_label.setStyleSheet("""
            QLabel {
                color: #E6E6E6;
                font-size: 11px;
            }
        """)
        grid_layout.addWidget(start_label, 2, 0)
        
        self.start_date_edit = QLineEdit()
        self.start_date_edit.setPlaceholderText("YYYY-MM-DD")
        self.start_date_edit.setToolTip("Start date (ISO format: YYYY-MM-DD)")
        self.start_date_edit.setEnabled(False)
        self.start_date_edit.setStyleSheet("""
            QLineEdit {
                background-color: #1E1E1E;
                color: #E6E6E6;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 4px;
                font-size: 11px;
            }
            QLineEdit:disabled {
                background-color: #2A2A2A;
                color: #888888;
                border: 1px solid #444444;
            }
            QLineEdit:focus {
                border: 1px solid #3A8DFF;
            }
        """)
        self.start_date_edit.textChanged.connect(self._handle_date_changed)
        grid_layout.addWidget(self.start_date_edit, 2, 1)
        
        end_label = QLabel("End:")
        end_label.setStyleSheet("""
            QLabel {
                color: #E6E6E6;
                font-size: 11px;
            }
        """)
        grid_layout.addWidget(end_label, 2, 2)
        
        self.end_date_edit = QLineEdit()
        self.end_date_edit.setPlaceholderText("YYYY-MM-DD")
        self.end_date_edit.setToolTip("End date (ISO format: YYYY-MM-DD)")
        self.end_date_edit.setEnabled(False)
        self.end_date_edit.setStyleSheet("""
            QLineEdit {
                background-color: #1E1E1E;
                color: #E6E6E6;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 4px;
                font-size: 11px;
            }
            QLineEdit:disabled {
                background-color: #2A2A2A;
                color: #888888;
                border: 1px solid #444444;
            }
            QLineEdit:focus {
                border: 1px solid #3A8DFF;
            }
        """)
        self.end_date_edit.textChanged.connect(self._handle_date_changed)
        grid_layout.addWidget(self.end_date_edit, 2, 3)
        
        # Validation status
        self.validation_label = QLabel("")
        self.validation_label.setStyleSheet("""
            QLabel {
                color: #9A9A9A;
                font-size: 10px;
                font-style: italic;
            }
        """)
        grid_layout.addWidget(self.validation_label, 3, 1, 1, 3)
        
        main_layout.addWidget(container)
        
    def update_auto_dates(self, derived_data: Optional[DerivedDatasets]):
        """Update auto-derived dates from dataset."""
        if derived_data and derived_data.data1_min_date and derived_data.data1_max_date:
            self.auto_start_date = derived_data.data1_min_date
            self.auto_end_date = derived_data.data1_max_date
            self.auto_dates_label.setText(f"{self.auto_start_date} to {self.auto_end_date}")
            
            # If override is not enabled, set the manual inputs to auto dates
            if not self.is_override_enabled:
                self.start_date_edit.setText(self.auto_start_date)
                self.end_date_edit.setText(self.auto_end_date)
                self._validate_dates()
        else:
            self.auto_start_date = None
            self.auto_end_date = None
            self.auto_dates_label.setText("No date range available")
            
            # If no auto dates and override is not enabled, clear inputs
            if not self.is_override_enabled:
                self.start_date_edit.clear()
                self.end_date_edit.clear()
                self.validation_label.setText("No auto-derived date range available")
    
    def _handle_override_changed(self, state: int):
        """Handle override checkbox state change."""
        self.is_override_enabled = state == Qt.CheckState.Checked.value
        
        # Enable/disable manual inputs
        self.start_date_edit.setEnabled(self.is_override_enabled)
        self.end_date_edit.setEnabled(self.is_override_enabled)
        
        # Update info label
        if self.is_override_enabled:
            self.info_label.setText("(Manually overridden)")
            self.info_label.setStyleSheet("""
                QLabel {
                    color: #FF9800;
                    font-size: 10px;
                    font-style: italic;
                }
            """)
        else:
            self.info_label.setText("(Auto-derived from DATA1)")
            self.info_label.setStyleSheet("""
                QLabel {
                    color: #9A9A9A;
                    font-size: 10px;
                    font-style: italic;
                }
            """)
            
            # Reset to auto dates if available
            if self.auto_start_date and self.auto_end_date:
                self.start_date_edit.setText(self.auto_start_date)
                self.end_date_edit.setText(self.auto_end_date)
            else:
                self.start_date_edit.clear()
                self.end_date_edit.clear()
        
        # Emit signal
        self.override_changed.emit(self.is_override_enabled)
        self._emit_date_range_changed()
    
    def _handle_date_changed(self):
        """Handle date input changes."""
        self._validate_dates()
        self._emit_date_range_changed()
    
    def _validate_dates(self):
        """Validate date inputs and update validation label."""
        start_text = self.start_date_edit.text().strip()
        end_text = self.end_date_edit.text().strip()
        
        if not start_text and not end_text:
            self.validation_label.setText("Enter dates or use auto-derived")
            self.validation_label.setStyleSheet("""
                QLabel {
                    color: #9A9A9A;
                    font-size: 10px;
                    font-style: italic;
                }
            """)
            return
        
        # Basic ISO date format validation (YYYY-MM-DD)
        import re
        iso_pattern = r'^\d{4}-\d{2}-\d{2}$'
        
        start_valid = bool(re.match(iso_pattern, start_text)) if start_text else False
        end_valid = bool(re.match(iso_pattern, end_text)) if end_text else False
        
        if not start_valid or not end_valid:
            self.validation_label.setText("Invalid date format (use YYYY-MM-DD)")
            self.validation_label.setStyleSheet("""
                QLabel {
                    color: #F44336;
                    font-size: 10px;
                    font-style: italic;
                }
            """)
            return
        
        # Check logical order
        from datetime import datetime
        try:
            start_date = datetime.strptime(start_text, "%Y-%m-%d")
            end_date = datetime.strptime(end_text, "%Y-%m-%d")
            
            if start_date > end_date:
                self.validation_label.setText("Start date must be before end date")
                self.validation_label.setStyleSheet("""
                    QLabel {
                        color: #F44336;
                        font-size: 10px;
                        font-style: italic;
                    }
                """)
                return
            
            # Check if dates are within auto-derived range (if available)
            if self.auto_start_date and self.auto_end_date:
                auto_start = datetime.strptime(self.auto_start_date, "%Y-%m-%d")
                auto_end = datetime.strptime(self.auto_end_date, "%Y-%m-%d")
                
                if start_date < auto_start or end_date > auto_end:
                    self.validation_label.setText("Dates outside auto-derived range")
                    self.validation_label.setStyleSheet("""
                        QLabel {
                            color: #FF9800;
                            font-size: 10px;
                            font-style: italic;
                        }
                    """)
                else:
                    self.validation_label.setText("Dates valid")
                    self.validation_label.setStyleSheet("""
                        QLabel {
                            color: #4CAF50;
                            font-size: 10px;
                            font-style: italic;
                        }
                    """)
            else:
                self.validation_label.setText("Dates valid")
                self.validation_label.setStyleSheet("""
                    QLabel {
                        color: #4CAF50;
                        font-size: 10px;
                        font-style: italic;
                    }
                """)
                
        except ValueError:
            self.validation_label.setText("Invalid date")
            self.validation_label.setStyleSheet("""
                QLabel {
                    color: #F44336;
                    font-size: 10px;
                    font-style: italic;
                }
            """)
    
    def _emit_date_range_changed(self):
        """Emit date range changed signal."""
        start_date = self.start_date_edit.text().strip()
        end_date = self.end_date_edit.text().strip()
        
        # Only emit if both dates are non-empty
        if start_date and end_date:
            self.date_range_changed.emit(start_date, end_date)
    
    def get_date_range(self) -> Tuple[Optional[str], Optional[str]]:
        """Get current date range (start, end)."""
        start_date = self.start_date_edit.text().strip()
        end_date = self.end_date_edit.text().strip()
        
        if start_date and end_date:
            return start_date, end_date
        return None, None
    
    def is_valid(self) -> bool:
        """Check if date range is valid."""
        start_date, end_date = self.get_date_range()
        return bool(start_date and end_date)
    
    def clear(self):
        """Clear all inputs and reset to auto-derived dates."""
        self.override_checkbox.setChecked(False)
        self.start_date_edit.clear()
        self.end_date_edit.clear()
        self.validation_label.clear()
        
        if self.auto_start_date and self.auto_end_date:
            self.start_date_edit.setText(self.auto_start_date)
            self.end_date_edit.setText(self.auto_end_date)