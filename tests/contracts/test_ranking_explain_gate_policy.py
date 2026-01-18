"""
Tests for ranking explain gate policy (DP6 Phase III).
"""

import pytest

from src.contracts.ranking_explain_gate_policy import (
    GateImpact,
    DEFAULT_RANKING_EXPLAIN_GATE_MAP,
    ranking_explain_gate_impact,
    get_gate_status_from_impact,
    get_gate_impact_message,
)
from src.contracts.ranking_explain import RankingExplainReasonCode


class TestGateImpactEnum:
    """Test GateImpact enum values."""
    
    def test_enum_values(self):
        """Test GateImpact enum has correct values."""
        assert GateImpact.NONE == "NONE"
        assert GateImpact.WARN_ONLY == "WARN_ONLY"
        assert GateImpact.BLOCK == "BLOCK"
        
        # Ensure all values are present
        values = {e.value for e in GateImpact}
        assert values == {"NONE", "WARN_ONLY", "BLOCK"}


class TestDefaultMapping:
    """Test DEFAULT_RANKING_EXPLAIN_GATE_MAP matches specification."""
    
    def test_mapping_exists(self):
        """Test mapping is defined."""
        assert isinstance(DEFAULT_RANKING_EXPLAIN_GATE_MAP, dict)
        assert len(DEFAULT_RANKING_EXPLAIN_GATE_MAP) > 0
    
    def test_block_codes(self):
        """Test BLOCK codes match specification."""
        block_codes = {
            RankingExplainReasonCode.CONCENTRATION_HIGH,
            RankingExplainReasonCode.MDD_INVALID_OR_ZERO,
            RankingExplainReasonCode.METRICS_MISSING_REQUIRED_FIELDS,
        }
        
        for code in block_codes:
            assert code in DEFAULT_RANKING_EXPLAIN_GATE_MAP
            assert DEFAULT_RANKING_EXPLAIN_GATE_MAP[code] == GateImpact.BLOCK
    
    def test_warn_only_codes(self):
        """Test WARN_ONLY codes match specification."""
        warn_codes = {
            RankingExplainReasonCode.CONCENTRATION_MODERATE,
            RankingExplainReasonCode.PLATEAU_WEAK_STABILITY,
            RankingExplainReasonCode.PLATEAU_MISSING_ARTIFACT,
            RankingExplainReasonCode.TRADES_TOO_LOW_FOR_RANKING,
            RankingExplainReasonCode.AVG_PROFIT_BELOW_MIN,
        }
        
        for code in warn_codes:
            assert code in DEFAULT_RANKING_EXPLAIN_GATE_MAP
            assert DEFAULT_RANKING_EXPLAIN_GATE_MAP[code] == GateImpact.WARN_ONLY
    
    def test_phase1_codes_not_in_mapping(self):
        """Test Phase I INFO-only codes are NOT in mapping (default to NONE)."""
        phase1_codes = {
            RankingExplainReasonCode.SCORE_FORMULA,
            RankingExplainReasonCode.THRESHOLD_TMAX_APPLIED,
            RankingExplainReasonCode.THRESHOLD_MIN_AVG_PROFIT_APPLIED,
            RankingExplainReasonCode.METRIC_SUMMARY,
            RankingExplainReasonCode.PLATEAU_CONFIRMED,
            RankingExplainReasonCode.DATA_MISSING_PLATEAU_ARTIFACT,
        }
        
        for code in phase1_codes:
            # These should NOT be in the mapping (default to NONE)
            assert code not in DEFAULT_RANKING_EXPLAIN_GATE_MAP
    
    def test_other_phase2_codes_not_in_mapping(self):
        """Test other Phase II codes not in mapping default to NONE."""
        other_phase2_codes = {
            RankingExplainReasonCode.CONCENTRATION_OK,
            RankingExplainReasonCode.PLATEAU_STRONG_STABILITY,
        }
        
        for code in other_phase2_codes:
            # These should NOT be in the mapping (default to NONE)
            assert code not in DEFAULT_RANKING_EXPLAIN_GATE_MAP


