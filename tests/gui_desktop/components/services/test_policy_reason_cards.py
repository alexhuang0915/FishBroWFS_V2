"""
Unit tests for Policy Enforcement Reason Cards builder.
"""

import pytest
from unittest.mock import patch

from gui.services.gate_reason_cards_registry import (
    build_reason_cards_for_gate,
    POLICY_VIOLATION,
    POLICY_ARTIFACT_MISSING,
    GATE_POLICY_ENFORCEMENT,
)


def test_policy_artifact_missing():
    """Missing policy_check.json → returns POLICY_ARTIFACT_MISSING card."""
    job_id = "test-job-123"
    
    with patch('control.reporting.io.read_job_artifact') as mock_read:
        mock_read.return_value = None
        
        cards = build_reason_cards_for_gate(GATE_POLICY_ENFORCEMENT, job_id)
        
        assert len(cards) == 1
        card = cards[0]
        assert card.code == POLICY_ARTIFACT_MISSING
        assert card.title == "Policy Check Artifact Missing"
        assert card.severity == "WARN"
        assert "policy_check.json not produced by job" in card.why
        assert "Policy compliance cannot be verified" in card.impact
        assert "Ensure job produces policy_check.json" in card.recommended_action
        assert card.evidence_artifact == "policy_check.json"
        assert card.evidence_path == "$"


def test_policy_violation_rejected():
    """overall_status=REJECTED → returns POLICY_VIOLATION card."""
    job_id = "test-job-123"
    
    artifact_data = {
        "overall_status": "REJECTED",
        "failure_code": "POLICY_PREFLIGHT_FAILED",
        "policy_stage": "preflight",
        "final_reason": {
            "policy_stage": "preflight",
            "failure_code": "POLICY_PREFLIGHT_FAILED",
        }
    }
    
    with patch('control.reporting.io.read_job_artifact') as mock_read:
        mock_read.return_value = artifact_data
        
        cards = build_reason_cards_for_gate(GATE_POLICY_ENFORCEMENT, job_id)
        
        assert len(cards) == 1
        card = cards[0]
        assert card.code == POLICY_VIOLATION
        assert card.title == "Policy Violation"
        assert card.severity == "FAIL"
        assert "Policy preflight violation: POLICY_PREFLIGHT_FAILED" in card.why
        assert "Job rejected / blocked by governance" in card.impact
        assert "Fix config / inputs to comply with policy requirements" in card.recommended_action
        assert card.evidence_artifact == "policy_check.json"
        assert card.evidence_path == "$.overall_status"


def test_policy_violation_failed():
    """overall_status=FAILED → returns POLICY_VIOLATION card."""
    job_id = "test-job-123"
    
    artifact_data = {
        "overall_status": "FAILED",
        "failure_code": "POLICY_POSTFLIGHT_FAILED",
        "policy_stage": "postflight",
        "final_reason": {
            "policy_stage": "postflight",
            "failure_code": "POLICY_POSTFLIGHT_FAILED",
        }
    }
    
    with patch('control.reporting.io.read_job_artifact') as mock_read:
        mock_read.return_value = artifact_data
        
        cards = build_reason_cards_for_gate(GATE_POLICY_ENFORCEMENT, job_id)
        
        assert len(cards) == 1
        card = cards[0]
        assert card.code == POLICY_VIOLATION
        assert "Policy postflight violation: POLICY_POSTFLIGHT_FAILED" in card.why


def test_policy_passed():
    """overall_status=PASS → returns empty list."""
    job_id = "test-job-123"
    
    artifact_data = {
        "overall_status": "PASS",
        "failure_code": "",
        "policy_stage": "preflight",
    }
    
    with patch('control.reporting.io.read_job_artifact') as mock_read:
        mock_read.return_value = artifact_data
        
        cards = build_reason_cards_for_gate(GATE_POLICY_ENFORCEMENT, job_id)
        
        assert len(cards) == 0


def test_policy_unknown_status():
    """overall_status not REJECTED/FAILED/PASS → returns empty list."""
    job_id = "test-job-123"
    
    artifact_data = {
        "overall_status": "UNKNOWN",
        "failure_code": "",
        "policy_stage": "",
    }
    
    with patch('control.reporting.io.read_job_artifact') as mock_read:
        mock_read.return_value = artifact_data
        
        cards = build_reason_cards_for_gate(GATE_POLICY_ENFORCEMENT, job_id)
        
        assert len(cards) == 0


def test_artifact_missing_skips_violation_check():
    """Missing artifact should return only missing card, not check for violations."""
    job_id = "test-job-123"
    
    with patch('control.reporting.io.read_job_artifact') as mock_read:
        mock_read.return_value = None
        
        cards = build_reason_cards_for_gate(GATE_POLICY_ENFORCEMENT, job_id)
        
        assert len(cards) == 1
        assert cards[0].code == POLICY_ARTIFACT_MISSING


def test_case_insensitive_status_matching():
    """Status matching should be case-insensitive."""
    job_id = "test-job-123"
    
    artifact_data = {
        "overall_status": "rejected",  # lowercase
        "failure_code": "POLICY_PREFLIGHT_FAILED",
        "policy_stage": "preflight",
    }
    
    with patch('control.reporting.io.read_job_artifact') as mock_read:
        mock_read.return_value = artifact_data
        
        cards = build_reason_cards_for_gate(GATE_POLICY_ENFORCEMENT, job_id)
        
        assert len(cards) == 1
        assert cards[0].code == POLICY_VIOLATION


def test_deterministic_ordering():
    """If artifact missing, only missing card returned."""
    job_id = "test-job-123"
    
    with patch('control.reporting.io.read_job_artifact') as mock_read:
        mock_read.return_value = None
        
        cards = build_reason_cards_for_gate(GATE_POLICY_ENFORCEMENT, job_id)
        
        assert len(cards) == 1
        assert cards[0].code == POLICY_ARTIFACT_MISSING