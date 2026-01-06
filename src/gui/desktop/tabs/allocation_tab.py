"""
Allocation Tab - Phase C Professional CTA Desktop UI.

Portfolio Build + Viewer with PortfolioReportV1 integration.
"""

import logging
from typing import Optional, List, Dict, Any

from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout,
    QLabel, QPushButton, QTableView, QSplitter,
    QGroupBox, QHeaderView, QMessageBox, QDoubleSpinBox,
    QLineEdit, QComboBox, QCheckBox, QScrollArea,
    QApplication, QSizePolicy
)
from PySide6.QtGui import QFont, QColor

from ..widgets.metric_cards import MetricCard, MetricRow
from ..widgets.charts.heatmap import HeatmapWidget
from ...services.supervisor_client import (
    get_portfolio_report_v1, SupervisorClientError,
    get_registry_strategies
)

logger = logging.getLogger(__name__)


class AllocationTab(QWidget):
    """Allocation Tab - Phase C Professional CTA Portfolio Builder."""
    
    # Signals for communication with main window
    log_signal = Signal(str)
    
    def __init__(self):
        super().__init__()
        self.setup_ui()
        self.setup_connections()
        self.load_registry_data()
    
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
        
        # Left panel: Build Controls
        left_widget = QWidget()
        left_widget.setStyleSheet("background-color: #121212;")
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(4, 4, 4, 4)
        left_layout.setSpacing(8)
        
        # Build Controls group
        build_group = QGroupBox("Portfolio Build Controls")
        build_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 2px solid #FF9800;
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
        
        # Scroll area for form
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: #1E1E1E;
            }
        """)
        
        form_widget = QWidget()
        form_layout = QFormLayout(form_widget)
        form_layout.setContentsMargins(12, 12, 12, 12)
        form_layout.setSpacing(10)
        form_layout.setLabelAlignment(Qt.AlignRight)
        
        # Risk budget
        self.risk_budget_spin = QDoubleSpinBox()
        self.risk_budget_spin.setRange(0.0, 1000000.0)
        self.risk_budget_spin.setDecimals(2)
        self.risk_budget_spin.setPrefix("$")
        self.risk_budget_spin.setValue(100000.0)
        self.risk_budget_spin.setToolTip("Total risk budget for portfolio")
        form_layout.addRow("Risk Budget:", self.risk_budget_spin)
        
        # Correlation threshold
        self.corr_threshold_spin = QDoubleSpinBox()
        self.corr_threshold_spin.setRange(0.0, 1.0)
        self.corr_threshold_spin.setDecimals(3)
        self.corr_threshold_spin.setSingleStep(0.05)
        self.corr_threshold_spin.setValue(0.7)
        self.corr_threshold_spin.setToolTip("Maximum allowed correlation between strategies")
        form_layout.addRow("Corr Threshold:", self.corr_threshold_spin)
        
        # Strategy whitelist (multi-select)
        self.strategy_whitelist_label = QLabel("Select strategies to include:")
        form_layout.addRow(self.strategy_whitelist_label)
        
        self.strategy_checkboxes = []
        strategy_checkbox_layout = QVBoxLayout()
        
        # Will be populated dynamically
        self.strategy_checkbox_container = QWidget()
        self.strategy_checkbox_container.setLayout(strategy_checkbox_layout)
        
        scroll_checkboxes = QScrollArea()
        scroll_checkboxes.setWidgetResizable(True)
        scroll_checkboxes.setMaximumHeight(150)
        scroll_checkboxes.setWidget(self.strategy_checkbox_container)
        form_layout.addRow(scroll_checkboxes)
        
        # Select all/none buttons
        checkbox_buttons_layout = QHBoxLayout()
        self.select_all_btn = QPushButton("Select All")
        self.select_none_btn = QPushButton("Select None")
        checkbox_buttons_layout.addWidget(self.select_all_btn)
        checkbox_buttons_layout.addWidget(self.select_none_btn)
        checkbox_buttons_layout.addStretch()
        form_layout.addRow(checkbox_buttons_layout)
        
        # Add stretch to push button to bottom
        form_layout.addItem(QSizePolicy(QSizePolicy.Minimum, QSizePolicy.Expanding))
        
        # BUILD PORTFOLIO button (disabled with tooltip)
        self.build_button = QPushButton("BUILD PORTFOLIO")
        self.build_button.setEnabled(False)
        self.build_button.setToolTip("Portfolio build action is pending API wiring; report viewer is available.")
        self.build_button.setStyleSheet("""
            QPushButton {
                background-color: #424242;
                color: #9e9e9e;
                font-weight: bold;
                font-size: 14px;
                padding: 12px;
                border-radius: 6px;
                border: 2px solid #616161;
            }
            QPushButton:hover {
                background-color: #424242;
                border: 2px solid #616161;
            }
        """)
        self.build_button.setMinimumHeight(50)
        form_layout.addRow(self.build_button)
        
        # Set form widget to scroll area
        scroll.setWidget(form_widget)
        
        # Add scroll area to build group
        build_layout = QVBoxLayout(build_group)
        build_layout.addWidget(scroll)
        
        # Add build group to left panel
        left_layout.addWidget(build_group)
        
        # Right panel: Portfolio Viewer
        right_widget = QWidget()
        right_widget.setStyleSheet("background-color: #121212;")
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(4, 4, 4, 4)
        right_layout.setSpacing(8)
        
        # Portfolio Viewer group
        viewer_group = QGroupBox("Portfolio Report Viewer")
        viewer_group.setStyleSheet("""
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
        
        # Portfolio ID input
        portfolio_input_layout = QHBoxLayout()
        portfolio_input_layout.addWidget(QLabel("Portfolio ID:"))
        
        self.portfolio_id_input = QLineEdit()
        self.portfolio_id_input.setPlaceholderText("Enter portfolio ID...")
        self.portfolio_id_input.setStyleSheet("""
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
        portfolio_input_layout.addWidget(self.portfolio_id_input)
        
        self.load_portfolio_btn = QPushButton("Load Report")
        self.load_portfolio_btn.setToolTip("Load portfolio report by ID")
        portfolio_input_layout.addWidget(self.load_portfolio_btn)
        
        portfolio_input_layout.addStretch()
        right_layout.addLayout(portfolio_input_layout)
        
        # Portfolio report display area
        self.portfolio_display_area = QScrollArea()
        self.portfolio_display_area.setWidgetResizable(True)
        self.portfolio_display_area.setStyleSheet("""
            QScrollArea {
                border: 1px solid #333333;
                background-color: #1E1E1E;
            }
        """)
        
        # Initial placeholder
        self.portfolio_placeholder = QLabel("No portfolio report loaded.\nEnter a portfolio ID and click 'Load Report'.")
        self.portfolio_placeholder.setAlignment(Qt.AlignCenter)
        self.portfolio_placeholder.setStyleSheet("color: #9e9e9e; font-size: 14px; padding: 40px;")
        self.portfolio_display_area.setWidget(self.portfolio_placeholder)
        
        viewer_layout = QVBoxLayout(viewer_group)
        viewer_layout.addWidget(self.portfolio_display_area)
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
        self.build_button.clicked.connect(self.build_portfolio)
        self.load_portfolio_btn.clicked.connect(self.load_portfolio_report)
        self.select_all_btn.clicked.connect(self.select_all_strategies)
        self.select_none_btn.clicked.connect(self.select_none_strategies)
    
    def load_registry_data(self):
        """Load registry strategies for whitelist."""
        try:
            strategies = get_registry_strategies()
            
            # Clear existing checkboxes
            for checkbox in self.strategy_checkboxes:
                checkbox.setParent(None)
            self.strategy_checkboxes.clear()
            
            # Get layout
            layout = self.strategy_checkbox_container.layout()
            
            # Add checkboxes for each strategy
            for strategy in strategies:
                if isinstance(strategy, dict):
                    strategy_id = strategy.get('id', '')
                    strategy_name = strategy.get('name', strategy_id)
                else:
                    strategy_id = str(strategy)
                    strategy_name = strategy_id
                
                checkbox = QCheckBox(strategy_name)
                checkbox.setChecked(True)
                checkbox.setToolTip(f"ID: {strategy_id}")
                layout.addWidget(checkbox)
                self.strategy_checkboxes.append(checkbox)
            
            self.status_label.setText(f"Loaded {len(self.strategy_checkboxes)} strategies")
            
        except SupervisorClientError as e:
            self.status_label.setText(f"Failed to load registry: {e}")
            logger.error(f"Failed to load registry data: {e}")
    
    def select_all_strategies(self):
        """Select all strategy checkboxes."""
        for checkbox in self.strategy_checkboxes:
            checkbox.setChecked(True)
    
    def select_none_strategies(self):
        """Deselect all strategy checkboxes."""
        for checkbox in self.strategy_checkboxes:
            checkbox.setChecked(False)
    
    def get_selected_strategies(self) -> List[str]:
        """Get list of selected strategy IDs."""
        selected = []
        for checkbox in self.strategy_checkboxes:
            if checkbox.isChecked():
                # Extract strategy ID from tooltip
                tooltip = checkbox.toolTip()
                if "ID: " in tooltip:
                    strategy_id = tooltip.split("ID: ")[1]
                    selected.append(strategy_id)
                else:
                    selected.append(checkbox.text())
        return selected
    
    def build_portfolio(self):
        """Build portfolio (disabled in Phase C)."""
        # This button is disabled with tooltip explaining API wiring is pending
        QMessageBox.information(
            self, 
            "Portfolio Build Pending",
            "Portfolio build action is pending API wiring.\n\n"
            "In Phase C, the UI is ready but the backend API for portfolio building "
            "will be implemented in Phase E.\n\n"
            "You can load existing portfolio reports using the viewer on the right."
        )
    
    def load_portfolio_report(self):
        """Load and display portfolio report by ID."""
        portfolio_id = self.portfolio_id_input.text().strip()
        if not portfolio_id:
            QMessageBox.warning(self, "Input Required", "Please enter a portfolio ID")
            return
        
        try:
            self.status_label.setText(f"Loading portfolio report {portfolio_id}...")
            QApplication.processEvents()
            
            # Fetch report from supervisor
            report_data = get_portfolio_report_v1(portfolio_id)
            if not report_data:
                QMessageBox.warning(self, "Report Not Found", f"No portfolio report found for ID {portfolio_id}")
                self.status_label.setText(f"Report not found")
                return
            
            # Create a simple display widget
            display_widget = self.create_portfolio_display(report_data)
            self.portfolio_display_area.setWidget(display_widget)
            
            self.status_label.setText(f"Portfolio report {portfolio_id} loaded")
            self.log_signal.emit(f"Loaded portfolio report {portfolio_id}")
            
        except SupervisorClientError as e:
            QMessageBox.critical(self, "Report Error", f"Failed to load portfolio report: {e}")
            self.status_label.setText(f"Error: {e}")
            logger.error(f"Failed to load portfolio report {portfolio_id}: {e}")
    
    def create_portfolio_display(self, report_data: Dict[str, Any]) -> QWidget:
        """Create a display widget for portfolio report."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)
        
        # Header
        meta = report_data.get('meta', {})
        header_label = QLabel(f"Portfolio Report: {meta.get('portfolio_id', 'Unknown')}")
        header_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #E6E6E6;")
        layout.addWidget(header_label)
        
        # Created info
        created_label = QLabel(f"Created: {meta.get('created_at', 'N/A')}")
        created_label.setStyleSheet("color: #9e9e9e; font-size: 12px;")
        layout.addWidget(created_label)
        
        # Metrics row
        metrics = report_data.get('metrics', {})
        metric_row = MetricRow([
            ("Admitted", str(metrics.get('admitted_count', 0)), "Admitted strategies"),
            ("Rejected", str(metrics.get('rejected_count', 0)), "Rejected strategies"),
            ("Total Risk", f"${metrics.get('total_risk_budget', 0):,.0f}", "Total risk budget"),
            ("Corr Threshold", f"{metrics.get('correlation_threshold', 0):.3f}", "Correlation threshold"),
        ])
        layout.addWidget(metric_row)
        
        # Correlation heatmap (if available)
        correlation = report_data.get('correlation', {})
        matrix = correlation.get('matrix', [])
        labels = correlation.get('labels', [])
        
        if matrix and labels:
            heatmap_group = QGroupBox("Correlation Heatmap")
            heatmap_group.setStyleSheet("""
                QGroupBox {
                    font-weight: bold;
                    border: 1px solid #555555;
                    background-color: #1E1E1E;
                    margin-top: 5px;
                    padding-top: 8px;
                    font-size: 11px;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 8px;
                    padding: 0 4px 0 4px;
                    color: #E6E6E6;
                }
            """)
            
            heatmap_layout = QVBoxLayout()
            heatmap_label = QLabel("Strategy correlation matrix (simplified view)")
            heatmap_label.setStyleSheet("color: #9e9e9e; font-size: 10px;")
            heatmap_layout.addWidget(heatmap_label)
            
            # Create a simple table representation
            table = QTableView()
            table.setAlternatingRowColors(True)
            table.setStyleSheet("""
                QTableView {
                    background-color: #1E1E1E;
                    alternate-background-color: #252525;
                    gridline-color: #333333;
                    color: #E6E6E6;
                    font-size: 10px;
                }
                QHeaderView::section {
                    background-color: #2a2a2a;
                    color: #E6E6E6;
                    padding: 4px;
                    border: 1px solid #333333;
                    font-weight: bold;
                }
            """)
            
            # Create a simple model for the correlation matrix
            from PySide6.QtCore import QAbstractTableModel
            
            class CorrelationTableModel(QAbstractTableModel):
                def __init__(self, matrix, labels):
                    super().__init__()
                    self.matrix = matrix
                    self.labels = labels
                
                def rowCount(self, parent=None):
                    return len(self.matrix)
                
                def columnCount(self, parent=None):
                    return len(self.matrix[0]) if self.matrix else 0
                
                def data(self, index, role=Qt.DisplayRole):
                    if not index.isValid():
                        return None
                    
                    row, col = index.row(), index.column()
                    
                    if role == Qt.DisplayRole:
                        return f"{self.matrix[row][col]:.3f}"
                    
                    elif role == Qt.TextAlignmentRole:
                        return Qt.AlignCenter
                    
                    elif role == Qt.BackgroundRole:
                        value = self.matrix[row][col]
                        # Color code by correlation value
                        if value >= 0.8:
                            return QColor(255, 100, 100, 50)  # Red for high correlation
                        elif value >= 0.5:
                            return QColor(255, 200, 100, 50)  # Orange for medium
                        elif value >= 0:
                            return QColor(100, 255, 100, 30)  # Green for low/positive
                        else:
                            return QColor(100, 100, 255, 30)  # Blue for negative
                    
                    return None
                
                def headerData(self, section, orientation, role=Qt.DisplayRole):
                    if role == Qt.DisplayRole:
                        if orientation == Qt.Horizontal:
                            return self.labels[section] if section < len(self.labels) else ""
                        else:
                            return self.labels[section] if section < len(self.labels) else ""
                    return None
            
            model = CorrelationTableModel(matrix, labels)
            table.setModel(model)
            
            # Adjust column widths
            for i in range(len(labels)):
                table.setColumnWidth(i, 60)
            
            heatmap_layout.addWidget(table)
            heatmap_group.setLayout(heatmap_layout)
            layout.addWidget(heatmap_group)
        
        # Admitted strategies table
        admitted = report_data.get('admitted', [])
        if admitted:
            admitted_group = QGroupBox("Admitted Strategies")
            admitted_group.setStyleSheet("""
                QGroupBox {
                    font-weight: bold;
                    border: 1px solid #4CAF50;
                    background-color: #1E1E1E;
                    margin-top: 5px;
                    padding-top: 8px;
                    font-size: 11px;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 8px;
                    padding: 0 4px 0 4px;
                    color: #E6E6E6;
                }
            """)
            
            admitted_layout = QVBoxLayout()
            
            # Create simple text display
            admitted_text = ""
            for i, strategy in enumerate(admitted[:10]):  # Show first 10
                name = strategy.get('name', strategy.get('strategy_id', 'Unknown'))
                weight = strategy.get('weight', 0)
                risk = strategy.get('risk_budget', 0)
                score = strategy.get('score', 0)
                admitted_text += f"{i+1}. {name}: weight={weight:.1%}, risk=${risk:,.0f}, score={score:.2f}\n"
            
            if len(admitted) > 10:
                admitted_text += f"\n... and {len(admitted) - 10} more strategies"
            
            admitted_label = QLabel(admitted_text)
            admitted_label.setStyleSheet("color: #E6E6E6; font-size: 11px; font-family: monospace;")
            admitted_label.setWordWrap(True)
            admitted_layout.addWidget(admitted_label)
            
            admitted_group.setLayout(admitted_layout)
            layout.addWidget(admitted_group)
        
        # Rejected strategies table
        rejected = report_data.get('rejected', [])
        if rejected:
            rejected_group = QGroupBox("Rejected Strategies")
            rejected_group.setStyleSheet("""
                QGroupBox {
                    font-weight: bold;
                    border: 1px solid #F44336;
                    background-color: #1E1E1E;
                    margin-top: 5px;
                    padding-top: 8px;
                    font-size: 11px;
                }
                QGroupBox::title {
                    subcontrol-origin: margin;
                    left: 8px;
                    padding: 0 4px 0 4px;
                    color: #E6E6E6;
                }
            """)
            
            rejected_layout = QVBoxLayout()
            
            # Create simple text display
            rejected_text = ""
            for i, strategy in enumerate(rejected[:10]):  # Show first 10
                name = strategy.get('name', strategy.get('strategy_id', 'Unknown'))
                reason = strategy.get('reason', 'Unknown')
                score = strategy.get('score', 0)
                rejected_text += f"{i+1}. {name}: {reason} (score={score:.2f})\n"
            
            if len(rejected) > 10:
                rejected_text += f"\n... and {len(rejected) - 10} more strategies"
            
            rejected_label = QLabel(rejected_text)
            rejected_label.setStyleSheet("color: #E6E6E6; font-size: 11px; font-family: monospace;")
            rejected_label.setWordWrap(True)
            rejected_layout.addWidget(rejected_label)
            
            rejected_group.setLayout(rejected_layout)
            layout.addWidget(rejected_group)
        
        # Add stretch at the bottom
        layout.addStretch()
        
        return widget
    
    def log(self, message: str):
        """Append message to log."""
        self.log_signal.emit(message)
        self.status_label.setText(message)