class TestRankingExplainGateImpact:
    """Test ranking_explain_gate_impact function."""
    
    def test_block_codes(self):
        """Test BLOCK codes return BLOCK impact."""
        block_codes = [
            RankingExplainReasonCode.CONCENTRATION_HIGH,
            RankingExplainReasonCode.MDD_INVALID_OR_ZERO,
            RankingExplainReasonCode.METRICS_MISSING_REQUIRED_FIELDS,
        ]
        
        for code in block_codes:
            impact = ranking_explain_gate_impact(code)
            assert impact == GateImpact.BLOCK
    
    def test_warn_only_codes(self):
        """Test WARN_ONLY codes return WARN_ONLY impact."""
        warn_codes = [
            RankingExplainReasonCode.CONCENTRATION_MODERATE,
            RankingExplainReasonCode.PLATEAU_WEAK_STABILITY,
            RankingExplainReasonCode.PLATEAU_MISSING_ARTIFACT,
            RankingExplainReasonCode.TRADES_TOO_LOW_FOR_RANKING,
            RankingExplainReasonCode.AVG_PROFIT_BELOW_MIN,
        ]
        
        for code in warn_codes:
            impact = ranking_explain_gate_impact(code)
            assert impact == GateImpact.WARN_ONLY
    
    def test_unknown_codes_return_none(self):
        """Test unknown codes return NONE impact."""
        # Test a code not in mapping
        code = RankingExplainReasonCode.SCORE_FORMULA  # Phase I INFO-only
        impact = ranking_explain_gate_impact(code)
        assert impact == GateImpact.NONE
        
        # Test another unmapped code
        code = RankingExplainReasonCode.CONCENTRATION_OK  # Phase II INFO
        impact = ranking_explain_gate_impact(code)
        assert impact == GateImpact.NONE


class TestGetGateStatusFromImpact:
    """Test get_gate_status_from_impact function."""
    
    def test_block_to_fail(self):
        """Test BLOCK impact returns FAIL status."""
        status = get_gate_status_from_impact(GateImpact.BLOCK)
        assert status == "FAIL"
    
    def test_warn_only_to_warn(self):
        """Test WARN_ONLY impact returns WARN status."""
        status = get_gate_status_from_impact(GateImpact.WARN_ONLY)
        assert status == "WARN"
    
    def test_none_to_pass(self):
        """Test NONE impact returns PASS status."""
        status = get_gate_status_from_impact(GateImpact.NONE)
        assert status == "PASS"


class TestGetGateImpactMessage:
    """Test get_gate_impact_message function."""
    
    def test_mapped_codes_have_messages(self):
        """Test mapped codes return specific messages."""
        test_cases = [
            (RankingExplainReasonCode.CONCENTRATION_HIGH, "INFO",
             "High concentration risk (top1_share ≥ 50%)"),
            (RankingExplainReasonCode.CONCENTRATION_MODERATE, "WARN",
             "Moderate concentration risk (top1_share ≥ 35%)"),
            (RankingExplainReasonCode.MDD_INVALID_OR_ZERO, "ERROR",
             "MDD invalid or near zero"),
            (RankingExplainReasonCode.PLATEAU_MISSING_ARTIFACT, "WARN",
             "Plateau artifact missing"),
        ]
        
        for code, severity, expected in test_cases:
            message = get_gate_impact_message(code, severity)
            assert message == expected
    
    def test_unmapped_codes_have_fallback(self):
        """Test unmapped codes return fallback message with severity."""
        code = RankingExplainReasonCode.SCORE_FORMULA
        severity = "INFO"
        message = get_gate_impact_message(code, severity)
        
        # Should contain code and severity
        assert "Score Formula" in message  # Code formatted
        assert "(INFO)" in message  # Severity in parentheses
    
    def test_all_mapped_codes_have_messages(self):
        """Test all codes in DEFAULT_RANKING_EXPLAIN_GATE_MAP have messages."""
        for code in DEFAULT_RANKING_EXPLAIN_GATE_MAP.keys():
            message = get_gate_impact_message(code, "INFO")
            # Message should not be empty or contain error indicators
            assert message
            assert "{" not in message  # No unformatted template strings


if __name__ == "__main__":
    pytest.main([__file__, "-v"])