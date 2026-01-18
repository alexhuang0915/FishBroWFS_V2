"""
Gate Reason Code Explain Dictionary v1.4 (SSOT).

Provides structured explanations for GateReasonCode values with:
- Developer View: Technical explanation for engineers
- Business View: Impact explanation for stakeholders
- Recommended Action: Concrete steps to resolve

This dictionary is the SSOT for all gate reason code explanations.
UI must NOT contain hardcoded mappings (no if code == ...: text = ...).
"""

from typing import Dict, TypedDict, Optional
from enum import Enum
from .gate_summary_schemas import GateReasonCode


# Version constant for explain dictionary
DICTIONARY_VERSION = "v1.5.0"  # Updated for v1.5 Governance Trust Lock


class GateReasonExplanation(TypedDict):
    """Structured explanation for a gate reason code."""
    # Developer View (for engineers debugging)
    developer_explanation: str
    # Business View (for stakeholders understanding impact)
    business_impact: str
    # Recommended action to resolve
    recommended_action: str
    # Severity level (INFO, WARN, ERROR)
    severity: str
    # Audience targeting (dev, business, both)
    audience: str


# SSOT Dictionary: GateReasonCode → GateReasonExplanation
GATE_REASON_EXPLAIN_DICTIONARY: Dict[str, GateReasonExplanation] = {
    # ============================================================================
    # Parse Errors (GATE_ITEM_PARSE_ERROR)
    # ============================================================================
    GateReasonCode.GATE_ITEM_PARSE_ERROR.value: {
        "developer_explanation": (
            "Failed to parse raw data into GateItemV1 model. "
            "The raw data structure does not match the expected schema, "
            "or required fields are missing/invalid."
        ),
        "business_impact": (
            "Gate evaluation cannot proceed due to malformed data. "
            "This prevents accurate assessment of system health or job readiness."
        ),
        "recommended_action": (
            "Check the raw data source for schema compliance. "
            "Ensure all required fields (gate_id, gate_name, status, message) are present. "
            "Review error details for specific validation failures."
        ),
        "severity": "ERROR",
        "audience": "both",
    },
    
    # ============================================================================
    # Summary Parse Errors (GATE_SUMMARY_PARSE_ERROR)
    # ============================================================================
    GateReasonCode.GATE_SUMMARY_PARSE_ERROR.value: {
        "developer_explanation": (
            "Failed to parse raw data into GateSummaryV1 model. "
            "The overall gate summary structure is invalid, "
            "missing required top-level fields, or contains malformed gate arrays."
        ),
        "business_impact": (
            "Complete gate summary unavailable. "
            "Cannot determine overall system/job status, blocking decision-making."
        ),
        "recommended_action": (
            "Validate the gate summary source (API response or artifact). "
            "Check schema_version field and ensure gates array is properly formatted. "
            "Review error telemetry for specific validation failures."
        ),
        "severity": "ERROR",
        "audience": "both",
    },
    
    # ============================================================================
    # Schema Version Errors (GATE_SCHEMA_VERSION_UNSUPPORTED)
    # ============================================================================
    GateReasonCode.GATE_SCHEMA_VERSION_UNSUPPORTED.value: {
        "developer_explanation": (
            "Gate summary schema version mismatch. "
            "The data claims schema_version='{schema_version}' but only 'v1' is supported. "
            "This indicates backward/forward compatibility issue."
        ),
        "business_impact": (
            "Cannot interpret gate summary due to version incompatibility. "
            "Newer or older schema versions require corresponding client updates."
        ),
        "recommended_action": (
            "Update client to support the reported schema version, "
            "or ensure data source emits only 'v1' schema. "
            "Check for version drift between components."
        ),
        "severity": "ERROR",
        "audience": "dev",
    },
    
    # ============================================================================
    # Fetch Errors (GATE_SUMMARY_FETCH_ERROR)
    # ============================================================================
    GateReasonCode.GATE_SUMMARY_FETCH_ERROR.value: {
        "developer_explanation": (
            "Failed to fetch gate summary from backend/artifact source. "
            "Network error, timeout, or source unavailable. "
            "Error: {error_class}: {error_message}"
        ),
        "business_impact": (
            "Gate status information unavailable. "
            "Cannot assess system/job health, creating operational blind spot."
        ),
        "recommended_action": (
            "Check backend service health and network connectivity. "
            "Verify artifact paths exist and are accessible. "
            "Retry operation after addressing underlying issue."
        ),
        "severity": "ERROR",
        "audience": "both",
    },
    
    # ============================================================================
    # Backend JSON Errors (GATE_BACKEND_INVALID_JSON)
    # ============================================================================
    GateReasonCode.GATE_BACKEND_INVALID_JSON.value: {
        "developer_explanation": (
            "Backend returned malformed JSON that cannot be parsed. "
            "Syntax error, encoding issue, or truncated response. "
            "Raw preview: {raw_preview}"
        ),
        "business_impact": (
            "Backend communication failure. "
            "Gate evaluation cannot proceed due to data format corruption."
        ),
        "recommended_action": (
            "Inspect backend logs for JSON serialization errors. "
            "Check response encoding and content-length headers. "
            "Validate backend endpoint returns valid JSON."
        ),
        "severity": "ERROR",
        "audience": "dev",
    },
    
    # ============================================================================
    # v1.5 Governance Trust Lock: Evidence Snapshot Errors
    # ============================================================================
    GateReasonCode.EVIDENCE_SNAPSHOT_MISSING.value: {
        "developer_explanation": (
            "Evidence snapshot file not found for job {job_id}. "
            "The evidence_snapshot_v1.json file is missing from the deployment bundle. "
            "Cannot guarantee time-consistent evidence interpretation."
        ),
        "business_impact": (
            "Historical verdict reproducibility compromised. "
            "Cannot verify that current evidence matches what was evaluated at verdict time."
        ),
        "recommended_action": (
            "Ensure evidence snapshot is created during bundle finalization. "
            "Check deployment bundle integrity and snapshot writer configuration. "
            "Regenerate snapshot from original evidence if available."
        ),
        "severity": "ERROR",
        "audience": "dev",
    },
    
    GateReasonCode.EVIDENCE_SNAPSHOT_HASH_MISMATCH.value: {
        "developer_explanation": (
            "Evidence file hash mismatch for {relpath}. "
            "Expected SHA256: {expected_sha256}, got: {observed_sha256} "
            "File content has changed since verdict time."
        ),
        "business_impact": (
            "Evidence tampering or accidental modification detected. "
            "Historical verdict interpretation is no longer reliable."
        ),
        "recommended_action": (
            "Restore original evidence file from backup or snapshot. "
            "Investigate unauthorized modifications to evidence files. "
            "Regenerate verdict with current evidence if intentional change."
        ),
        "severity": "ERROR",
        "audience": "both",
    },
    
    # ============================================================================
    # v1.5 Governance Trust Lock: Verdict Stamp Errors
    # ============================================================================
    GateReasonCode.VERDICT_STAMP_MISSING.value: {
        "developer_explanation": (
            "Verdict stamp file not found for job {job_id}. "
            "The verdict_stamp_v1.json file is missing from the deployment bundle. "
            "Cannot guarantee verdict reproducibility across policy/dictionary versions."
        ),
        "business_impact": (
            "Cannot verify which policy/dictionary versions were used for verdict. "
            "Historical verdict interpretation ambiguous."
        ),
        "recommended_action": (
            "Ensure verdict stamp is created during bundle finalization. "
            "Check deployment bundle integrity and stamp writer configuration. "
            "Recreate stamp with current versions if original unavailable."
        ),
        "severity": "WARN",
        "audience": "dev",
    },
    
    # ============================================================================
    # v1.5 Governance Trust Lock: Gate Dependency Errors
    # ============================================================================
    GateReasonCode.GATE_DEPENDENCY_CYCLE.value: {
        "developer_explanation": (
            "Gate dependency cycle detected in gate graph. "
            "Cycle path: {cycle_path}. "
            "Circular dependencies prevent proper primary/propagated failure classification."
        ),
        "business_impact": (
            "Gate failure causality analysis unreliable. "
            "Cannot determine root cause vs propagated failures."
        ),
        "recommended_action": (
            "Review gate dependency declarations for circular references. "
            "Ensure gate dependencies form a directed acyclic graph (DAG). "
            "Fix dependency declarations to eliminate cycles."
        ),
        "severity": "ERROR",
        "audience": "dev",
    },
}


