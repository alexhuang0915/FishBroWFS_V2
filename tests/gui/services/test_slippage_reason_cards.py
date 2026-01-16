"""
Unit tests for Slippage Stress Reason Cards builder.
"""

import pytest
from unittest.mock import patch, mock_open, MagicMock
import json

from gui.services.gate_reason_cards_registry import (
    build_reason_cards_for_gate,
    SLIPPAGE_STRESS_EXCEEDED,
    SLIPPAGE_STRESS_ARTIFACT_MISSING,
    GATE_SLIPPAGE_STRESS,
)


def test_slippage_stress_artifact_missing():
    """Missing slippage_stress.json → returns SLIPPAGE_STRESS_ARTIFACT_MISSING card."""
    job_id = "test-job-123"
    
    # Mock artifact path to not exist
    with patch('core.paths.get_outputs_root') as mock_root:
        mock_root.return_value = "/tmp/outputs"
        with patch('control.supervisor.models.get_job_artifact_dir') as mock_dir:
            mock_dir.return_value = "/tmp/outputs/jobs/test-job-123"
            with patch('pathlib.Path.exists') as mock_exists:
                mock_exists.return_value = False
                
                cards = build_reason_cards_for_gate(GATE_SLIPPAGE_STRESS, job_id)
                
                assert len(cards) == 1
                card = cards[0]
                assert card.code == SLIPPAGE_STRESS_ARTIFACT_MISSING
                assert card.title == "Slippage Stress Artifact Missing"
                assert card.severity == "WARN"
                assert "slippage_stress.json not produced by research job" in card.why
                assert "Slippage stress cannot be evaluated" in card.impact
                assert "Ensure research job includes slippage stress test" in card.recommended_action
                assert card.evidence_artifact == "slippage_stress.json"
                assert card.evidence_path == "$"


def test_slippage_stress_artifact_malformed():
    """Malformed slippage_stress.json → returns SLIPPAGE_STRESS_ARTIFACT_MISSING card."""
    job_id = "test-job-123"
    
    with patch('core.paths.get_outputs_root') as mock_root:
        mock_root.return_value = "/tmp/outputs"
        with patch('control.supervisor.models.get_job_artifact_dir') as mock_dir:
            mock_dir.return_value = "/tmp/outputs/jobs/test-job-123"
            with patch('pathlib.Path.exists') as mock_exists:
                mock_exists.return_value = True
                with patch('control.reporting.io.read_job_artifact') as mock_read:
                    mock_read.return_value = "not a dict"
                    
                    cards = build_reason_cards_for_gate(GATE_SLIPPAGE_STRESS, job_id)
                    
                    assert len(cards) == 1
                    card = cards[0]
                    assert card.code == SLIPPAGE_STRESS_ARTIFACT_MISSING
                    assert "exists but cannot be parsed" in card.title or "Malformed" in card.title
                    assert card.severity == "WARN"


def test_slippage_stress_test_failed():
    """stress_test_passed=False → returns SLIPPAGE_STRESS_EXCEEDED card."""
    job_id = "test-job-123"
    
    artifact_data = {
        "stress_test_passed": False,
        "stress_matrix": {
            "S3": {
                "net_after_cost": -123.45,
                "turnover": 100.0,
                "slippage_bps": 5.0,
            }
        }
    }
    
    with patch('core.paths.get_outputs_root') as mock_root:
        mock_root.return_value = "/tmp/outputs"
        with patch('control.supervisor.models.get_job_artifact_dir') as mock_dir:
            mock_dir.return_value = "/tmp/outputs/jobs/test-job-123"
            with patch('pathlib.Path.exists') as mock_exists:
                mock_exists.return_value = True
                with patch('control.reporting.io.read_job_artifact') as mock_read:
                    mock_read.return_value = artifact_data
                    
                    cards = build_reason_cards_for_gate(GATE_SLIPPAGE_STRESS, job_id)
                    
                    assert len(cards) == 1
                    card = cards[0]
                    assert card.code == SLIPPAGE_STRESS_EXCEEDED
                    assert card.title == "Slippage Stress Test Failed"
                    assert card.severity == "FAIL"
                    assert "S3 net profit -123.45 <= threshold 0.0" in card.why
                    assert "PnL may be overstated; live performance risk increases" in card.impact
                    assert "Reduce turnover/entries, widen stops, adjust fill assumptions" in card.recommended_action
                    assert card.evidence_artifact == "slippage_stress.json"
                    assert card.evidence_path == "$.stress_test_passed"


def test_slippage_stress_test_passed():
    """stress_test_passed=True → returns empty list."""
    job_id = "test-job-123"
    
    artifact_data = {
        "stress_test_passed": True,
        "stress_matrix": {
            "S3": {
                "net_after_cost": 456.78,
                "turnover": 100.0,
                "slippage_bps": 5.0,
            }
        }
    }
    
    with patch('core.paths.get_outputs_root') as mock_root:
        mock_root.return_value = "/tmp/outputs"
        with patch('control.supervisor.models.get_job_artifact_dir') as mock_dir:
            mock_dir.return_value = "/tmp/outputs/jobs/test-job-123"
            with patch('pathlib.Path.exists') as mock_exists:
                mock_exists.return_value = True
                with patch('control.reporting.io.read_job_artifact') as mock_read:
                    mock_read.return_value = artifact_data
                    
                    cards = build_reason_cards_for_gate(GATE_SLIPPAGE_STRESS, job_id)
                    
                    assert len(cards) == 0


def test_deterministic_ordering():
    """If artifact missing, only missing card returned (no other cards)."""
    job_id = "test-job-123"
    
    with patch('core.paths.get_outputs_root') as mock_root:
        mock_root.return_value = "/tmp/outputs"
        with patch('control.supervisor.models.get_job_artifact_dir') as mock_dir:
            mock_dir.return_value = "/tmp/outputs/jobs/test-job-123"
            with patch('pathlib.Path.exists') as mock_exists:
                mock_exists.return_value = False
                
                cards = build_reason_cards_for_gate(GATE_SLIPPAGE_STRESS, job_id)
                
                # Should have exactly 1 card
                assert len(cards) == 1
                assert cards[0].code == SLIPPAGE_STRESS_ARTIFACT_MISSING


def test_formatting_deterministic():
    """Numeric values formatted deterministically (:.2f)."""
    job_id = "test-job-123"
    
    artifact_data = {
        "stress_test_passed": False,
        "stress_matrix": {
            "S3": {
                "net_after_cost": -123.456789,  # Should be formatted as -123.46
                "turnover": 100.0,
                "slippage_bps": 5.0,
            }
        }
    }
    
    with patch('core.paths.get_outputs_root') as mock_root:
        mock_root.return_value = "/tmp/outputs"
        with patch('control.supervisor.models.get_job_artifact_dir') as mock_dir:
            mock_dir.return_value = "/tmp/outputs/jobs/test-job-123"
            with patch('pathlib.Path.exists') as mock_exists:
                mock_exists.return_value = True
                with patch('control.reporting.io.read_job_artifact') as mock_read:
                    mock_read.return_value = artifact_data
                    
                    cards = build_reason_cards_for_gate(GATE_SLIPPAGE_STRESS, job_id)
                    
                    assert len(cards) == 1
                    card = cards[0]
                    # Check formatting
                    assert "-123.46" in card.why
                    assert "0.0" in card.why  # threshold