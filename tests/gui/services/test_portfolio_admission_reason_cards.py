"""
Unit tests for Portfolio Admission Reason Cards builder.
"""

import pytest

from gui.services.portfolio_admission_status import (
    AdmissionStatus,
    build_portfolio_admission_reason_cards,
    PORTFOLIO_MISSING_ARTIFACT,
    PORTFOLIO_CORRELATION_TOO_HIGH,
    PORTFOLIO_MDD_EXCEEDED,
    PORTFOLIO_INSUFFICIENT_HISTORY,
    ADMISSION_DECISION_FILE,
    DEFAULT_CORRELATION_THRESHOLD,
    DEFAULT_MDD_THRESHOLD,
)


def test_missing_artifact_returns_one_card():
    """MISSING status → returns exactly 1 card with code=PORTFOLIO_MISSING_ARTIFACT."""
    status = AdmissionStatus(
        status="MISSING",
        artifact_relpath=ADMISSION_DECISION_FILE,
        artifact_abspath="/tmp/test/admission_decision.json",
        message="Portfolio admission decision artifact not found",
        metrics={},
    )
    
    cards = build_portfolio_admission_reason_cards(
        job_id="test-job",
        status=status,
        correlation_threshold=DEFAULT_CORRELATION_THRESHOLD,
        mdd_threshold=DEFAULT_MDD_THRESHOLD,
    )
    
    assert len(cards) == 1
    card = cards[0]
    assert card.code == PORTFOLIO_MISSING_ARTIFACT
    assert card.title == "Portfolio Admission Artifact Missing"
    assert card.severity == "WARN"
    assert card.why == "admission_decision.json not produced by BUILD_PORTFOLIO"
    assert card.impact == "Portfolio admission cannot be audited; downstream allocation may be risky"
    assert card.recommended_action == "Re-run BUILD_PORTFOLIO for this job or inspect runner logs"
    assert card.evidence_artifact == ADMISSION_DECISION_FILE
    assert card.evidence_path == "$"
    assert card.action_target == "/tmp/test/admission_decision.json"


def test_correlation_violations_returns_card():
    """Metrics with correlation_violations → includes CORRELATION_TOO_HIGH card."""
    status = AdmissionStatus(
        status="FAIL",
        artifact_relpath=ADMISSION_DECISION_FILE,
        artifact_abspath="/tmp/test/admission_decision.json",
        message="Portfolio admission rejected",
        metrics={
            "verdict": "REJECTED",
            "reasons": {},
            "correlation_violations": [{"pair": "S1/S2", "correlation": 0.85}],
            "risk_budget_steps": [],
        },
    )
    
    cards = build_portfolio_admission_reason_cards(
        job_id="test-job",
        status=status,
        correlation_threshold=DEFAULT_CORRELATION_THRESHOLD,
        mdd_threshold=DEFAULT_MDD_THRESHOLD,
    )
    
    assert len(cards) == 1
    card = cards[0]
    assert card.code == PORTFOLIO_CORRELATION_TOO_HIGH
    assert card.title == "Correlation Too High"
    assert card.severity == "FAIL"
    assert card.why == f"Correlation exceeded threshold {DEFAULT_CORRELATION_THRESHOLD:.2f}"
    assert card.impact == "Portfolio diversification is reduced; drawdowns may amplify"
    assert card.recommended_action == "Remove or replace highly correlated strategies"
    assert card.evidence_artifact == ADMISSION_DECISION_FILE
    assert card.evidence_path == "$.correlation_violations"
    assert card.action_target == "/tmp/test/admission_decision.json"


def test_mdd_exceeded_returns_card():
    """Metrics with risk_budget_steps → includes MDD_EXCEEDED card."""
    status = AdmissionStatus(
        status="WARN",
        artifact_relpath=ADMISSION_DECISION_FILE,
        artifact_abspath="/tmp/test/admission_decision.json",
        message="Portfolio admission warning",
        metrics={
            "verdict": "ADMITTED",
            "reasons": {},
            "correlation_violations": [],
            "risk_budget_steps": [{"step": "mdd_check", "passed": False}],
        },
    )
    
    cards = build_portfolio_admission_reason_cards(
        job_id="test-job",
        status=status,
        correlation_threshold=DEFAULT_CORRELATION_THRESHOLD,
        mdd_threshold=DEFAULT_MDD_THRESHOLD,
    )
    
    assert len(cards) == 1
    card = cards[0]
    assert card.code == PORTFOLIO_MDD_EXCEEDED
    assert card.title == "Maximum Drawdown Exceeded"
    assert card.severity == "WARN"
    assert card.why == f"Maximum drawdown exceeded threshold {DEFAULT_MDD_THRESHOLD:.0%}"
    assert card.impact == "Portfolio risk exceeds budget; potential for large losses"
    assert card.recommended_action == "Reduce position sizes, increase diversification, or adjust risk budget"
    assert card.evidence_artifact == ADMISSION_DECISION_FILE
    assert card.evidence_path == "$.risk_budget_steps"
    assert card.action_target == "/tmp/test/admission_decision.json"


