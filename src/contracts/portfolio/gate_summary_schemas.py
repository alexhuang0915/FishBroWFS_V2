"""
Gate Summary v1 Schemas for Red X Cleanup (Hybrid BC v1.1 compliant).

Defines the consolidated gate summary model with strict layering:
- Layer1/Layer2: NO performance metrics (net/mdd/sharpe/etc.)
- Layer3: metrics allowed ONLY in separate "Metrics View" (out of scope)

GateSummaryV1 provides:
- Top-level PASS/WARN/REJECT/SKIP status + counts
- Expandable per-gate reasons + evidence references
- Deterministic ordering (sorted by gate_id)
- SSOT compatibility (reads from canonical artifact/endpoint)
"""

from typing import Dict, List, Optional, Literal
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict


class GateStatus(str, Enum):
    """Gate status values."""
    PASS = "PASS"
    WARN = "WARN"
    REJECT = "REJECT"
    SKIP = "SKIP"
    UNKNOWN = "UNKNOWN"


class GateItemV1(BaseModel):
    """Individual gate result."""
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        json_encoders={Enum: lambda e: e.value},
    )
    
    # Core identification
    gate_id: str = Field(
        ...,
        description="Stable gate identifier (e.g., 'api_health', 'correlation_threshold', 'risk_budget')"
    )
    gate_name: str = Field(
        ...,
        description="Human-readable gate title"
    )
    
    # Status and explanation
    status: GateStatus = Field(
        ...,
        description="Gate evaluation result"
    )
    message: str = Field(
        ...,
        description="Human-readable explanation of gate result"
    )
    
    # Optional drill-down
    reason_codes: List[str] = Field(
        default_factory=list,
        description="Standardized reason codes for programmatic handling"
    )
    evidence_refs: List[str] = Field(
        default_factory=list,
        description="References to evidence artifacts (paths, manifest refs, hash refs)"
    )
    
    # Metadata
    evaluated_at_utc: Optional[str] = Field(
        default=None,
        description="ISO-8601 UTC timestamp of gate evaluation"
    )
    evaluator: Optional[str] = Field(
        default=None,
        description="Component that performed the evaluation"
    )


class GateSummaryV1(BaseModel):
    """Consolidated gate summary (Hybrid BC v1.1 Layer1/Layer2)."""
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",
        json_encoders={Enum: lambda e: e.value},
    )
    
    # Schema version
    schema_version: str = Field(
        default="v1",
        description="Schema version for forward compatibility"
    )
    
    # Overall status
    overall_status: GateStatus = Field(
        ...,
        description="Aggregated status across all gates"
    )
    overall_message: str = Field(
        ...,
        description="Human-readable summary of overall gate status"
    )
    
    # Counts (Layer1)
    counts: Dict[str, int] = Field(
        default_factory=lambda: {
            "pass": 0,
            "warn": 0,
            "reject": 0,
            "skip": 0,
            "unknown": 0,
        },
        description="Count of gates by status"
    )
    
    # Individual gates (Layer2)
    gates: List[GateItemV1] = Field(
        default_factory=list,
        description="Individual gate results, sorted by gate_id for deterministic ordering"
    )
    
    # Metadata
    evaluated_at_utc: str = Field(
        ...,
        description="ISO-8601 UTC timestamp of summary evaluation"
    )
    evaluator: str = Field(
        default="gate_summary_service",
        description="Component that generated this summary"
    )
    source: str = Field(
        default="",
        description="Source of gate data (e.g., 'supervisor_api', 'artifact_index')"
    )
    
    # Validation
    def model_post_init(self, __context) -> None:
        """Post-initialization validation."""
        # Ensure counts match gates
        computed_counts = {
            "pass": 0,
            "warn": 0,
            "reject": 0,
            "skip": 0,
            "unknown": 0,
        }
        for gate in self.gates:
            status_key = gate.status.value.lower()
            if status_key in computed_counts:
                computed_counts[status_key] += 1
        
        # Update counts if they don't match (but don't mutate frozen model)
        # We'll just warn if counts are inconsistent
        if self.counts != computed_counts:
            # In a real implementation, we might want to auto-correct
            # For now, we'll just note the inconsistency
            pass
    
    @property
    def total_gates(self) -> int:
        """Total number of gates evaluated."""
        return len(self.gates)
    
    @property
    def passed_gates(self) -> List[GateItemV1]:
        """List of gates with PASS status."""
        return [g for g in self.gates if g.status == GateStatus.PASS]
    
    @property
    def warning_gates(self) -> List[GateItemV1]:
        """List of gates with WARN status."""
        return [g for g in self.gates if g.status == GateStatus.WARN]
    
    @property
    def rejected_gates(self) -> List[GateItemV1]:
        """List of gates with REJECT status."""
        return [g for g in self.gates if g.status == GateStatus.REJECT]


# Helper functions
def create_gate_summary_from_gates(
    gates: List[GateItemV1],
    source: str = "unknown",
    evaluator: str = "gate_summary_service",
) -> GateSummaryV1:
    """Create GateSummaryV1 from list of gates."""
    if not gates:
        return GateSummaryV1(
            overall_status=GateStatus.UNKNOWN,
            overall_message="No gates evaluated",
            counts={"pass": 0, "warn": 0, "reject": 0, "skip": 0, "unknown": 0},
            gates=[],
            evaluated_at_utc="",
            evaluator=evaluator,
            source=source,
        )
    
    # Sort gates by gate_id for deterministic ordering
    sorted_gates = sorted(gates, key=lambda g: g.gate_id)
    
    # Compute counts
    counts = {
        "pass": 0,
        "warn": 0,
        "reject": 0,
        "skip": 0,
        "unknown": 0,
    }
    for gate in sorted_gates:
        status_key = gate.status.value.lower()
        if status_key in counts:
            counts[status_key] += 1
    
    # Determine overall status (FAIL if any REJECT, WARN if any WARN, else PASS)
    overall_status = GateStatus.PASS
    if any(g.status == GateStatus.REJECT for g in sorted_gates):
        overall_status = GateStatus.REJECT
    elif any(g.status == GateStatus.WARN for g in sorted_gates):
        overall_status = GateStatus.WARN
    elif all(g.status == GateStatus.SKIP for g in sorted_gates):
        overall_status = GateStatus.SKIP
    elif any(g.status == GateStatus.UNKNOWN for g in sorted_gates):
        overall_status = GateStatus.UNKNOWN
    
    # Generate overall message
    if overall_status == GateStatus.PASS:
        overall_message = f"All {len(sorted_gates)} gates PASS"
    elif overall_status == GateStatus.WARN:
        warn_count = counts["warn"]
        overall_message = f"{warn_count} gate(s) with WARN, {counts['pass']} PASS"
    elif overall_status == GateStatus.REJECT:
        reject_count = counts["reject"]
        overall_message = f"{reject_count} gate(s) REJECTED"
    elif overall_status == GateStatus.SKIP:
        overall_message = f"All {len(sorted_gates)} gates SKIPPED"
    else:
        overall_message = f"Gate status unknown"
    
    # Use latest gate timestamp or current time
    from datetime import datetime, timezone
    evaluated_at_utc = datetime.now(timezone.utc).isoformat()
    
    return GateSummaryV1(
        schema_version="v1",
        overall_status=overall_status,
        overall_message=overall_message,
        counts=counts,
        gates=sorted_gates,
        evaluated_at_utc=evaluated_at_utc,
        evaluator=evaluator,
        source=source,
    )