"""
Allocation Tab - Phase C Professional CTA Desktop UI.

Portfolio Build + Viewer with PortfolioReportV1 integration.
"""

import logging
import time
from typing import Optional, List, Dict, Any

from PySide6.QtCore import Qt, Signal, Slot  # type: ignore
from PySide6.QtWidgets import (  # type: ignore
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QFormLayout,
    QLabel, QPushButton, QTableView, QSplitter,
    QGroupBox, QHeaderView, QMessageBox, QDoubleSpinBox,
    QLineEdit, QComboBox, QCheckBox, QScrollArea,
    QApplication, QSizePolicy, QSpacerItem
)
from PySide6.QtGui import QFont, QColor  # type: ignore

from ..widgets.metric_cards import MetricCard, MetricRow
from ..widgets.charts.heatmap import HeatmapWidget
from ..widgets.report_widgets.portfolio_report_widget import PortfolioReportWidget
from ...services.supervisor_client import (
    get_portfolio_report_v1, SupervisorClientError,
    get_registry_strategies, post_portfolio_build,
    get_job, get_job_artifacts
)

logger = logging.getLogger(__name__)


class AllocationTab(QWidget):
    """Allocation Tab - Phase C Professional CTA Portfolio Builder."""
    
    # Signals for communication with main window
    log_signal = Signal(str)
    allocation_changed = Signal(dict)  # audit_event
    
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
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
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
        form_layout.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        
        # Season
        self.season_input = QLineEdit()
        self.season_input.setPlaceholderText("e.g., 2026Q1")
        self.season_input.setText("2026Q1")
        self.season_input.setToolTip("Season identifier (e.g., 2026Q1)")
        form_layout.addRow("Season:", self.season_input)
        
        # Timeframe
        self.timeframe_input = QLineEdit()
        self.timeframe_input.setPlaceholderText("e.g., 60m")
        self.timeframe_input.setText("60m")
        self.timeframe_input.setToolTip("Timeframe (e.g., 60m)")
        form_layout.addRow("Timeframe:", self.timeframe_input)
        
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
        
        self.strategy_checkboxes = list()
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
        form_layout.addItem(QSpacerItem(20, 40, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))
        
        # BUILD PORTFOLIO button (enabled when strategies selected)
        self.build_button = QPushButton("BUILD PORTFOLIO")
        self.build_button.setEnabled(True)
        self.build_button.setToolTip("Build portfolio from selected strategies")
        self.build_button.setStyleSheet("""
            QPushButton {
                background-color: #FF9800;
                color: #121212;
                font-weight: bold;
                font-size: 14px;
                padding: 12px;
                border-radius: 6px;
                border: 2px solid #FF9800;
            }
            QPushButton:hover {
                background-color: #FFB74D;
                border: 2px solid #FFB74D;
            }
            QPushButton:disabled {
                background-color: #424242;
                color: #9e9e9e;
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
        self.portfolio_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
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
        selected = list()
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
        """Build portfolio from selected strategies with guardrails."""
        # Get selected strategies
        selected_strategies = self.get_selected_strategies()
        
        # Guardrail B1: Empty portfolio build
        if not selected_strategies:
            QMessageBox.warning(self, "No Strategies Selected",
                               "Please select at least one strategy to include in the portfolio.")
            return
        
        # Guardrail B2: Check if all candidates are FAILED/REJECTED
        # (We would need to fetch job statuses for each selected strategy,
        # but for now we'll implement a simpler check)
        try:
            from ...services.supervisor_client import get_jobs
            recent_jobs = get_jobs(limit=100)
            job_status_map = {}
            for job in recent_jobs:
                job_id = job.get("job_id")
                if job_id:
                    job_status_map[job_id] = job.get("status", "UNKNOWN")
            
            # Count failed/rejected among selected strategies
            failed_count = 0
            for strategy_id in selected_strategies:
                status = job_status_map.get(strategy_id, "UNKNOWN")
                if status in ["FAILED", "REJECTED"]:
                    failed_count += 1
            
            if failed_count == len(selected_strategies):
                reply = QMessageBox.warning(
                    self,
                    "All Candidates Failed",
                    f"All {failed_count} selected strategies have FAILED or REJECTED status.\n\n"
                    "Building a portfolio with only failed candidates is unlikely to succeed.\n"
                    "Do you want to continue anyway?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.No:
                    self.status_label.setText("Portfolio build cancelled (all candidates failed)")
                    return
        
        except Exception as e:
            # If we can't check job statuses, continue anyway
            logger.warning(f"Failed to check candidate job statuses: {e}")
        
        # Get season and timeframe
        season = self.season_input.text().strip()
        timeframe = self.timeframe_input.text().strip()
        if not season or not timeframe:
            QMessageBox.warning(self, "Missing Parameters",
                               "Please enter both season and timeframe.")
            return
        
        # Get governance parameters
        corr_threshold = float(self.corr_threshold_spin.value())
        risk_budget = float(self.risk_budget_spin.value())
        
        # Guardrail C: Correlation/risk override sanity
        warnings = list()
        
        if corr_threshold < 0.1 or corr_threshold > 0.99:
            warnings.append(f"Correlation threshold ({corr_threshold}) is extreme (<0.1 or >0.99)")
        
        if risk_budget <= 0:
            QMessageBox.critical(self, "Invalid Risk Budget",
                               f"Risk budget must be positive (got ${risk_budget:.2f})")
            return
        
        if risk_budget < 1000:
            warnings.append(f"Risk budget (${risk_budget:.2f}) is very small")
        
        if warnings:
            warning_msg = "Potential issues detected:\n\n" + "\n".join(f"• {w}" for w in warnings)
            warning_msg += "\n\nDo you want to continue with these values?"
            
            reply = QMessageBox.warning(
                self,
                "Governance Parameter Warnings",
                warning_msg,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No
            )
            
            if reply == QMessageBox.StandardButton.No:
                self.status_label.setText("Portfolio build cancelled (parameter warnings)")
                return
        
        governance_params_overrides = {
            "max_pairwise_correlation": corr_threshold,
            "portfolio_risk_budget_max": risk_budget
        }
        
        # Compose request payload
        request_payload = {
            "season": season,
            "timeframe": timeframe,
            "candidate_run_ids": selected_strategies,
            "governance_params_overrides": governance_params_overrides
        }
        
        # Disable controls and show progress
        self.build_button.setEnabled(False)
        self.build_button.setText("BUILDING...")
        self.status_label.setText("Submitting portfolio build request...")
        QApplication.processEvents()
        
        try:
            # Submit portfolio build request
            response = post_portfolio_build(request_payload)
            job_id = response.get("job_id")
            
            if not job_id:
                raise SupervisorClientError(message="No job_id in response")
            
            self.status_label.setText(f"Portfolio build job created: {job_id}")
            self.log_signal.emit(f"Portfolio build job created: {job_id}")
            
            # Poll job status
            self.poll_job_status(job_id)
            
        except SupervisorClientError as e:
            QMessageBox.critical(self, "Build Failed",
                               f"Failed to submit portfolio build request: {e}")
            self.status_label.setText(f"Build failed: {e}")
            logger.error(f"Portfolio build failed: {e}")
            self.reset_build_button()
        except Exception as e:
            QMessageBox.critical(self, "Unexpected Error",
                               f"Unexpected error during portfolio build: {e}")
            self.status_label.setText(f"Unexpected error: {e}")
            logger.error(f"Unexpected error during portfolio build: {e}")
            self.reset_build_button()
    
    def reset_build_button(self):
        """Reset the build button to its initial state."""
        self.build_button.setEnabled(True)
        self.build_button.setText("BUILD PORTFOLIO")
    
    def poll_job_status(self, job_id: str):
        """Poll job status until terminal state."""
        import time
        
        max_polls = 300  # 5 minutes at 1 second intervals
        poll_interval = 1.0  # seconds
        
        for poll_count in range(max_polls):
            try:
                job = get_job(job_id)
                status = job.get("status")
                
                self.status_label.setText(f"Job {job_id}: {status} (poll {poll_count+1}/{max_polls})")
                QApplication.processEvents()
                
                if status in ["SUCCEEDED", "FAILED", "REJECTED"]:
                    # Terminal state reached
                    if status == "SUCCEEDED":
                        # Extract portfolio_id from job artifacts
                        portfolio_id = self.extract_portfolio_id_from_job(job_id)
                        if portfolio_id:
                            self.on_portfolio_build_success(portfolio_id)
                        else:
                            QMessageBox.warning(self, "Build Complete",
                                             f"Portfolio build job {job_id} succeeded but portfolio_id not found.")
                            self.status_label.setText(f"Build succeeded but portfolio_id missing")
                    else:
                        # Failed or rejected
                        error_msg = f"Portfolio build job {job_id} {status.lower()}"
                        QMessageBox.critical(self, "Build Failed", error_msg)
                        self.status_label.setText(f"Build {status.lower()}")
                    
                    self.reset_build_button()
                    return
                
                # Continue polling
                time.sleep(poll_interval)
                
            except SupervisorClientError as e:
                # If job not found after some polls, maybe it's still being created
                if poll_count > 10:
                    QMessageBox.warning(self, "Job Status Error",
                                      f"Failed to get job status after multiple attempts: {e}")
                    self.status_label.setText(f"Job status error: {e}")
                    self.reset_build_button()
                    return
                time.sleep(poll_interval)
                continue
            except Exception as e:
                QMessageBox.critical(self, "Polling Error",
                                  f"Error while polling job status: {e}")
                self.status_label.setText(f"Polling error: {e}")
                self.reset_build_button()
                return
        
        # Timeout
        QMessageBox.warning(self, "Build Timeout",
                          f"Portfolio build job {job_id} did not complete within timeout.")
        self.status_label.setText(f"Build timeout")
        self.reset_build_button()
    
    def extract_portfolio_id_from_job(self, job_id: str) -> Optional[str]:
        """Extract portfolio_id from job artifacts."""
        try:
            artifacts = get_job_artifacts(job_id)
            # Look for portfolio_id.json or other pointer files
            files = artifacts.get("files", list())
            for file_info in files:
                filename = file_info.get("filename", "")
                if filename == "portfolio_id.json":
                    # Download and parse the file
                    import json
                    content = get_job_artifacts(job_id)  # This returns the index, not file content
                    # Actually we need to get the file content
                    # For now, try to find portfolio_id in job details
                    pass
            
            # Alternative: check job config snapshot for portfolio_id
            job = get_job(job_id)
            config = job.get("spec", {}).get("config_snapshot", {})
            portfolio_id = config.get("portfolio_id")
            if portfolio_id:
                return portfolio_id
            
            # Last resort: check if job has a portfolio_id field
            portfolio_id = job.get("portfolio_id")
            if portfolio_id:
                return portfolio_id
            
        except Exception as e:
            logger.error(f"Failed to extract portfolio_id from job {job_id}: {e}")
        
        return None
    
    def on_portfolio_build_success(self, portfolio_id: str):
        """Handle successful portfolio build."""
        self.status_label.setText(f"Portfolio build successful: {portfolio_id}")
        self.log_signal.emit(f"Portfolio build successful: {portfolio_id}")
        
        # Update portfolio ID input field
        self.portfolio_id_input.setText(portfolio_id)
        
        # Load and display the portfolio report
        self.load_portfolio_report()
        
        # Signal to main window to open Audit tab with portfolio report
        # This would require integration with main window signals
        # For now, just show a success message
        QMessageBox.information(self, "Build Successful",
                              f"Portfolio {portfolio_id} built successfully.\n\n"
                              f"The portfolio report has been loaded in the viewer.")
    
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
            
            # Create the new portfolio report widget
            display_widget = PortfolioReportWidget(portfolio_id, report_data)
            self.portfolio_display_area.setWidget(display_widget)
            
            self.status_label.setText(f"Portfolio report {portfolio_id} loaded")
            self.log_signal.emit(f"Loaded portfolio report {portfolio_id}")
            
        except SupervisorClientError as e:
            QMessageBox.critical(self, "Report Error", f"Failed to load portfolio report: {e}")
            self.status_label.setText(f"Error: {e}")
            logger.error(f"Failed to load portfolio report {portfolio_id}: {e}")
    
    
    def log(self, message: str):
        """Append message to log."""
        self.log_signal.emit(message)
        self.status_label.setText(message)