def get_gate_reason_explanation(
    reason_code: str,
    context_vars: Optional[Dict[str, str]] = None
) -> GateReasonExplanation:
    """
    Get structured explanation for a gate reason code.
    
    Args:
        reason_code: GateReasonCode value (string)
        context_vars: Optional dictionary of template variables for explanation
        
    Returns:
        GateReasonExplanation with developer/business views and recommended action
        
    Raises:
        KeyError: If reason_code not in dictionary (should not happen for valid codes)
    """
    if reason_code not in GATE_REASON_EXPLAIN_DICTIONARY:
        # Fallback for unknown codes (defensive programming)
        return {
            "developer_explanation": f"Unknown reason code: {reason_code}",
            "business_impact": "Unknown error impact",
            "recommended_action": "Contact development team with error details",
            "severity": "ERROR",
            "audience": "dev",
        }
    
    explanation = GATE_REASON_EXPLAIN_DICTIONARY[reason_code].copy()
    
    # Apply template variables if provided
    if context_vars:
        for key in ["developer_explanation", "business_impact", "recommended_action"]:
            if key in explanation:
                for var_name, var_value in context_vars.items():
                    placeholder = f"{{{var_name}}}"
                    if placeholder in explanation[key]:
                        explanation[key] = explanation[key].replace(
                            placeholder, str(var_value)
                        )
    
    return explanation


def format_gate_reason_message(
    reason_code: str,
    context_vars: Optional[Dict[str, str]] = None
) -> str:
    """
    Format a human-readable message for a gate reason code.
    
    Combines developer explanation with business impact for a comprehensive message.
    
    Args:
        reason_code: GateReasonCode value
        context_vars: Optional template variables
        
    Returns:
        Formatted message suitable for UI display
    """
    explanation = get_gate_reason_explanation(reason_code, context_vars)
    
    return (
        f"{explanation['developer_explanation']} "
        f"Business impact: {explanation['business_impact']} "
        f"Recommended action: {explanation['recommended_action']}"
    )


def get_all_gate_reason_codes() -> list[str]:
    """Get all registered gate reason codes (for validation/testing)."""
    return list(GATE_REASON_EXPLAIN_DICTIONARY.keys())


# Validation: Ensure all GateReasonCode enum values have explanations
def validate_dictionary_completeness() -> None:
    """Validate that all GateReasonCode enum values have dictionary entries."""
    missing = []
    for code_enum in GateReasonCode:
        code_value = code_enum.value
        if code_value not in GATE_REASON_EXPLAIN_DICTIONARY:
            missing.append(code_value)
    
    if missing:
        raise ValueError(
            f"GateReasonCode dictionary incomplete. Missing entries for: {missing}"
        )


# Run validation on import (fail fast)
try:
    validate_dictionary_completeness()
except ValueError as e:
    # Log but don't crash in production
    import logging
    logging.getLogger(__name__).warning(f"Gate reason dictionary validation failed: {e}")