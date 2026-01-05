"""
Portfolio admission decision schemas (stable contracts).

These schemas define the structure of the admission decision and its evidence bundle.
All field names and ordering are stable; changes must be backward compatible.
"""
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field, ConfigDict
from enum import Enum


class AdmissionVerdict(str, Enum):
    """Overall admission verdict."""
    ADMITTED = "ADMITTED"
    REJECTED = "REJECTED"


class AdmissionDecision(BaseModel):
    """Final decision of the Portfolio Admission Gate."""
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        json_encoders={Enum: lambda e: e.value},
    )

    # Core decision
    verdict: AdmissionVerdict = Field(
        ...,
        description="Overall admission verdict"
    )
    admitted_run_ids: List[str] = Field(
        default_factory=list,
        description="Sorted list of run IDs that passed all gates"
    )
    rejected_run_ids: List[str] = Field(
        default_factory=list,
        description="Sorted list of run IDs that were rejected"
    )
    reasons: Dict[str, str] = Field(
        default_factory=dict,
        description="Mapping from run_id to human‑readable rejection reason"
    )
    portfolio_id: str = Field(
        ...,
        description="Identifier of the portfolio being evaluated"
    )
    evaluated_at_utc: str = Field(
        ...,
        description="ISO‑8601 UTC timestamp of evaluation"
    )

    # Gate‑level details (optional, for debugging)
    correlation_violations: Optional[Dict[str, List[str]]] = Field(
        default=None,
        description="Mapping from run_id to list of run_ids with which correlation exceeded threshold"
    )
    risk_budget_steps: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Step‑by‑step record of risk‑budget rejection iterations"
    )
    missing_artifacts: Optional[List[str]] = Field(
        default=None,
        description="List of run_ids that were rejected due to missing artifacts"
    )

    @property
    def admitted(self) -> bool:
        """Convenience property matching the spec's `admitted` bool."""
        return self.verdict == AdmissionVerdict.ADMITTED


# -----------------------------------------------------------------------------
# Evidence file names (constants to avoid drift)
# -----------------------------------------------------------------------------

ADMISSION_DECISION_FILE = "admission_decision.json"
GOVERNANCE_PARAMS_SNAPSHOT_FILE = "governance_params_snapshot.json"
CORRELATION_MATRIX_FILE = "correlation_matrix.json"
CORRELATION_VIOLATIONS_FILE = "correlation_violations.json"
RISK_BUDGET_SNAPSHOT_FILE = "risk_budget_snapshot.json"
ADMITTED_RUN_IDS_FILE = "admitted_run_ids.json"
REJECTED_RUN_IDS_FILE = "rejected_run_ids.json"

# Optional auxiliary files
MISSING_ARTIFACTS_FILE = "missing_artifacts.json"
GATE_SUMMARY_FILE = "gate_summary.json"

EVIDENCE_FILES = [
    ADMISSION_DECISION_FILE,
    GOVERNANCE_PARAMS_SNAPSHOT_FILE,
    CORRELATION_MATRIX_FILE,
    CORRELATION_VIOLATIONS_FILE,
    RISK_BUDGET_SNAPSHOT_FILE,
    ADMITTED_RUN_IDS_FILE,
    REJECTED_RUN_IDS_FILE,
]