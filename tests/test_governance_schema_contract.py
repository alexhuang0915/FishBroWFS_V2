"""Contract tests for governance schema.

Tests that governance schema is JSON-serializable and follows contracts.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from FishBroWFS_V2.core.governance_schema import (
    Decision,
    EvidenceRef,
    GovernanceItem,
    GovernanceReport,
)


def test_governance_report_json_serializable() -> None:
    """
    Test that GovernanceReport is JSON-serializable.
    
    This is a critical contract: governance.json must be machine-readable.
    """
    # Create sample evidence
    evidence = [
        EvidenceRef(
            run_id="test-run-123",
            stage_name="stage1_topk",
            artifact_paths=["manifest.json", "metrics.json", "winners.json"],
            key_metrics={"param_id": 0, "net_profit": 100.0, "trades": 10},
        ),
    ]
    
    # Create sample item
    item = GovernanceItem(
        candidate_id="donchian_atr:abc123def456",
        decision=Decision.KEEP,
        reasons=["R3: density_5_over_threshold_3"],
        evidence=evidence,
        created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        git_sha="abc123def456",
    )
    
    # Create report
    report = GovernanceReport(
        items=[item],
        metadata={
            "governance_id": "gov-20251218T000000Z-12345678",
            "season": "test_season",
            "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "git_sha": "abc123def456",
        },
    )
    
    # Convert to dict
    report_dict = report.to_dict()
    
    # Serialize to JSON
    json_str = json.dumps(report_dict, ensure_ascii=False, sort_keys=True, indent=2)
    
    # Deserialize back
    report_dict_roundtrip = json.loads(json_str)
    
    # Verify structure
    assert "items" in report_dict_roundtrip
    assert "metadata" in report_dict_roundtrip
    assert len(report_dict_roundtrip["items"]) == 1
    
    item_dict = report_dict_roundtrip["items"][0]
    assert item_dict["candidate_id"] == "donchian_atr:abc123def456"
    assert item_dict["decision"] == "KEEP"
    assert len(item_dict["reasons"]) == 1
    assert len(item_dict["evidence"]) == 1
    
    evidence_dict = item_dict["evidence"][0]
    assert evidence_dict["run_id"] == "test-run-123"
    assert evidence_dict["stage_name"] == "stage1_topk"
    assert "artifact_paths" in evidence_dict
    assert "key_metrics" in evidence_dict


def test_decision_enum_values() -> None:
    """Test that Decision enum has correct values."""
    assert Decision.KEEP.value == "KEEP"
    assert Decision.FREEZE.value == "FREEZE"
    assert Decision.DROP.value == "DROP"


def test_evidence_ref_contains_subsample_fields() -> None:
    """
    Test that EvidenceRef can contain subsample fields in key_metrics.
    
    This is a critical requirement: subsample info must be in evidence.
    """
    evidence = EvidenceRef(
        run_id="test-run-123",
        stage_name="stage1_topk",
        artifact_paths=["manifest.json", "metrics.json", "winners.json"],
        key_metrics={
            "param_id": 0,
            "net_profit": 100.0,
            "stage_planned_subsample": 0.1,
            "param_subsample_rate": 0.1,
            "params_effective": 100,
        },
    )
    
    # Verify subsample fields are present
    assert "stage_planned_subsample" in evidence.key_metrics
    assert "param_subsample_rate" in evidence.key_metrics
    assert "params_effective" in evidence.key_metrics
