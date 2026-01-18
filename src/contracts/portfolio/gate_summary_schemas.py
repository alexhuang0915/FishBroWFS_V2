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

from typing import Dict, List, Optional, Literal, Any, Union
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict, ValidationError
import json


class GateStatus(str, Enum):
    """Gate status values."""
    PASS = "PASS"
    WARN = "WARN"
    REJECT = "REJECT"
    SKIP = "SKIP"
    UNKNOWN = "UNKNOWN"


class GateReasonCode(str, Enum):
    """Standardized reason codes for gate items (SSOT guard)."""
    GATE_ITEM_PARSE_ERROR = "GATE_ITEM_PARSE_ERROR"
    GATE_SUMMARY_PARSE_ERROR = "GATE_SUMMARY_PARSE_ERROR"
    GATE_SCHEMA_VERSION_UNSUPPORTED = "GATE_SCHEMA_VERSION_UNSUPPORTED"
    GATE_SUMMARY_FETCH_ERROR = "GATE_SUMMARY_FETCH_ERROR"
    GATE_BACKEND_INVALID_JSON = "GATE_BACKEND_INVALID_JSON"
    # v1.5 Governance Trust Lock additions
    EVIDENCE_SNAPSHOT_MISSING = "EVIDENCE_SNAPSHOT_MISSING"
    EVIDENCE_SNAPSHOT_HASH_MISMATCH = "EVIDENCE_SNAPSHOT_HASH_MISMATCH"
    VERDICT_STAMP_MISSING = "VERDICT_STAMP_MISSING"
    GATE_DEPENDENCY_CYCLE = "GATE_DEPENDENCY_CYCLE"


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
    
    # v1.5 Governance Trust Lock: Dependency graph fields
    depends_on: List[str] = Field(
        default_factory=list,
        description="List of gate_ids this gate depends on (for causal analysis)"
    )
    is_primary_fail: bool = Field(
        default=False,
        description="True if this gate failed and none of its dependencies failed"
    )
    is_propagated_fail: bool = Field(
        default=False,
        description="True if this gate failed and at least one dependency failed"
    )
    
    # Telemetry and semantic slots (v1.3+)
    details: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Structured telemetry and semantic slots for error details, diagnostics, etc."
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
    *,
    compute_dependencies: bool = True,
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
    
    # Compute dependency flags if requested (v1.5)
    if compute_dependencies:
        gates = compute_gate_dependency_flags(gates)
    
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


# Backward compatibility alias for tests
GateV1 = GateItemV1


# ============================================================================
# v1.5 Governance Trust Lock: Gate Dependency Graph Computation
# ============================================================================

