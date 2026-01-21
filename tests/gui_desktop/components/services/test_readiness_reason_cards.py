"""
Unit tests for Readiness Reason Cards builder.
"""

import pytest
from unittest.mock import patch

from gui.services.gate_reason_cards_registry import (
    build_reason_cards_for_gate,
    READINESS_DATA2_NOT_PREPARED,
    READINESS_DATA_COVERAGE_INSUFFICIENT,
    READINESS_ARTIFACT_MISSING,
    GATE_API_READINESS,
)


def test_readiness_artifact_missing():
    """Missing readiness_report.json → returns READINESS_ARTIFACT_MISSING card."""
    job_id = "test-job-123"
    
    with patch('control.reporting.io.read_job_artifact') as mock_read:
        mock_read.return_value = None
        
        cards = build_reason_cards_for_gate(GATE_API_READINESS, job_id)
        
        assert len(cards) == 1
        card = cards[0]
        assert card.code == READINESS_ARTIFACT_MISSING
        assert card.title == "Readiness Artifact Missing"
        assert card.severity == "WARN"
        assert "readiness_report.json not produced by job" in card.why
        assert "Data readiness cannot be evaluated" in card.impact
        assert "Ensure job produces readiness_report.json" in card.recommended_action
        assert card.evidence_artifact == "readiness_report.json"
        assert card.evidence_path == "$"


def test_readiness_artifact_malformed():
    """Malformed readiness artifact → returns READINESS_ARTIFACT_MISSING card."""
    job_id = "test-job-123"
    
    with patch('control.reporting.io.read_job_artifact') as mock_read:
        mock_read.return_value = "not a dict"
        
        cards = build_reason_cards_for_gate(GATE_API_READINESS, job_id)
        
        assert len(cards) == 1
        card = cards[0]
        assert card.code == READINESS_ARTIFACT_MISSING
        assert card.severity == "WARN"


def test_data2_not_prepared():
    """data2_prepared=False → returns READINESS_DATA2_NOT_PREPARED card."""
    job_id = "test-job-123"
    
    artifact_data = {
        "data2_prepared": False,
        "coverage_sufficient": True,
        "missing_periods": [],
    }
    
    with patch('control.reporting.io.read_job_artifact') as mock_read:
        mock_read.return_value = artifact_data
        
        cards = build_reason_cards_for_gate(GATE_API_READINESS, job_id)
        
        assert len(cards) == 1
        card = cards[0]
        assert card.code == READINESS_DATA2_NOT_PREPARED
        assert card.title == "Data2 Not Prepared"
        assert card.severity == "FAIL"
        assert "Data2 (context feeds) not prepared" in card.why
        assert "Job cannot proceed; Data2-dependent features will be unavailable" in card.impact
        assert "Run shared build for Data2 or select different data source" in card.recommended_action
        assert card.evidence_artifact == "readiness_report.json"
        assert card.evidence_path == "$.data2_prepared"


def test_data_coverage_insufficient():
    """coverage_sufficient=False → returns READINESS_DATA_COVERAGE_INSUFFICIENT card."""
    job_id = "test-job-123"
    
    artifact_data = {
        "data2_prepared": True,
        "coverage_sufficient": False,
        "missing_periods": ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"],
    }
    
    with patch('control.reporting.io.read_job_artifact') as mock_read:
        mock_read.return_value = artifact_data
        
        cards = build_reason_cards_for_gate(GATE_API_READINESS, job_id)
        
        assert len(cards) == 1
        card = cards[0]
        assert card.code == READINESS_DATA_COVERAGE_INSUFFICIENT
        assert card.title == "Data Coverage Insufficient"
        assert card.severity == "WARN"
        assert "Data missing for periods: ['2024-01-01', '2024-01-02', '2024-01-03']..." in card.why
        assert "Analysis may have gaps; results may not be representative" in card.impact
        assert "Extend data collection or adjust analysis timeframe" in card.recommended_action
        assert card.evidence_artifact == "readiness_report.json"
        assert card.evidence_path == "$.coverage_sufficient"


def test_multiple_issues():
    """Both data2_not_prepared and coverage_insufficient → returns both cards in deterministic order."""
    job_id = "test-job-123"
    
    artifact_data = {
        "data2_prepared": False,
        "coverage_sufficient": False,
        "missing_periods": ["2024-01-01"],
    }
    
    with patch('control.reporting.io.read_job_artifact') as mock_read:
        mock_read.return_value = artifact_data
        
        cards = build_reason_cards_for_gate(GATE_API_READINESS, job_id)
        
        # Should have 2 cards: DATA2_NOT_PREPARED (FAIL) first, then COVERAGE_INSUFFICIENT (WARN)
        assert len(cards) == 2
        assert cards[0].code == READINESS_DATA2_NOT_PREPARED
        assert cards[0].severity == "FAIL"
        assert cards[1].code == READINESS_DATA_COVERAGE_INSUFFICIENT
        assert cards[1].severity == "WARN"


def test_no_issues_returns_empty():
    """All readiness checks pass → returns empty list."""
    job_id = "test-job-123"
    
    artifact_data = {
        "data2_prepared": True,
        "coverage_sufficient": True,
        "missing_periods": [],
    }
    
    with patch('control.reporting.io.read_job_artifact') as mock_read:
        mock_read.return_value = artifact_data
        
        cards = build_reason_cards_for_gate(GATE_API_READINESS, job_id)
        
        assert len(cards) == 0


def test_artifact_missing_skips_other_checks():
    """Missing artifact should return only missing card, not check data2/coverage."""
    job_id = "test-job-123"
    
    with patch('control.reporting.io.read_job_artifact') as mock_read:
        mock_read.return_value = None
        
        cards = build_reason_cards_for_gate(GATE_API_READINESS, job_id)
        
        assert len(cards) == 1
        assert cards[0].code == READINESS_ARTIFACT_MISSING


def test_deterministic_formatting():
    """Missing periods list truncated deterministically."""
    job_id = "test-job-123"
    
    artifact_data = {
        "data2_prepared": True,
        "coverage_sufficient": False,
        "missing_periods": ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05"],
    }
    
    with patch('control.reporting.io.read_job_artifact') as mock_read:
        mock_read.return_value = artifact_data
        
        cards = build_reason_cards_for_gate(GATE_API_READINESS, job_id)
        
        assert len(cards) == 1
        card = cards[0]
        # Should show first 3 items and "..."
        assert "['2024-01-01', '2024-01-02', '2024-01-03']..." in card.why