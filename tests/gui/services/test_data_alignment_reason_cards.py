"""
Unit tests for Data Alignment Reason Cards builder.
"""

import pytest

from gui.services.data_alignment_status import (
    DataAlignmentStatus,
    build_data_alignment_reason_cards,
    DATA_ALIGNMENT_MISSING,
    DATA_ALIGNMENT_HIGH_FORWARD_FILL_RATIO,
    DATA_ALIGNMENT_DROPPED_ROWS,
    DEFAULT_FORWARD_FILL_WARN_THRESHOLD,
    ARTIFACT_NAME,
)


def test_missing_artifact_returns_one_card():
    """MISSING status → returns exactly 1 card with code=DATA_ALIGNMENT_MISSING."""
    status = DataAlignmentStatus(
        status="MISSING",
        artifact_relpath=ARTIFACT_NAME,
        artifact_abspath="/tmp/test/data_alignment_report.json",
        message="data_alignment_report.json not produced by BUILD_DATA",
        metrics={},
    )
    
    cards = build_data_alignment_reason_cards(
        job_id="test-job",
        status=status,
        warn_forward_fill_ratio=DEFAULT_FORWARD_FILL_WARN_THRESHOLD,
    )
    
    assert len(cards) == 1
    card = cards[0]
    assert card.code == DATA_ALIGNMENT_MISSING
    assert card.title == "Data Alignment Report Missing"
    assert card.severity == "WARN"
    assert card.why == "data_alignment_report.json not produced by BUILD_DATA"
    assert card.impact == "Alignment quality cannot be audited; downstream metrics may be less trustworthy"
    assert card.recommended_action == "Re-run BUILD_DATA for this job or inspect runner logs to confirm artifact generation"
    assert card.evidence_artifact == ARTIFACT_NAME
    assert card.evidence_path == "$"
    assert card.action_target == "/tmp/test/data_alignment_report.json"


def test_high_forward_fill_ratio_returns_card():
    """OK status with forward_fill_ratio > threshold → includes HIGH_FORWARD_FILL_RATIO card."""
    status = DataAlignmentStatus(
        status="OK",
        artifact_relpath=ARTIFACT_NAME,
        artifact_abspath="/tmp/test/data_alignment_report.json",
        message="data_alignment_report.json is available",
        metrics={
            "forward_fill_ratio": 0.75,  # > 0.5 threshold
            "dropped_rows": 0,
            "forward_filled_rows": 10,
        },
    )
    
    cards = build_data_alignment_reason_cards(
        job_id="test-job",
        status=status,
        warn_forward_fill_ratio=0.5,
    )
    
    # Should have exactly 1 card for high forward-fill ratio
    assert len(cards) == 1
    card = cards[0]
    assert card.code == DATA_ALIGNMENT_HIGH_FORWARD_FILL_RATIO
    assert card.title == "High Forward-Fill Ratio"
    assert card.severity == "WARN"
    # Check that why includes measured and threshold formatted deterministically
    assert "Forward-fill ratio 75.0% exceeds warning threshold 50%" in card.why
    assert card.impact == "Data2 contains gaps; model inputs may be biased by forward-filled values"
    assert card.recommended_action == "Inspect data_alignment_report.json and consider adjusting Data2 source/coverage or excluding affected windows"
    assert card.evidence_artifact == ARTIFACT_NAME
    assert card.evidence_path == "$.forward_fill_ratio"
    assert card.action_target == "/tmp/test/data_alignment_report.json"


