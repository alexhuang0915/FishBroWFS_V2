"""
Test ranking explain contracts.

Ensure:
1. Pydantic models validate correctly
2. INFO severity enforcement for Phase I
3. Context-aware wording mapping
4. Reason card ordering
"""

import json
import pytest
from datetime import datetime
from pathlib import Path

from contracts.ranking_explain import (
    RankingExplainContext,
    RankingExplainSeverity,
    RankingExplainReasonCode,
    RankingExplainReasonCard,
    RankingExplainReport,
    get_context_wording,
    get_research_actions,
)


def test_ranking_explain_context_enum():
    """Test RankingExplainContext enum values."""
    assert RankingExplainContext.CANDIDATE.value == "CANDIDATE"
    assert RankingExplainContext.FINAL_SELECTION.value == "FINAL_SELECTION"
    
    # Test string representation (enum str returns full name)
    assert "CANDIDATE" in str(RankingExplainContext.CANDIDATE)
    assert "FINAL_SELECTION" in str(RankingExplainContext.FINAL_SELECTION)


def test_ranking_explain_severity_enum():
    """Test RankingExplainSeverity enum values."""
    assert RankingExplainSeverity.INFO.value == "INFO"
    assert RankingExplainSeverity.WARN.value == "WARN"
    assert RankingExplainSeverity.ERROR.value == "ERROR"
    
    # Phase II supports INFO, WARN, ERROR
    assert len(list(RankingExplainSeverity)) == 3


def test_ranking_explain_reason_code_enum():
    """Test RankingExplainReasonCode enum values."""
    # Test Phase I codes
    assert RankingExplainReasonCode.SCORE_FORMULA.value == "SCORE_FORMULA"
    assert RankingExplainReasonCode.THRESHOLD_TMAX_APPLIED.value == "THRESHOLD_TMAX_APPLIED"
    assert RankingExplainReasonCode.THRESHOLD_MIN_AVG_PROFIT_APPLIED.value == "THRESHOLD_MIN_AVG_PROFIT_APPLIED"
    assert RankingExplainReasonCode.METRIC_SUMMARY.value == "METRIC_SUMMARY"
    assert RankingExplainReasonCode.PLATEAU_CONFIRMED.value == "PLATEAU_CONFIRMED"
    assert RankingExplainReasonCode.DATA_MISSING_PLATEAU_ARTIFACT.value == "DATA_MISSING_PLATEAU_ARTIFACT"
    
    # Test Phase II codes
    assert RankingExplainReasonCode.CONCENTRATION_HIGH.value == "CONCENTRATION_HIGH"
    assert RankingExplainReasonCode.CONCENTRATION_MODERATE.value == "CONCENTRATION_MODERATE"
    assert RankingExplainReasonCode.CONCENTRATION_OK.value == "CONCENTRATION_OK"
    assert RankingExplainReasonCode.PLATEAU_STRONG_STABILITY.value == "PLATEAU_STRONG_STABILITY"
    assert RankingExplainReasonCode.PLATEAU_WEAK_STABILITY.value == "PLATEAU_WEAK_STABILITY"
    assert RankingExplainReasonCode.PLATEAU_MISSING_ARTIFACT.value == "PLATEAU_MISSING_ARTIFACT"
    assert RankingExplainReasonCode.AVG_PROFIT_BELOW_MIN.value == "AVG_PROFIT_BELOW_MIN"
    assert RankingExplainReasonCode.MDD_INVALID_OR_ZERO.value == "MDD_INVALID_OR_ZERO"
    assert RankingExplainReasonCode.TRADES_TOO_LOW_FOR_RANKING.value == "TRADES_TOO_LOW_FOR_RANKING"
    assert RankingExplainReasonCode.METRICS_MISSING_REQUIRED_FIELDS.value == "METRICS_MISSING_REQUIRED_FIELDS"
    
    # Test that all codes are accessible
    for code in RankingExplainReasonCode:
        assert isinstance(code.value, str)