def test_insufficient_history_returns_card():
    """Metrics with insufficient history reason → includes INSUFFICIENT_HISTORY card."""
    status = AdmissionStatus(
        status="WARN",
        artifact_relpath=ADMISSION_DECISION_FILE,
        artifact_abspath="/tmp/test/admission_decision.json",
        message="Portfolio admission warning",
        metrics={
            "verdict": "ADMITTED",
            "reasons": {"history": "insufficient historical data"},
            "correlation_violations": [],
            "risk_budget_steps": [],
        },
    )
    
    cards = build_portfolio_admission_reason_cards(
        job_id="test-job",
        status=status,
        correlation_threshold=DEFAULT_CORRELATION_THRESHOLD,
        mdd_threshold=DEFAULT_MDD_THRESHOLD,
    )
    
    assert len(cards) == 1
    card = cards[0]
    assert card.code == PORTFOLIO_INSUFFICIENT_HISTORY
    assert card.title == "Insufficient History"
    assert card.severity == "WARN"
    assert card.why == "Strategy lacks sufficient historical data for reliable admission"
    assert card.impact == "Admission decision may be based on limited sample; increased uncertainty"
    assert card.recommended_action == "Collect more historical data or adjust admission thresholds"
    assert card.evidence_artifact == ADMISSION_DECISION_FILE
    assert card.evidence_path == "$.reasons"
    assert card.action_target == "/tmp/test/admission_decision.json"


def test_multiple_cards_deterministic_order():
    """Multiple triggers → cards appear in deterministic order."""
    status = AdmissionStatus(
        status="FAIL",
        artifact_relpath=ADMISSION_DECISION_FILE,
        artifact_abspath="/tmp/test/admission_decision.json",
        message="Portfolio admission rejected",
        metrics={
            "verdict": "REJECTED",
            "reasons": {"history": "insufficient"},
            "correlation_violations": [{"pair": "S1/S2", "correlation": 0.9}],
            "risk_budget_steps": [{"step": "mdd_check", "passed": False}],
        },
    )
    
    cards = build_portfolio_admission_reason_cards(
        job_id="test-job",
        status=status,
        correlation_threshold=DEFAULT_CORRELATION_THRESHOLD,
        mdd_threshold=DEFAULT_MDD_THRESHOLD,
    )
    
    # Expect 3 cards: CORRELATION, MDD, HISTORY (MISSING not triggered)
    assert len(cards) == 3
    codes = [c.code for c in cards]
    # Order should be: CORRELATION_TOO_HIGH, MDD_EXCEEDED, INSUFFICIENT_HISTORY
    assert codes[0] == PORTFOLIO_CORRELATION_TOO_HIGH
    assert codes[1] == PORTFOLIO_MDD_EXCEEDED
    assert codes[2] == PORTFOLIO_INSUFFICIENT_HISTORY


def test_no_warnings_returns_empty_list():
    """OK status with no violations → returns empty list."""
    status = AdmissionStatus(
        status="OK",
        artifact_relpath=ADMISSION_DECISION_FILE,
        artifact_abspath="/tmp/test/admission_decision.json",
        message="Portfolio admission passed",
        metrics={
            "verdict": "ADMITTED",
            "reasons": {},
            "correlation_violations": [],
            "risk_budget_steps": [],
        },
    )
    
    cards = build_portfolio_admission_reason_cards(
        job_id="test-job",
        status=status,
        correlation_threshold=DEFAULT_CORRELATION_THRESHOLD,
        mdd_threshold=DEFAULT_MDD_THRESHOLD,
    )
    
    assert len(cards) == 0