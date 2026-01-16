"""
Unit tests for Control Actions Reason Cards builder.
"""

import pytest
from unittest.mock import patch, MagicMock
import os

from gui.services.gate_reason_cards_registry import (
    build_reason_cards_for_gate,
    CONTROL_ACTION_EVIDENCE_MISSING,
    GATE_CONTROL_ACTIONS,
)


def test_control_actions_disabled():
    """FISHBRO_ENABLE_CONTROL_ACTIONS not set → returns empty list."""
    job_id = "test-job-123"
    
    with patch.dict(os.environ, {}, clear=True):
        cards = build_reason_cards_for_gate(GATE_CONTROL_ACTIONS, job_id)
        
        assert len(cards) == 0


def test_control_actions_enabled_no_evidence():
    """Control actions enabled but no evidence files → returns CONTROL_ACTION_EVIDENCE_MISSING card."""
    job_id = "test-job-123"
    
    with patch.dict(os.environ, {'FISHBRO_ENABLE_CONTROL_ACTIONS': '1'}, clear=True):
        with patch('core.paths.get_outputs_root') as mock_root:
            mock_root.return_value = "/tmp/outputs"
            with patch('control.supervisor.models.get_job_artifact_dir') as mock_dir:
                mock_dir.return_value = "/tmp/outputs/jobs/test-job-123"
                with patch('pathlib.Path.glob') as mock_glob:
                    mock_glob.return_value = []  # No evidence files
                    
                    cards = build_reason_cards_for_gate(GATE_CONTROL_ACTIONS, job_id)
                    
                    assert len(cards) == 1
                    card = cards[0]
                    assert card.code == CONTROL_ACTION_EVIDENCE_MISSING
                    assert card.title == "Control Action Evidence Missing"
                    assert card.severity == "WARN"
                    assert "No evidence file found for control actions" in card.why
                    assert "Audit trail incomplete; action attribution unclear" in card.impact
                    assert "Ensure control actions write evidence artifacts" in card.recommended_action
                    assert card.evidence_artifact == "*abort*evidence*.json"
                    assert card.evidence_path == "$"


def test_control_actions_enabled_with_evidence():
    """Control actions enabled and evidence files exist → returns empty list."""
    job_id = "test-job-123"
    
    with patch.dict(os.environ, {'FISHBRO_ENABLE_CONTROL_ACTIONS': '1'}, clear=True):
        with patch('core.paths.get_outputs_root') as mock_root:
            mock_root.return_value = "/tmp/outputs"
            with patch('control.supervisor.models.get_job_artifact_dir') as mock_dir:
                mock_dir.return_value = "/tmp/outputs/jobs/test-job-123"
                with patch('pathlib.Path.glob') as mock_glob:
                    # Mock a Path object for evidence file
                    mock_path = MagicMock()
                    mock_path.name = "abort_evidence_20240101.json"
                    mock_glob.return_value = [mock_path]
                    
                    cards = build_reason_cards_for_gate(GATE_CONTROL_ACTIONS, job_id)
                    
                    assert len(cards) == 0


def test_control_actions_enabled_multiple_evidence_files():
    """Multiple evidence files → returns empty list."""
    job_id = "test-job-123"
    
    with patch.dict(os.environ, {'FISHBRO_ENABLE_CONTROL_ACTIONS': '1'}, clear=True):
        with patch('core.paths.get_outputs_root') as mock_root:
            mock_root.return_value = "/tmp/outputs"
            with patch('control.supervisor.models.get_job_artifact_dir') as mock_dir:
                mock_dir.return_value = "/tmp/outputs/jobs/test-job-123"
                with patch('pathlib.Path.glob') as mock_glob:
                    mock_path1 = MagicMock()
                    mock_path1.name = "abort_evidence_20240101.json"
                    mock_path2 = MagicMock()
                    mock_path2.name = "pause_evidence_20240102.json"
                    mock_glob.return_value = [mock_path1, mock_path2]
                    
                    cards = build_reason_cards_for_gate(GATE_CONTROL_ACTIONS, job_id)
                    
                    assert len(cards) == 0


def test_control_actions_disabled_env_0():
    """FISHBRO_ENABLE_CONTROL_ACTIONS=0 → returns empty list."""
    job_id = "test-job-123"
    
    with patch.dict(os.environ, {'FISHBRO_ENABLE_CONTROL_ACTIONS': '0'}, clear=True):
        cards = build_reason_cards_for_gate(GATE_CONTROL_ACTIONS, job_id)
        
        assert len(cards) == 0


def test_control_actions_disabled_empty_string():
    """FISHBRO_ENABLE_CONTROL_ACTIONS empty string → returns empty list."""
    job_id = "test-job-123"
    
    with patch.dict(os.environ, {'FISHBRO_ENABLE_CONTROL_ACTIONS': ''}, clear=True):
        cards = build_reason_cards_for_gate(GATE_CONTROL_ACTIONS, job_id)
        
        assert len(cards) == 0


def test_deterministic_ordering():
    """Only one possible card (CONTROL_ACTION_EVIDENCE_MISSING) when conditions met."""
    job_id = "test-job-123"
    
    with patch.dict(os.environ, {'FISHBRO_ENABLE_CONTROL_ACTIONS': '1'}, clear=True):
        with patch('core.paths.get_outputs_root') as mock_root:
            mock_root.return_value = "/tmp/outputs"
            with patch('control.supervisor.models.get_job_artifact_dir') as mock_dir:
                mock_dir.return_value = "/tmp/outputs/jobs/test-job-123"
                with patch('pathlib.Path.glob') as mock_glob:
                    mock_glob.return_value = []
                    
                    cards = build_reason_cards_for_gate(GATE_CONTROL_ACTIONS, job_id)
                    
                    assert len(cards) == 1
                    assert cards[0].code == CONTROL_ACTION_EVIDENCE_MISSING