def test_ranking_explain_reason_card_validation():
    """Test RankingExplainReasonCard validation."""
    # Valid reason card
    card = RankingExplainReasonCard(
        code=RankingExplainReasonCode.SCORE_FORMULA,
        title="Score formula explanation",
        summary="Net/MDD ratio with trade count bonus",
        actions=["inspect scoring breakdown", "validate formula parameters"],
        details={"formula": "Net/MDD * Trades^0.25"}
    )
    
    assert card.code == RankingExplainReasonCode.SCORE_FORMULA
    assert card.severity == RankingExplainSeverity.INFO  # Default should be INFO
    assert card.title == "Score formula explanation"
    assert len(card.actions) == 2
    assert "inspect" in card.actions[0]
    
    # Test that severity defaults to INFO
    assert card.severity == RankingExplainSeverity.INFO
    
    # Test that WARN severity is allowed (Phase II)
    warn_card = RankingExplainReasonCard(
        code=RankingExplainReasonCode.SCORE_FORMULA,
        title="Test",
        summary="Test",
        severity="WARN",
        actions=[],
        details={}
    )
    assert warn_card.severity == RankingExplainSeverity.WARN
    
    # Test that ERROR severity is allowed (Phase II)
    error_card = RankingExplainReasonCard(
        code=RankingExplainReasonCode.SCORE_FORMULA,
        title="Test",
        summary="Test",
        severity="ERROR",
        actions=[],
        details={}
    )
    assert error_card.severity == RankingExplainSeverity.ERROR
    
    # Test that actions must use research-oriented verbs
    with pytest.raises(ValueError, match="Action must start with"):
        RankingExplainReasonCard(
            code=RankingExplainReasonCode.SCORE_FORMULA,
            title="Test",
            summary="Test",
            actions=["execute trade", "buy stock"],  # Invalid actions
            details={}
        )


def test_ranking_explain_report_validation():
    """Test RankingExplainReport validation."""
    # Create a valid reason card
    reason_card = RankingExplainReasonCard(
        code=RankingExplainReasonCode.SCORE_FORMULA,
        title="Test",
        summary="Test",
        actions=["inspect test"],
        details={"formula": "test"}
    )
    
    # Valid report
    report = RankingExplainReport(
        context=RankingExplainContext.CANDIDATE,
        job_id="test_job_123",
        scoring={"formula": "Net/MDD * Trades^0.25", "t_max": 100, "alpha": 0.25},
        reasons=[reason_card]
    )
    
    assert report.context == RankingExplainContext.CANDIDATE
    assert report.job_id == "test_job_123"
    assert report.schema_version == "1"
    assert report.scoring["formula"] == "Net/MDD * Trades^0.25"
    assert len(report.reasons) == 1
    assert report.reasons[0].code == RankingExplainReasonCode.SCORE_FORMULA
    
    # Test that scoring must contain formula field
    with pytest.raises(ValueError, match="Scoring dict must contain 'formula' field"):
        RankingExplainReport(
            context=RankingExplainContext.CANDIDATE,
            job_id="test_job_123",
            scoring={},  # Missing formula
            reasons=[]
        )
    
    # Test that reasons are sorted by code
    reason_card1 = RankingExplainReasonCard(
        code=RankingExplainReasonCode.METRIC_SUMMARY,
        title="Metric summary",
        summary="Test",
        actions=["inspect test"],
        details={}
    )
    
    reason_card2 = RankingExplainReasonCard(
        code=RankingExplainReasonCode.SCORE_FORMULA,
        title="Score formula",
        summary="Test",
        actions=["inspect test"],
        details={}
    )
    
    # Create report with unsorted reasons
    report = RankingExplainReport(
        context=RankingExplainContext.CANDIDATE,
        job_id="test_job_123",
        scoring={"formula": "test"},
        reasons=[reason_card1, reason_card2]  # METRIC_SUMMARY comes before SCORE_FORMULA alphabetically
    )
    
    # After validation, reasons should be sorted by code (alphabetically)
    # METRIC_SUMMARY (M) comes before SCORE_FORMULA (S) alphabetically
    assert report.reasons[0].code == RankingExplainReasonCode.METRIC_SUMMARY
    assert report.reasons[1].code == RankingExplainReasonCode.SCORE_FORMULA