def compute_gate_dependency_flags(
    gates: List[GateItemV1],
    *,
    fail_threshold: GateStatus = GateStatus.REJECT,
) -> List[GateItemV1]:
    """
    Compute primary vs propagated failure flags based on dependency graph.
    
    Args:
        gates: List of GateItemV1 with depends_on fields
        fail_threshold: Status considered as failure (default: REJECT)
        
    Returns:
        New list of GateItemV1 with is_primary_fail and is_propagated_fail set
        
    Rules:
    1. A gate is considered "failed" if status >= fail_threshold (REJECT by default)
    2. A gate is "primary_fail" if it fails and none of its dependencies fail
    3. A gate is "propagated_fail" if it fails and at least one dependency fails
    4. Detect cycles and add synthetic error gate if cycle found
    5. Return new gate objects (frozen models cannot be mutated)
    """
    from copy import deepcopy
    
    # Build gate lookup
    gate_by_id = {gate.gate_id: gate for gate in gates}
    
    # Check for cycles
    def detect_cycles() -> Optional[List[str]]:
        """Detect dependency cycles using DFS."""
        visited = set()
        rec_stack = set()
        cycle_path = []
        
        def dfs(gate_id: str, path: List[str]) -> Optional[List[str]]:
            if gate_id not in gate_by_id:
                return None
                
            if gate_id in rec_stack:
                # Cycle detected
                cycle_start = path.index(gate_id)
                return path[cycle_start:] + [gate_id]
                
            if gate_id in visited:
                return None
                
            visited.add(gate_id)
            rec_stack.add(gate_id)
            path.append(gate_id)
            
            gate = gate_by_id[gate_id]
            for dep_id in gate.depends_on:
                if dep_id in gate_by_id:
                    result = dfs(dep_id, path)
                    if result:
                        return result
                        
            rec_stack.remove(gate_id)
            path.pop()
            return None
        
        for gate_id in gate_by_id:
            if gate_id not in visited:
                result = dfs(gate_id, [])
                if result:
                    return result
        return None
    
    # Detect cycles
    cycle = detect_cycles()
    if cycle:
        # Create synthetic error gate for cycle
        cycle_gate = build_error_gate_item(
            gate_id="gate_dependency_cycle",
            reason_code=GateReasonCode.GATE_DEPENDENCY_CYCLE.value,
            error=ValueError(f"Dependency cycle detected: {' -> '.join(cycle)}"),
            error_path="gate_summary_schemas.compute_gate_dependency_flags",
            raw={"cycle_path": cycle},
        )
        # Return original gates plus error gate
        return gates + [cycle_gate]
    
    # Determine which gates are failed (status >= fail_threshold)
    # GateStatus order: PASS < WARN < REJECT < SKIP < UNKNOWN
    status_order = {
        GateStatus.PASS: 0,
        GateStatus.WARN: 1,
        GateStatus.REJECT: 2,
        GateStatus.SKIP: 3,
        GateStatus.UNKNOWN: 4,
    }
    
    failed_gate_ids = {
        gate.gate_id for gate in gates
        if status_order.get(gate.status, 0) >= status_order.get(fail_threshold, 0)
    }
    
    # Compute transitive closure of failures (propagation)
    def has_failed_dependency(gate_id: str, visited: set = None) -> bool:
        """Check if any dependency (transitive) is failed."""
        if visited is None:
            visited = set()
            
        if gate_id in visited:
            return False
        visited.add(gate_id)
        
        gate = gate_by_id.get(gate_id)
        if not gate:
            return False
            
        # Check direct dependencies
        for dep_id in gate.depends_on:
            if dep_id in failed_gate_ids:
                return True
            # Recursively check transitive dependencies
            if has_failed_dependency(dep_id, visited):
                return True
        return False
    
    # Create new gates with computed flags
    result_gates = []
    for gate in gates:
        # Create copy with updated flags
        gate_dict = gate.model_dump()
        is_failed = gate.gate_id in failed_gate_ids
        
        if is_failed:
            has_failed_dep = has_failed_dependency(gate.gate_id)
            gate_dict["is_primary_fail"] = not has_failed_dep
            gate_dict["is_propagated_fail"] = has_failed_dep
        else:
            gate_dict["is_primary_fail"] = False
            gate_dict["is_propagated_fail"] = False
        
        result_gates.append(GateItemV1.model_validate(gate_dict))
    
    return result_gates


# ============================================================================
# SSOT Safe Helpers (v1.3 MAX)
# ============================================================================

def sanitize_raw(value: Any, *, max_len: int = 4096) -> Any:
    """
    Sanitize raw value for safe inclusion in telemetry.
    
    Rules:
    - If value is dict/list/str/int/float/bool/None => keep but truncate long strings
    - If unknown type => repr(value)
    - For dict/list, if deep/large, truncate by limiting string lengths and item counts
    - Return JSON-safe structure
    """
    if value is None:
        return None
    elif isinstance(value, (int, float, bool)):
        return value
    elif isinstance(value, str):
        if len(value) > max_len:
            return value[:max_len] + f"... (truncated, total {len(value)} chars)"
        return value
    elif isinstance(value, dict):
        result = {}
        for i, (k, v) in enumerate(value.items()):
            if i >= 50:  # Limit to 50 keys
                result[f"__truncated_keys__"] = f"{len(value) - 50} more keys"
                break
            if isinstance(k, str):
                result[k] = sanitize_raw(v, max_len=max_len)
            else:
                result[str(k)] = sanitize_raw(v, max_len=max_len)
        return result
    elif isinstance(value, list):
        result = []
        for i, item in enumerate(value):
            if i >= 100:  # Limit to 100 items
                result.append(f"... (truncated, total {len(value)} items)")
                break
            result.append(sanitize_raw(item, max_len=max_len))
        return result
    else:
        # Unknown type - convert to string representation
        repr_str = repr(value)
        if len(repr_str) > max_len:
            repr_str = repr_str[:max_len] + "..."
        return repr_str


