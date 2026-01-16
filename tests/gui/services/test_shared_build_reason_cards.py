"""
Unit tests for Shared Build Reason Cards builder.
"""

import pytest
from unittest.mock import patch, MagicMock

from gui.services.gate_reason_cards_registry import (
    build_reason_cards_for_gate,
    SHARED_BUILD_GATE_FAILED,
    SHARED_BUILD_GATE_WARN,
    SHARED_BUILD_ARTIFACT_MISSING,
    GATE_SHARED_BUILD,
)


def test_shared_build_artifact_missing():
    """Missing shared_build_manifest.json → returns SHARED_BUILD_ARTIFACT_MISSING card."""
    job_id = "test-job-123"
    
    with patch('core.paths.get_outputs_root') as mock_root:
        mock_root.return_value = "/tmp/outputs"
        with patch('control.supervisor.models.get_job_artifact_dir') as mock_dir:
            mock_dir.return_value = "/tmp/outputs/jobs/test-job-123"
            with patch('pathlib.Path.exists') as mock_exists:
                mock_exists.return_value = False
                
                cards = build_reason_cards_for_gate(GATE_SHARED_BUILD, job_id)
                
                assert len(cards) == 1
                card = cards[0]
                assert card.code == SHARED_BUILD_ARTIFACT_MISSING
                assert card.title == "Shared Build Manifest Missing"
                assert card.severity == "WARN"
                assert "shared_build_manifest.json not produced by shared build" in card.why
                assert "Shared data dependencies unknown; job may fail due to missing bars/features" in card.impact
                assert "Run shared build for required season/dataset or check build logs" in card.recommended_action
                assert card.evidence_artifact == "shared_build_manifest.json"
                assert card.evidence_path == "$"


def test_shared_build_artifact_malformed():
    """Malformed shared_build_manifest.json → returns SHARED_BUILD_ARTIFACT_MISSING card."""
    job_id = "test-job-123"
    
    with patch('core.paths.get_outputs_root') as mock_root:
        mock_root.return_value = "/tmp/outputs"
        with patch('control.supervisor.models.get_job_artifact_dir') as mock_dir:
            mock_dir.return_value = "/tmp/outputs/jobs/test-job-123"
            with patch('pathlib.Path.exists') as mock_exists:
                mock_exists.return_value = True
                with patch('control.reporting.io.read_job_artifact') as mock_read:
                    mock_read.return_value = "not a dict"
                    
                    cards = build_reason_cards_for_gate(GATE_SHARED_BUILD, job_id)
                    
                    assert len(cards) == 1
                    card = cards[0]
                    assert card.code == SHARED_BUILD_ARTIFACT_MISSING
                    assert "exists but cannot be parsed" in card.title or "Malformed" in card.title
                    assert card.severity == "WARN"


def test_shared_build_failed():
    """build_status=FAILED → returns SHARED_BUILD_GATE_FAILED card."""
    job_id = "test-job-123"
    
    artifact_data = {
        "build_status": "FAILED",
        "failure_reason": "Data source unavailable",
        "warnings": [],
    }
    
    with patch('core.paths.get_outputs_root') as mock_root:
        mock_root.return_value = "/tmp/outputs"
        with patch('control.supervisor.models.get_job_artifact_dir') as mock_dir:
            mock_dir.return_value = "/tmp/outputs/jobs/test-job-123"
            with patch('pathlib.Path.exists') as mock_exists:
                mock_exists.return_value = True
                with patch('control.reporting.io.read_job_artifact') as mock_read:
                    mock_read.return_value = artifact_data
                    
                    cards = build_reason_cards_for_gate(GATE_SHARED_BUILD, job_id)
                    
                    assert len(cards) == 1
                    card = cards[0]
                    assert card.code == SHARED_BUILD_GATE_FAILED
                    assert card.title == "Shared Build Failed"
                    assert card.severity == "FAIL"
                    assert "Shared build failed: Data source unavailable" in card.why
                    assert "Required bars/features unavailable; dependent jobs will fail" in card.impact
                    assert "Fix shared build configuration and re-run" in card.recommended_action
                    assert card.evidence_artifact == "shared_build_manifest.json"
                    assert card.evidence_path == "$.build_status"


def test_shared_build_warn():
    """build_status=WARN → returns SHARED_BUILD_GATE_WARN card."""
    job_id = "test-job-123"
    
    artifact_data = {
        "build_status": "WARN",
        "failure_reason": "",
        "warnings": ["Missing data for 2024-01-01", "Feature X incomplete"],
    }
    
    with patch('core.paths.get_outputs_root') as mock_root:
        mock_root.return_value = "/tmp/outputs"
        with patch('control.supervisor.models.get_job_artifact_dir') as mock_dir:
            mock_dir.return_value = "/tmp/outputs/jobs/test-job-123"
            with patch('pathlib.Path.exists') as mock_exists:
                mock_exists.return_value = True
                with patch('control.reporting.io.read_job_artifact') as mock_read:
                    mock_read.return_value = artifact_data
                    
                    cards = build_reason_cards_for_gate(GATE_SHARED_BUILD, job_id)
                    
                    assert len(cards) == 1
                    card = cards[0]
                    assert card.code == SHARED_BUILD_GATE_WARN
                    assert card.title == "Shared Build Warnings"
                    assert card.severity == "WARN"
                    assert "Shared build completed with warnings: Missing data for 2024-01-01, Feature X incomplete" in card.why
                    assert "Some data may be incomplete or suboptimal" in card.impact
                    assert "Review shared build warnings and adjust as needed" in card.recommended_action
                    assert card.evidence_artifact == "shared_build_manifest.json"
                    assert card.evidence_path == "$.build_status"