def test_get_context_wording():
    """Test get_context_wording function."""
    # Test with CANDIDATE context
    title, summary = get_context_wording(
        context=RankingExplainContext.CANDIDATE,
        code=RankingExplainReasonCode.SCORE_FORMULA,
        metric_values={"formula": "Net/MDD * Trades^0.25"}
    )
    
    assert "候選" in title  # Chinese annotation for CANDIDATE
    assert "Score formula applied" in title
    assert "Net/MDD" in summary
    
    # Test with FINAL_SELECTION context
    title, summary = get_context_wording(
        context=RankingExplainContext.FINAL_SELECTION,
        code=RankingExplainReasonCode.SCORE_FORMULA,
        metric_values={"formula": "Net/MDD * Trades^0.25"}
    )
    
    assert "勝出" in title  # Chinese annotation for FINAL_SELECTION
    assert "Score formula applied" in title
    
    # Test with metric values for templating
    title, summary = get_context_wording(
        context=RankingExplainContext.CANDIDATE,
        code=RankingExplainReasonCode.METRIC_SUMMARY,
        metric_values={
            "net_profit": 12345.67,
            "max_dd": 2345.67,
            "trades": 100
        }
    )
    
    assert "$12345.67" in summary
    assert "2345.67" in summary
    assert "100" in summary
    
    # Test with unknown code (should use fallback)
    # Use a string that's not in the enum to test fallback
    class FakeCode:
        value = "FAKE_CODE"
    
    fake_code = FakeCode()
    title, summary = get_context_wording(
        context=RankingExplainContext.CANDIDATE,
        code=fake_code,  # Not in enum
        metric_values={}
    )
    
    assert "候選" in title
    assert "Fake Code" in title or "FAKE_CODE" in title


def test_get_research_actions():
    """Test get_research_actions function."""
    # Test actions for SCORE_FORMULA
    actions = get_research_actions(RankingExplainReasonCode.SCORE_FORMULA)
    assert isinstance(actions, list)
    assert len(actions) == 2
    assert all(isinstance(action, str) for action in actions)
    assert "inspect" in actions[0]
    assert "validate" in actions[1]
    
    # Test actions for PLATEAU_CONFIRMED
    actions = get_research_actions(RankingExplainReasonCode.PLATEAU_CONFIRMED)
    assert len(actions) == 2
    assert "inspect plateau report" in actions[0]
    
    # Test actions for unknown code (should return default)
    # Use a string that's not in the enum to test fallback
    class FakeCode:
        value = "FAKE_CODE"
    
    fake_code = FakeCode()
    actions = get_research_actions(fake_code)
    assert len(actions) == 1
    assert "review relevant artifacts" in actions[0]


def test_report_json_serialization():
    """Test that report can be serialized to JSON."""
    reason_card = RankingExplainReasonCard(
        code=RankingExplainReasonCode.SCORE_FORMULA,
        title="Test title",
        summary="Test summary",
        actions=["inspect test"],
        details={"formula": "Net/MDD * Trades^0.25"}
    )
    
    report = RankingExplainReport(
        context=RankingExplainContext.CANDIDATE,
        job_id="test_job_123",
        scoring={"formula": "Net/MDD * Trades^0.25", "t_max": 100},
        reasons=[reason_card]
    )
    
    # Convert to dict
    report_dict = report.model_dump()
    
    # Convert to JSON
    report_json = json.dumps(report_dict, indent=2)
    
    # Parse back
    parsed_dict = json.loads(report_json)
    
    assert parsed_dict["schema_version"] == "1"
    assert parsed_dict["context"] == "CANDIDATE"
    assert parsed_dict["job_id"] == "test_job_123"
    assert parsed_dict["scoring"]["formula"] == "Net/MDD * Trades^0.25"
    assert len(parsed_dict["reasons"]) == 1
    assert parsed_dict["reasons"][0]["code"] == "SCORE_FORMULA"
    assert parsed_dict["reasons"][0]["severity"] == "INFO"


def test_phase_ii_severity_support():
    """Test that Phase II supports INFO, WARN, and ERROR severity."""
    # Test that all reason cards can have different severities
    test_codes = [
        RankingExplainReasonCode.SCORE_FORMULA,
        RankingExplainReasonCode.CONCENTRATION_HIGH,
        RankingExplainReasonCode.PLATEAU_WEAK_STABILITY,
        RankingExplainReasonCode.MDD_INVALID_OR_ZERO,
    ]
    
    for code in test_codes:
        # Test INFO severity
        info_card = RankingExplainReasonCard(
            code=code,
            title=f"Test {code.value}",
            summary="Test summary",
            severity=RankingExplainSeverity.INFO,
            actions=["inspect test"],
            details={}
        )
        assert info_card.severity == RankingExplainSeverity.INFO
        
        # Test WARN severity
        warn_card = RankingExplainReasonCard(
            code=code,
            title=f"Test {code.value}",
            summary="Test summary",
            severity=RankingExplainSeverity.WARN,
            actions=["inspect test"],
            details={}
        )
        assert warn_card.severity == RankingExplainSeverity.WARN
        
        # Test ERROR severity
        error_card = RankingExplainReasonCard(
            code=code,
            title=f"Test {code.value}",
            summary="Test summary",
            severity=RankingExplainSeverity.ERROR,
            actions=["inspect test"],
            details={}
        )
        assert error_card.severity == RankingExplainSeverity.ERROR


