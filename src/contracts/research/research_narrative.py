"""
Research Narrative Layer v2.1 - SSOT Contracts

Defines the single authoritative human-readable narrative for Research OS.
Converts ResearchFlowState into a "human explanation pack" that:
- Provides clear headlines (1 sentence)
- Explains "why" in simple terms
- Recommends single next step
- Supports Developer View and Business View

NON-NEGOTIABLE CONSTITUTION:
- Kernel remains SSOT for truth. Narrative must not change state.
- Narrative must be pure function of Kernel output (+ optional evidence lookups)
- Every narrative MUST output: headline, why, next_step
- Must support Developer View and Business View (reuse v1.4 dictionary style)
- Must be frozen models (ConfigDict(frozen=True))
- Must terminate deterministically (make check), no servers
"""

from enum import Enum, StrEnum
from typing import List, Dict, Any, Literal, Optional
from pydantic import BaseModel, Field, ConfigDict

from contracts.research.research_flow_kernel import ResearchStage, ResearchFlowState
from contracts.portfolio.gate_summary_schemas import GateReasonCode


class NarrativeActionId(StrEnum):
    """
    Stable action IDs for narrative layer (SSOT).
    
    These action IDs are stable contracts that UI can map to buttons.
    """
    OPEN_DATA_READINESS = "open_data_readiness"
    RUN_RESEARCH = "run_research"
    OPEN_GATE_DASHBOARD = "open_gate_dashboard"
    OPEN_REPORT = "open_report"
    OPEN_AUDIT = "open_audit"
    BUILD_PORTFOLIO = "build_portfolio"
    OPEN_ADMISSION = "open_admission"
    RETRY_LAST = "retry_last"