def test_shared_build_warn_truncated():
    """Warnings list truncated deterministically."""
    job_id = "test-job-123"
    
    artifact_data = {
        "build_status": "WARN",
        "failure_reason": "",
        "warnings": ["Warning 1", "Warning 2", "Warning 3", "Warning 4", "Warning 5"],
    }
    
    with patch('core.paths.get_outputs_root') as mock_root:
        mock_root.return_value = "/tmp/outputs"
        with patch('control.supervisor.models.get_job_artifact_dir') as mock_dir:
            mock_dir.return_value = "/tmp/outputs/jobs/test-job-123"
            with patch('pathlib.Path.exists') as mock_exists:
                mock_exists.return_value = True
                with patch('control.reporting.io.read_job_artifact') as mock_read:
                    mock_read.return_value = artifact_data
                    
                    cards = build_reason_cards_for_gate(GATE_SHARED_BUILD, job_id)
                    
                    assert len(cards) == 1
                    card = cards[0]
                    # Should show first 2 warnings and "..."
                    assert "Warning 1, Warning 2..." in card.why


def test_shared_build_passed():
    """build_status=PASS → returns empty list."""
    job_id = "test-job-123"
    
    artifact_data = {
        "build_status": "PASS",
        "failure_reason": "",
        "warnings": [],
    }
    
    with patch('core.paths.get_outputs_root') as mock_root:
        mock_root.return_value = "/tmp/outputs"
        with patch('control.supervisor.models.get_job_artifact_dir') as mock_dir:
            mock_dir.return_value = "/tmp/outputs/jobs/test-job-123"
            with patch('pathlib.Path.exists') as mock_exists:
                mock_exists.return_value = True
                with patch('control.reporting.io.read_job_artifact') as mock_read:
                    mock_read.return_value = artifact_data
                    
                    cards = build_reason_cards_for_gate(GATE_SHARED_BUILD, job_id)
                    
                    assert len(cards) == 0


def test_shared_build_unknown_status():
    """build_status not FAILED/WARN/PASS → returns empty list."""
    job_id = "test-job-123"
    
    artifact_data = {
        "build_status": "UNKNOWN",
        "failure_reason": "",
        "warnings": [],
    }
    
    with patch('core.paths.get_outputs_root') as mock_root:
        mock_root.return_value = "/tmp/outputs"
        with patch('control.supervisor.models.get_job_artifact_dir') as mock_dir:
            mock_dir.return_value = "/tmp/outputs/jobs/test-job-123"
            with patch('pathlib.Path.exists') as mock_exists:
                mock_exists.return_value = True
                with patch('control.reporting.io.read_job_artifact') as mock_read:
                    mock_read.return_value = artifact_data
                    
                    cards = build_reason_cards_for_gate(GATE_SHARED_BUILD, job_id)
                    
                    assert len(cards) == 0


def test_artifact_missing_skips_other_checks():
    """Missing artifact should return only missing card, not check build status."""
    job_id = "test-job-123"
    
    with patch('core.paths.get_outputs_root') as mock_root:
        mock_root.return_value = "/tmp/outputs"
        with patch('control.supervisor.models.get_job_artifact_dir') as mock_dir:
            mock_dir.return_value = "/tmp/outputs/jobs/test-job-123"
            with patch('pathlib.Path.exists') as mock_exists:
                mock_exists.return_value = False
                
                cards = build_reason_cards_for_gate(GATE_SHARED_BUILD, job_id)
                
                assert len(cards) == 1
                assert cards[0].code == SHARED_BUILD_ARTIFACT_MISSING


def test_deterministic_ordering():
    """If artifact missing, only missing card returned."""
    job_id = "test-job-123"
    
    with patch('core.paths.get_outputs_root') as mock_root:
        mock_root.return_value = "/tmp/outputs"
        with patch('control.supervisor.models.get_job_artifact_dir') as mock_dir:
            mock_dir.return_value = "/tmp/outputs/jobs/test-job-123"
            with patch('pathlib.Path.exists') as mock_exists:
                mock_exists.return_value = False
                
                cards = build_reason_cards_for_gate(GATE_SHARED_BUILD, job_id)
                
                assert len(cards) == 1
                assert cards[0].code == SHARED_BUILD_ARTIFACT_MISSING