def test_reason_card_ordering_in_report():
    """Test that reason cards maintain deterministic ordering in report."""
    # Create reason cards in arbitrary order
    cards = [
        RankingExplainReasonCard(
            code=RankingExplainReasonCode.METRIC_SUMMARY,
            title="Metric summary",
            summary="Test",
            actions=["inspect test"],
            details={}
        ),
        RankingExplainReasonCard(
            code=RankingExplainReasonCode.SCORE_FORMULA,
            title="Score formula",
            summary="Test",
            actions=["inspect test"],
            details={}
        ),
        RankingExplainReasonCard(
            code=RankingExplainReasonCode.THRESHOLD_TMAX_APPLIED,
            title="T-max threshold",
            summary="Test",
            actions=["inspect test"],
            details={}
        )
    ]
    
    # Create report with unsorted cards
    report = RankingExplainReport(
        context=RankingExplainContext.CANDIDATE,
        job_id="test_job_123",
        scoring={"formula": "test"},
        reasons=cards
    )
    
    # After validation, reasons should be sorted by code
    assert len(report.reasons) == 3
    # Sorted order should be: SCORE_FORMULA (S), THRESHOLD_TMAX_APPLIED (T), METRIC_SUMMARY (M)
    # Actually alphabetical: METRIC_SUMMARY (M), SCORE_FORMULA (S), THRESHOLD_TMAX_APPLIED (T)
    # Wait, let me check: M comes before S comes before T
    # So order should be: METRIC_SUMMARY, SCORE_FORMULA, THRESHOLD_TMAX_APPLIED
    
    codes = [card.code for card in report.reasons]
    assert codes == [
        RankingExplainReasonCode.METRIC_SUMMARY,
        RankingExplainReasonCode.SCORE_FORMULA,
        RankingExplainReasonCode.THRESHOLD_TMAX_APPLIED
    ]


def test_context_wording_chinese_annotations():
    """Test that Chinese annotations are correctly applied based on context."""
    # CANDIDATE context should have "候選"
    title_candidate, _ = get_context_wording(
        context=RankingExplainContext.CANDIDATE,
        code=RankingExplainReasonCode.SCORE_FORMULA,
        metric_values={}
    )
    assert "候選" in title_candidate
    assert "勝出" not in title_candidate
    
    # FINAL_SELECTION context should have "勝出"
    title_final, _ = get_context_wording(
        context=RankingExplainContext.FINAL_SELECTION,
        code=RankingExplainReasonCode.SCORE_FORMULA,
        metric_values={}
    )
    assert "勝出" in title_final
    assert "候選" not in title_final


def test_research_actions_verbs():
    """Test that research actions use only allowed verbs."""
    # Test all reason codes
    for code in RankingExplainReasonCode:
        actions = get_research_actions(code)
        
        # All actions should start with allowed verbs
        allowed_prefixes = ("inspect", "validate", "review")
        for action in actions:
            action_lower = action.strip().lower()
            assert any(action_lower.startswith(prefix) for prefix in allowed_prefixes), \
                f"Action '{action}' for code {code} doesn't start with allowed verb"


def test_report_generated_at_timestamp():
    """Test that report includes proper UTC timestamp."""
    report = RankingExplainReport(
        context=RankingExplainContext.CANDIDATE,
        job_id="test_job_123",
        scoring={"formula": "test"},
        reasons=[]
    )
    
    # Generated_at should be ISO 8601 with Z suffix
    assert report.generated_at.endswith("Z")
    
    # Should be parseable as datetime
    try:
        datetime.fromisoformat(report.generated_at.replace("Z", "+00:00"))
    except ValueError:
        pytest.fail(f"Invalid ISO 8601 timestamp: {report.generated_at}")