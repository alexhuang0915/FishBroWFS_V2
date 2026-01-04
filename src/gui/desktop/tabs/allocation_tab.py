"""
Allocation Tab - Portfolio allocation management.
"""

import logging
from typing import List, Dict, Any

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QGroupBox, QHeaderView, QMessageBox, QDoubleSpinBox,
    QSpinBox, QLineEdit
)

logger = logging.getLogger(__name__)


class AllocationTab(QWidget):
    """Allocation tab - portfolio weight and risk management."""
    
    # Signals for communication with main window
    log_signal = Signal(str)
    allocation_changed = Signal(dict)  # Emit audit event
    
    def __init__(self):
        super().__init__()
        self.setup_ui()
        self.setup_connections()
        self.refresh_allocation()
    
    def setup_ui(self):
        """Initialize the UI components."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)
        
        # Header
        header_label = QLabel("Portfolio Allocation")
        header_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        main_layout.addWidget(header_label)
        
        # Description
        desc_label = QLabel("Current allocation table with weight, risk budget, and limits")
        desc_label.setStyleSheet("font-size: 12px; color: #666;")
        main_layout.addWidget(desc_label)
        
        # Control buttons
        control_layout = QHBoxLayout()
        
        self.refresh_btn = QPushButton("🔄 Refresh")
        self.refresh_btn.setMinimumHeight(40)
        control_layout.addWidget(self.refresh_btn)
        
        self.rebalance_btn = QPushButton("⚖️ Rebalance")
        self.rebalance_btn.setMinimumHeight(40)
        self.rebalance_btn.setEnabled(False)
        control_layout.addWidget(self.rebalance_btn)
        
        self.apply_btn = QPushButton("✅ Apply Allocation")
        self.apply_btn.setMinimumHeight(40)
        self.apply_btn.setEnabled(False)
        control_layout.addWidget(self.apply_btn)
        
        control_layout.addStretch()
        main_layout.addLayout(control_layout)
        
        # Allocation table
        table_group = QGroupBox("Current Allocation")
        table_layout = QVBoxLayout()
        
        self.allocation_table = QTableWidget()
        self.allocation_table.setColumnCount(6)
        self.allocation_table.setHorizontalHeaderLabels([
            "Strategy ID", "Weight (%)", "Risk Budget", "Min Weight", "Max Weight", "Current Exposure"
        ])
        
        # Configure table with balanced column widths
        header = self.allocation_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Interactive)  # Strategy ID: 25-30%
        header.setSectionResizeMode(1, QHeaderView.Interactive)  # Weight: 10-15%
        header.setSectionResizeMode(2, QHeaderView.Interactive)  # Risk Budget: 15-20%
        header.setSectionResizeMode(3, QHeaderView.Interactive)  # Min Weight: 10-15%
        header.setSectionResizeMode(4, QHeaderView.Interactive)  # Max Weight: 10-15%
        header.setSectionResizeMode(5, QHeaderView.Interactive)  # Current Exposure: 15-20%
        
        # Set minimum sizes
        header.setMinimumSectionSize(60)
        
        # Set default sizes
        self.allocation_table.setColumnWidth(0, 200)  # Strategy ID
        self.allocation_table.setColumnWidth(1, 100)  # Weight
        self.allocation_table.setColumnWidth(2, 120)  # Risk Budget
        self.allocation_table.setColumnWidth(3, 100)  # Min Weight
        self.allocation_table.setColumnWidth(4, 100)  # Max Weight
        self.allocation_table.setColumnWidth(5, 120)  # Current Exposure
        
        self.allocation_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.allocation_table.setSelectionMode(QTableWidget.SingleSelection)
        
        table_layout.addWidget(self.allocation_table)
        table_group.setLayout(table_layout)
        main_layout.addWidget(table_group)
        
        # Edit panel
        edit_group = QGroupBox("Edit Allocation")
        edit_layout = QGridLayout()
        
        edit_layout.addWidget(QLabel("Strategy:"), 0, 0)
        self.edit_strategy_label = QLabel("None selected")
        edit_layout.addWidget(self.edit_strategy_label, 0, 1)
        
        edit_layout.addWidget(QLabel("Weight (%):"), 1, 0)
        self.weight_spin = QDoubleSpinBox()
        self.weight_spin.setRange(0.0, 100.0)
        self.weight_spin.setDecimals(2)
        self.weight_spin.setSingleStep(1.0)
        edit_layout.addWidget(self.weight_spin, 1, 1)
        
        edit_layout.addWidget(QLabel("Risk Budget:"), 2, 0)
        self.risk_spin = QDoubleSpinBox()
        self.risk_spin.setRange(0.0, 1000000.0)
        self.risk_spin.setDecimals(2)
        self.risk_spin.setPrefix("$")
        edit_layout.addWidget(self.risk_spin, 2, 1)
        
        edit_layout.addWidget(QLabel("Min Weight (%):"), 3, 0)
        self.min_weight_spin = QDoubleSpinBox()
        self.min_weight_spin.setRange(0.0, 100.0)
        self.min_weight_spin.setDecimals(2)
        edit_layout.addWidget(self.min_weight_spin, 3, 1)
        
        edit_layout.addWidget(QLabel("Max Weight (%):"), 4, 0)
        self.max_weight_spin = QDoubleSpinBox()
        self.max_weight_spin.setRange(0.0, 100.0)
        self.max_weight_spin.setDecimals(2)
        edit_layout.addWidget(self.max_weight_spin, 4, 1)
        
        # Update button
        self.update_btn = QPushButton("Update Selected")
        self.update_btn.setMinimumHeight(40)
        self.update_btn.setEnabled(False)
        edit_layout.addWidget(self.update_btn, 5, 0, 1, 2)
        
        edit_group.setLayout(edit_layout)
        main_layout.addWidget(edit_group)
        
        # Status bar
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("font-size: 11px; color: #666;")
        main_layout.addWidget(self.status_label)
    
    def setup_connections(self):
        """Connect signals and slots."""
        self.refresh_btn.clicked.connect(self.refresh_allocation)
        self.rebalance_btn.clicked.connect(self.rebalance_allocation)
        self.apply_btn.clicked.connect(self.apply_allocation)
        self.update_btn.clicked.connect(self.update_selected)
        self.allocation_table.itemSelectionChanged.connect(self.on_selection_changed)
        self.weight_spin.valueChanged.connect(self.on_edit_changed)
        self.risk_spin.valueChanged.connect(self.on_edit_changed)
        self.min_weight_spin.valueChanged.connect(self.on_edit_changed)
        self.max_weight_spin.valueChanged.connect(self.on_edit_changed)
    
    def log(self, message: str):
        """Append message to log."""
        self.log_signal.emit(message)
        self.status_label.setText(message)
    
    def refresh_allocation(self):
        """Refresh allocation data from backend."""
        self.log("Refreshing allocation from backend...")
        
        # Clear table
        self.allocation_table.setRowCount(0)
        
        try:
            # TODO: Replace with actual backend call
            # For now, use mock data
            allocations = self._get_mock_allocations()
            
            self.allocation_table.setRowCount(len(allocations))
            
            for row, alloc in enumerate(allocations):
                # Strategy ID
                self.allocation_table.setItem(row, 0, QTableWidgetItem(alloc["strategy_id"]))
                
                # Weight (%)
                weight_item = QTableWidgetItem(f"{alloc['weight']:.2f}%")
                self.allocation_table.setItem(row, 1, weight_item)
                
                # Risk Budget
                risk_item = QTableWidgetItem(f"${alloc['risk_budget']:,.2f}")
                self.allocation_table.setItem(row, 2, risk_item)
                
                # Min Weight
                min_item = QTableWidgetItem(f"{alloc['min_weight']:.2f}%")
                self.allocation_table.setItem(row, 3, min_item)
                
                # Max Weight
                max_item = QTableWidgetItem(f"{alloc['max_weight']:.2f}%")
                self.allocation_table.setItem(row, 4, max_item)
                
                # Current Exposure
                exposure_item = QTableWidgetItem(f"${alloc['current_exposure']:,.2f}")
                self.allocation_table.setItem(row, 5, exposure_item)
            
            self.log(f"Loaded {len(allocations)} allocation entries")
            
            # Update button states
            self.update_button_states()
            
        except Exception as e:
            self.log(f"ERROR: Failed to refresh allocation: {e}")
            QMessageBox.critical(self, "Allocation Error", f"Failed to load allocation: {e}")
    
    def _get_mock_allocations(self) -> List[Dict[str, Any]]:
        """Get mock allocation data for development."""
        return [
            {
                "strategy_id": "S1_baseline",
                "weight": 40.0,
                "risk_budget": 50000.0,
                "min_weight": 20.0,
                "max_weight": 60.0,
                "current_exposure": 42000.0
            },
            {
                "strategy_id": "S2_momentum",
                "weight": 30.0,
                "risk_budget": 35000.0,
                "min_weight": 15.0,
                "max_weight": 45.0,
                "current_exposure": 31500.0
            },
            {
                "strategy_id": "S3_reversal",
                "weight": 20.0,
                "risk_budget": 25000.0,
                "min_weight": 10.0,
                "max_weight": 30.0,
                "current_exposure": 21000.0
            },
            {
                "strategy_id": "SMA_cross",
                "weight": 10.0,
                "risk_budget": 15000.0,
                "min_weight": 5.0,
                "max_weight": 20.0,
                "current_exposure": 10500.0
            }
        ]
    
    def on_selection_changed(self):
        """Handle table selection change."""
        selected_rows = self.allocation_table.selectionModel().selectedRows()
        if not selected_rows:
            self.edit_strategy_label.setText("None selected")
            self.update_btn.setEnabled(False)
            return
        
        row = selected_rows[0].row()
        strategy_item = self.allocation_table.item(row, 0)
        weight_item = self.allocation_table.item(row, 1)
        risk_item = self.allocation_table.item(row, 2)
        min_item = self.allocation_table.item(row, 3)
        max_item = self.allocation_table.item(row, 4)
        
        if strategy_item:
            self.edit_strategy_label.setText(strategy_item.text())
            
            # Parse values from table items
            if weight_item:
                weight_text = weight_item.text().replace('%', '')
                try:
                    self.weight_spin.setValue(float(weight_text))
                except ValueError:
                    pass
            
            if risk_item:
                risk_text = risk_item.text().replace('$', '').replace(',', '')
                try:
                    self.risk_spin.setValue(float(risk_text))
                except ValueError:
                    pass
            
            if min_item:
                min_text = min_item.text().replace('%', '')
                try:
                    self.min_weight_spin.setValue(float(min_text))
                except ValueError:
                    pass
            
            if max_item:
                max_text = max_item.text().replace('%', '')
                try:
                    self.max_weight_spin.setValue(float(max_text))
                except ValueError:
                    pass
            
            self.update_btn.setEnabled(True)
    
    def on_edit_changed(self):
        """Handle edit control changes."""
        # Enable apply button if any allocation has been modified
        self.apply_btn.setEnabled(True)
    
    def update_button_states(self):
        """Update button states based on table content."""
        has_rows = self.allocation_table.rowCount() > 0
        self.rebalance_btn.setEnabled(has_rows)
    
    def update_selected(self):
        """Update selected row with edited values."""
        selected_rows = self.allocation_table.selectionModel().selectedRows()
        if not selected_rows:
            return
        
        row = selected_rows[0].row()
        
        # Update table items
        weight_item = QTableWidgetItem(f"{self.weight_spin.value():.2f}%")
        self.allocation_table.setItem(row, 1, weight_item)
        
        risk_item = QTableWidgetItem(f"${self.risk_spin.value():,.2f}")
        self.allocation_table.setItem(row, 2, risk_item)
        
        min_item = QTableWidgetItem(f"{self.min_weight_spin.value():.2f}%")
        self.allocation_table.setItem(row, 3, min_item)
        
        max_item = QTableWidgetItem(f"{self.max_weight_spin.value():.2f}%")
        self.allocation_table.setItem(row, 4, max_item)
        
        self.log(f"Updated allocation for {self.edit_strategy_label.text()}")
        self.apply_btn.setEnabled(True)
    
    def rebalance_allocation(self):
        """Rebalance allocation based on current strategy performance."""
        reply = QMessageBox.question(
            self, "Confirm Rebalance",
            "Rebalance allocation based on current strategy performance?\n\nThis will calculate optimal weights using risk parity.",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.log("Rebalancing allocation...")
            # TODO: Call actual rebalance function
            self.log("Rebalance would call portfolio.manager.rebalance_allocation()")
            QMessageBox.information(self, "Rebalance", "Allocation rebalanced (placeholder)")
            self.refresh_allocation()
    
    def apply_allocation(self):
        """Apply allocation changes to backend."""
        reply = QMessageBox.question(
            self, "Confirm Apply",
            "Apply allocation changes to portfolio?\n\nThis will emit an audit event.",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.log("Applying allocation changes...")
            
            # Collect allocation data from table
            allocations = []
            for row in range(self.allocation_table.rowCount()):
                strategy_item = self.allocation_table.item(row, 0)
                weight_item = self.allocation_table.item(row, 1)
                risk_item = self.allocation_table.item(row, 2)
                min_item = self.allocation_table.item(row, 3)
                max_item = self.allocation_table.item(row, 4)
                
                if all([strategy_item, weight_item, risk_item, min_item, max_item]):
                    try:
                        weight = float(weight_item.text().replace('%', ''))
                        risk = float(risk_item.text().replace('$', '').replace(',', ''))
                        min_weight = float(min_item.text().replace('%', ''))
                        max_weight = float(max_item.text().replace('%', ''))
                        
                        allocations.append({
                            "strategy_id": strategy_item.text(),
                            "weight": weight,
                            "risk_budget": risk,
                            "min_weight": min_weight,
                            "max_weight": max_weight
                        })
                    except ValueError:
                        continue
            
            # Emit audit event
            audit_event = {
                "event_type": "allocation_change",
                "timestamp": "2026-01-03T12:00:00Z",  # TODO: Use actual timestamp
                "allocations": allocations
            }
            self.allocation_changed.emit(audit_event)
            
            # TODO: Call actual apply function
            self.log("Apply would call portfolio.manager.apply_allocation()")
            QMessageBox.information(self, "Apply", "Allocation applied (placeholder)")
            
            # Reset apply button
            self.apply_btn.setEnabled(False)