def build_error_gate_item(
    *,
    gate_id: str,
    reason_code: str,
    error: Optional[Exception] = None,
    error_path: str,
    raw: Any = None,
) -> GateItemV1:
    """
    Create an ERROR gate item with structured telemetry.
    
    Args:
        gate_id: Gate identifier (e.g., "gate_summary", "system_api_health")
        reason_code: Reason code from GateReasonCode
        error: Optional exception object
        error_path: Path where error occurred (e.g., "gui.cross_job_gate_summary_service.fetch_gate_summary_for_job")
        raw: Raw data that caused the error (sanitized)
    
    Returns:
        GateItemV1 with status=REJECT (ERROR) and telemetry in details
    """
    from datetime import datetime, timezone
    
    # Build context variables for explanation template
    context_vars = {
        "error_class": error.__class__.__name__ if error else "Unknown",
        "error_message": str(error) if error else "No error details",
        "error_path": error_path,
    }
    
    # Add schema_version if available in raw data
    if isinstance(raw, dict) and "schema_version" in raw:
        context_vars["schema_version"] = raw["schema_version"]
    
    # Add raw preview for JSON errors
    if isinstance(raw, (str, bytes)) and len(str(raw)) > 100:
        context_vars["raw_preview"] = str(raw)[:100] + "..."
    elif raw is not None:
        context_vars["raw_preview"] = str(raw)
    
    # Get structured explanation from v1.4 dictionary
    try:
        from .gate_reason_explain import get_gate_reason_explanation
        explanation = get_gate_reason_explanation(reason_code, context_vars)
    except ImportError:
        # Fallback if dictionary not available
        explanation = {
            "developer_explanation": f"Failed to process {gate_id}: {reason_code}",
            "business_impact": "Gate evaluation failed",
            "recommended_action": "Check error details and retry",
            "severity": "ERROR",
            "audience": "dev",
        }
    
    # Build error details with L6 telemetry
    details = {
        "error_class": context_vars["error_class"],
        "error_message": context_vars["error_message"],
        "error_path": error_path,
        "raw": sanitize_raw(raw),
        # Semantic slots (v1.4)
        "diagnostic_trace": [],
        "action_hints": [explanation["recommended_action"]],
        "audience": explanation["audience"],
        # v1.4 explain dictionary integration
        "explanation": explanation,
    }
    
    # Format message combining developer and business views
    message = (
        f"{explanation['developer_explanation']} "
        f"Impact: {explanation['business_impact']}"
    )
    
    return GateItemV1(
        gate_id=gate_id,
        gate_name=f"Error: {gate_id}",
        status=GateStatus.REJECT,  # ERROR status
        message=message,
        reason_codes=[reason_code],
        evidence_refs=[],
        details=details,
        evaluated_at_utc=datetime.now(timezone.utc).isoformat(),
        evaluator="gate_summary_schemas_safe_helpers",
    )


def safe_gate_item_from_raw(gate_id: str, raw: Any, *, error_path: str) -> GateItemV1:
    """
    Safely create GateItemV1 from raw data, with fallback to error gate on failure.
    
    Args:
        gate_id: Gate identifier
        raw: Raw data (dict or other)
        error_path: Path for error telemetry
    
    Returns:
        GateItemV1, either validated from raw or error fallback
    """
    try:
        if isinstance(raw, dict):
            # Ensure gate_id is set
            data = {**raw, "gate_id": gate_id}
            return GateItemV1.model_validate(data)
        else:
            raise ValueError(f"Raw data must be dict, got {type(raw)}")
    except Exception as e:
        return build_error_gate_item(
            gate_id=gate_id,
            reason_code=GateReasonCode.GATE_ITEM_PARSE_ERROR.value,
            error=e,
            error_path=error_path,
            raw=raw,
        )


def safe_gate_summary_from_raw(raw: Any, *, error_path: str) -> GateSummaryV1:
    """
    Safely create GateSummaryV1 from raw data, with fallback to error summary on failure.
    
    Args:
        raw: Raw data (dict or other)
        error_path: Path for error telemetry
    
    Returns:
        GateSummaryV1, either validated from raw or error fallback
    """
    try:
        if not isinstance(raw, dict):
            raise ValueError(f"Raw data must be dict, got {type(raw)}")
        
        # Check schema version
        schema_version = raw.get("schema_version", "v1")
        if schema_version != "v1":
            # Unknown schema version - create error summary
            error_gate = build_error_gate_item(
                gate_id="gate_summary",
                reason_code=GateReasonCode.GATE_SCHEMA_VERSION_UNSUPPORTED.value,
                error=ValueError(f"Unsupported schema version: {schema_version}"),
                error_path=error_path,
                raw={"schema_version": schema_version},
            )
            return create_gate_summary_from_gates(
                gates=[error_gate],
                source="safe_gate_summary_from_raw",
                evaluator="gate_summary_schemas_safe_helpers",
            )
        
        # Try to validate
        return GateSummaryV1.model_validate(raw)
        
    except Exception as e:
        # Parse error - create error summary
        error_gate = build_error_gate_item(
            gate_id="gate_summary",
            reason_code=GateReasonCode.GATE_SUMMARY_PARSE_ERROR.value,
            error=e,
            error_path=error_path,
            raw=sanitize_raw(raw),
        )
        return create_gate_summary_from_gates(
            gates=[error_gate],
            source="safe_gate_summary_from_raw",
            evaluator="gate_summary_schemas_safe_helpers",
        )