"""
Desktop Control Station - Main window with 4-tab architecture.
Matching historical product design with 1:1 functional parity.
"""

import logging
import os
import time
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal, Slot, QThread, QTimer  # type: ignore
from PySide6.QtWidgets import (  # type: ignore
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QLabel, QPushButton, QStatusBar, QMessageBox
)
from PySide6.QtGui import QFont, QFontDatabase  # type: ignore

from .tabs.op_tab import OpTab
from .tabs.report_tab import ReportTab
from .tabs.registry_tab import RegistryTab
from .tabs.allocation_tab import AllocationTab
from .tabs.audit_tab import AuditTab
from .tabs.portfolio_admission_tab import PortfolioAdmissionTab
from .tabs.gate_summary_dashboard_tab import GateSummaryDashboardTab
from .supervisor_lifecycle import (
    ensure_supervisor_running,
    SupervisorStatus,
    detect_port_occupant_8000,
)
from .config import SUPERVISOR_BASE_URL

logger = logging.getLogger(__name__)


def _is_wayland() -> bool:
    """Detect if running under Wayland compositor."""
    wayland_display = os.environ.get("WAYLAND_DISPLAY")
    qt_platform = os.environ.get("QT_QPA_PLATFORM", "").lower()
    
    # If WAYLAND_DISPLAY is set and we're not explicitly forcing XCB
    # Check if platform contains "xcb" (case-insensitive)
    # This handles variations like "xcb", "xcb_egl", "XCB", etc.
    is_xcb = "xcb" in qt_platform
    return bool(wayland_display) and not is_xcb


def _apply_initial_geometry(window, target_w: int = 1920, target_h: int = 1080):
    """
    Apply initial window geometry in a Wayland-safe manner.
    
    On Wayland:
    - Use resize() only (no setGeometry)
    - Never maximize
    - Clamp to available screen geometry
    
    On X11/Windows:
    - Use setGeometry with default position
    """
    if _is_wayland():
        # Wayland: use resize only, clamp to available geometry
        from PySide6.QtWidgets import QApplication  # type: ignore
        screen = QApplication.primaryScreen()
        if screen:
            available = screen.availableGeometry()
            # Clamp to 90% of available size
            clamped_w = min(target_w, int(available.width() * 0.9))
            clamped_h = min(target_h, int(available.height() * 0.9))
            window.resize(clamped_w, clamped_h)
            logger.info(f"Wayland: resized to {clamped_w}x{clamped_h} (clamped from {target_w}x{target_h})")
        else:
            window.resize(target_w, target_h)
            logger.info(f"Wayland: resized to {target_w}x{target_h}")
    else:
        # X11/Windows: use setGeometry with default position
        window.setGeometry(100, 100, target_w, target_h)
        logger.info(f"X11/Windows: setGeometry to 100,100,{target_w},{target_h}")