def test_dropped_rows_non_zero_returns_card():
    """OK status with dropped_rows > 0 → includes DROPPED_ROWS card."""
    status = DataAlignmentStatus(
        status="OK",
        artifact_relpath=ARTIFACT_NAME,
        artifact_abspath="/tmp/test/data_alignment_report.json",
        message="data_alignment_report.json is available",
        metrics={
            "forward_fill_ratio": 0.1,  # below threshold
            "dropped_rows": 5,
            "forward_filled_rows": 2,
        },
    )
    
    cards = build_data_alignment_reason_cards(
        job_id="test-job",
        status=status,
        warn_forward_fill_ratio=0.5,
    )
    
    assert len(cards) == 1
    card = cards[0]
    assert card.code == DATA_ALIGNMENT_DROPPED_ROWS
    assert card.title == "Dropped Rows in Alignment"
    assert card.severity == "WARN"
    assert card.why == "Dropped 5 row(s) during alignment"
    assert card.impact == "Some input rows could not be aligned; sample size reduced"
    assert card.recommended_action == "Inspect data_alignment_report.json and consider adjusting Data1/Data2 coverage or timeframe"
    assert card.evidence_artifact == ARTIFACT_NAME
    assert card.evidence_path == "$.dropped_rows"
    assert card.action_target == "/tmp/test/data_alignment_report.json"


def test_multiple_conditions_returns_multiple_cards():
    """OK status with both high ratio and dropped rows → returns both cards in deterministic order."""
    status = DataAlignmentStatus(
        status="OK",
        artifact_relpath=ARTIFACT_NAME,
        artifact_abspath="/tmp/test/data_alignment_report.json",
        message="data_alignment_report.json is available",
        metrics={
            "forward_fill_ratio": 0.75,
            "dropped_rows": 3,
            "forward_filled_rows": 10,
        },
    )
    
    cards = build_data_alignment_reason_cards(
        job_id="test-job",
        status=status,
        warn_forward_fill_ratio=0.5,
    )
    
    # Should have 2 cards: HIGH_FORWARD_FILL_RATIO first, then DROPPED_ROWS
    assert len(cards) == 2
    assert cards[0].code == DATA_ALIGNMENT_HIGH_FORWARD_FILL_RATIO
    assert cards[1].code == DATA_ALIGNMENT_DROPPED_ROWS


def test_no_warnings_returns_empty_list():
    """OK status with ratio <= threshold and dropped_rows == 0 → returns empty list."""
    status = DataAlignmentStatus(
        status="OK",
        artifact_relpath=ARTIFACT_NAME,
        artifact_abspath="/tmp/test/data_alignment_report.json",
        message="data_alignment_report.json is available",
        metrics={
            "forward_fill_ratio": 0.3,  # below threshold
            "dropped_rows": 0,
            "forward_filled_rows": 5,
        },
    )
    
    cards = build_data_alignment_reason_cards(
        job_id="test-job",
        status=status,
        warn_forward_fill_ratio=0.5,
    )
    
    assert len(cards) == 0


def test_missing_artifact_skips_other_checks():
    """MISSING status should return only missing card, not check ratio/dropped."""
    status = DataAlignmentStatus(
        status="MISSING",
        artifact_relpath=ARTIFACT_NAME,
        artifact_abspath="/tmp/test/data_alignment_report.json",
        message="data_alignment_report.json not produced by BUILD_DATA",
        metrics={
            "forward_fill_ratio": 0.99,  # would trigger if OK
            "dropped_rows": 99,
        },
    )
    
    cards = build_data_alignment_reason_cards(
        job_id="test-job",
        status=status,
        warn_forward_fill_ratio=0.5,
    )
    
    assert len(cards) == 1
    assert cards[0].code == DATA_ALIGNMENT_MISSING


def test_threshold_formatting():
    """Verify threshold formatting in why message."""
    status = DataAlignmentStatus(
        status="OK",
        artifact_relpath=ARTIFACT_NAME,
        artifact_abspath="/tmp/test/data_alignment_report.json",
        message="data_alignment_report.json is available",
        metrics={
            "forward_fill_ratio": 0.67,
            "dropped_rows": 0,
            "forward_filled_rows": 0,
        },
    )
    
    cards = build_data_alignment_reason_cards(
        job_id="test-job",
        status=status,
        warn_forward_fill_ratio=0.6,  # 60% threshold
    )
    
    assert len(cards) == 1
    card = cards[0]
    # Should format as percentages without decimal places for threshold
    assert "Forward-fill ratio 67.0% exceeds warning threshold 60%" in card.why