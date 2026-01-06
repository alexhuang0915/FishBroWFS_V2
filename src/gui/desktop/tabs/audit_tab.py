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
    get_outputs_summary, SupervisorClientError
)

logger = logging.getLogger(__name__)


class ReportExplorerModel(QAbstractItemModel):
    """Tree model for report explorer using outputs summary."""
    
    def __init__(self):
        super().__init__()
        self.root_item = {
            'name': 'Reports',
            'type': 'root',
            'children': [
                {'name': 'Strategy Runs', 'type': 'category', 'children': []},
                {'name': 'Portfolios', 'type': 'category', 'children': []}
            ]
        }
        self.all_items = []  # Flat list of all items for filtering
        self.filter_text = ""
        self.filter_type = "all"  # "jobs", "portfolios", "all"
    
    def refresh(self):
        """Refresh report data from supervisor outputs summary."""
        try:
            # Get outputs summary from supervisor
            summary = get_outputs_summary()
            
            # Clear existing data
            self.all_items = []
            
            # Process jobs
            jobs_category = self.root_item['children'][0]
            jobs_category['children'] = []
            
            for job in summary.get('jobs', {}).get('recent', []):
                # Create human-readable label
                status = job.get('status', 'UNKNOWN')
                strategy_name = job.get('strategy_name', 'Unknown')
                instrument = job.get('instrument', 'Unknown')
                timeframe = job.get('timeframe', 0)
                season = job.get('season', 'Unknown')
                short_id = job.get('job_id', '')[:8]
                
                label = f"{status} • {strategy_name} • {instrument} • {timeframe}m • {season} • {short_id}"
                
                item = {
                    'name': label,
                    'type': 'job',
                    'job_id': job.get('job_id'),
                    'status': status,
                    'strategy_name': strategy_name,
                    'instrument': instrument,
                    'timeframe': timeframe,
                    'season': season,
                    'run_mode': job.get('run_mode'),
                    'created_at': job.get('created_at'),
                    'finished_at': job.get('finished_at'),
                    'links': job.get('links', {}),
                    'original_data': job
                }
                jobs_category['children'].append(item)
                self.all_items.append(item)
            
            # Process portfolios
            portfolios_category = self.root_item['children'][1]
            portfolios_category['children'] = []
            
            for portfolio in summary.get('portfolios', {}).get('recent', []):
                # Create human-readable label
                portfolio_id = portfolio.get('portfolio_id', 'Unknown')
                season = portfolio.get('season', 'Unknown')
                timeframe = portfolio.get('timeframe', 0)
                admitted_count = portfolio.get('admitted_count', 0)
                rejected_count = portfolio.get('rejected_count', 0)
                short_id = portfolio_id[:8] if portfolio_id else 'Unknown'
                
                label = f"Portfolio • {season} • {timeframe}m • admitted {admitted_count} • {short_id}"
                
                item = {
                    'name': label,
                    'type': 'portfolio',
                    'portfolio_id': portfolio_id,
                    'season': season,
                    'timeframe': timeframe,
                    'admitted_count': admitted_count,
                    'rejected_count': rejected_count,
                    'created_at': portfolio.get('created_at'),
                    'links': portfolio.get('links', {}),
                    'original_data': portfolio
                }
                portfolios_category['children'].append(item)
                self.all_items.append(item)
            
            self.apply_filters()
            
        except SupervisorClientError as e:
            logger.error(f"Failed to refresh reports: {e}")
    
    def set_filter(self, text: str = "", filter_type: str = "all"):
        """Set filter text and type."""
        self.filter_text = text.lower()
        self.filter_type = filter_type
        self.apply_filters()
    
    def apply_filters(self):
        """Apply current filters to the tree."""
        self.beginResetModel()
        
        # Get categories
        jobs_category = self.root_item['children'][0]
        portfolios_category = self.root_item['children'][1]
        
        # Reset categories
        jobs_category['children'] = []
        portfolios_category['children'] = []
        
        # Apply filters to all items
        for item in self.all_items:
            # Type filter
            if self.filter_type == "jobs" and item['type'] != 'job':
                continue
            if self.filter_type == "portfolios" and item['type'] != 'portfolio':
                continue
            
            # Text filter
            if self.filter_text:
                if self.filter_text not in item['name'].lower():
                    continue
            
            # Add to appropriate category
            if item['type'] == 'job':
                jobs_category['children'].append(item)
            elif item['type'] == 'portfolio':
                portfolios_category['children'].append(item)
        
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
        
        elif role == Qt.ForegroundRole:
            item_type = item.get('type', '')
            status = item.get('status', '').upper()
            
            if item_type == 'category':
                return QColor("#4A90E2")
            elif item_type == 'job':
                if status in ['FAILED', 'REJECTED']:
                    return QColor("#FF5252")  # Red for failed
                elif status == 'SUCCEEDED':
                    return QColor("#50E3C2")  # Green for succeeded
                else:
                    return QColor("#E6E6E6")  # Default
            elif item_type == 'portfolio':
                return QColor("#F5A623")  # Orange for portfolios
        
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
        explorer_group = QGroupBox("Evidence Explorer")
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
        
        # Search box
        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("Search:"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Filter by name, instrument, season...")
        self.search_input.setClearButtonEnabled(True)
        search_layout.addWidget(self.search_input)
        left_layout.addLayout(search_layout)
        
        # Quick filters
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Show:"))
        
        self.filter_all_btn = QPushButton("All")
        self.filter_all_btn.setCheckable(True)
        self.filter_all_btn.setChecked(True)
        self.filter_all_btn.setToolTip("Show both jobs and portfolios")
        filter_layout.addWidget(self.filter_all_btn)
        
        self.filter_jobs_btn = QPushButton("Jobs Only")
        self.filter_jobs_btn.setCheckable(True)
        self.filter_jobs_btn.setToolTip("Show only strategy runs")
        filter_layout.addWidget(self.filter_jobs_btn)
        
        self.filter_portfolios_btn = QPushButton("Portfolios Only")
        self.filter_portfolios_btn.setCheckable(True)
        self.filter_portfolios_btn.setToolTip("Show only portfolio builds")
        filter_layout.addWidget(self.filter_portfolios_btn)
        
        filter_layout.addStretch()
        left_layout.addLayout(filter_layout)
        
        # Control buttons
        control_layout = QHBoxLayout()
        
        self.refresh_btn = QPushButton("🔄 Refresh")
        self.refresh_btn.setToolTip("Refresh report list")
        control_layout.addWidget(self.refresh_btn)
        
        control_layout.addStretch()
        left_layout.addLayout(control_layout)
        
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
        
        # Actions panel (initially hidden)
        self.actions_group = QGroupBox("Actions")
        self.actions_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 2px solid #4CAF50;
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
        self.actions_group.setVisible(False)
        
        actions_layout = QVBoxLayout(self.actions_group)
        
        # Action buttons
        self.open_report_btn = QPushButton("📄 Open Report")
        self.open_report_btn.setToolTip("Open the selected report")
        self.open_report_btn.setEnabled(False)
        actions_layout.addWidget(self.open_report_btn)
        
        self.view_logs_btn = QPushButton("📋 View Logs")
        self.view_logs_btn.setToolTip("View logs for the selected job")
        self.view_logs_btn.setEnabled(False)
        actions_layout.addWidget(self.view_logs_btn)
        
        self.open_evidence_btn = QPushButton("📁 Open Evidence Folder")
        self.open_evidence_btn.setToolTip("Open the evidence folder for the selected item")
        self.open_evidence_btn.setEnabled(False)
        actions_layout.addWidget(self.open_evidence_btn)
        
        self.export_json_btn = QPushButton("💾 Export JSON")
        self.export_json_btn.setToolTip("Export report data as JSON")
        self.export_json_btn.setEnabled(False)
        actions_layout.addWidget(self.export_json_btn)
        
        # Advanced section (collapsible)
        self.advanced_group = QGroupBox("Advanced")
        self.advanced_group.setCheckable(True)
        self.advanced_group.setChecked(False)
        self.advanced_group.setStyleSheet("""
            QGroupBox {
                font-weight: normal;
                border: 1px solid #555555;
                background-color: #1A1A1A;
                margin-top: 5px;
                padding-top: 8px;
                font-size: 11px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px 0 4px;
                color: #AAAAAA;
            }
        """)
        
        advanced_layout = QVBoxLayout(self.advanced_group)
        self.advanced_text = QTextEdit()
        self.advanced_text.setReadOnly(True)
        self.advanced_text.setMaximumHeight(150)
        self.advanced_text.setStyleSheet("""
            QTextEdit {
                background-color: #1A1A1A;
                color: #CCCCCC;
                font-family: monospace;
                font-size: 10px;
                border: 1px solid #333333;
            }
        """)
        advanced_layout.addWidget(self.advanced_text)
        actions_layout.addWidget(self.advanced_group)
        
        left_layout.addWidget(self.actions_group)
        
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
        main_splitter.setSizes([350, 650])  # 35% left, 65% right
        
        # Add splitter to main layout
        main_layout.addWidget(main_splitter)
    
    def setup_connections(self):
        """Connect signals and slots."""
        self.refresh_btn.clicked.connect(self.refresh_reports)
        self.report_tree.doubleClicked.connect(self.on_report_double_clicked)
        self.report_tabs.tabCloseRequested.connect(self.close_report_tab)
        
        # Search and filter connections
        self.search_input.textChanged.connect(self.on_search_changed)
        self.filter_all_btn.clicked.connect(lambda: self.on_filter_changed("all"))
        self.filter_jobs_btn.clicked.connect(lambda: self.on_filter_changed("jobs"))
        self.filter_portfolios_btn.clicked.connect(lambda: self.on_filter_changed("portfolios"))
        
        # Action button connections
        self.open_report_btn.clicked.connect(self.on_open_report_clicked)
        self.view_logs_btn.clicked.connect(self.on_view_logs_clicked)
        self.open_evidence_btn.clicked.connect(self.on_open_evidence_clicked)
        self.export_json_btn.clicked.connect(self.on_export_json_clicked)
        
        # Selection change
        self.report_tree.selectionModel().selectionChanged.connect(self.on_selection_changed)
        
        # Advanced section
        self.advanced_group.toggled.connect(self.on_advanced_toggled)
    
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
        
        if item_type == 'job':
            job_id = item_data.get('job_id')
            links = item_data.get('links', {})
            report_url = links.get('report_url')
            
            if report_url:
                # Open strategy report
                self.load_strategy_report(job_id)
            else:
                # Show logs dialog
                self.show_logs_dialog(job_id)
        
        elif item_type == 'portfolio':
            portfolio_id = item_data.get('portfolio_id')
            links = item_data.get('links', {})
            report_url = links.get('report_url')
            
            if report_url:
                # Open portfolio report
                self.load_portfolio_report_by_id(portfolio_id)
            else:
                # Show "Report not available" dialog
                QMessageBox.information(
                    self,
                    "Report Not Available",
                    f"No report available for portfolio {portfolio_id}"
                )
    
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
        """Load default portfolio report (legacy method)."""
        QMessageBox.information(
            self,
            "Info",
            "Use the Evidence Explorer to select and open portfolio reports."
        )
    
    def load_specific_portfolio(self):
        """Load portfolio report by ID from input (legacy method)."""
        QMessageBox.information(
            self,
            "Info",
            "Use the Evidence Explorer to select and open portfolio reports."
        )
    
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
    
    # ===== Search and Filter Methods =====
    
    def on_search_changed(self, text: str):
        """Handle search text changed."""
        self.report_explorer_model.set_filter(text=text)
    
    def on_filter_changed(self, filter_type: str):
        """Handle filter button clicked."""
        # Update button states
        self.filter_all_btn.setChecked(filter_type == "all")
        self.filter_jobs_btn.setChecked(filter_type == "jobs")
        self.filter_portfolios_btn.setChecked(filter_type == "portfolios")
        
        # Apply filter
        self.report_explorer_model.set_filter(filter_type=filter_type)
    
    # ===== Selection Handling =====
    
    def on_selection_changed(self):
        """Handle tree selection change."""
        indexes = self.report_tree.selectedIndexes()
        if not indexes:
            self.actions_group.setVisible(False)
            return
        
        index = indexes[0]
        item_data = self.report_explorer_model.get_item_data(index)
        if not item_data:
            self.actions_group.setVisible(False)
            return
        
        # Show actions panel
        self.actions_group.setVisible(True)
        
        # Update action buttons based on item type
        item_type = item_data.get('type', '')
        links = item_data.get('links', {})
        has_report_url = bool(links.get('report_url'))
        
        # Enable/disable buttons
        self.open_report_btn.setEnabled(has_report_url)
        self.view_logs_btn.setEnabled(item_type == 'job')
        self.open_evidence_btn.setEnabled(True)
        self.export_json_btn.setEnabled(True)
        
        # Store current selection
        self.current_selection = item_data
        
        # Clear advanced text
        self.advanced_text.clear()
    
    # ===== Action Button Handlers =====
    
    def on_open_report_clicked(self):
        """Handle Open Report button click."""
        if not hasattr(self, 'current_selection') or not self.current_selection:
            return
        
        item_data = self.current_selection
        item_type = item_data.get('type', '')
        
        if item_type == 'job':
            job_id = item_data.get('job_id')
            if job_id:
                self.load_strategy_report(job_id)
        elif item_type == 'portfolio':
            portfolio_id = item_data.get('portfolio_id')
            if portfolio_id:
                self.load_portfolio_report_by_id(portfolio_id)
    
    def on_view_logs_clicked(self):
        """Handle View Logs button click."""
        if not hasattr(self, 'current_selection') or not self.current_selection:
            return
        
        item_data = self.current_selection
        if item_data.get('type') != 'job':
            return
        
        job_id = item_data.get('job_id')
        if job_id:
            self.show_logs_dialog(job_id)
    
    def on_open_evidence_clicked(self):
        """Handle Open Evidence Folder button click."""
        if not hasattr(self, 'current_selection') or not self.current_selection:
            return
        
        item_data = self.current_selection
        item_type = item_data.get('type', '')
        
        if item_type == 'job':
            job_id = item_data.get('job_id')
            if job_id:
                # Open job evidence folder
                import subprocess
                import os
                path = os.path.join("outputs", "jobs", job_id)
                if os.path.exists(path):
                    subprocess.Popen(['xdg-open', path])
                else:
                    QMessageBox.warning(self, "Folder Not Found", f"Evidence folder not found: {path}")
        
        elif item_type == 'portfolio':
            portfolio_id = item_data.get('portfolio_id')
            if portfolio_id:
                # Open portfolio admission folder
                import subprocess
                import os
                path = os.path.join("outputs", "portfolios", portfolio_id, "admission")
                if os.path.exists(path):
                    subprocess.Popen(['xdg-open', path])
                else:
                    QMessageBox.warning(self, "Folder Not Found", f"Admission folder not found: {path}")
    
    def on_export_json_clicked(self):
        """Handle Export JSON button click."""
        if not hasattr(self, 'current_selection') or not self.current_selection:
            return
        
        item_data = self.current_selection
        original_data = item_data.get('original_data', {})
        
        # For now, just show in advanced text area
        import json
        formatted_json = json.dumps(original_data, indent=2)
        self.advanced_text.setText(formatted_json)
        self.advanced_group.setChecked(True)
    
    # ===== Advanced Section =====
    
    def on_advanced_toggled(self, checked: bool):
        """Handle advanced section toggled."""
        if checked and hasattr(self, 'current_selection') and self.current_selection:
            # Fetch artifact details if needed
            item_data = self.current_selection
            item_type = item_data.get('type', '')
            
            if item_type == 'job':
                job_id = item_data.get('job_id')
                if job_id:
                    # TODO: Fetch artifact index from API
                    artifacts_info = f"Artifacts for job {job_id}:\n- strategy_report.json\n- metrics.csv\n- logs.txt"
                    self.advanced_text.setText(artifacts_info)
            elif item_type == 'portfolio':
                portfolio_id = item_data.get('portfolio_id')
                if portfolio_id:
                    artifacts_info = f"Artifacts for portfolio {portfolio_id}:\n- admission_report.json\n- candidates.csv"
                    self.advanced_text.setText(artifacts_info)
    
    # ===== Helper Methods =====
    
    def show_logs_dialog(self, job_id: str):
        """Show logs dialog for a job."""
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QTextEdit, QPushButton
        
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Logs for Job {job_id[:8]}")
        dialog.setMinimumSize(600, 400)
        
        layout = QVBoxLayout(dialog)
        
        text_edit = QTextEdit()
        text_edit.setReadOnly(True)
        text_edit.setStyleSheet("""
            QTextEdit {
                background-color: #1E1E1E;
                color: #E6E6E6;
                font-family: monospace;
                font-size: 10px;
            }
        """)
        
        # TODO: Fetch actual logs from API
        text_edit.setText(f"Logs for job {job_id}\n\nLogs would be fetched from supervisor API...")
        
        layout.addWidget(text_edit)
        
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.close)
        layout.addWidget(close_btn)
        
        dialog.exec()