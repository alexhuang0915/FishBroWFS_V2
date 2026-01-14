"""
Run Readiness Panel - Pre-flight summary with gate status.

Features:
- Shows DATA2 gate status (PASS, WARNING, FAIL)
- Displays strategy dependency information
- Shows dataset readiness status
- Visual indicators for gate outcomes
- Submission readiness check
"""

from typing import Optional, List, Dict, Any
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QFrame, QPushButton, QSizePolicy, QSpacerItem
)
from PySide6.QtGui import QFont, QColor

from gui.services.dataset_resolver import GateStatus, DerivedDatasets


class RunReadinessPanel(QWidget):
    """
    Pre-flight summary panel showing gate status and run readiness.
    
    Displays DATA2 gate evaluation, strategy dependency, and overall readiness.
    """
    
    # Signals
    readiness_changed = Signal(bool)  # True if ready for submission
    gate_status_changed = Signal(str)  # gate status: "PASS", "WARNING", "FAIL"
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.gate_status: Optional[GateStatus] = None
        self.derived_data: Optional[DerivedDatasets] = None
        self.strategy_requires_data2: bool = True
        self.is_ready: bool = False
        
        self.setup_ui()
        
    def setup_ui(self):
        """Initialize the UI components."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(8)
        
        # Header
        header_layout = QHBoxLayout()
        
        # Title
        title_label = QLabel("Run Readiness")
        title_label.setStyleSheet("""
            QLabel {
                font-weight: bold;
                font-size: 13px;
                color: #E6E6E6;
            }
        """)
        header_layout.addWidget(title_label)
        
        header_layout.addSpacerItem(QSpacerItem(20, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
        
        main_layout.addLayout(header_layout)
        
        # Status card
        self.status_card = QFrame()
        self.status_card.setStyleSheet("""
            QFrame {
                background-color: #252525;
                border: 2px solid #444444;
                border-radius: 6px;
            }
        """)
        
        status_layout = QVBoxLayout(self.status_card)
        status_layout.setContentsMargins(12, 12, 12, 12)
        status_layout.setSpacing(8)
        
        # Gate status row
        gate_row = QHBoxLayout()
        
        gate_label = QLabel("DATA2 Gate:")
        gate_label.setStyleSheet("""
            QLabel {
                font-weight: bold;
                font-size: 11px;
                color: #E6E6E6;
            }
        """)
        gate_row.addWidget(gate_label)
        
        self.gate_status_label = QLabel("Not evaluated")
        self.gate_status_label.setStyleSheet("""
            QLabel {
                font-weight: bold;
                font-size: 11px;
                color: #9E9E9E;
            }
        """)
        gate_row.addWidget(self.gate_status_label)
        
        gate_row.addSpacerItem(QSpacerItem(20, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
        
        status_layout.addLayout(gate_row)
        
        # Strategy dependency row
        dep_row = QHBoxLayout()
        
        dep_label = QLabel("Strategy requires DATA2:")
        dep_label.setStyleSheet("""
            QLabel {
                font-size: 10px;
                color: #B0B0B0;
            }
        """)
        dep_row.addWidget(dep_label)
        
        self.dep_value_label = QLabel("Unknown")
        self.dep_value_label.setStyleSheet("""
            QLabel {
                font-size: 10px;
                color: #9E9E9E;
                font-style: italic;
            }
        """)
        dep_row.addWidget(self.dep_value_label)
        
        dep_row.addSpacerItem(QSpacerItem(20, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
        
        status_layout.addLayout(dep_row)
        
        # DATA2 status row
        data2_row = QHBoxLayout()
        
        data2_label = QLabel("DATA2 Status:")
        data2_label.setStyleSheet("""
            QLabel {
                font-size: 10px;
                color: #B0B0B0;
            }
        """)
        data2_row.addWidget(data2_label)
        
        self.data2_status_label = QLabel("Unknown")
        self.data2_status_label.setStyleSheet("""
            QLabel {
                font-size: 10px;
                color: #9E9E9E;
                font-style: italic;
            }
        """)
        data2_row.addWidget(self.data2_status_label)
        
        data2_row.addSpacerItem(QSpacerItem(20, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum))
        
        status_layout.addLayout(data2_row)
        
        # Gate detail
        self.gate_detail_label = QLabel("Select strategy, instrument, and timeframe to evaluate DATA2 gate.")
        self.gate_detail_label.setWordWrap(True)
        self.gate_detail_label.setStyleSheet("""
            QLabel {
                color: #9A9A9A;
                font-size: 9px;
                font-style: italic;
                padding: 4px;
                background-color: #2A2A2A;
                border-radius: 4px;
            }
        """)
        status_layout.addWidget(self.gate_detail_label)
        
        main_layout.addWidget(self.status_card)
        
        # Readiness summary
        self.readiness_summary_label = QLabel("Configuration incomplete")
        self.readiness_summary_label.setStyleSheet("""
            QLabel {
                color: #FF9800;
                font-size: 11px;
                font-weight: bold;
            }
        """)
        main_layout.addWidget(self.readiness_summary_label)
        
        # Test submission button (for debugging)
        self.test_button = QPushButton("Test Readiness Check")
        self.test_button.setStyleSheet("""
            QPushButton {
                background-color: #424242;
                color: #E6E6E6;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 6px 12px;
                font-size: 10px;
            }
            QPushButton:hover {
                background-color: #555555;
                border: 1px solid #666666;
            }
            QPushButton:pressed {
                background-color: #333333;
            }
            QPushButton:disabled {
                background-color: #2A2A2A;
                color: #666666;
                border: 1px solid #444444;
            }
        """)
        self.test_button.clicked.connect(self._test_readiness)
        self.test_button.setVisible(False)  # Hidden by default, for debugging only
        main_layout.addWidget(self.test_button)
        
    def update_gate_status(self, gate_status: Optional[GateStatus], 
                          derived_data: Optional[DerivedDatasets],
                          strategy_requires_data2: bool = True):
        """Update the panel with gate evaluation results."""
        self.gate_status = gate_status
        self.derived_data = derived_data
        self.strategy_requires_data2 = strategy_requires_data2
        
        if not gate_status:
            self._clear_display()
            return
        
        # Update gate status with color
        status_text = gate_status.level
        status_color = self._get_gate_color(gate_status.level)
        self.gate_status_label.setText(status_text)
        self.gate_status_label.setStyleSheet(f"""
            QLabel {{
                font-weight: bold;
                font-size: 11px;
                color: {status_color};
            }}
        """)
        
        # Update strategy dependency
        dep_text = "Yes" if strategy_requires_data2 else "No"
        dep_color = "#FF9800" if strategy_requires_data2 else "#4CAF50"
        self.dep_value_label.setText(dep_text)
        self.dep_value_label.setStyleSheet(f"""
            QLabel {{
                font-size: 10px;
                color: {dep_color};
                font-weight: bold;
            }}
        """)
        
        # Update DATA2 status
        if derived_data and derived_data.data2_id:
            data2_status = derived_data.data2_status.value
            data2_color = self._get_dataset_status_color(data2_status)
            self.data2_status_label.setText(data2_status)
            self.data2_status_label.setStyleSheet(f"""
                QLabel {{
                    font-size: 10px;
                    color: {data2_color};
                    font-weight: bold;
                }}
            """)
        else:
            self.data2_status_label.setText("Not required")
            self.data2_status_label.setStyleSheet("""
                QLabel {
                    font-size: 10px;
                    color: #9E9E9E;
                    font-style: italic;
                }
            """)
        
        # Update gate detail
        self.gate_detail_label.setText(gate_status.detail)
        
        # Update border color based on gate status
        border_color = status_color
        self.status_card.setStyleSheet(f"""
            QFrame {{
                background-color: #252525;
                border: 2px solid {border_color};
                border-radius: 6px;
            }}
        """)
        
        # Update readiness
        self._update_readiness(gate_status)
        
        # Emit signals
        self.gate_status_changed.emit(gate_status.level)
        
    def _get_gate_color(self, gate_level: str) -> str:
        """Get color for a gate level."""
        color_map = {
            "PASS": "#4CAF50",    # green
            "WARNING": "#FF9800", # amber
            "FAIL": "#F44336",    # red
        }
        return color_map.get(gate_level, "#9E9E9E")
    
    def _get_dataset_status_color(self, status: str) -> str:
        """Get color for a dataset status."""
        color_map = {
            "READY": "#4CAF50",    # green
            "MISSING": "#F44336",  # red
            "STALE": "#FF9800",    # amber
            "UNKNOWN": "#9E9E9E",  # gray
        }
        return color_map.get(status, "#9E9E9E")
    
    def _update_readiness(self, gate_status: GateStatus):
        """Update readiness based on gate status."""
        # Determine if ready for submission
        if gate_status.level == "FAIL":
            self.is_ready = False
            self.readiness_summary_label.setText("❌ Blocked: DATA2 gate failed")
            self.readiness_summary_label.setStyleSheet("""
                QLabel {
                    color: #F44336;
                    font-size: 11px;
                    font-weight: bold;
                }
            """)
        elif gate_status.level == "WARNING":
            self.is_ready = True  # Can proceed with warning
            self.readiness_summary_label.setText("⚠️  Warning: DATA2 is stale (can proceed)")
            self.readiness_summary_label.setStyleSheet("""
                QLabel {
                    color: #FF9800;
                    font-size: 11px;
                    font-weight: bold;
                }
            """)
        elif gate_status.level == "PASS":
            self.is_ready = True
            self.readiness_summary_label.setText("✅ Ready: All gates passed")
            self.readiness_summary_label.setStyleSheet("""
                QLabel {
                    color: #4CAF50;
                    font-size: 11px;
                    font-weight: bold;
                }
            """)
        else:
            self.is_ready = False
            self.readiness_summary_label.setText("Configuration incomplete")
            self.readiness_summary_label.setStyleSheet("""
                QLabel {
                    color: #FF9800;
                    font-size: 11px;
                    font-weight: bold;
                }
            """)
        
        # Emit readiness signal
        self.readiness_changed.emit(self.is_ready)
    
    def _clear_display(self):
        """Clear the display."""
        self.gate_status_label.setText("Not evaluated")
        self.gate_status_label.setStyleSheet("""
            QLabel {
                font-weight: bold;
                font-size: 11px;
                color: #9E9E9E;
            }
        """)
        
        self.dep_value_label.setText("Unknown")
        self.dep_value_label.setStyleSheet("""
            QLabel {
                font-size: 10px;
                color: #9E9E9E;
                font-style: italic;
            }
        """)
        
        self.data2_status_label.setText("Unknown")
        self.data2_status_label.setStyleSheet("""
            QLabel {
                font-size: 10px;
                color: #9E9E9E;
                font-style: italic;
            }
        """)
        
        self.gate_detail_label.setText("Select strategy, instrument, and timeframe to evaluate DATA2 gate.")
        
        self.status_card.setStyleSheet("""
            QFrame {
                background-color: #252525;
                border: 2px solid #444444;
                border-radius: 6px;
            }
        """)
        
        self.readiness_summary_label.setText("Configuration incomplete")
        self.readiness_summary_label.setStyleSheet("""
            QLabel {
                color: #FF9800;
                font-size: 11px;
                font-weight: bold;
            }
        """)
        
        self.is_ready = False
        self.readiness_changed.emit(False)
    
    def is_ready_for_submission(self) -> bool:
        """Check if configuration is ready for submission."""
        return self.is_ready
    
    def get_gate_status(self) -> Optional[GateStatus]:
        """Get the current gate status."""
        return self.gate_status
    
    def _test_readiness(self):
        """Test function for debugging readiness checks."""
        # This would simulate different gate statuses for testing
        pass