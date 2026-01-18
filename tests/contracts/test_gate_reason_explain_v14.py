"""
Test Gate Reason Explain Dictionary v1.4 (Snapshot Lock).

Ensures the SSOT dictionary remains complete and unchanged without explicit approval.
"""

import pytest
from contracts.portfolio.gate_reason_explain import (
    GATE_REASON_EXPLAIN_DICTIONARY,
    get_gate_reason_explanation,
    get_all_gate_reason_codes,
    validate_dictionary_completeness,
)
from contracts.portfolio.gate_summary_schemas import GateReasonCode


def test_dictionary_contains_all_gate_reason_codes():
    """Verify all GateReasonCode enum values have dictionary entries."""
    validate_dictionary_completeness()
    
    # Double-check: count should match
    enum_codes = {code.value for code in GateReasonCode}
    dict_codes = set(GATE_REASON_EXPLAIN_DICTIONARY.keys())
    
    assert enum_codes == dict_codes, (
        f"Dictionary missing codes: {enum_codes - dict_codes}\n"
        f"Extra codes: {dict_codes - enum_codes}"
    )


def test_dictionary_structure():
    """Verify all dictionary entries have required fields."""
    required_fields = {
        "developer_explanation",
        "business_impact", 
        "recommended_action",
        "severity",
        "audience",
    }
    
    for code, explanation in GATE_REASON_EXPLAIN_DICTIONARY.items():
        missing_fields = required_fields - set(explanation.keys())
        assert not missing_fields, (
            f"Code {code} missing fields: {missing_fields}"
        )
        
        # Check field types
        assert isinstance(explanation["developer_explanation"], str)
        assert isinstance(explanation["business_impact"], str)
        assert isinstance(explanation["recommended_action"], str)
        assert explanation["severity"] in {"INFO", "WARN", "ERROR"}
        assert explanation["audience"] in {"dev", "business", "both"}


def test_get_gate_reason_explanation():
    """Test retrieving explanations with context variables."""
    # Test with GATE_ITEM_PARSE_ERROR
    explanation = get_gate_reason_explanation(GateReasonCode.GATE_ITEM_PARSE_ERROR.value)
    
    assert "developer_explanation" in explanation
    assert "Failed to parse raw data" in explanation["developer_explanation"]
    assert explanation["severity"] == "ERROR"
    
    # Test with context variables
    context = {"error_class": "ValidationError", "error_message": "Field missing"}
    explanation = get_gate_reason_explanation(
        GateReasonCode.GATE_SUMMARY_FETCH_ERROR.value,
        context
    )
    assert "ValidationError" in explanation["developer_explanation"]


def test_get_gate_reason_explanation_unknown_code():
    """Test fallback for unknown reason codes."""
    explanation = get_gate_reason_explanation("UNKNOWN_CODE_XYZ")
    
    assert "Unknown reason code" in explanation["developer_explanation"]
    assert explanation["severity"] == "ERROR"
    assert explanation["audience"] == "dev"


def test_get_all_gate_reason_codes():
    """Test retrieving all registered codes."""
    codes = get_all_gate_reason_codes()
    
    assert isinstance(codes, list)
    assert len(codes) == len(GateReasonCode)
    
    # All codes should be strings
    for code in codes:
        assert isinstance(code, str)
    
    # Should contain known codes
    assert GateReasonCode.GATE_ITEM_PARSE_ERROR.value in codes
    assert GateReasonCode.GATE_SUMMARY_PARSE_ERROR.value in codes


def test_dictionary_snapshot():
    """
    Snapshot test to detect unauthorized changes to the dictionary.
    
    This test will fail if the dictionary content changes, ensuring
    all modifications require explicit review and snapshot update.
    """
    # Create a deterministic snapshot of the dictionary
    snapshot = {}
    
    for code in sorted(GATE_REASON_EXPLAIN_DICTIONARY.keys()):
        explanation = GATE_REASON_EXPLAIN_DICTIONARY[code]
        # Create a hashable representation
        snapshot[code] = {
            "dev_len": len(explanation["developer_explanation"]),
            "business_len": len(explanation["business_impact"]),
            "action_len": len(explanation["recommended_action"]),
            "severity": explanation["severity"],
            "audience": explanation["audience"],
            # First 50 chars for quick comparison
            "dev_preview": explanation["developer_explanation"][:50],
        }
    
    # Expected snapshot (v1.4 initial implementation)
    # This will fail if dictionary changes without updating test
    expected_snapshot = {
        "EVIDENCE_SNAPSHOT_HASH_MISMATCH": {
            "action_len": 177,
            "audience": "both",
            "business_len": 112,
            "dev_len": 162,
            "dev_preview": "Evidence file hash mismatch for {relpath}. Expecte",
            "severity": "ERROR",
        },
        "EVIDENCE_SNAPSHOT_MISSING": {
            "action_len": 189,
            "audience": "dev",
            "business_len": 127,
            "dev_len": 182,
            "dev_preview": "Evidence snapshot file not found for job {job_id}.",
            "severity": "ERROR",
        },
        "GATE_BACKEND_INVALID_JSON": {
            "action_len": 149,
            "audience": "dev",
            "business_len": 92,
            "dev_len": 134,
            "dev_preview": "Backend returned malformed JSON that cannot be par",
            "severity": "ERROR",
        },
        "GATE_DEPENDENCY_CYCLE": {
            "action_len": 171,
            "audience": "dev",
            "business_len": 95,
            "dev_len": 151,
            "dev_preview": "Gate dependency cycle detected in gate graph. Cycl",
            "severity": "ERROR",
        },
        "GATE_ITEM_PARSE_ERROR": {
            "action_len": 181,
            "audience": "both",
            "business_len": 122,
            "dev_len": 146,
            "dev_preview": "Failed to parse raw data into GateItemV1 model. Th",
            "severity": "ERROR",
        },
        "GATE_SCHEMA_VERSION_UNSUPPORTED": {
            "action_len": 143,
            "audience": "dev",
            "business_len": 130,
            "dev_len": 168,
            "dev_preview": "Gate summary schema version mismatch. The data cla",
            "severity": "ERROR",
        },
        "GATE_SUMMARY_FETCH_ERROR": {
            "action_len": 153,
            "audience": "both",
            "business_len": 102,
            "dev_len": 143,
            "dev_preview": "Failed to fetch gate summary from backend/artifact",
            "severity": "ERROR",
        },
        "GATE_SUMMARY_PARSE_ERROR": {
            "action_len": 190,
            "audience": "both",
            "business_len": 104,
            "dev_len": 167,
            "dev_preview": "Failed to parse raw data into GateSummaryV1 model.",
            "severity": "ERROR",
        },
        "VERDICT_STAMP_MISSING": {
            "action_len": 187,
            "audience": "dev",
            "business_len": 114,
            "dev_len": 192,
            "dev_preview": "Verdict stamp file not found for job {job_id}. The",
            "severity": "WARN",
        },
    }
    
    # Compare snapshots
    assert snapshot == expected_snapshot, (
        "Gate reason dictionary changed! "
        "If this is intentional, update the expected_snapshot in this test. "
        f"Diff: {set(snapshot.items()) ^ set(expected_snapshot.items())}"
    )


if __name__ == "__main__":
    # Quick validation
    validate_dictionary_completeness()
    print("✓ Dictionary validation passed")
    print(f"✓ Contains {len(GATE_REASON_EXPLAIN_DICTIONARY)} reason code explanations")