class ResearchNarrativeV1(BaseModel):
    """
    Frozen Research Narrative Model (SSOT).
    
    Represents the human-readable explanation pack for Research OS.
    Converts ResearchFlowState into actionable, understandable narrative.
    
    ConfigDict(frozen=True) ensures no mutation after creation.
    """
    model_config = ConfigDict(frozen=True, extra="forbid")
    
    # Version identifier (must be "v2.1.0")
    version: str = Field(
        default="v2.1.0",
        description="Narrative layer version (must be 'v2.1.0')"
    )
    
    # Core state reference
    stage: ResearchStage = Field(
        ...,
        description="Research stage this narrative describes"
    )
    
    # Severity classification
    severity: Literal["OK", "BLOCKED", "WARN"] = Field(
        ...,
        description="Severity level: OK (proceed), BLOCKED (cannot proceed), WARN (proceed with caution)"
    )
    
    # Headline (1 sentence, <= 120 chars)
    headline: str = Field(
        ...,
        description="One-sentence summary of current state (<= 120 characters)"
    )
    
    # Why explanation (short, <= 400 chars)
    why: str = Field(
        ...,
        description="Short explanation of why we're in this state (<= 400 characters)"
    )
    
    # Primary reason code (never null)
    primary_reason_code: GateReasonCode = Field(
        ...,
        description="Primary GateReasonCode for current state (never null)"
    )
    
    # Developer view (structured details, <= 800 chars)
    developer_view: str = Field(
        ...,
        description="Developer-focused explanation with technical details (<= 800 characters)"
    )
    
    # Business view (human friendly, <= 800 chars)
    business_view: str = Field(
        ...,
        description="Business-friendly explanation of impact and next steps (<= 800 characters)"
    )
    
    # Next step action (stable action ID)
    next_step_action: NarrativeActionId = Field(
        ...,
        description="Stable action ID for recommended next step (not UI label)"
    )
    
    # Next step label (human label)
    next_step_label: str = Field(
        ...,
        description="Human-readable label for the next step action"
    )
    
    # Drilldown actions (max 5 items)
    drilldown_actions: List[Dict[str, str]] = Field(
        default_factory=list,
        description="Additional actions for drilldown (max 5 items, each dict has 'action' and 'label')"
    )
    
    # Evidence references (max 10)
    evidence_refs: List[str] = Field(
        default_factory=list,
        description="Paths/IDs to evidence artifacts supporting this narrative (max 10)"
    )
    
    def validate_narrative(self) -> None:
        """
        Validate narrative constraints.
        
        Raises:
            ValueError: If narrative violates constraints
        """
        # Headline length constraint
        if len(self.headline) > 120:
            raise ValueError(f"Headline exceeds 120 characters: {len(self.headline)}")
        
        # Why length constraint
        if len(self.why) > 400:
            raise ValueError(f"Why explanation exceeds 400 characters: {len(self.why)}")
        
        # Developer view length constraint
        if len(self.developer_view) > 800:
            raise ValueError(f"Developer view exceeds 800 characters: {len(self.developer_view)}")
        
        # Business view length constraint
        if len(self.business_view) > 800:
            raise ValueError(f"Business view exceeds 800 characters: {len(self.business_view)}")
        
        # Severity constraints
        if self.severity != "OK":
            if not self.why:
                raise ValueError(f"Non-OK severity ({self.severity}) must have non-empty 'why'")
        
        # Drilldown actions constraint
        if len(self.drilldown_actions) > 5:
            raise ValueError(f"Drilldown actions exceed maximum of 5: {len(self.drilldown_actions)}")
        
        # Evidence refs constraint
        if len(self.evidence_refs) > 10:
            raise ValueError(f"Evidence references exceed maximum of 10: {len(self.evidence_refs)}")
        
        # Validate drilldown action structure
        for action in self.drilldown_actions:
            if "action" not in action or "label" not in action:
                raise ValueError("Drilldown action must have 'action' and 'label' keys")
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert narrative to dictionary for serialization.
        
        Returns:
            Dictionary representation of narrative
        """
        return {
            "version": self.version,
            "stage": self.stage.value,
            "severity": self.severity,
            "headline": self.headline,
            "why": self.why,
            "primary_reason_code": self.primary_reason_code.value,
            "developer_view": self.developer_view,
            "business_view": self.business_view,
            "next_step_action": self.next_step_action.value,
            "next_step_label": self.next_step_label,
            "drilldown_actions": self.drilldown_actions,
            "evidence_refs": self.evidence_refs,
        }
    
    def get_ui_summary(self) -> Dict[str, str]:
        """
        Get UI summary for display.
        
        Returns:
            Dictionary with UI-friendly summary
        """
        return {
            "headline": self.headline,
            "why": self.why,
            "next_step": self.next_step_label,
            "severity": self.severity,
        }


# Helper function for creating narratives
def create_narrative(
    stage: ResearchStage,
    severity: Literal["OK", "BLOCKED", "WARN"],
    headline: str,
    why: str,
    primary_reason_code: GateReasonCode,
    developer_view: str,
    business_view: str,
    next_step_action: NarrativeActionId,
    next_step_label: str,
    drilldown_actions: Optional[List[Dict[str, str]]] = None,
    evidence_refs: Optional[List[str]] = None,
) -> ResearchNarrativeV1:
    """
    Create a ResearchNarrativeV1 instance with validation.
    
    Args:
        stage: Research stage
        severity: Severity level
        headline: One-sentence summary (<= 120 chars)
        why: Short explanation (<= 400 chars)
        primary_reason_code: Primary GateReasonCode
        developer_view: Developer-focused explanation (<= 800 chars)
        business_view: Business-friendly explanation (<= 800 chars)
        next_step_action: Stable action ID
        next_step_label: Human-readable label
        drilldown_actions: Optional drilldown actions (max 5)
        evidence_refs: Optional evidence references (max 10)
        
    Returns:
        Validated ResearchNarrativeV1 instance
    """
    narrative = ResearchNarrativeV1(
        stage=stage,
        severity=severity,
        headline=headline,
        why=why,
        primary_reason_code=primary_reason_code,
        developer_view=developer_view,
        business_view=business_view,
        next_step_action=next_step_action,
        next_step_label=next_step_label,
        drilldown_actions=drilldown_actions or [],
        evidence_refs=evidence_refs or [],
    )
    
    # Validate narrative constraints
    narrative.validate_narrative()
    
    return narrative