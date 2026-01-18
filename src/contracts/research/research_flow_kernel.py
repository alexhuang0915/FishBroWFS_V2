"""
Research OS Kernel v2.0 - SSOT Contracts

Defines the single authoritative research lifecycle kernel for FishBroWFS_V2.
This is the SSOT (Single Source of Truth) for research flow state and stages.

NON-NEGOTIABLE CONSTITUTION:
- There must be exactly ONE Master Research Flow
- All research must enter and exit through this flow
- No existing UI page may act as a primary entry point
- All decisions must be explainable via GateReasonCode + Explain Dictionary
- No silent state transitions
- No daemon / long-running processes
- All verification must terminate (make check)
"""

from enum import Enum
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict

from contracts.portfolio.gate_summary_schemas import GateReasonCode


class ResearchStage(str, Enum):
    """
    STRICT Research Stage Enum (SSOT).
    
    Exactly FOUR stages, no additional stages allowed.
    No skipping allowed.
    No custom stages allowed.
    """
    DATA_READINESS = "data_readiness"
    RUN_RESEARCH = "run_research"
    OUTCOME_TRIAGE = "outcome_triage"
    DECISION = "decision"


class ResearchFlowState(BaseModel):
    """
    Frozen Research Flow State Model (SSOT).
    
    Represents the current state of the research lifecycle.
    ConfigDict(frozen=True) ensures no mutation after creation.
    Every blocked state MUST include explain text.
    """
    model_config = ConfigDict(frozen=True)
    
    # Core state
    current_stage: ResearchStage = Field(
        ...,
        description="Current research stage (STRICT: exactly one of four stages)"
    )
    
    # Blocking information
    is_blocked: bool = Field(
        default=False,
        description="Whether research flow is blocked from progressing"
    )
    
    blocking_reason: Optional[GateReasonCode] = Field(
        default=None,
        description="GateReasonCode for why flow is blocked (required if is_blocked=True)"
    )
    
    blocking_explain: Optional[str] = Field(
        default=None,
        description="Human-readable explanation from Explain Dictionary (required if is_blocked=True)"
    )
    
    # Allowed actions
    allowed_actions: List[str] = Field(
        default_factory=list,
        description="List of action strings that are allowed in current state"
    )
    
    recommended_next_action: Optional[str] = Field(
        default=None,
        description="Recommended next action for user (if any)"
    )
    
    # Evidence references
    evidence_refs: List[str] = Field(
        default_factory=list,
        description="List of evidence artifact references supporting current state"
    )
    
    # Metadata
    evaluated_at: datetime = Field(
        default_factory=datetime.now,
        description="Timestamp when state was evaluated"
    )
    
    evaluation_duration_ms: Optional[int] = Field(
        default=None,
        description="Duration of evaluation in milliseconds"
    )
    
    # System context
    system_context: Dict[str, Any] = Field(
        default_factory=dict,
        description="System context used for evaluation (gates, jobs, artifacts, etc.)"
    )
    
    def validate_blocking_state(self) -> None:
        """
        Validate that blocked states have required fields.
        
        Raises:
            ValueError: If blocked state missing required fields
        """
        if self.is_blocked:
            if not self.blocking_reason:
                raise ValueError("Blocked state must have blocking_reason")
            if not self.blocking_explain:
                raise ValueError("Blocked state must have blocking_explain")
    
    def get_stage_description(self) -> str:
        """
        Get human-readable description of current stage.
        """
        descriptions = {
            ResearchStage.DATA_READINESS: "Data Readiness - Preparing datasets and validating system gates",
            ResearchStage.RUN_RESEARCH: "Run Research - Executing research jobs and generating artifacts",
            ResearchStage.OUTCOME_TRIAGE: "Outcome Triage - Analyzing results and evaluating gate summaries",
            ResearchStage.DECISION: "Decision - Making portfolio decisions based on research outcomes",
        }
        return descriptions.get(self.current_stage, "Unknown stage")
    
    def get_blocking_summary(self) -> Optional[str]:
        """
        Get summary of blocking reason if blocked.
        
        Returns:
            Optional[str]: Summary string or None if not blocked
        """
        if not self.is_blocked:
            return None
        
        return f"Blocked: {self.blocking_reason.value} - {self.blocking_explain}"
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert state to dictionary for serialization.
        """
        return {
            "current_stage": self.current_stage.value,
            "is_blocked": self.is_blocked,
            "blocking_reason": self.blocking_reason.value if self.blocking_reason else None,
            "blocking_explain": self.blocking_explain,
            "allowed_actions": self.allowed_actions,
            "recommended_next_action": self.recommended_next_action,
            "evidence_refs": self.evidence_refs,
            "evaluated_at": self.evaluated_at.isoformat(),
            "evaluation_duration_ms": self.evaluation_duration_ms,
            "stage_description": self.get_stage_description(),
            "blocking_summary": self.get_blocking_summary(),
        }


class StageTransition(BaseModel):
    """
    Research stage transition definition.
    
    Defines allowed transitions between research stages.
    """
    model_config = ConfigDict(frozen=True)
    
    from_stage: ResearchStage = Field(
        ...,
        description="Source stage"
    )
    
    to_stage: ResearchStage = Field(
        ...,
        description="Target stage"
    )
    
    required_conditions: List[str] = Field(
        default_factory=list,
        description="List of conditions required for transition"
    )
    
    blocking_reasons: List[GateReasonCode] = Field(
        default_factory=list,
        description="Possible blocking reasons for this transition"
    )


# STRICT stage transition matrix
# Defines exactly which transitions are allowed (no skipping)
STAGE_TRANSITIONS = [
    StageTransition(
        from_stage=ResearchStage.DATA_READINESS,
        to_stage=ResearchStage.RUN_RESEARCH,
        required_conditions=[
            "All system gates pass",
            "Required datasets available",
            "Registry validation complete",
            "Policy gates pass",
        ],
        blocking_reasons=[
            GateReasonCode.GATE_ITEM_PARSE_ERROR,
            GateReasonCode.GATE_SUMMARY_FETCH_ERROR,
            # Add more specific data readiness codes as needed
        ],
    ),
    StageTransition(
        from_stage=ResearchStage.RUN_RESEARCH,
        to_stage=ResearchStage.OUTCOME_TRIAGE,
        required_conditions=[
            "Research job completed",
            "Artifacts present and valid",
            "Gate summary available",
        ],
        blocking_reasons=[
            GateReasonCode.GATE_SUMMARY_PARSE_ERROR,
            GateReasonCode.EVIDENCE_SNAPSHOT_MISSING,
            GateReasonCode.EVIDENCE_SNAPSHOT_HASH_MISMATCH,
        ],
    ),
    StageTransition(
        from_stage=ResearchStage.OUTCOME_TRIAGE,
        to_stage=ResearchStage.DECISION,
        required_conditions=[
            "At least one candidate passed triage",
            "Portfolio build possible",
            "Admission gates pass",
        ],
        blocking_reasons=[
            GateReasonCode.VERDICT_STAMP_MISSING,
            GateReasonCode.GATE_DEPENDENCY_CYCLE,
        ],
    ),
]


def get_allowed_transitions(from_stage: ResearchStage) -> List[ResearchStage]:
    """
    Get allowed transitions from a given stage.
    
    Args:
        from_stage: Source research stage
        
    Returns:
        List of allowed target stages
    """
    return [
        transition.to_stage
        for transition in STAGE_TRANSITIONS
        if transition.from_stage == from_stage
    ]


def validate_transition(from_stage: ResearchStage, to_stage: ResearchStage) -> bool:
    """
    Validate if transition between stages is allowed.
    
    Args:
        from_stage: Source research stage
        to_stage: Target research stage
        
    Returns:
        bool: True if transition is allowed, False otherwise
    """
    return any(
        transition.from_stage == from_stage and transition.to_stage == to_stage
        for transition in STAGE_TRANSITIONS
    )