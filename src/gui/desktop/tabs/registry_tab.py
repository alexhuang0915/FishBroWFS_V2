"""
Registry Tab - Desktop-only governance view.
Replaces legacy web UI "Registry" tab with direct backend access (no HTTP/localhost).
"""

import logging
from typing import List, Dict, Any

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QTableWidget, QTableWidgetItem,
    QGroupBox, QHeaderView, QMessageBox
)

from ..widgets.cleanup_dialog import CleanupDialog

logger = logging.getLogger(__name__)


class RegistryTab(QWidget):
    """Registry tab - strategy governance and artifact management."""
    
    # Signals for communication with main window
    log_signal = Signal(str)
    
    def __init__(self):
        super().__init__()
        self.setup_ui()
        self.setup_connections()
        self.refresh_registry()
    
    def setup_ui(self):
        """Initialize the UI components."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)
        
        # Header
        header_label = QLabel("Strategy Registry - Desktop Governance View")
        header_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        main_layout.addWidget(header_label)
        
        # Description
        desc_label = QLabel("Direct backend access to registry/portfolio store (no HTTP/localhost)")
        desc_label.setStyleSheet("font-size: 12px; color: #666;")
        main_layout.addWidget(desc_label)
        
        # Control buttons
        control_layout = QHBoxLayout()
        
        self.refresh_btn = QPushButton("🔄 Refresh")
        self.refresh_btn.setMinimumHeight(40)
        control_layout.addWidget(self.refresh_btn)
        
        self.promote_btn = QPushButton("💾 Promote Selected")
        self.promote_btn.setMinimumHeight(40)
        self.promote_btn.setEnabled(False)
        control_layout.addWidget(self.promote_btn)
        
        self.freeze_btn = QPushButton("❄️ Freeze Selected")
        self.freeze_btn.setMinimumHeight(40)
        self.freeze_btn.setEnabled(False)
        control_layout.addWidget(self.freeze_btn)
        
        self.remove_btn = QPushButton("🗑️ Remove Selected")
        self.remove_btn.setMinimumHeight(40)
        self.remove_btn.setEnabled(False)
        control_layout.addWidget(self.remove_btn)
        
        # Clean Up button
        self.cleanup_btn = QPushButton("🧹 Clean Up...")
        self.cleanup_btn.setMinimumHeight(40)
        self.cleanup_btn.setToolTip("Safe deletion tools for runs, artifacts, and cache")
        control_layout.addWidget(self.cleanup_btn)
        
        control_layout.addStretch()
        main_layout.addLayout(control_layout)
        
        # Registry table
        table_group = QGroupBox("Registered Strategies")
        table_layout = QVBoxLayout()
        
        self.registry_table = QTableWidget()
        self.registry_table.setColumnCount(6)
        self.registry_table.setHorizontalHeaderLabels([
            "Strategy ID", "Latest Artifact", "Net PnL", "Max DD", "Trades", "State"
        ])
        
        # Configure table with balanced column widths
        header = self.registry_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Interactive)  # Strategy ID: 25-35%
        header.setSectionResizeMode(1, QHeaderView.Interactive)  # Latest Artifact: 25-30%
        header.setSectionResizeMode(2, QHeaderView.Interactive)  # Net PnL: 10-15%
        header.setSectionResizeMode(3, QHeaderView.Interactive)  # Max DD: 10-15%
        header.setSectionResizeMode(4, QHeaderView.Interactive)  # Trades: 8-10%
        header.setSectionResizeMode(5, QHeaderView.Interactive)  # State: 8-10%
        
        # Set minimum sizes
        header.setMinimumSectionSize(60)
        
        # Set default sizes (will be adjusted on resize)
        self.registry_table.setColumnWidth(0, 250)  # Strategy ID
        self.registry_table.setColumnWidth(1, 200)  # Latest Artifact
        self.registry_table.setColumnWidth(2, 100)  # Net PnL
        self.registry_table.setColumnWidth(3, 100)  # Max DD
        self.registry_table.setColumnWidth(4, 80)   # Trades
        self.registry_table.setColumnWidth(5, 80)   # State
        
        self.registry_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.registry_table.setSelectionMode(QTableWidget.SingleSelection)
        
        table_layout.addWidget(self.registry_table)
        table_group.setLayout(table_layout)
        main_layout.addWidget(table_group)
        
        # Status bar
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("font-size: 11px; color: #666;")
        main_layout.addWidget(self.status_label)
    
    def setup_connections(self):
        """Connect signals and slots."""
        self.refresh_btn.clicked.connect(self.refresh_registry)
        self.promote_btn.clicked.connect(self.promote_selected)
        self.freeze_btn.clicked.connect(self.freeze_selected)
        self.remove_btn.clicked.connect(self.remove_selected)
        self.cleanup_btn.clicked.connect(self.open_cleanup_dialog)
        self.registry_table.itemSelectionChanged.connect(self.update_button_states)
    
    def log(self, message: str):
        """Append message to log."""
        self.log_signal.emit(message)
        self.status_label.setText(message)
    
    def refresh_registry(self):
        """Refresh registry data from backend."""
        self.log("Refreshing registry from backend...")
        
        # Clear table
        self.registry_table.setRowCount(0)
        
        try:
            # TODO: Replace with actual backend call
            # For now, use mock data
            strategies = self._get_mock_strategies()
            
            self.registry_table.setRowCount(len(strategies))
            
            for row, strategy in enumerate(strategies):
                # Strategy ID
                self.registry_table.setItem(row, 0, QTableWidgetItem(strategy["strategy_id"]))
                
                # Latest artifact
                self.registry_table.setItem(row, 1, QTableWidgetItem(strategy["latest_artifact"]))
                
                # Net PnL
                pnl_item = QTableWidgetItem(f"{strategy['net_pnl']:,.2f}")
                if strategy["net_pnl"] >= 0:
                    pnl_item.setForeground(Qt.darkGreen)
                else:
                    pnl_item.setForeground(Qt.darkRed)
                self.registry_table.setItem(row, 2, pnl_item)
                
                # Max DD
                dd_item = QTableWidgetItem(f"{strategy['max_dd']:,.2f}")
                dd_item.setForeground(Qt.darkRed)
                self.registry_table.setItem(row, 3, dd_item)
                
                # Trades
                self.registry_table.setItem(row, 4, QTableWidgetItem(str(strategy["trades"])))
                
                # State
                state_item = QTableWidgetItem(strategy["state"])
                if strategy["state"] == "ACTIVE":
                    state_item.setForeground(Qt.darkGreen)
                elif strategy["state"] == "INCUBATION":
                    state_item.setForeground(Qt.darkBlue)
                elif strategy["state"] == "FROZEN":
                    state_item.setForeground(Qt.darkGray)
                self.registry_table.setItem(row, 5, state_item)
            
            self.log(f"Loaded {len(strategies)} strategies")
            
        except Exception as e:
            self.log(f"ERROR: Failed to refresh registry: {e}")
            QMessageBox.critical(self, "Registry Error", f"Failed to load registry: {e}")
    
    def _get_mock_strategies(self) -> List[Dict[str, Any]]:
        """Get mock strategy data for development."""
        return [
            {
                "strategy_id": "S1_baseline",
                "latest_artifact": "artifact_20260103_123456",
                "net_pnl": 12500.50,
                "max_dd": -2500.75,
                "trades": 342,
                "state": "ACTIVE"
            },
            {
                "strategy_id": "S2_momentum",
                "latest_artifact": "artifact_20260102_234567",
                "net_pnl": 8500.25,
                "max_dd": -1800.30,
                "trades": 215,
                "state": "INCUBATION"
            },
            {
                "strategy_id": "S3_reversal",
                "latest_artifact": "artifact_20260101_345678",
                "net_pnl": -1200.75,
                "max_dd": -3500.50,
                "trades": 128,
                "state": "FROZEN"
            },
            {
                "strategy_id": "SMA_cross",
                "latest_artifact": "artifact_20251231_456789",
                "net_pnl": 3200.00,
                "max_dd": -950.25,
                "trades": 187,
                "state": "ACTIVE"
            }
        ]
    
    def update_button_states(self):
        """Update button states based on selection."""
        selected_rows = self.registry_table.selectionModel().selectedRows()
        has_selection = len(selected_rows) > 0
        
        self.promote_btn.setEnabled(has_selection)
        self.freeze_btn.setEnabled(has_selection)
        self.remove_btn.setEnabled(has_selection)
    
    def get_selected_strategy_id(self) -> str:
        """Get the strategy ID of the selected row."""
        selected_rows = self.registry_table.selectionModel().selectedRows()
        if not selected_rows:
            return ""
        
        row = selected_rows[0].row()
        item = self.registry_table.item(row, 0)  # Strategy ID column
        return item.text() if item else ""
    
    def promote_selected(self):
        """Promote selected strategy artifact."""
        strategy_id = self.get_selected_strategy_id()
        if not strategy_id:
            return
        
        reply = QMessageBox.question(
            self, "Confirm Promotion",
            f"Promote latest artifact for strategy '{strategy_id}'?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.log(f"Promoting strategy: {strategy_id}")
            # TODO: Call actual promote function
            self.log("Promotion would call portfolio.manager.promote_strategy()")
            QMessageBox.information(self, "Promotion", f"Strategy '{strategy_id}' promoted (placeholder)")
    
    def freeze_selected(self):
        """Freeze selected strategy."""
        strategy_id = self.get_selected_strategy_id()
        if not strategy_id:
            return
        
        reply = QMessageBox.question(
            self, "Confirm Freeze",
            f"Freeze strategy '{strategy_id}'?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.log(f"Freezing strategy: {strategy_id}")
            # TODO: Call actual freeze function
            self.log("Freeze would call portfolio.manager.freeze_strategy()")
            QMessageBox.information(self, "Freeze", f"Strategy '{strategy_id}' frozen (placeholder)")
            self.refresh_registry()
    
    def remove_selected(self):
        """Remove selected strategy from registry."""
        strategy_id = self.get_selected_strategy_id()
        if not strategy_id:
            return
        
        reply = QMessageBox.warning(
            self, "Confirm Removal",
            f"Remove strategy '{strategy_id}' from registry?\n\nThis action cannot be undone.",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.log(f"Removing strategy: {strategy_id}")
            # TODO: Call actual remove function
            self.log("Remove would call portfolio.manager.remove_strategy()")
            QMessageBox.information(self, "Removal", f"Strategy '{strategy_id}' removed (placeholder)")
            self.refresh_registry()
    
    def open_cleanup_dialog(self):
        """Open the cleanup dialog."""
        dialog = CleanupDialog(self)
        dialog.cleanup_performed.connect(self.on_cleanup_performed)
        dialog.exec()
    
    def on_cleanup_performed(self, audit_event: dict):
        """Handle cleanup completion."""
        scope = audit_event.get("scope", "unknown")
        item_count = audit_event.get("item_count", 0)
        self.log(f"Cleanup performed: {scope}, {item_count} items moved to trash")
        
        # Refresh registry since cleanup might have affected artifacts
        self.refresh_registry()