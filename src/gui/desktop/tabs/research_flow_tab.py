"""
Research Flow Tab v2.1 - THE SINGLE PRIMARY ENTRY POINT with Narrative Layer

This is THE ONLY PRIMARY ENTRY POINT for the Research OS.
All research must enter and exit through this flow.

NON-NEGOTIABLE CONSTITUTION:
- Exactly ONE primary entry point
- No tables, no metrics, no raw data
- Current Stage (big, explicit)
- Human-readable narrative (headline, why, next_step)
- At most 2 primary buttons
- Optional "View Details" links (secondary UI)
- Clicking any existing tab MUST internally pass through ResearchFlowController
- MUST NOT bypass stage rules
- MUST use Narrative Layer v2.1 for all human-readable text
"""

import logging
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QSizePolicy, QSpacerItem
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont, QPalette, QColor

from contracts.research.research_flow_kernel import ResearchFlowState, ResearchStage
from core.research.research_flow_controller import ResearchFlowController
from core.research.research_narrative_builder import build_research_narrative
from contracts.research.research_narrative import ResearchNarrativeV1

logger = logging.getLogger(__name__)


class ResearchFlowTab(QWidget):
    """
    Research Flow Tab v2.1 - THE SINGLE PRIMARY ENTRY POINT with Narrative Layer.
    
    This tab provides:
    1. Current Stage (big, explicit)
    2. Human-readable narrative (headline, why, next_step)
    3. At most 2 primary buttons
    4. Optional "View Details" links (secondary UI)
    
    NO TABLES, NO METRICS, NO RAW DATA.
    MUST use Narrative Layer v2.1 for all human-readable text.
    """
    
    # Signal emitted when user wants to navigate to another tab
    navigate_to_tab = Signal(str, dict)  # tab_name, context
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Research flow controller (KERNEL)
        self._controller = ResearchFlowController()
        self._current_state: Optional[ResearchFlowState] = None
        self._current_narrative: Optional[ResearchNarrativeV1] = None
        
        # Setup UI
        self._setup_ui()
        
        # Auto-refresh timer
        self._refresh_timer = QTimer()
        self._refresh_timer.timeout.connect(self._refresh_state)
        self._refresh_timer.start(5000)  # Refresh every 5 seconds
        
        # Initial refresh
        self._refresh_state()
    
    def _setup_ui(self):
        """Setup the research flow UI."""
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(30, 30, 30, 30)
        
        # Title
        title_label = QLabel("Research Flow")
        title_font = QFont()
        title_font.setPointSize(24)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title_label)
        
        # Separator
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFrameShadow(QFrame.Sunken)
        main_layout.addWidget(separator)
        
        # Current Stage Section
        stage_section = self._create_stage_section()
        main_layout.addWidget(stage_section)
        
        # System Verdict Section
        verdict_section = self._create_verdict_section()
        main_layout.addWidget(verdict_section)
        
        # Primary Actions Section (MAX 2 buttons)
        actions_section = self._create_actions_section()
        main_layout.addWidget(actions_section)
        
        # Secondary Links Section
        links_section = self._create_links_section()
        main_layout.addWidget(links_section)
        
        # Spacer to push everything up
        main_layout.addStretch()
    
    def _create_stage_section(self) -> QWidget:
        """Create current stage section."""
        section = QWidget()
        layout = QVBoxLayout(section)
        layout.setSpacing(10)
        
        # Section title
        title = QLabel("Current Research Stage")
        title_font = QFont()
        title_font.setPointSize(14)
        title.setFont(title_font)
        layout.addWidget(title)
        
        # Stage display (big, explicit)
        self._stage_label = QLabel("Evaluating...")
        stage_font = QFont()
        stage_font.setPointSize(32)
        stage_font.setBold(True)
        self._stage_label.setFont(stage_font)
        self._stage_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # Stage description
        self._stage_description = QLabel("")
        desc_font = QFont()
        desc_font.setPointSize(12)
        self._stage_description.setFont(desc_font)
        self._stage_description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._stage_description.setWordWrap(True)
        
        layout.addWidget(self._stage_label)
        layout.addWidget(self._stage_description)
        
        return section
    
    def _create_verdict_section(self) -> QWidget:
        """Create system verdict section."""
        section = QWidget()
        layout = QVBoxLayout(section)
        layout.setSpacing(10)
        
        # Section title
        title = QLabel("System Verdict")
        title_font = QFont()
        title_font.setPointSize(14)
        title.setFont(title_font)
        layout.addWidget(title)
        
        # Verdict display (one sentence)
        self._verdict_label = QLabel("Evaluating system state...")
        verdict_font = QFont()
        verdict_font.setPointSize(16)
        self._verdict_label.setFont(verdict_font)
        self._verdict_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._verdict_label.setWordWrap(True)
        
        # Blocking reason (if any)
        self._blocking_label = QLabel("")
        blocking_font = QFont()
        blocking_font.setPointSize(12)
        blocking_font.setItalic(True)
        self._blocking_label.setFont(blocking_font)
        self._blocking_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._blocking_label.setWordWrap(True)
        
        layout.addWidget(self._verdict_label)
        layout.addWidget(self._blocking_label)
        
        return section
    
    def _create_actions_section(self) -> QWidget:
        """Create primary actions section (MAX 2 buttons)."""
        section = QWidget()
        layout = QHBoxLayout(section)
        layout.setSpacing(20)
        
        # Primary Action 1
        self._primary_action_1 = QPushButton("Evaluate State")
        self._primary_action_1.setMinimumHeight(50)
        self._primary_action_1.clicked.connect(self._refresh_state)
        layout.addWidget(self._primary_action_1)
        
        # Primary Action 2
        self._primary_action_2 = QPushButton("Start Research")
        self._primary_action_2.setMinimumHeight(50)
        self._primary_action_2.clicked.connect(self._handle_start_research)
        layout.addWidget(self._primary_action_2)
        
        return section
    
    def _create_links_section(self) -> QWidget:
        """Create secondary links section."""
        section = QWidget()
        layout = QVBoxLayout(section)
        layout.setSpacing(10)
        
        # Section title
        title = QLabel("View Details")
        title_font = QFont()
        title_font.setPointSize(12)
        title.setFont(title_font)
        layout.addWidget(title)
        
        # Links container
        links_container = QWidget()
        links_layout = QHBoxLayout(links_container)
        links_layout.setSpacing(15)
        
        # Operation tab link
        self._op_link = QPushButton("Operation")
        self._op_link.setFlat(True)
        self._op_link.setStyleSheet("color: #0066cc; text-decoration: underline;")
        self._op_link.clicked.connect(lambda: self._navigate_to_tab("operation"))
        links_layout.addWidget(self._op_link)
        
        # Gate Dashboard link
        self._gate_link = QPushButton("Gate Dashboard")
        self._gate_link.setFlat(True)
        self._gate_link.setStyleSheet("color: #0066cc; text-decoration: underline;")
        self._gate_link.clicked.connect(lambda: self._navigate_to_tab("gate_dashboard"))
        links_layout.addWidget(self._gate_link)
        
        # Report link
        self._report_link = QPushButton("Report")
        self._report_link.setFlat(True)
        self._report_link.setStyleSheet("color: #0066cc; text-decoration: underline;")
        self._report_link.clicked.connect(lambda: self._navigate_to_tab("report"))
        links_layout.addWidget(self._report_link)
        
        # Allocation link
        self._allocation_link = QPushButton("Allocation")
        self._allocation_link.setFlat(True)
        self._allocation_link.setStyleSheet("color: #0066cc; text-decoration: underline;")
        self._allocation_link.clicked.connect(lambda: self._navigate_to_tab("allocation"))
        links_layout.addWidget(self._allocation_link)
        
        links_layout.addStretch()
        layout.addWidget(links_container)
        
        return section
    
    def _refresh_state(self):
        """Refresh research flow state and build narrative."""
        try:
            # Evaluate current state using kernel
            self._current_state = self._controller.evaluate_current_state()
            
            # Build human-readable narrative
            self._current_narrative = build_research_narrative(self._current_state)
            
            # Update UI with narrative
            self._update_ui_from_narrative()
            
        except Exception as e:
            logger.error(f"Failed to refresh research flow state: {e}")
            self._stage_label.setText("ERROR")
            self._stage_description.setText("Failed to evaluate research state")
            self._verdict_label.setText(f"Error: {str(e)}")
            self._blocking_label.setText("Check system logs for details")
    
    def _update_ui_from_narrative(self):
        """Update UI from current research narrative."""
        if not self._current_narrative:
            return
        
        # Update stage display
        stage = self._current_narrative.stage
        self._stage_label.setText(stage.value.upper().replace("_", " "))
        self._stage_description.setText(self._current_narrative.why)
        
        # Update verdict with headline
        self._verdict_label.setText(self._current_narrative.headline)
        
        # Set color based on severity
        if self._current_narrative.severity == "BLOCKED":
            self._verdict_label.setStyleSheet("color: #cc0000;")
            self._blocking_label.setText(f"Blocked: {self._current_narrative.primary_reason_code.value}")
            self._blocking_label.setStyleSheet("color: #cc0000;")
        elif self._current_narrative.severity == "WARN":
            self._verdict_label.setStyleSheet("color: #ff9900;")
            self._blocking_label.setText("Warning: Check system state")
            self._blocking_label.setStyleSheet("color: #ff9900;")
        else:  # OK
            self._verdict_label.setStyleSheet("color: #00aa00;")
            self._blocking_label.setText("")
            self._blocking_label.setStyleSheet("")
        
        # Update primary actions with narrative next step
        self._update_primary_actions_from_narrative()
        
        # Update secondary links
        self._update_secondary_links()
    
    def _update_primary_actions_from_narrative(self):
        """Update primary actions based on current narrative."""
        if not self._current_narrative:
            return
        
        # Action 1: Always "Refresh Evaluation"
        self._primary_action_1.setText("Refresh Evaluation")
        
        # Action 2: Use narrative next step
        self._primary_action_2.setText(self._current_narrative.next_step_label)
        self._primary_action_2.setEnabled(True)
        
        # Connect action 2 to appropriate handler based on action ID
        try:
            # Disconnect previous connections
            self._primary_action_2.clicked.disconnect()
        except:
            pass  # No previous connections
        
        # Connect based on action ID
        action_id = self._current_narrative.next_step_action
        if action_id == "open_data_readiness":
            self._primary_action_2.clicked.connect(lambda: self._navigate_to_tab("operation"))
        elif action_id == "run_research":
            self._primary_action_2.clicked.connect(self._handle_start_research)
        elif action_id == "open_gate_dashboard":
            self._primary_action_2.clicked.connect(lambda: self._navigate_to_tab("gate_dashboard"))
        elif action_id == "open_report":
            self._primary_action_2.clicked.connect(lambda: self._navigate_to_tab("report"))
        elif action_id == "open_audit":
            self._primary_action_2.clicked.connect(lambda: self._navigate_to_tab("audit"))
        elif action_id == "build_portfolio":
            self._primary_action_2.clicked.connect(lambda: self._navigate_to_tab("allocation"))
        elif action_id == "open_admission":
            self._primary_action_2.clicked.connect(lambda: self._navigate_to_tab("portfolio_admission"))
        elif action_id == "retry_last":
            self._primary_action_2.clicked.connect(self._refresh_state)
        else:
            # Default to refresh
            self._primary_action_2.clicked.connect(self._refresh_state)
    
    def _update_secondary_links(self):
        """Update secondary links based on current state."""
        if not self._current_state:
            return
        
        # All links are always available but will pass through controller
        # when clicked (enforced in _navigate_to_tab)
        pass
    
    def _handle_start_research(self):
        """Handle start research action (legacy method, now uses narrative)."""
        if not self._current_narrative:
            return
        
        # Use narrative action ID to determine what to do
        action_id = self._current_narrative.next_step_action
        
        if self._current_narrative.severity == "BLOCKED":
            # Show narrative details for blocked state
            self._show_narrative_details()
        else:
            # Navigate based on action ID
            if action_id == "run_research":
                self._navigate_to_tab("operation", {"action": "start_research"})
            elif action_id == "open_gate_dashboard":
                self._navigate_to_tab("gate_dashboard", {"action": "monitor_jobs"})
            elif action_id == "open_report":
                self._navigate_to_tab("report", {"action": "analyze_results"})
            elif action_id == "build_portfolio":
                self._navigate_to_tab("allocation", {"action": "make_decisions"})
            else:
                # Default to operation tab
                self._navigate_to_tab("operation", {"action": "start_research"})
    
    def _show_narrative_details(self):
        """Show detailed narrative information."""
        if not self._current_narrative:
            return
        
        # TODO: Implement proper narrative details dialog
        # For now, log the details
        logger.info(f"Narrative details:")
        logger.info(f"  Headline: {self._current_narrative.headline}")
        logger.info(f"  Why: {self._current_narrative.why}")
        logger.info(f"  Developer View: {self._current_narrative.developer_view}")
        logger.info(f"  Business View: {self._current_narrative.business_view}")
        logger.info(f"  Next Step: {self._current_narrative.next_step_label}")
        logger.info(f"  Severity: {self._current_narrative.severity}")
        logger.info(f"  Reason Code: {self._current_narrative.primary_reason_code.value}")
        
        # Update UI to show more details temporarily
        if self._current_narrative.severity == "BLOCKED":
            self._blocking_label.setText(
                f"{self._current_narrative.primary_reason_code.value}: "
                f"{self._current_narrative.developer_view[:100]}..."
            )
    
    def _navigate_to_tab(self, tab_name: str, context: Optional[dict] = None):
        """
        Navigate to another tab (MUST pass through ResearchFlowController).
        
        This method enforces that ALL navigation passes through the kernel.
        The kernel validates if navigation is allowed based on current state.
        
        Args:
            tab_name: Name of tab to navigate to
            context: Optional navigation context
        """
        if not self._current_state:
            logger.warning("Cannot navigate: no current state")
            return
        
        # Validate navigation through kernel
        is_allowed, reason, classification = self._controller.validate_ui_navigation(
            tab_name, self._current_state.current_stage
        )
        
        if not is_allowed:
            # Show blocking message
            logger.warning(f"Navigation to {tab_name} blocked: {reason}")
            
            # TODO: Show user-friendly blocking dialog
            self._show_navigation_blocked_dialog(tab_name, reason, classification)
            return
        
        # Log navigation details
        if classification:
            logger.info(
                f"Navigating to {tab_name} ({classification.tier.value} tier) "
                f"from stage {self._current_state.current_stage.value}"
            )
        
        # Emit navigation signal
        self.navigate_to_tab.emit(tab_name, context or {})
        
        logger.info(f"Navigating to {tab_name} with context: {context}")
    
    def _show_navigation_blocked_dialog(self, tab_name: str, reason: str, classification):
        """Show dialog when navigation is blocked."""
        # TODO: Implement proper blocking dialog
        logger.warning(f"Navigation to {tab_name} blocked: {reason}")
        
        # For now, update verdict to show blocking
        if self._current_state:
            self._verdict_label.setText(f"Cannot navigate to {tab_name}")
            self._verdict_label.setStyleSheet("color: #cc0000;")
            self._blocking_label.setText(reason)
            self._blocking_label.setStyleSheet("color: #cc0000;")
    
    def closeEvent(self, event):
        """Handle tab close event."""
        self._refresh_timer.stop()
        super().closeEvent(event)