class ControlStation(QMainWindow):
    """Main control station window with 4-tab architecture."""
    
    def __init__(self):
        super().__init__()
        
        # Supervisor state
        self.supervisor_status = SupervisorStatus.NOT_RUNNING
        self.supervisor_details = {}
        
        self.setup_ui()
        self.setup_connections()
        
        # Start supervisor on initialization
        self.start_supervisor()
        
        # Timer for periodic updates
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.update_status)
        self.update_timer.start(1000)  # 1 second
    
    def setup_ui(self):
        """Initialize the UI components."""
        self.setWindowTitle("FishBro Quant Pro Station")
        
        # Apply Wayland-safe geometry
        _apply_initial_geometry(self, 1920, 1080)
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Header - compact, terminal-like
        header_widget = QWidget()
        header_widget.setStyleSheet("background-color: #1E1E1E;")
        header_layout = QHBoxLayout(header_widget)
        header_layout.setContentsMargins(10, 5, 10, 5)
        
        title_label = QLabel("Quant Pro Station")
        title_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #E6E6E6;")
        header_layout.addWidget(title_label)
        
        header_layout.addStretch()
        
        # Status indicator
        self.status_indicator = QLabel("🟢 Ready")
        self.status_indicator.setStyleSheet("font-size: 11px; color: #9A9A9A;")
        header_layout.addWidget(self.status_indicator)
        
        main_layout.addWidget(header_widget)
        
        # Tab widget - compact, dense
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabPosition(QTabWidget.TabPosition.North)
        self.tab_widget.setMovable(False)
        
        # Create tabs
        self.op_tab = OpTab()
        self.report_tab = ReportTab()
        self.registry_tab = RegistryTab()
        self.allocation_tab = AllocationTab()
        self.audit_tab = AuditTab()
        self.portfolio_admission_tab = PortfolioAdmissionTab()
        self.gate_summary_dashboard_tab = GateSummaryDashboardTab()
        
        # Add tabs
        self.tab_widget.addTab(self.op_tab, "Operation")
        self.tab_widget.addTab(self.report_tab, "Report")
        self.tab_widget.addTab(self.registry_tab, "Strategy Library")
        self.tab_widget.addTab(self.allocation_tab, "Allocation")
        self.tab_widget.addTab(self.audit_tab, "Audit")
        self.tab_widget.addTab(self.portfolio_admission_tab, "Portfolio Admission")
        self.tab_widget.addTab(self.gate_summary_dashboard_tab, "Gate Dashboard")
        
        main_layout.addWidget(self.tab_widget)
        
        # Status bar - minimal
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        
        # Status bar widgets
        self.status_bar.showMessage("Ready")
        
        # Add version info
        version_label = QLabel("Phase 18.1 - Quant Pro Station")
        version_label.setStyleSheet("color: #9A9A9A; font-size: 10px;")
        self.status_bar.addPermanentWidget(version_label)
    
    def setup_connections(self):
        """Connect signals and slots."""
        # Connect tab signals to main window
        self.op_tab.log_signal.connect(self.handle_log)
        self.op_tab.progress_signal.connect(self.handle_progress)
        self.op_tab.artifact_state_changed.connect(self.handle_artifact_state)
        self.op_tab.switch_to_audit_tab.connect(self.handle_open_report_request)
        
        self.report_tab.log_signal.connect(self.handle_log)
        self.registry_tab.log_signal.connect(self.handle_log)
        self.allocation_tab.log_signal.connect(self.handle_log)
        self.allocation_tab.allocation_changed.connect(self.handle_allocation_change)
        self.audit_tab.log_signal.connect(self.handle_log)
        self.portfolio_admission_tab.log_signal.connect(self.handle_log)
        self.gate_summary_dashboard_tab.log_signal.connect(self.handle_log)
        
        # Tab change events
        self.tab_widget.currentChanged.connect(self.on_tab_changed)
    
    @Slot(str)
    def handle_log(self, message: str):
        """Handle log messages from tabs."""
        logger.info(message)
        # Update status bar with last message
        self.status_bar.showMessage(message, 3000)  # Show for 3 seconds
    
    @Slot(int)
    def handle_progress(self, value: int):
        """Handle progress updates from tabs."""
        # Could update a progress bar in status bar if needed
        pass
    
    @Slot(str, str, str)
    def handle_artifact_state(self, state: str, run_id: str, run_dir: str):
        """Handle artifact state changes from OP tab."""
        logger.info(f"Artifact state changed: {state} ({run_id})")
        # Could update other tabs or UI elements
        if state == "READY":
            # Refresh registry tab to show new artifact
            self.registry_tab.refresh_registry()
    
    @Slot(dict)
    def handle_allocation_change(self, audit_event: dict):
        """Handle allocation change events."""
        logger.info(f"Allocation change: {audit_event}")
        # Emit audit event to audit tab
        # TODO: Actually add event to audit trail
        self.handle_log(f"Allocation change audited: {audit_event.get('event_type', 'unknown')}")

    @Slot(str)
    def handle_open_report_request(self, job_id: str):
        """Handle request to open a strategy report from OP tab."""
        logger.info(f"Opening strategy report for job {job_id}")
        # Switch to Audit tab (index 4)
        self.tab_widget.setCurrentIndex(4)
        # Call audit tab's open_strategy_report method
        self.audit_tab.open_strategy_report(job_id)
        # Log the action
        self.handle_log(f"Opened strategy report for job {job_id[:8]}...")

    @Slot(int)
    def on_tab_changed(self, index: int):
        """Handle tab change events."""
        tab_names = ["OP", "Report", "Registry", "Allocation", "Audit", "Portfolio Admission", "Gate Dashboard"]
        if 0 <= index < len(tab_names):
            self.handle_log(f"Switched to {tab_names[index]} tab")
    
    def start_supervisor(self):
        """Ensure supervisor is running at desktop startup."""
        logger.info("Checking supervisor status...")
        self.supervisor_status, self.supervisor_details = ensure_supervisor_running()
        
        # Handle different statuses
        if self.supervisor_status == SupervisorStatus.PORT_OCCUPIED:
            # Show blocking error for port occupied by non-fishbro process
            pid = self.supervisor_details.get("pid")
            process_name = self.supervisor_details.get("process_name", "unknown")
            cmdline = self.supervisor_details.get("cmdline", list())
            
            error_msg = (
                f"Port 8000 is occupied by another process.\n\n"
                f"PID: {pid}\n"
                f"Process: {process_name}\n"
                f"Command: {' '.join(cmdline[:5]) if cmdline else 'unknown'}\n\n"
                f"Please stop the service using port 8000 and restart the Desktop."
            )
            
            QMessageBox.critical(
                self,
                "Port Conflict",
                error_msg,
                QMessageBox.StandardButton.Ok
            )
            logger.error(f"Port 8000 occupied by non-fishbro process: {self.supervisor_details}")
        
        elif self.supervisor_status == SupervisorStatus.ERROR:
            error_msg = (
                f"Failed to start supervisor.\n\n"
                f"Error: {self.supervisor_details.get('message', 'Unknown error')}\n\n"
                f"Check logs at outputs/_dp_evidence/desktop_supervisor_runtime.log"
            )
            
            QMessageBox.warning(
                self,
                "Supervisor Error",
                error_msg,
                QMessageBox.StandardButton.Ok
            )
            logger.error(f"Supervisor startup error: {self.supervisor_details}")
        
        elif self.supervisor_status == SupervisorStatus.RUNNING:
            logger.info(f"Supervisor is running: {self.supervisor_details}")
        
        elif self.supervisor_status == SupervisorStatus.STARTING:
            logger.info("Supervisor is starting...")
        
        # Update status indicator immediately
        self.update_supervisor_status_indicator()

    def update_supervisor_status_indicator(self):
        """Update the status indicator based on supervisor state."""
        if self.supervisor_status == SupervisorStatus.RUNNING:
            self.status_indicator.setText(f"🟢 Connected to {SUPERVISOR_BASE_URL}")
            self.status_indicator.setStyleSheet("font-size: 11px; color: #4CAF50;")
        
        elif self.supervisor_status == SupervisorStatus.STARTING:
            self.status_indicator.setText("🟡 Starting Supervisor...")
            self.status_indicator.setStyleSheet("font-size: 11px; color: #FFC107;")
        
        elif self.supervisor_status == SupervisorStatus.PORT_OCCUPIED:
            self.status_indicator.setText("🔴 Port 8000 occupied")
            self.status_indicator.setStyleSheet("font-size: 11px; color: #F44336;")
        
        elif self.supervisor_status == SupervisorStatus.ERROR:
            self.status_indicator.setText("🔴 Supervisor error")
            self.status_indicator.setStyleSheet("font-size: 11px; color: #F44336;")
        
        else:  # NOT_RUNNING
            self.status_indicator.setText("⚪ Supervisor not running")
            self.status_indicator.setStyleSheet("font-size: 11px; color: #9A9A9A;")

    @Slot()
    def update_status(self):
        """Periodic status update."""
        # Update supervisor status indicator
        self.update_supervisor_status_indicator()
        
        # If supervisor is not running, try to restart periodically
        if self.supervisor_status in [SupervisorStatus.NOT_RUNNING, SupervisorStatus.ERROR]:
            # Only retry every 30 seconds to avoid spam
            if hasattr(self, '_last_supervisor_retry'):
                elapsed = time.time() - self._last_supervisor_retry
                if elapsed < 30:
                    return
            
            logger.info("Attempting to restart supervisor...")
            self.supervisor_status, self.supervisor_details = ensure_supervisor_running()
            self._last_supervisor_retry = time.time()
    
    def closeEvent(self, event):
        """Handle window close event."""
        # Clean up any resources
        self.update_timer.stop()
        
        # Log closure
        logger.info("Desktop Control Station closed")
        
        event.accept()