"""
Explain Hub Tabs Widget - v2.2-C

Tabbed widget for job explanation with three tabs:
1. Narrative: ResearchNarrativeV1 content (headline, why, next_step)
2. Dev: Technical details, gate summaries, explain dictionary
3. Biz: Business implications, recommendations

Driven strictly by ResearchNarrativeV1 (SSOT narrative contract) and Explain Dictionary outputs.

Actionable Explain Layer: Emits UI actions for drilldown navigation, evidence viewing, and gate explanation.
All actions are routed through ActionRouterService for governance compliance.
"""

import logging
from typing import Optional, Dict, Any

from PySide6.QtCore import Qt, Signal, Slot, QObject  # type: ignore
from PySide6.QtWidgets import (  # type: ignore
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QLabel, QTextEdit, QGroupBox, QPushButton, QScrollArea,
    QSizePolicy, QComboBox
)
from PySide6.QtGui import QFont, QTextCursor  # type: ignore

from gui.services.cross_job_gate_summary_service import JobGateSummary
from contracts.research.research_narrative import (
    ResearchNarrativeV1,
    NarrativeActionId,
    create_narrative,
)
from contracts.research.explain_persona import (
    ExplainPersona,
    get_default_persona,
    get_persona_display_name,
    validate_persona,
)
from gui.services.explain_export_service import (
    ExplainExportService,
    ExportFormat,
    ExportContent,
    get_explain_export_service,
)
from contracts.research.research_flow_kernel import (
    ResearchStage,
    ResearchFlowState,
    GateReasonCode,
)
from core.research.research_narrative_builder import (
    ResearchNarrativeBuilder,
    get_stage_narrative,
    build_research_narrative,
)
from contracts.portfolio.gate_summary_schemas import GateSummaryV1, GateStatus
from gui.services.action_router_service import get_action_router_service
from contracts.ui_action_registry import get_action_metadata_for_target

logger = logging.getLogger(__name__)


