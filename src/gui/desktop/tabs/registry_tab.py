"""
Registry Tab - Phase C Professional CTA Desktop UI.

Searchable table of registry strategies from Supervisor API.
"""

import logging
from typing import Optional, List, Dict, Any

from PySide6.QtCore import Qt, Signal, Slot, QModelIndex, QAbstractTableModel, QSortFilterProxyModel  # type: ignore
from PySide6.QtWidgets import (  # type: ignore
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QTableView, QLineEdit,
    QGroupBox, QHeaderView, QMessageBox, QComboBox,
    QApplication
)
from PySide6.QtGui import QFont, QColor, QAction  # type: ignore

from ...services.supervisor_client import (
    get_registry_strategies, SupervisorClientError
)

logger = logging.getLogger(__name__)


class RegistryTableModel(QAbstractTableModel):
    """Table model for displaying registry strategies."""
    
    def __init__(self):
        super().__init__()
        self.strategies: List[Dict[str, Any]] = list()
        self.headers = [
            "Strategy ID", "Name", "Verification", "File Path", "Type"
        ]
    
    def refresh(self):
        """Refresh registry data from supervisor."""
        try:
            strategies = get_registry_strategies()
            self.set_strategies(strategies)
            
        except SupervisorClientError as e:
            logger.error(f"Failed to refresh registry: {e}")
            raise
    
    def set_strategies(self, strategies: List[Dict[str, Any]]):
        """Set strategies data and update table."""
        self.beginResetModel()
        
        # Normalize strategies data
        self.strategies = list()
        for strategy in strategies:
            if isinstance(strategy, dict):
                self.strategies.append({
                    'id': strategy.get('id', ''),
                    'name': strategy.get('name', ''),
                    'verification': strategy.get('verification_status', 'unknown'),
                    'file_path': strategy.get('file_path', ''),
                    'type': strategy.get('type', 'unknown')
                })
            else:
                # If API returns simple strings
                self.strategies.append({
                    'id': str(strategy),
                    'name': str(strategy),
                    'verification': 'unknown',
                    'file_path': '',
                    'type': 'unknown'
                })
        
        self.endResetModel()
    
    def rowCount(self, parent=QModelIndex()):
        return len(self.strategies)
    
    def columnCount(self, parent=QModelIndex()):
        return len(self.headers)
    
    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        
        row = index.row()
        col = index.column()
        
        if row >= len(self.strategies):
            return None
        
        strategy = self.strategies[row]
        
        if role == Qt.ItemDataRole.DisplayRole:
            if col == 0:  # Strategy ID
                return strategy.get('id', '')
            elif col == 1:  # Name
                return strategy.get('name', '')
            elif col == 2:  # Verification
                return strategy.get('verification', 'unknown')
            elif col == 3:  # File Path
                return strategy.get('file_path', '')
            elif col == 4:  # Type
                return strategy.get('type', 'unknown')
        
        elif role == Qt.ItemDataRole.ForegroundRole:
            if col == 2:  # Verification column
                verification = strategy.get('verification', '').lower()
                if verification == 'verified':
                    return QColor("#4CAF50")
                elif verification == 'pending':
                    return QColor("#FF9800")
                elif verification == 'failed':
                    return QColor("#F44336")
                else:
                    return QColor("#9A9A9A")
        
        elif role == Qt.ItemDataRole.FontRole:
            if col == 0:  # Strategy ID column
                font = QFont()
                font.setBold(True)
                return font
        
        elif role == Qt.ItemDataRole.ToolTipRole:
            if col == 3:  # File Path
                file_path = strategy.get('file_path', '')
                if file_path:
                    return f"File: {file_path}"
        
        return None
    
    def headerData(self, section: int, orientation: Qt.Orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            if section < len(self.headers):
                return self.headers[section]
        return None


class RegistryTab(QWidget):
    """Registry Tab - Phase C Professional CTA UI."""
    
    # Signals for communication with main window
    log_signal = Signal(str)
    
    def __init__(self):
        super().__init__()
        self.registry_model = RegistryTableModel()
        self.filter_proxy = QSortFilterProxyModel()
        self.filter_proxy.setSourceModel(self.registry_model)
        self.filter_proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        
        self.setup_ui()
        self.setup_connections()
        self.refresh_registry()
    
    def setup_ui(self):
        """Initialize the UI components."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)
        
        # Header
        header_label = QLabel("Strategy Registry")
        header_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #E6E6E6;")
        main_layout.addWidget(header_label)
        
        # Description
        desc_label = QLabel("Searchable table of registered strategies from Supervisor API")
        desc_label.setStyleSheet("font-size: 12px; color: #9e9e9e;")
        main_layout.addWidget(desc_label)
        
        # Control panel
        control_group = QGroupBox("Controls")
        control_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 2px solid #7B1FA2;
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
        
        control_layout = QHBoxLayout()
        
        # Search bar
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("Search:"))
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search strategies...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.setStyleSheet("""
            QLineEdit {
                background-color: #2a2a2a;
                color: #E6E6E6;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 6px;
                font-size: 12px;
            }
            QLineEdit:focus {
                border: 1px solid #3A8DFF;
            }
        """)
        search_layout.addWidget(self.search_input)
        
        # Filter by verification
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Verification:"))
        
        self.verification_filter = QComboBox()
        self.verification_filter.addItems(["All", "Verified", "Pending", "Failed", "Unknown"])
        self.verification_filter.setStyleSheet("""
            QComboBox {
                background-color: #2a2a2a;
                color: #E6E6E6;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 6px;
                font-size: 12px;
                min-width: 120px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #E6E6E6;
            }
        """)
        filter_layout.addWidget(self.verification_filter)
        
        # Refresh button
        self.refresh_btn = QPushButton("🔄 Refresh")
        self.refresh_btn.setToolTip("Refresh registry data")
        self.refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #2a2a2a;
                color: #E6E6E6;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 8px 16px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #333333;
                border: 1px solid #3A8DFF;
            }
            QPushButton:pressed {
                background-color: #1a1a1a;
            }
        """)
        
        control_layout.addLayout(search_layout)
        control_layout.addSpacing(20)
        control_layout.addLayout(filter_layout)
        control_layout.addStretch()
        control_layout.addWidget(self.refresh_btn)
        
        control_group.setLayout(control_layout)
        main_layout.addWidget(control_group)
        
        # Registry table
        table_group = QGroupBox("Registered Strategies")
        table_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 2px solid #0288D1;
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
        
        table_layout = QVBoxLayout()
        
        self.registry_table = QTableView()
        self.registry_table.setModel(self.filter_proxy)
        self.registry_table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.registry_table.setSelectionMode(QTableView.SelectionMode.SingleSelection)
        self.registry_table.setAlternatingRowColors(True)
        self.registry_table.setSortingEnabled(True)
        self.registry_table.setStyleSheet("""
            QTableView {
                background-color: #1E1E1E;
                alternate-background-color: #252525;
                gridline-color: #333333;
                color: #E6E6E6;
                font-size: 11px;
            }
            QTableView::item {
                padding: 4px;
            }
            QTableView::item:selected {
                background-color: #2a2a2a;
                color: #FFFFFF;
            }
            QHeaderView::section {
                background-color: #2a2a2a;
                color: #E6E6E6;
                padding: 6px;
                border: 1px solid #333333;
                font-weight: bold;
            }
            QHeaderView::section:checked {
                background-color: #3A8DFF;
            }
        """)
        
        # Configure column widths
        header = self.registry_table.horizontalHeader()
        header.setStretchLastSection(True)
        self.registry_table.setColumnWidth(0, 200)  # Strategy ID
        self.registry_table.setColumnWidth(1, 150)  # Name
        self.registry_table.setColumnWidth(2, 100)  # Verification
        self.registry_table.setColumnWidth(3, 300)  # File Path
        self.registry_table.setColumnWidth(4, 80)   # Type
        
        table_layout.addWidget(self.registry_table)
        table_group.setLayout(table_layout)
        main_layout.addWidget(table_group)

        main_layout.addWidget(table_group)
        
        # Status bar
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: #9e9e9e; font-size: 10px;")
        main_layout.addWidget(self.status_label)
    
    def setup_connections(self):
        """Connect signals and slots."""
        self.refresh_btn.clicked.connect(self.refresh_registry)
        self.search_input.textChanged.connect(self.on_search_changed)
        self.verification_filter.currentTextChanged.connect(self.on_filter_changed)
    
    def refresh_registry(self):
        """Refresh registry data from supervisor."""
        try:
            self.status_label.setText("Refreshing registry...")
            QApplication.processEvents()
            
            self.registry_model.refresh()
            
            count = self.registry_model.rowCount()
            self.status_label.setText(f"Loaded {count} strategies")
            self.log_signal.emit(f"Registry refreshed: {count} strategies")
            
        except SupervisorClientError as e:
            error_msg = f"Failed to refresh registry: {e}"
            self.status_label.setText(f"Error: {e}")
            QMessageBox.critical(self, "Registry Error", error_msg)
            logger.error(error_msg)
        except Exception as e:
            error_msg = f"Unexpected error: {e}"
            self.status_label.setText(f"Error: {e}")
            QMessageBox.critical(self, "Registry Error", error_msg)
            logger.error(error_msg)
    
    def on_search_changed(self, text: str):
        """Handle search text change."""
        self.filter_proxy.setFilterFixedString(text)
        
        # Update status
        visible_count = self.filter_proxy.rowCount()
        total_count = self.registry_model.rowCount()
        if text:
            self.status_label.setText(f"Showing {visible_count} of {total_count} strategies (filtered)")
        else:
            self.status_label.setText(f"Showing all {total_count} strategies")
    
    def on_filter_changed(self, filter_text: str):
        """Handle verification filter change."""
        if filter_text == "All":
            self.filter_proxy.setFilterRegExp("")
        else:
            # Filter by verification status (case-insensitive)
            self.filter_proxy.setFilterFixedString(filter_text)
        
        # Update status
        visible_count = self.filter_proxy.rowCount()
        total_count = self.registry_model.rowCount()
        if filter_text != "All":
            self.status_label.setText(f"Showing {visible_count} strategies ({filter_text.lower()})")
        else:
            self.status_label.setText(f"Showing all {total_count} strategies")

    
    def log(self, message: str):
        """Append message to log."""
        self.log_signal.emit(message)
        self.status_label.setText(message)
    
    def get_selected_strategy(self) -> Optional[Dict[str, Any]]:
        """Get the selected strategy data."""
        selected = self.registry_table.selectionModel().selectedRows()
        if not selected:
            return None
        
        proxy_index = selected[0]
        source_index = self.filter_proxy.mapToSource(proxy_index)
        row = source_index.row()
        
        if 0 <= row < self.registry_model.rowCount():
            return self.registry_model.strategies[row]
        
        return None