"""
Job-level admission decision schemas (DP8).

Defines the structure of job admission decisions based on gate summaries.
These are deterministic, read-only evaluations of whether a job should be admitted
to downstream processing based on its gate status.
"""

from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field, ConfigDict
from enum import Enum
from datetime import datetime, timezone


class JobAdmissionVerdict(str, Enum):
    """Overall job admission verdict."""
    ADMITTED = "ADMITTED"
    REJECTED = "REJECTED"
    HOLD = "HOLD"  # Requires manual review


class JobAdmissionDecision(BaseModel):
    """Final admission decision for a single job based on gate summary evaluation."""
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        json_encoders={Enum: lambda e: e.value},
    )

    # Core decision
    verdict: JobAdmissionVerdict = Field(
        ...,
        description="Overall job admission verdict"
    )
    job_id: str = Field(
        ...,
        description="Job identifier being evaluated"
    )
    evaluated_at_utc: str = Field(
        ...,
        description="ISO‑8601 UTC timestamp of evaluation"
    )
    
    # Gate summary context
    gate_summary_status: str = Field(
        ...,
        description="Overall gate summary status (PASS/WARN/REJECT/UNKNOWN)"
    )
    total_gates: int = Field(
        ...,
        description="Total number of gates evaluated"
    )
    gate_counts: Dict[str, int] = Field(
        ...,
        description="Count of gates by status"
    )
    
    # Decision rationale
    decision_reason: str = Field(
        ...,
        description="Human-readable explanation of the decision"
    )
    policy_rules_applied: List[str] = Field(
        default_factory=list,
        description="List of policy rule identifiers that were applied"
    )
    
    # Gate-level details (for debugging/explanation)
    failing_gates: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Details of gates that contributed to rejection/hold"
    )
    warning_gates: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Details of gates with WARN status"
    )
    
    # Evidence references
    gate_summary_artifact: str = Field(
        default="gate_summary.json",
        description="Relative path to gate summary artifact"
    )
    ranking_explain_artifact: Optional[str] = Field(
        default=None,
        description="Relative path to ranking explain report (if applicable)"
    )
    
    # Navigation actions (for UI)
    navigation_actions: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="List of navigation actions available for this decision"
    )


# -----------------------------------------------------------------------------
# Policy rule definitions
# -----------------------------------------------------------------------------

class AdmissionPolicyRule(str, Enum):
    """Predefined admission policy rules."""
    
    # Basic gate status rules
    PASS_ALWAYS_ADMIT = "PASS_ALWAYS_ADMIT"
    REJECT_ALWAYS_REJECT = "REJECT_ALWAYS_REJECT"
    WARN_REQUIRES_REVIEW = "WARN_REQUIRES_REVIEW"
    UNKNOWN_REQUIRES_REVIEW = "UNKNOWN_REQUIRES_REVIEW"
    
    # Gate count thresholds
    MAX_WARN_GATES = "MAX_WARN_GATES"
    MAX_FAIL_GATES = "MAX_FAIL_GATES"
    
    # Specific gate rules
    RANKING_EXPLAIN_WARN = "RANKING_EXPLAIN_WARN"
    DATA_ALIGNMENT_FAIL = "DATA_ALIGNMENT_FAIL"
    PORTFOLIO_ADMISSION_FAIL = "PORTFOLIO_ADMISSION_FAIL"
    
    # Composite rules
    MIXED_STATUS_EVALUATION = "MIXED_STATUS_EVALUATION"


# -----------------------------------------------------------------------------
# Policy configuration
# -----------------------------------------------------------------------------

class AdmissionPolicyConfig(BaseModel):
    """Configuration for job admission policy engine."""
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
    )
    
    # Default verdict for each gate summary status
    default_verdict_for_pass: JobAdmissionVerdict = Field(
        default=JobAdmissionVerdict.ADMITTED,
        description="Default verdict when overall status is PASS"
    )
    default_verdict_for_reject: JobAdmissionVerdict = Field(
        default=JobAdmissionVerdict.REJECTED,
        description="Default verdict when overall status is REJECT"
    )
    default_verdict_for_warn: JobAdmissionVerdict = Field(
        default=JobAdmissionVerdict.HOLD,
        description="Default verdict when overall status is WARN"
    )
    default_verdict_for_unknown: JobAdmissionVerdict = Field(
        default=JobAdmissionVerdict.HOLD,
        description="Default verdict when overall status is UNKNOWN"
    )
    
    # Thresholds
    max_warn_gates: int = Field(
        default=2,
        description="Maximum number of WARN gates allowed for ADMITTED verdict"
    )
    max_fail_gates: int = Field(
        default=0,
        description="Maximum number of FAIL gates allowed for ADMITTED verdict"
    )
    
    # Critical gates that cause immediate rejection
    critical_gates: List[str] = Field(
        default_factory=lambda: ["data_alignment", "portfolio_admission"],
        description="Gate IDs that cause immediate rejection if they fail"
    )
    
    # Warning gates that require review but don't cause rejection
    warning_gates_require_review: List[str] = Field(
        default_factory=lambda: ["ranking_explain"],
        description="Gate IDs that cause HOLD verdict when in WARN status"
    )
    
    # Enable/disable specific rules
    enabled_rules: List[AdmissionPolicyRule] = Field(
        default_factory=lambda: list(AdmissionPolicyRule),
        description="List of enabled policy rules"
    )


# -----------------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------------

JOB_ADMISSION_DECISION_FILE = "job_admission_decision.json"
"""Filename for job admission decision artifact."""

DEFAULT_POLICY_CONFIG = AdmissionPolicyConfig()
"""Default policy configuration."""


def create_default_policy() -> AdmissionPolicyConfig:
    """Create default admission policy configuration."""
    return DEFAULT_POLICY_CONFIG