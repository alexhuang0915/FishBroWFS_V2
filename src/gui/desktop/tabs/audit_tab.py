"""
Audit Tab - Phase C Professional CTA Desktop UI.

Report Center with StrategyReportV1 and PortfolioReportV1 viewers.
Layout: QSplitter horizontal with Report Explorer (left) and Report Viewer (right).
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

from PySide6.QtCore import Qt, Signal, Slot, QModelIndex, QAbstractItemModel, QSortFilterProxyModel
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout,
    QLabel, QPushButton, QTableView, QTreeView, QSplitter,
    QGroupBox, QScrollArea, QHeaderView, QSizePolicy,
    QTabWidget, QTextEdit, QLineEdit, QComboBox,
    QApplication, QMessageBox, QStackedWidget,
    QTreeWidget, QTreeWidgetItem, QAbstractItemView
)
from PySide6.QtGui import QFont, QColor, QAction, QDesktopServices

from ..widgets.metric_cards import MetricCard, MetricRow
from ..widgets.report_host import ReportHostWidget
from ..widgets.charts.line_chart import LineChartWidget
from ..widgets.charts.heatmap import HeatmapWidget
from ..widgets.charts.histogram import HistogramWidget
from ..widgets.report_widgets.strategy_report_widget import StrategyReportWidget
from ..widgets.report_widgets.portfolio_report_widget import PortfolioReportWidget
from ...services.supervisor_client import (
    get_jobs, get_strategy_report_v1, get_portfolio_report_v1,
    SupervisorClientError
)

logger = logging.getLogger(__name__)


class ReportExplorerModel(QAbstractItemModel):
    """Tree model for report explorer."""
    
    def __init__(self):
        super().__init__()
        self.root_item = {
            'name': 'Reports',
            'children': [
                {'name': 'Strategy Reports', 'type': 'category', 'children': []},
                {'name': 'Portfolio Reports', 'type': 'category', 'children': []}
            ]
        }
        self.strategy_reports = []
        self.portfolio_reports = []
    
    def refresh(self):
        """Refresh report data from supervisor."""
        try:
            # Get jobs with reports
            jobs = get_jobs(limit=100)
            self.strategy_reports = []
            
            for job in jobs:
                artifacts = job.get("artifacts", {})
                links = artifacts.get("links", {})
                if links.get("strategy_report_v1_url"):
                    self.strategy_reports.append({
                        'name': f"{job.get('strategy_id', 'Unknown')} - {job.get('job_id', '')[:8]}",
                        'type': 'strategy_report',
                        'job_id': job.get('job_id'),
                        'created_at': job.get('created_at'),
                        'status': job.get('status')
                    })
            
            # TODO: Get portfolio reports from API when endpoint exists
            # For now, use mock portfolio reports
            self.portfolio_reports = [
                {'name': 'Portfolio_2026Q1', 'type': 'portfolio_report', 'portfolio_id': 'portfolio_2026q1'},
                {'name': 'Portfolio_2025Q4', 'type': 'portfolio_report', 'portfolio_id': 'portfolio_2025q4'},
            ]
            
            self.update_tree()
            
        except SupervisorClientError as e:
            logger.error(f"Failed to refresh reports: {e}")
    
    def update_tree(self):
        """Update tree structure with current reports."""
        self.beginResetModel()
        
        # Update strategy reports
        strategy_category = self.root_item['children'][0]
        strategy_category['children'] = self.strategy_reports
        
        # Update portfolio reports
        portfolio_category = self.root_item['children'][1]
        portfolio_category['children'] = self.portfolio_reports
        
        self.endResetModel()
    
    def index(self, row: int, column: int, parent=QModelIndex()):
        if not self.hasIndex(row, column, parent):
            return QModelIndex()
        
        if not parent.isValid():
            parent_item = self.root_item
        else:
            parent_item = parent.internalPointer()
        
        if 'children' in parent_item and row < len(parent_item['children']):
            child_item = parent_item['children'][row]
            return self.createIndex(row, column, child_item)
        
        return QModelIndex()
    
    def parent(self, index: QModelIndex):
        if not index.isValid():
            return QModelIndex()
        
        child_item = index.internalPointer()
        
        # Find parent of this item
        def find_parent(current_item, target_item):
            if 'children' in current_item:
                for i, child in enumerate(current_item['children']):
                    if child is target_item:
                        return current_item, i
                    result = find_parent(child, target_item)
                    if result[0]:
                        return result
            return None, -1
        
        parent_item, row = find_parent(self.root_item, child_item)
        if parent_item:
            return self.createIndex(row, 0, parent_item)
        
        return QModelIndex()
    
    def rowCount(self, parent=QModelIndex()):
        if parent.column() > 0:
            return 0
        
        if not parent.isValid():
            parent_item = self.root_item
        else:
            parent_item = parent.internalPointer()
        
        return len(parent_item.get('children', []))
    
    def columnCount(self, parent=QModelIndex()):
        return 1
    
    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        
        item = index.internalPointer()
        
        if role == Qt.DisplayRole:
            return item.get('name', '')
        
        elif role == Qt.DecorationRole:
            # TODO: Add icons for different report types
            pass
        
        elif role == Qt.ForegroundRole:
            item_type = item.get('type', '')
            if item_type == 'category':
                return QColor("#4A90E2")
            elif item_type == 'strategy_report':
                return QColor("#50E3C2")
            elif item_type == 'portfolio_report':
                return QColor("#F5A623")
        
        elif role == Qt.FontRole:
            item_type = item.get('type', '')
            if item_type == 'category':
                font = QFont()
                font.setBold(True)
                return font
        
        return None
    
    def get_item_data(self, index: QModelIndex) -> Optional[Dict[str, Any]]:
        """Get data for the item at index."""
        if not index.isValid():
            return None
        
        item = index.internalPointer()
        return item




class AuditTab(QWidget):
    """Audit Tab - Phase C Professional CTA Report Center."""
    
    # Signals for communication with main window
    log_signal = Signal(str)
    
    def __init__(self):
        super().__init__()
        self.report_explorer_model = ReportExplorerModel()
        self.open_reports = {}  # job_id/portfolio_id -> widget
        self.setup_ui()
        self.setup_connections()
        self.refresh_reports()
    
    def setup_ui(self):
        """Initialize the UI components with QSplitter layout."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)
        
        # Create main splitter
        main_splitter = QSplitter(Qt.Horizontal)
        main_splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #555555;
                width: 1px;
            }
            QSplitter::handle:hover {
                background-color: #3A8DFF;
            }
        """)
        
        # Left panel: Report Explorer
        left_widget = QWidget()
        left_widget.setStyleSheet("background-color: #121212;")
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(4, 4, 4, 4)
        left_layout.setSpacing(8)
        
        # Report Explorer group
        explorer_group = QGroupBox("Report Explorer")
        explorer_group.setStyleSheet("""
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
        
        # Control buttons
        control_layout = QHBoxLayout()
        
        self.refresh_btn = QPushButton("🔄 Refresh")
        self.refresh_btn.setToolTip("Refresh report list")
        control_layout.addWidget(self.refresh_btn)
        
        self.load_portfolio_btn = QPushButton("📊 Load Portfolio")
        self.load_portfolio_btn.setToolTip("Load portfolio report by ID")
        control_layout.addWidget(self.load_portfolio_btn)
        
        control_layout.addStretch()
        left_layout.addLayout(control_layout)
        
        # Portfolio ID input (for manual loading)
        portfolio_layout = QHBoxLayout()
        portfolio_layout.addWidget(QLabel("Portfolio ID:"))
        
        self.portfolio_id_input = QLineEdit()
        self.portfolio_id_input.setPlaceholderText("Enter portfolio ID...")
        portfolio_layout.addWidget(self.portfolio_id_input)
        
        self.load_specific_btn = QPushButton("Load")
        self.load_specific_btn.setToolTip("Load specific portfolio report")
        portfolio_layout.addWidget(self.load_specific_btn)
        
        left_layout.addLayout(portfolio_layout)
        
        # Tree view for reports
        self.report_tree = QTreeView()
        self.report_tree.setModel(self.report_explorer_model)
        self.report_tree.setHeaderHidden(True)
        self.report_tree.setStyleSheet("""
            QTreeView {
                background-color: #1E1E1E;
                color: #E6E6E6;
                font-size: 11px;
                border: 1px solid #333333;
            }
            QTreeView::item {
                padding: 4px;
            }
            QTreeView::item:selected {
                background-color: #2a2a2a;
                color: #FFFFFF;
            }
            QTreeView::item:hover {
                background-color: #333333;
            }
        """)
        self.report_tree.setExpandsOnDoubleClick(True)
        self.report_tree.expandAll()
        
        left_layout.addWidget(self.report_tree)
        
        # Add explorer group to left panel
        explorer_layout = QVBoxLayout(explorer_group)
        explorer_layout.addWidget(self.report_tree)
        left_layout.addWidget(explorer_group)
        
        # Right panel: Report Viewer
        right_widget = QWidget()
        right_widget.setStyleSheet("background-color: #121212;")
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(4, 4, 4, 4)
        right_layout.setSpacing(8)
        
        # Report Viewer group
        viewer_group = QGroupBox("Report Viewer")
        viewer_group.setStyleSheet("""
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
        
        # Tab widget for multiple reports
        self.report_tabs = QTabWidget()
        self.report_tabs.setTabsClosable(True)
        self.report_tabs.setMovable(True)
        self.report_tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #333333;
                background-color: #1E1E1E;
            }
            QTabBar::tab {
                background-color: #2a2a2a;
                color: #E6E6E6;
                padding: 8px 16px;
                margin-right: 2px;
                border: 1px solid #333333;
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }
            QTabBar::tab:selected {
                background-color: #0288D1;
                color: white;
            }
            QTabBar::tab:hover {
                background-color: #333333;
            }
            QTabBar::close-button {
                image: none;
                subcontrol-position: right;
                padding: 2px;
            }
            QTabBar::close-button:hover {
                background-color: #F44336;
                border-radius: 2px;
            }
        """)
        
        viewer_layout = QVBoxLayout(viewer_group)
        viewer_layout.addWidget(self.report_tabs)
        right_layout.addWidget(viewer_group)
        
        # Status label
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("color: #9e9e9e; font-size: 10px;")
        right_layout.addWidget(self.status_label)
        
        # Add panels to splitter
        main_splitter.addWidget(left_widget)
        main_splitter.addWidget(right_widget)
        main_splitter.setSizes([300, 700])  # 30% left, 70% right
        
        # Add splitter to main layout
        main_layout.addWidget(main_splitter)
    
    def setup_connections(self):
        """Connect signals and slots."""
        self.refresh_btn.clicked.connect(self.refresh_reports)
        self.load_portfolio_btn.clicked.connect(self.load_portfolio_report)
        self.load_specific_btn.clicked.connect(self.load_specific_portfolio)
        self.report_tree.doubleClicked.connect(self.on_report_double_clicked)
        self.report_tabs.tabCloseRequested.connect(self.close_report_tab)
    
    def refresh_reports(self):
        """Refresh report explorer data."""
        try:
            self.status_label.setText("Refreshing reports...")
            self.report_explorer_model.refresh()
            self.report_tree.expandAll()
            self.status_label.setText(f"Reports refreshed")
            self.log_signal.emit("Report explorer refreshed")
            
        except Exception as e:
            self.status_label.setText(f"Error: {e}")
            logger.error(f"Failed to refresh reports: {e}")
    
    def on_report_double_clicked(self, index: QModelIndex):
        """Handle double-click on report item."""
        item_data = self.report_explorer_model.get_item_data(index)
        if not item_data:
            return
        
        item_type = item_data.get('type', '')
        
        if item_type == 'strategy_report':
            job_id = item_data.get('job_id')
            if job_id:
                self.load_strategy_report(job_id)
        
        elif item_type == 'portfolio_report':
            portfolio_id = item_data.get('portfolio_id')
            if portfolio_id:
                self.load_portfolio_report_by_id(portfolio_id)
    
    def load_strategy_report(self, job_id: str):
        """Load and display strategy report."""
        try:
            self.status_label.setText(f"Loading strategy report {job_id[:8]}...")
            
            # Check if already open
            tab_key = f"strategy_{job_id}"
            if tab_key in self.open_reports:
                # Switch to existing tab
                widget = self.open_reports[tab_key]
                index = self.report_tabs.indexOf(widget)
                if index >= 0:
                    self.report_tabs.setCurrentIndex(index)
                self.status_label.setText(f"Report already open")
                return
            
            # Fetch report from supervisor
            report_data = get_strategy_report_v1(job_id)
            if not report_data:
                QMessageBox.warning(self, "Report Not Found", f"No strategy report found for job {job_id}")
                self.status_label.setText(f"Report not found")
                return
            
            # Create widget
            widget = StrategyReportWidget(job_id, report_data)
            tab_title = f"Strategy: {report_data.get('meta', {}).get('strategy_name', 'Unknown')}"
            
            # Add to tabs
            index = self.report_tabs.addTab(widget, tab_title)
            self.report_tabs.setCurrentIndex(index)
            
            # Store reference
            self.open_reports[tab_key] = widget
            
            self.status_label.setText(f"Strategy report loaded")
            self.log_signal.emit(f"Loaded strategy report for job {job_id}")
            
        except SupervisorClientError as e:
            QMessageBox.critical(self, "Report Error", f"Failed to load strategy report: {e}")
            self.status_label.setText(f"Error: {e}")
            logger.error(f"Failed to load strategy report {job_id}: {e}")
    
    def load_portfolio_report(self):
        """Load default portfolio report."""
        # For now, load a mock portfolio
        self.load_portfolio_report_by_id("portfolio_2026q1")
    
    def load_specific_portfolio(self):
        """Load portfolio report by ID from input."""
        portfolio_id = self.portfolio_id_input.text().strip()
        if not portfolio_id:
            QMessageBox.warning(self, "Input Required", "Please enter a portfolio ID")
            return
        
        self.load_portfolio_report_by_id(portfolio_id)
    
    def load_portfolio_report_by_id(self, portfolio_id: str):
        """Load and display portfolio report by ID."""
        try:
            self.status_label.setText(f"Loading portfolio report {portfolio_id}...")
            
            # Check if already open
            tab_key = f"portfolio_{portfolio_id}"
            if tab_key in self.open_reports:
                # Switch to existing tab
                widget = self.open_reports[tab_key]
                index = self.report_tabs.indexOf(widget)
                if index >= 0:
                    self.report_tabs.setCurrentIndex(index)
                self.status_label.setText(f"Report already open")
                return
            
            # Fetch report from supervisor
            report_data = get_portfolio_report_v1(portfolio_id)
            if not report_data:
                QMessageBox.warning(self, "Report Not Found", f"No portfolio report found for ID {portfolio_id}")
                self.status_label.setText(f"Report not found")
                return
            
            # Create widget (pass both portfolio_id and report_data)
            widget = PortfolioReportWidget(portfolio_id, report_data)
            tab_title = f"Portfolio: {portfolio_id}"
            
            # Add to tabs
            index = self.report_tabs.addTab(widget, tab_title)
            self.report_tabs.setCurrentIndex(index)
            
            # Store reference
            self.open_reports[tab_key] = widget
            
            self.status_label.setText(f"Portfolio report loaded")
            self.log_signal.emit(f"Loaded portfolio report {portfolio_id}")
            
        except SupervisorClientError as e:
            QMessageBox.critical(self, "Report Error", f"Failed to load portfolio report: {e}")
            self.status_label.setText(f"Error: {e}")
            logger.error(f"Failed to load portfolio report {portfolio_id}: {e}")
    
    def close_report_tab(self, index: int):
        """Close a report tab."""
        widget = self.report_tabs.widget(index)
        if widget:
            # Find and remove from open_reports
            for key, w in list(self.open_reports.items()):
                if w is widget:
                    del self.open_reports[key]
                    break
            
            # Remove tab
            self.report_tabs.removeTab(index)
            
            # Clean up widget
            widget.deleteLater()
    
    def open_strategy_report(self, job_id: str):
        """Public method to open a strategy report (called from OP tab)."""
        self.load_strategy_report(job_id)
        
        # Ensure Audit tab is visible (signal main window)
        # This will be handled by main window switching to this tab
    
    def log(self, message: str):
        """Append message to log."""
        self.log_signal.emit(message)
        self.status_label.setText(message)