class ExplainHubTabs(QWidget):
    """Tabbed explain hub widget with Narrative/Dev/Biz tabs."""
    
    # Signal emitted when narrative is loaded
    narrative_loaded = Signal(ResearchNarrativeV1)
    
    # Signal emitted when UI action should be routed
    action_requested = Signal(str, dict)  # target, context
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_job_id: Optional[str] = None
        self.current_job_summary: Optional[JobGateSummary] = None
        self.current_narrative: Optional[ResearchNarrativeV1] = None
        self.current_persona: ExplainPersona = get_default_persona()
        
        self.setup_ui()
        
    def setup_ui(self):
        """Initialize the UI with three tabs."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Create tab widget
        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #555555;
                background-color: #1E1E1E;
                border-radius: 4px;
                margin-top: 4px;
            }
            QTabBar::tab {
                background-color: #2A2A2A;
                color: #B0B0B0;
                padding: 8px 16px;
                margin-right: 2px;
                border: 1px solid #555555;
                border-bottom: none;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
                font-size: 11px;
                font-weight: bold;
            }
            QTabBar::tab:selected {
                background-color: #1E1E1E;
                color: #E6E6E6;
                border-color: #0288d1;
            }
            QTabBar::tab:hover:!selected {
                background-color: #3A3A3A;
                color: #E6E6E6;
            }
        """)
        
        # Create tabs
        self.narrative_tab = self._create_narrative_tab()
        self.dev_tab = self._create_dev_tab()
        self.biz_tab = self._create_biz_tab()
        
        # Add tabs to widget
        self.tab_widget.addTab(self.narrative_tab, "Narrative")
        self.tab_widget.addTab(self.dev_tab, "Dev")
        self.tab_widget.addTab(self.biz_tab, "Biz")
        
        main_layout.addWidget(self.tab_widget)
        
        # Status label at bottom
        self.status_label = QLabel("No job selected")
        self.status_label.setStyleSheet("color: #9A9A9A; font-size: 10px; padding: 4px;")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.status_label)
        
    def _create_narrative_tab(self) -> QWidget:
        """Create the Narrative tab with ResearchNarrativeV1 content and persona selector."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)
        
        # Header with persona selector
        header_widget = QWidget()
        header_widget.setStyleSheet("background-color: #1A1A1A; border-radius: 4px; padding: 8px;")
        header_layout = QVBoxLayout(header_widget)
        
        # Title row
        title_row = QWidget()
        title_layout = QHBoxLayout(title_row)
        title_layout.setContentsMargins(0, 0, 0, 0)
        
        self.narrative_title = QLabel("Research Narrative")
        self.narrative_title.setStyleSheet("font-size: 14px; font-weight: bold; color: #E6E6E6;")
        title_layout.addWidget(self.narrative_title)
        
        title_layout.addStretch()
        
        # Persona selector
        persona_selector_widget = QWidget()
        persona_selector_layout = QHBoxLayout(persona_selector_widget)
        persona_selector_layout.setContentsMargins(0, 0, 0, 0)
        persona_selector_layout.setSpacing(4)
        
        persona_label = QLabel("Audience:")
        persona_label.setStyleSheet("color: #B0B0B0; font-size: 10px;")
        persona_selector_layout.addWidget(persona_label)
        
        self.persona_combo = QComboBox()
        self.persona_combo.setStyleSheet("""
            QComboBox {
                background-color: #2A2A2A;
                color: #E6E6E6;
                border: 1px solid #555555;
                border-radius: 3px;
                padding: 4px 8px;
                font-size: 10px;
                min-width: 120px;
            }
            QComboBox:hover {
                border: 1px solid #0288d1;
            }
            QComboBox::drop-down {
                border: none;
                width: 20px;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 4px solid transparent;
                border-right: 4px solid transparent;
                border-top: 6px solid #B0B0B0;
                margin-right: 8px;
            }
        """)
        self.persona_combo.setToolTip("Select audience persona for narrative content")
        
        # Add personas to combo box
        for persona in ExplainPersona:
            display_name = get_persona_display_name(persona)
            self.persona_combo.addItem(display_name, persona.value)
        
        # Set default persona
        default_persona = get_default_persona()
        default_index = self.persona_combo.findData(default_persona.value)
        if default_index >= 0:
            self.persona_combo.setCurrentIndex(default_index)
        
        self.persona_combo.currentIndexChanged.connect(self._on_persona_changed)
        persona_selector_layout.addWidget(self.persona_combo)
        
        title_layout.addWidget(persona_selector_widget)
        header_layout.addWidget(title_row)
        
        self.narrative_subtitle = QLabel("SSOT narrative contract v2.3.0 with persona support")
        self.narrative_subtitle.setStyleSheet("color: #9A9A9A; font-size: 10px;")
        self.narrative_subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_layout.addWidget(self.narrative_subtitle)
        
        layout.addWidget(header_widget)
        
        # Severity indicator
        self.severity_widget = QWidget()
        self.severity_widget.setStyleSheet("background-color: #2A2A2A; border-radius: 4px; padding: 8px;")
        severity_layout = QHBoxLayout(self.severity_widget)
        
        self.severity_label = QLabel("Severity:")
        self.severity_label.setStyleSheet("color: #B0B0B0; font-size: 11px; font-weight: bold;")
        severity_layout.addWidget(self.severity_label)
        
        self.severity_value = QLabel("—")
        self.severity_value.setStyleSheet("color: #9E9E9E; font-size: 11px; font-weight: bold;")
        severity_layout.addWidget(self.severity_value)
        
        severity_layout.addStretch()
        
        self.stage_label = QLabel("Stage:")
        self.stage_label.setStyleSheet("color: #B0B0B0; font-size: 11px; font-weight: bold;")
        severity_layout.addWidget(self.stage_label)
        
        self.stage_value = QLabel("—")
        self.stage_value.setStyleSheet("color: #9E9E9E; font-size: 11px;")
        severity_layout.addWidget(self.stage_value)
        
        layout.addWidget(self.severity_widget)
        
        # Headline
        headline_group = QGroupBox("Headline")
        headline_group.setStyleSheet("""
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
        headline_layout = QVBoxLayout(headline_group)
        
        self.headline_text = QLabel("Select a job to view narrative")
        self.headline_text.setStyleSheet("color: #E6E6E6; font-size: 12px; padding: 8px;")
        self.headline_text.setWordWrap(True)
        self.headline_text.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        headline_layout.addWidget(self.headline_text)
        
        layout.addWidget(headline_group)
        
        # Why explanation
        why_group = QGroupBox("Why")
        why_group.setStyleSheet(headline_group.styleSheet())
        why_layout = QVBoxLayout(why_group)
        
        self.why_text = QTextEdit()
        self.why_text.setReadOnly(True)
        self.why_text.setStyleSheet("""
            QTextEdit {
                background-color: #1E1E1E;
                color: #B0B0B0;
                border: none;
                font-size: 11px;
                font-family: 'Segoe UI', 'Arial', sans-serif;
            }
        """)
        self.why_text.setPlaceholderText("Explanation will appear here when a job is selected")
        why_layout.addWidget(self.why_text)
        
        layout.addWidget(why_group)
        
        # Next step
        next_step_group = QGroupBox("Next Step")
        next_step_group.setStyleSheet(headline_group.styleSheet())
        next_step_layout = QVBoxLayout(next_step_group)
        
        self.next_step_text = QLabel("—")
        self.next_step_text.setStyleSheet("color: #E6E6E6; font-size: 11px; padding: 8px;")
        self.next_step_text.setWordWrap(True)
        next_step_layout.addWidget(self.next_step_text)
        
        layout.addWidget(next_step_group)
        
        # Drilldown actions (if any)
        self.actions_group = QGroupBox("Actions")
        self.actions_group.setStyleSheet(headline_group.styleSheet())
        self.actions_group.setVisible(False)
        actions_layout = QVBoxLayout(self.actions_group)
        
        self.actions_container = QWidget()
        self.actions_container_layout = QVBoxLayout(self.actions_container)
        self.actions_container_layout.setSpacing(4)
        actions_layout.addWidget(self.actions_container)
        
        layout.addWidget(self.actions_group)
        
        layout.addStretch()
        
        return tab
        
    def _create_dev_tab(self) -> QWidget:
        """Create the Dev tab with technical details and action buttons."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)
        
        # Header
        header_label = QLabel("Technical Details")
        header_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #E6E6E6;")
        header_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(header_label)
        
        # Action buttons row
        action_widget = QWidget()
        action_widget.setStyleSheet("background-color: #2A2A2A; border-radius: 4px; padding: 8px;")
        action_layout = QHBoxLayout(action_widget)
        action_layout.setSpacing(8)
        
        # Gate explanation button
        self.gate_explain_btn = QPushButton("🔍 Explain Gate")
        self.gate_explain_btn.setStyleSheet("""
            QPushButton {
                background-color: #0288d1;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 6px 12px;
                font-size: 10px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #039be5;
            }
            QPushButton:disabled {
                background-color: #555555;
                color: #9A9A9A;
            }
        """)
        self.gate_explain_btn.setToolTip("Open detailed gate explanation dialog")
        self.gate_explain_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.gate_explain_btn.setEnabled(False)
        self.gate_explain_btn.clicked.connect(self._on_gate_explain_clicked)
        action_layout.addWidget(self.gate_explain_btn)
        
        # Evidence viewer button
        self.evidence_viewer_btn = QPushButton("📁 View Evidence")
        self.evidence_viewer_btn.setStyleSheet("""
            QPushButton {
                background-color: #7b1fa2;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 6px 12px;
                font-size: 10px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #8e24aa;
            }
            QPushButton:disabled {
                background-color: #555555;
                color: #9A9A9A;
            }
        """)
        self.evidence_viewer_btn.setToolTip("Open evidence browser for this job")
        self.evidence_viewer_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.evidence_viewer_btn.setEnabled(False)
        self.evidence_viewer_btn.clicked.connect(self._on_evidence_viewer_clicked)
        action_layout.addWidget(self.evidence_viewer_btn)
        
        # Artifact navigator button
        self.artifact_nav_btn = QPushButton("📄 Open Artifact")
        self.artifact_nav_btn.setStyleSheet("""
            QPushButton {
                background-color: #388e3c;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 6px 12px;
                font-size: 10px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #43a047;
            }
            QPushButton:disabled {
                background-color: #555555;
                color: #9A9A9A;
            }
        """)
        self.artifact_nav_btn.setToolTip("Open artifact navigator for this job")
        self.artifact_nav_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.artifact_nav_btn.setEnabled(False)
        self.artifact_nav_btn.clicked.connect(self._on_artifact_nav_clicked)
        action_layout.addWidget(self.artifact_nav_btn)
        
        # Export button with dropdown
        self.export_btn = QPushButton("📤 Export")
        self.export_btn.setStyleSheet("""
            QPushButton {
                background-color: #ff9800;
                color: white;
                border: none;
                border-radius: 3px;
                padding: 6px 12px;
                font-size: 10px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #ffb74d;
            }
            QPushButton:disabled {
                background-color: #555555;
                color: #9A9A9A;
            }
        """)
        self.export_btn.setToolTip("Export narrative in various formats")
        self.export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.export_btn.setEnabled(False)
        self.export_btn.clicked.connect(self._on_export_clicked)
        action_layout.addWidget(self.export_btn)
        
        action_layout.addStretch()
        layout.addWidget(action_widget)
        
        # Gate summary section
        gate_group = QGroupBox("Gate Summary")
        gate_group.setStyleSheet("""
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
        gate_layout = QVBoxLayout(gate_group)
        
        self.gate_summary_text = QTextEdit()
        self.gate_summary_text.setReadOnly(True)
        self.gate_summary_text.setStyleSheet("""
            QTextEdit {
                background-color: #1E1E1E;
                color: #B0B0B0;
                border: none;
                font-size: 10px;
                font-family: 'Consolas', 'Monaco', monospace;
            }
        """)
        self.gate_summary_text.setPlaceholderText("Gate summary will appear here when a job is selected")
        gate_layout.addWidget(self.gate_summary_text)
        
        layout.addWidget(gate_group)
        
        # Job data section
        job_data_group = QGroupBox("Job Data")
        job_data_group.setStyleSheet(gate_group.styleSheet())
        job_data_layout = QVBoxLayout(job_data_group)
        
        self.job_data_text = QTextEdit()
        self.job_data_text.setReadOnly(True)
        self.job_data_text.setStyleSheet(self.gate_summary_text.styleSheet())
        self.job_data_text.setPlaceholderText("Job data will appear here when a job is selected")
        job_data_layout.addWidget(self.job_data_text)
        
        layout.addWidget(job_data_group)
        
        # Explain dictionary section (if available)
        self.explain_group = QGroupBox("Explain Dictionary")
        self.explain_group.setStyleSheet(gate_group.styleSheet())
        self.explain_group.setVisible(False)
        explain_layout = QVBoxLayout(self.explain_group)
        
        self.explain_text = QTextEdit()
        self.explain_text.setReadOnly(True)
        self.explain_text.setStyleSheet(self.gate_summary_text.styleSheet())
        explain_layout.addWidget(self.explain_text)
        
        layout.addWidget(self.explain_group)
        
        layout.addStretch()
        
        return tab
        
    def _create_biz_tab(self) -> QWidget:
        """Create the Biz tab with business implications."""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)
        
        # Header
        header_label = QLabel("Business View")
        header_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #E6E6E6;")
        header_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(header_label)
        
        # Business view from narrative
        biz_view_group = QGroupBox("Business Implications")
        biz_view_group.setStyleSheet("""
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
        biz_view_layout = QVBoxLayout(biz_view_group)
        
        self.biz_view_text = QTextEdit()
        self.biz_view_text.setReadOnly(True)
        self.biz_view_text.setStyleSheet("""
            QTextEdit {
                background-color: #1E1E1E;
                color: #B0B0B0;
                border: none;
                font-size: 11px;
                font-family: 'Segoe UI', 'Arial', sans-serif;
            }
        """)
        self.biz_view_text.setPlaceholderText("Business view will appear here when a job is selected")
        biz_view_layout.addWidget(self.biz_view_text)
        
        layout.addWidget(biz_view_group)
        
        # Recommendations
        recommendations_group = QGroupBox("Recommendations")
        recommendations_group.setStyleSheet(biz_view_group.styleSheet())
        recommendations_layout = QVBoxLayout(recommendations_group)
        
        self.recommendations_text = QLabel("—")
        self.recommendations_text.setStyleSheet("color: #E6E6E6; font-size: 11px; padding: 8px;")
        self.recommendations_text.setWordWrap(True)
        recommendations_layout.addWidget(self.recommendations_text)
        
        layout.addWidget(recommendations_group)
        
        # Risk assessment
        risk_group = QGroupBox("Risk Assessment")
        risk_group.setStyleSheet(biz_view_group.styleSheet())
        risk_layout = QVBoxLayout(risk_group)
        
        self.risk_text = QLabel("—")
        self.risk_text.setStyleSheet("color: #E6E6E6; font-size: 11px; padding: 8px;")
        self.risk_text.setWordWrap(True)
        risk_layout.addWidget(self.risk_text)
        
        layout.addWidget(risk_group)
        
        layout.addStretch()
        
        return tab
    
    def update_for_job(self, job_id: str, job_summary: JobGateSummary):
        """
        Update all tabs with data for the specified job.
        
        Args:
            job_id: Selected job ID
            job_summary: Job gate summary data
        """
        self.current_job_id = job_id
        self.current_job_summary = job_summary
        
        # Update status
        self.status_label.setText(f"Job: {job_id[:12]}... | Updated")
        
        # Enable action buttons
        self._update_action_buttons(True)
        
        try:
            # Build ResearchNarrativeV1 from job data
            narrative = self._build_narrative_for_job(job_summary)
            self.current_narrative = narrative
            
            # Update Narrative tab
            self._update_narrative_tab(narrative)
            
            # Update Dev tab
            self._update_dev_tab(job_summary)
            
            # Update Biz tab
            self._update_biz_tab(narrative, job_summary)
            
            # Emit signal
            self.narrative_loaded.emit(narrative)
            
        except Exception as e:
            logger.error(f"Failed to update ExplainHubTabs for job {job_id}: {e}")
            self._show_error(f"Failed to generate explanation: {str(e)}")
            # Disable action buttons on error
            self._update_action_buttons(False)
    
    def _on_persona_changed(self, index: int):
        """Handle persona selection change."""
        if index < 0:
            return
        
        persona_value = self.persona_combo.itemData(index)
        if not persona_value:
            return
        
        try:
            persona = validate_persona(persona_value)
            self.current_persona = persona
            logger.info(f"Persona changed to: {persona.value}")
            
            # Refresh narrative if job is selected
            if self.current_job_summary:
                self._refresh_narrative_for_current_persona()
        except ValueError as e:
            logger.error(f"Invalid persona selection: {e}")
    
    def _refresh_narrative_for_current_persona(self):
        """Refresh narrative with current persona."""
        if not self.current_job_summary:
            return
        
        try:
            # Rebuild narrative with current persona
            narrative = self._build_narrative_for_job(self.current_job_summary)
            self.current_narrative = narrative
            
            # Update Narrative tab
            self._update_narrative_tab(narrative)
            
            # Update Biz tab (persona affects business view)
            self._update_biz_tab(narrative, self.current_job_summary)
            
            logger.info(f"Narrative refreshed for persona: {self.current_persona.value}")
        except Exception as e:
            logger.error(f"Failed to refresh narrative for persona {self.current_persona.value}: {e}")
    
    def _build_narrative_for_job(self, job_summary: JobGateSummary) -> ResearchNarrativeV1:
        """Build ResearchNarrativeV1 from JobGateSummary with current persona."""
        # Extract job data
        job_data = job_summary.job_data
        gate_summary = job_summary.gate_summary
        
        # Determine research stage based on job data and gate summary
        stage = self._determine_research_stage(job_data, gate_summary)
        
        # Determine if blocked based on gate status
        is_blocked = gate_summary.overall_status == GateStatus.REJECT
        blocking_reason = None
        if is_blocked:
            # Use first failing gate's reason code if available
            for gate in gate_summary.gates:
                if gate.status == GateStatus.REJECT and gate.reason_codes:
                    blocking_reason = GateReasonCode(gate.reason_codes[0])
                    break
        
        # Build system context for narrative
        system_context = {
            "job_id": job_summary.job_id,
            "job_data": job_data,
            "gate_summary": gate_summary.model_dump(),
            "research_jobs": [{"job_id": job_summary.job_id, "data": job_data}],
            "artifacts": self._extract_artifacts_from_job_data(job_data),
        }
        
        # Use convenience function to get narrative with current persona
        narrative = get_stage_narrative(
            stage=stage,
            is_blocked=is_blocked,
            blocking_reason=blocking_reason,
            system_context=system_context,
            persona=self.current_persona,
        )
        
        return narrative
    
    def _determine_research_stage(self, job_data: Dict[str, Any], gate_summary: GateSummaryV1) -> ResearchStage:
        """Determine research stage based on job data and gate summary."""
        # Simplified logic - in real implementation, use ResearchFlowController logic
        job_type = job_data.get("job_type", "")
        
        if job_type == "RUN_RESEARCH_WFS":
            # Check if job is completed
            job_status = job_data.get("status", "")
            if job_status == "COMPLETED":
                # Check if gate summary has passes
                if gate_summary.overall_status == GateStatus.PASS:
                    return ResearchStage.DECISION
                else:
                    return ResearchStage.OUTCOME_TRIAGE
            else:
                return ResearchStage.RUN_RESEARCH
        else:
            # Default to DATA_READINESS for non-research jobs
            return ResearchStage.DATA_READINESS
    
    def _extract_artifacts_from_job_data(self, job_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract artifact information from job data."""
        artifacts = {}
        
        # Check for common artifact fields
        if "artifacts" in job_data:
            artifacts = job_data.get("artifacts", {})
        elif "artifact_paths" in job_data:
            # Convert list to dict
            for path in job_data.get("artifact_paths", []):
                artifacts[path.split("/")[-1]] = {"path": path}
        
        return artifacts
    
    def _update_narrative_tab(self, narrative: ResearchNarrativeV1):
        """Update Narrative tab with ResearchNarrativeV1 content."""
        # Update severity and stage
        severity_color = {
            "OK": "#4CAF50",
            "WARN": "#FF9800",
            "BLOCKED": "#F44336",
            "INFO": "#2196F3",
        }.get(narrative.severity, "#9E9E9E")
        
        self.severity_value.setText(narrative.severity)
        self.severity_value.setStyleSheet(f"color: {severity_color}; font-size: 11px; font-weight: bold;")
        
        self.stage_value.setText(narrative.stage.value.replace("_", " ").title())
        
        # Update headline
        self.headline_text.setText(narrative.headline)
        
        # Update why explanation
        self.why_text.setPlainText(narrative.why)
        
        # Update next step
        self.next_step_text.setText(narrative.next_step_label)
        
        # Update actions if any
        self._update_actions(narrative.drilldown_actions)
    
    def _update_actions(self, actions: list):
        """Update drilldown actions in Narrative tab."""
        # Clear existing actions
        while self.actions_container_layout.count():
            item = self.actions_container_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        if not actions:
            self.actions_group.setVisible(False)
            return
        
        # Create action buttons
        for action in actions[:5]:  # Limit to 5 actions
            btn = QPushButton(action.get("label", "Action"))
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #2A2A2A;
                    color: #E6E6E6;
                    border: 1px solid #555555;
                    border-radius: 3px;
                    padding: 6px 12px;
                    font-size: 10px;
                    text-align: left;
                }
                QPushButton:hover {
                    background-color: #3A3A3A;
                    border: 1px solid #3A8DFF;
                }
            """)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            
            # Store action data as property
            btn.setProperty("action_data", action)
            
            # Connect click handler
            btn.clicked.connect(lambda checked, b=btn: self._on_action_clicked(b))
            
            self.actions_container_layout.addWidget(btn)
        
        self.actions_group.setVisible(True)
        self.actions_group.show()
    
    def _on_action_clicked(self, button: QPushButton):
        """Handle action button click - route through ActionRouterService."""
        action = button.property("action_data")
        if not action:
            return
        
        action_type = action.get("action", "")
        label = action.get("label", "")
        logger.info(f"ExplainHub action clicked: {action_type} ({label})")
        
        # Route action through ActionRouterService
        self._route_action(action_type, action)
        
    def _update_dev_tab(self, job_summary: JobGateSummary):
        """Update Dev tab with technical details."""
        # Update gate summary
        gate_text = self._format_gate_summary(job_summary.gate_summary)
        self.gate_summary_text.setPlainText(gate_text)
        
        # Update job data
        job_data_text = self._format_job_data(job_summary.job_data)
        self.job_data_text.setPlainText(job_data_text)
        
        # Update explain dictionary if available
        explain_data = self._get_explain_dictionary(job_summary.job_id)
        if explain_data:
            self.explain_text.setPlainText(self._format_explain_dictionary(explain_data))
            self.explain_group.setVisible(True)
        else:
            self.explain_group.setVisible(False)
    
    def _format_gate_summary(self, gate_summary: GateSummaryV1) -> str:
        """Format gate summary for display."""
        lines = []
        
        lines.append(f"Overall Status: {gate_summary.overall_status.value}")
        lines.append(f"Overall Message: {gate_summary.overall_message}")
        lines.append(f"Total Gates: {gate_summary.total_gates}")
        lines.append(f"Evaluated At: {gate_summary.evaluated_at_utc}")
        lines.append("")
        
        if gate_summary.counts:
            lines.append("Gate Counts:")
            for status, count in gate_summary.counts.items():
                lines.append(f"  {status}: {count}")
            lines.append("")
        
        lines.append("Individual Gates:")
        for i, gate in enumerate(gate_summary.gates, 1):
            lines.append(f"{i}. {gate.gate_name} ({gate.gate_id})")
            lines.append(f"   Status: {gate.status.value}")
            lines.append(f"   Message: {gate.message}")
            if gate.reason_codes:
                lines.append(f"   Reason Codes: {', '.join(gate.reason_codes)}")
            if gate.details:
                lines.append(f"   Details: {len(gate.details)} items")
            lines.append("")
        
        return "\n".join(lines)
    
    def _format_job_data(self, job_data: Dict[str, Any]) -> str:
        """Format job data for display."""
        import json
        try:
            # Pretty print JSON
            return json.dumps(job_data, indent=2, default=str)
        except:
            # Fallback to string representation
            return str(job_data)
    
    def _get_explain_dictionary(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get explain dictionary for job (placeholder implementation)."""
        # TODO: Implement actual explain dictionary fetching
        # For now, return None
        return None
    
    def _format_explain_dictionary(self, explain_data: Dict[str, Any]) -> str:
        """Format explain dictionary for display."""
        import json
        try:
            return json.dumps(explain_data, indent=2, default=str)
        except:
            return str(explain_data)
    
    def _update_biz_tab(self, narrative: ResearchNarrativeV1, job_summary: JobGateSummary):
        """Update Biz tab with business implications."""
        # Update business view from narrative
        self.biz_view_text.setPlainText(narrative.business_view)
        
        # Generate recommendations based on narrative and gate summary
        recommendations = self._generate_recommendations(narrative, job_summary.gate_summary)
        self.recommendations_text.setText(recommendations)
        
        # Generate risk assessment
        risk_assessment = self._generate_risk_assessment(narrative, job_summary.gate_summary)
        self.risk_text.setText(risk_assessment)
    
    def _generate_recommendations(self, narrative: ResearchNarrativeV1, gate_summary: GateSummaryV1) -> str:
        """Generate business recommendations."""
        recommendations = []
        
        # Based on severity
        if narrative.severity == "BLOCKED":
            recommendations.append("Immediate action required to resolve blocking issues.")
            recommendations.append("Review gate failures before proceeding.")
        elif narrative.severity == "WARN":
            recommendations.append("Proceed with caution - address warnings before production deployment.")
            recommendations.append("Consider running additional validation tests.")
        elif narrative.severity == "OK":
            recommendations.append("Proceed to next stage - system is ready for production consideration.")
            recommendations.append("Monitor performance during initial deployment.")
        
        # Based on stage
        if narrative.stage == ResearchStage.DATA_READINESS:
            recommendations.append("Ensure data quality meets business requirements before research execution.")
        elif narrative.stage == ResearchStage.RUN_RESEARCH:
            recommendations.append("Monitor research execution for timely completion.")
        elif narrative.stage == ResearchStage.OUTCOME_TRIAGE:
            recommendations.append("Review research outcomes for business viability.")
        elif narrative.stage == ResearchStage.DECISION:
            recommendations.append("Make portfolio allocation decisions based on research outcomes.")
        
        return "\n".join(f"• {rec}" for rec in recommendations)
    
    def _generate_risk_assessment(self, narrative: ResearchNarrativeV1, gate_summary: GateSummaryV1) -> str:
        """Generate risk assessment."""
        risks = []
        
        # Risk based on gate status
        if gate_summary.overall_status == GateStatus.REJECT:
            risks.append("HIGH RISK: Critical gate failures detected.")
            risks.append("Potential data integrity or system reliability issues.")
        elif gate_summary.overall_status == GateStatus.WARN:
            risks.append("MEDIUM RISK: Non-critical warnings present.")
            risks.append("May impact performance or require manual intervention.")
        elif gate_summary.overall_status == GateStatus.PASS:
            risks.append("LOW RISK: All gates passed.")
            risks.append("Standard operational risks apply.")
        
        # Risk based on narrative severity
        if narrative.severity == "BLOCKED":
            risks.append("Blocking issues prevent progress - high business impact.")
        elif narrative.severity == "WARN":
            risks.append("Warnings may require attention - moderate business impact.")
        
        # Risk based on stage
        if narrative.stage in [ResearchStage.DATA_READINESS, ResearchStage.RUN_RESEARCH]:
            risks.append("Early stage - limited business risk until research completes.")
        elif narrative.stage in [ResearchStage.OUTCOME_TRIAGE, ResearchStage.DECISION]:
            risks.append("Later stage - higher business impact from decisions.")
        
        return "\n".join(f"• {risk}" for risk in risks)
    
    def _on_gate_explain_clicked(self):
        """Handle Gate Explanation button click."""
        if not self.current_job_id or not self.current_job_summary:
            return
        
        logger.info(f"Gate explanation requested for job: {self.current_job_id}")
        
        # Emit action for gate explanation
        context = {
            "job_id": self.current_job_id,
            "gate_summary": self.current_job_summary.gate_summary.model_dump() if self.current_job_summary.gate_summary else None,
            "source": "ExplainHubTabs",
            "tab": "Dev"
        }
        
        self.action_requested.emit(f"gate_explain://{self.current_job_id}", context)
    
    def _on_evidence_viewer_clicked(self):
        """Handle Evidence Viewer button click."""
        if not self.current_job_id:
            return
        
        logger.info(f"Evidence viewer requested for job: {self.current_job_id}")
        
        # Emit action for evidence viewer
        context = {
            "job_id": self.current_job_id,
            "source": "ExplainHubTabs",
            "tab": "Dev"
        }
        
        self.action_requested.emit(f"evidence://{self.current_job_id}", context)
    
    def _on_artifact_nav_clicked(self):
        """Handle Artifact Navigator button click."""
        if not self.current_job_id:
            return
        
        logger.info(f"Artifact navigator requested for job: {self.current_job_id}")
        
        # Emit action for artifact navigator
        context = {
            "job_id": self.current_job_id,
            "source": "ExplainHubTabs",
            "tab": "Dev"
        }
        
        self.action_requested.emit(f"artifact://{self.current_job_id}", context)
    
    def _on_export_clicked(self):
        """Handle Export button click - show export options."""
        if not self.current_narrative or not self.current_job_summary:
            return
        
        logger.info(f"Export requested for job: {self.current_job_id}")
        
        # Create export menu
        from PySide6.QtWidgets import QMenu, QMessageBox
        
        menu = QMenu(self)
        
        # JSON export
        json_action = menu.addAction("📊 Export as JSON")
        json_action.triggered.connect(lambda: self._export_narrative(ExportFormat.JSON))
        
        # Markdown export
        md_action = menu.addAction("📝 Export as Markdown")
        md_action.triggered.connect(lambda: self._export_narrative(ExportFormat.MARKDOWN))
        
        # CSV export
        csv_action = menu.addAction("📈 Export as CSV")
        csv_action.triggered.connect(lambda: self._export_narrative(ExportFormat.CSV))
        
        menu.addSeparator()
        
        # Export with gate summary
        json_full_action = menu.addAction("📊 Export JSON (with gate summary)")
        json_full_action.triggered.connect(lambda: self._export_narrative(
            ExportFormat.JSON, ExportContent.FULL_EXPLANATION
        ))
        
        # Show menu at button position
        button_pos = self.export_btn.mapToGlobal(self.export_btn.rect().bottomLeft())
        menu.exec(button_pos)
    
    def _export_narrative(
        self,
        format: ExportFormat,
        content: ExportContent = ExportContent.NARRATIVE_ONLY
    ):
        """Export current narrative in specified format."""
        if not self.current_narrative or not self.current_job_summary:
            return
        
        try:
            # Get export service
            export_service = get_explain_export_service()
            
            # Export narrative
            result = export_service.export_narrative(
                narrative=self.current_narrative,
                persona=self.current_persona,
                format=format,
                content=content,
                job_summary=self.current_job_summary,
                include_metadata=True
            )
            
            # Show success message
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.information(
                self,
                "Export Successful",
                f"Narrative exported successfully!\n\n"
                f"Format: {format.value.upper()}\n"
                f"File: {result['filepath']}\n"
                f"Size: {result['size_bytes']} bytes"
            )
            
            logger.info(f"Narrative exported: {result['filepath']}")
            
        except Exception as e:
            logger.error(f"Failed to export narrative: {e}")
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(
                self,
                "Export Failed",
                f"Failed to export narrative: {str(e)}"
            )
    
    def _route_action(self, action_type: str, action_data: Dict[str, Any]):
        """Route action through ActionRouterService."""
        if not self.current_job_id:
            logger.warning(f"Cannot route action {action_type}: no job selected")
            return
        
        # Build context for action
        context = {
            "job_id": self.current_job_id,
            "action_data": action_data,
            "source": "ExplainHubTabs",
            "tab": self.tab_widget.tabText(self.tab_widget.currentIndex())
        }
        
        # Add narrative context if available
        if self.current_narrative:
            context["narrative"] = {
                "stage": self.current_narrative.stage.value,
                "severity": self.current_narrative.severity,
                "next_step_action": self.current_narrative.next_step_action.value if self.current_narrative.next_step_action else None
            }
        
        # Add gate summary context if available
        if self.current_job_summary and self.current_job_summary.gate_summary:
            context["gate_summary"] = {
                "overall_status": self.current_job_summary.gate_summary.overall_status.value,
                "total_gates": self.current_job_summary.gate_summary.total_gates
            }
        
        # Map action type to ActionRouterService target
        target = self._map_action_to_target(action_type, action_data)
        
        if target:
            logger.info(f"Routing action: {target} with context: {context}")
            # Emit signal for parent to handle
            self.action_requested.emit(target, context)
        else:
            logger.warning(f"No target mapping for action type: {action_type}")
    
    def _map_action_to_target(self, action_type: str, action_data: Dict[str, Any]) -> Optional[str]:
        """Map action type to ActionRouterService target string."""
        # Common action mappings
        mappings = {
            "open_gate_dashboard": "gate_dashboard",
            "open_data_readiness": "data_readiness",
            "open_report": "report_view",
            "open_audit": "audit_view",
            "open_admission": "admission_view",
            "run_research": "research_run",
            "build_portfolio": "portfolio_build",
            "retry_last": "retry_last_job",
            "view_evidence": f"evidence://{self.current_job_id}",
            "explain_gate": f"gate_explain://{self.current_job_id}",
            "open_artifact": f"artifact://{self.current_job_id}",
        }
        
        # Check for direct mapping
        if action_type in mappings:
            return mappings[action_type]
        
        # Check for URL patterns
        if action_type.startswith("http://") or action_type.startswith("https://"):
            return action_type
        
        # Check for internal navigation patterns
        if action_type.startswith("internal://"):
            return action_type
        
        # Default: use action type as target
        return action_type
    
    def _show_error(self, error_message: str):
        """Show error state in all tabs."""
        self.status_label.setText(f"Error: {error_message[:50]}...")
        self.status_label.setStyleSheet("color: #F44336; font-size: 10px; padding: 4px;")
        
        # Clear all tabs
        self.headline_text.setText("Error loading narrative")
        self.why_text.setPlainText(f"Error: {error_message}")
        self.next_step_text.setText("Check system logs and try again")
        
        self.gate_summary_text.setPlainText(f"Error: {error_message}")
        self.job_data_text.setPlainText("Error loading job data")
        
        self.biz_view_text.setPlainText(f"Error: {error_message}")
        self.recommendations_text.setText("Unable to generate recommendations due to error")
        self.risk_text.setText("Risk assessment unavailable")
    
    def _update_action_buttons(self, enabled: bool):
        """Update action button states."""
        if hasattr(self, 'gate_explain_btn'):
            self.gate_explain_btn.setEnabled(enabled)
        if hasattr(self, 'evidence_viewer_btn'):
            self.evidence_viewer_btn.setEnabled(enabled)
        if hasattr(self, 'artifact_nav_btn'):
            self.artifact_nav_btn.setEnabled(enabled)
        if hasattr(self, 'export_btn'):
            self.export_btn.setEnabled(enabled)
    
    def clear(self):
        """Clear all tabs and reset to initial state."""
        self.current_job_id = None
        self.current_job_summary = None
        self.current_narrative = None
        # Reset persona to default
        default_persona = get_default_persona()
        default_index = self.persona_combo.findData(default_persona.value)
        if default_index >= 0:
            self.persona_combo.setCurrentIndex(default_index)
        self.current_persona = default_persona
        
        self.status_label.setText("No job selected")
        self.status_label.setStyleSheet("color: #9A9A9A; font-size: 10px; padding: 4px;")
        
        # Disable action buttons
        self._update_action_buttons(False)
        
        # Reset Narrative tab
        self.severity_value.setText("—")
        self.severity_value.setStyleSheet("color: #9E9E9E; font-size: 11px; font-weight: bold;")
        self.stage_value.setText("—")
        self.headline_text.setText("Select a job to view narrative")
        self.why_text.clear()
        self.why_text.setPlaceholderText("Explanation will appear here when a job is selected")
        self.next_step_text.setText("—")
        self.actions_group.setVisible(False)
        
        # Reset Dev tab
        self.gate_summary_text.clear()
        self.gate_summary_text.setPlaceholderText("Gate summary will appear here when a job is selected")
        self.job_data_text.clear()
        self.job_data_text.setPlaceholderText("Job data will appear here when a job is selected")
        self.explain_group.setVisible(False)
        
        # Reset Biz tab
        self.biz_view_text.clear()
        self.biz_view_text.setPlaceholderText("Business view will appear here when a job is selected")
        self.recommendations_text.setText("—")
        self.risk_text.setText("—")