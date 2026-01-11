"""
Readiness Panel – Visualizes dependency chain with satisfied/missing status.

Shows each prerequisite (supervisor, bars, features, registry, timeframe, parameters)
with a checkmark or cross, and a human‑readable reason.

Integrates with compute_ui_ready_state to reflect current UI selections.
"""

import logging
from typing import Optional, Dict

from PySide6.QtCore import Qt, Signal, Slot  # type: ignore
from PySide6.QtWidgets import (  # type: ignore
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGroupBox, QGridLayout
)
from PySide6.QtGui import QFont, QColor, QPalette  # type: ignore

from ..state.readiness_state import compute_ui_ready_state

logger = logging.getLogger(__name__)


class ReadinessPanel(QWidget):
    """Panel that displays readiness dependency chain."""
    
    # Signal emitted when readiness state changes
    readiness_changed = Signal(bool, dict)  # ready, missing
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_missing: Dict[str, str] = {}
        self.current_ready = False
        self.setup_ui()
    
    def setup_ui(self):
        """Initialize the UI components."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        
        # Group box
        self.group = QGroupBox("Readiness Dependencies")
        self.group.setStyleSheet("""
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
        
        # Grid layout for prerequisites
        self.grid = QGridLayout()
        self.grid.setColumnStretch(0, 0)  # Icon column
        self.grid.setColumnStretch(1, 1)  # Label column
        self.grid.setColumnStretch(2, 2)  # Reason column
        self.grid.setHorizontalSpacing(12)
        self.grid.setVerticalSpacing(6)
        
        # Create placeholder rows (will be populated by update)
        self.prereq_labels = {}
        self.prereq_icons = {}
        
        # Define prerequisites in order
        self.prereq_order = [
            ("supervisor", "Supervisor API", "Supervisor must be reachable and healthy"),
            ("parameters", "Parameters", "Primary market, timeframe, and season must be selected"),
            ("timeframe", "Timeframe Validity", "Timeframe must be in allowed list"),
            ("bars", "Bars Data", "Bar data must be ready for selected market/timeframe/season"),
            ("features", "Features Data", "Feature vectors must be pre‑computed"),
            ("registry", "Strategy Registry", "Registry must contain the selected strategy"),
            ("strategy", "Strategy Exists", "Selected strategy must exist in registry"),
        ]
        
        row = 0
        for key, label, description in self.prereq_order:
            # Icon label
            icon_label = QLabel()
            icon_label.setFixedSize(20, 20)
            icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.prereq_icons[key] = icon_label
            self.grid.addWidget(icon_label, row, 0)
            
            # Name label
            name_label = QLabel(label)
            name_label.setStyleSheet("color: #E6E6E6; font-weight: bold;")
            name_label.setToolTip(description)
            self.grid.addWidget(name_label, row, 1)
            
            # Reason label
            reason_label = QLabel("")
            reason_label.setStyleSheet("color: #9e9e9e; font-size: 10px;")
            reason_label.setWordWrap(True)
            self.prereq_labels[key] = reason_label
            self.grid.addWidget(reason_label, row, 2)
            
            row += 1
        
        # Add stretch row
        self.grid.setRowStretch(row, 1)
        
        # Summary label
        self.summary_label = QLabel("All prerequisites satisfied")
        self.summary_label.setStyleSheet("color: #4CAF50; font-weight: bold;")
        self.summary_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Add to group
        group_layout = QVBoxLayout(self.group)
        group_layout.addLayout(self.grid)
        group_layout.addWidget(self.summary_label)
        
        layout.addWidget(self.group)
    
    def update_readiness(self,
                         primary_market: Optional[str] = None,
                         timeframe: Optional[str] = None,
                         season: Optional[str] = None,
                         strategy_id: Optional[str] = None):
        """Update panel with new readiness state."""
        ready, _, missing = compute_ui_ready_state(
            primary_market=primary_market,
            timeframe=timeframe,
            season=season,
            strategy_id=strategy_id
        )
        
        self.current_ready = ready
        self.current_missing = missing
        
        # Update each prerequisite row
        for key, label, description in self.prereq_order:
            icon_label = self.prereq_icons[key]
            reason_label = self.prereq_labels[key]
            
            if key in missing:
                # Missing
                icon_label.setText("❌")
                icon_label.setStyleSheet("color: #F44336; font-size: 14px;")
                reason_label.setText(missing[key])
                reason_label.setStyleSheet("color: #F44336; font-size: 10px;")
            else:
                # Satisfied (or not applicable)
                icon_label.setText("✅")
                icon_label.setStyleSheet("color: #4CAF50; font-size: 14px;")
                reason_label.setText("Satisfied")
                reason_label.setStyleSheet("color: #9e9e9e; font-size: 10px;")
        
        # Update summary
        if ready:
            self.summary_label.setText("All prerequisites satisfied")
            self.summary_label.setStyleSheet("color: #4CAF50; font-weight: bold;")
        else:
            missing_count = len(missing)
            self.summary_label.setText(f"{missing_count} prerequisite(s) missing")
            self.summary_label.setStyleSheet("color: #FF9800; font-weight: bold;")
        
        # Emit signal
        self.readiness_changed.emit(ready, missing)
    
    def get_state(self):
        """Return current readiness state."""
        return self.current_ready, self.current_missing