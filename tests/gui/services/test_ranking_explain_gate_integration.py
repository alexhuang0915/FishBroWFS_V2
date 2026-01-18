"""
Unit tests for ranking explain gate integration in consolidated gate summary.

Tests the integration of ranking explain gates into the consolidated gate summary service,
including mapping policy, section builder, and job-specific gate inclusion.
"""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone
from pathlib import Path

from gui.services.consolidated_gate_summary_service import (
    ConsolidatedGateSummaryService,
    get_consolidated_gate_summary_service,
)
from contracts.portfolio.gate_summary_schemas import GateSummaryV1, GateItemV1, GateStatus
from contracts.ranking_explain import (
    RankingExplainReport,
    RankingExplainReasonCard,
    RankingExplainReasonCode,
    RankingExplainSeverity,
    RankingExplainContext,
)
from contracts.ranking_explain_gate_policy import (
    DEFAULT_RANKING_EXPLAIN_GATE_MAP,
    GateImpact,
    ranking_explain_gate_impact,
    get_gate_status_from_impact,
)


class TestRankingExplainGateIntegration:
    """Test ranking explain gate integration in consolidated gate summary."""
    
    def test_default_mapping_completeness(self):
        """Verify default mapping covers all required reason codes."""
        # All reason codes from Phase III requirements should be mapped
        required_codes = [
            RankingExplainReasonCode.CONCENTRATION_HIGH,
            RankingExplainReasonCode.CONCENTRATION_MODERATE,
            RankingExplainReasonCode.MDD_INVALID_OR_ZERO,
            RankingExplainReasonCode.METRICS_MISSING_REQUIRED_FIELDS,
            RankingExplainReasonCode.PLATEAU_WEAK_STABILITY,
            RankingExplainReasonCode.PLATEAU_MISSING_ARTIFACT,
            RankingExplainReasonCode.TRADES_TOO_LOW_FOR_RANKING,
            RankingExplainReasonCode.AVG_PROFIT_BELOW_MIN,
        ]
        
        for code in required_codes:
            assert code in DEFAULT_RANKING_EXPLAIN_GATE_MAP, f"Missing mapping for {code}"
    
    def test_mapping_policy_block_codes(self):
        """Verify BLOCK impact mapping."""
        block_codes = [
            RankingExplainReasonCode.CONCENTRATION_HIGH,
            RankingExplainReasonCode.MDD_INVALID_OR_ZERO,
            RankingExplainReasonCode.METRICS_MISSING_REQUIRED_FIELDS,
        ]
        
        for code in block_codes:
            impact = ranking_explain_gate_impact(code)
            assert impact == GateImpact.BLOCK, f"Expected BLOCK for {code}, got {impact}"
    
    def test_mapping_policy_warn_only_codes(self):
        """Verify WARN_ONLY impact mapping."""
        warn_codes = [
            RankingExplainReasonCode.CONCENTRATION_MODERATE,
            RankingExplainReasonCode.PLATEAU_WEAK_STABILITY,
            RankingExplainReasonCode.PLATEAU_MISSING_ARTIFACT,
            RankingExplainReasonCode.TRADES_TOO_LOW_FOR_RANKING,
            RankingExplainReasonCode.AVG_PROFIT_BELOW_MIN,
        ]
        
        for code in warn_codes:
            impact = ranking_explain_gate_impact(code)
            assert impact == GateImpact.WARN_ONLY, f"Expected WARN_ONLY for {code}, got {impact}"
    
    def test_gate_status_from_impact(self):
        """Test gate status determination from impact."""
        # BLOCK → FAIL
        assert get_gate_status_from_impact(GateImpact.BLOCK) == "FAIL"
        
        # WARN_ONLY → WARN
        assert get_gate_status_from_impact(GateImpact.WARN_ONLY) == "WARN"
        
        # NONE → PASS
        assert get_gate_status_from_impact(GateImpact.NONE) == "PASS"
    
    @patch('control.explain_service._get_ranking_explain')
    def test_build_ranking_explain_gate_section_success(self, mock_get_ranking_explain):
        """Test building ranking explain gate section with valid artifact."""
        # Mock ranking explain data
        mock_get_ranking_explain.return_value = {
            "available": True,
            "artifact": {
                "reasons": [
                    {
                        "code": "CONCENTRATION_MODERATE",
                        "severity": "WARN",
                        "title": "Moderate concentration risk",
                        "summary": "Top 3 items account for 45% of total score",
                        "actions": ["review score distribution"],
                        "details": {"top1_share": 0.45, "threshold": 0.4}
                    }
                ]
            },
            "message": "Ranking explain report available"
        }
        
        service = ConsolidatedGateSummaryService()
        gate = service.build_ranking_explain_gate_section("test_job")
        
        assert gate is not None
        assert gate.gate_id == "ranking_explain"
        assert gate.gate_name == "Ranking Explain"
        assert gate.status == GateStatus.WARN  # CONCENTRATION_MODERATE → WARN_ONLY → WARN
        assert "ranking explain" in gate.message.lower()
        assert len(gate.reason_codes) == 1
        assert gate.reason_codes[0] == "CONCENTRATION_MODERATE"
        assert len(gate.evidence_refs) == 1
        assert "ranking_explain_report.json" in gate.evidence_refs[0]
    
    @patch('control.explain_service._get_ranking_explain')
    def test_build_ranking_explain_gate_section_missing_artifact(self, mock_get_ranking_explain):
        """Test building ranking explain gate section when artifact is missing."""
        mock_get_ranking_explain.return_value = {
            "available": False,
            "message": "Ranking explain report not found"
        }
        
        service = ConsolidatedGateSummaryService()
        gate = service.build_ranking_explain_gate_section("test_job")
        
        assert gate is not None
        assert gate.gate_id == "ranking_explain_missing"
        assert gate.gate_name == "Ranking Explain"
        assert gate.status == GateStatus.WARN  # Missing artifact → WARN (Option A policy)
        assert "missing" in gate.message.lower() or "not found" in gate.message.lower()
        assert len(gate.reason_codes) == 1
        assert gate.reason_codes[0] == "RANKING_EXPLAIN_REPORT_MISSING"
    
    @patch('control.explain_service._get_ranking_explain')
    def test_build_ranking_explain_gate_section_block_reason(self, mock_get_ranking_explain):
        """Test building ranking explain gate section with BLOCK reason."""
        mock_get_ranking_explain.return_value = {
            "available": True,
            "artifact": {
                "reasons": [
                    {
                        "code": "MDD_INVALID_OR_ZERO",
                        "severity": "ERROR",
                        "title": "Invalid or zero max drawdown",
                        "summary": "MDD value 0.0 ≤ 0.001, may cause division illusions",
                        "actions": ["review drawdown calculation"],
                        "details": {"mdd": 0.0, "threshold": 0.001}
                    }
                ]
            },
            "message": "Ranking explain report available"
        }
        
        service = ConsolidatedGateSummaryService()
        gate = service.build_ranking_explain_gate_section("test_job")
        
        assert gate is not None
        assert gate.status == GateStatus.REJECT  # MDD_INVALID_OR_ZERO → BLOCK → REJECT
        assert "block" in gate.message.lower() or "redline" in gate.message.lower()
    
    @patch('control.explain_service._get_ranking_explain')
    def test_build_ranking_explain_gate_section_multiple_reasons(self, mock_get_ranking_explain):
        """Test building ranking explain gate section with multiple reason cards."""
        mock_get_ranking_explain.return_value = {
            "available": True,
            "artifact": {
                "reasons": [
                    {
                        "code": "TRADES_TOO_LOW_FOR_RANKING",
                        "severity": "WARN",
                        "title": "Trade count too low for reliable ranking",
                        "summary": "Only 5 trades < minimum 10 for statistical significance",
                        "actions": ["inspect trade count distribution"],
                        "details": {"trades": 5, "threshold": 10}
                    },
                    {
                        "code": "CONCENTRATION_MODERATE",
                        "severity": "WARN",
                        "title": "Moderate concentration risk",
                        "summary": "Top 3 items account for 45% of total score",
                        "actions": ["review score distribution"],
                        "details": {"top1_share": 0.45, "threshold": 0.4}
                    }
                ]
            },
            "message": "Ranking explain report available"
        }
        
        service = ConsolidatedGateSummaryService()
        gate = service.build_ranking_explain_gate_section("test_job")
        
        assert gate is not None
        assert gate.status == GateStatus.WARN  # Both are WARN_ONLY
        assert len(gate.reason_codes) == 2
        assert "TRADES_TOO_LOW_FOR_RANKING" in gate.reason_codes
        assert "CONCENTRATION_MODERATE" in gate.reason_codes
    
    @patch('control.explain_service._get_ranking_explain')
    def test_ranking_explain_gate_evidence_refs(self, mock_get_ranking_explain):
        """Test ranking explain gate includes correct evidence references."""
        mock_get_ranking_explain.return_value = {
            "available": True,
            "artifact": {
                "reasons": [
                    {
                        "code": "CONCENTRATION_MODERATE",
                        "severity": "WARN",
                        "title": "Moderate concentration risk",
                        "summary": "Top 3 items account for 45% of total score",
                        "actions": ["review score distribution"],
                        "details": {"top1_share": 0.45, "threshold": 0.4}
                    }
                ]
            },
            "message": "Ranking explain report available"
        }
        
        service = ConsolidatedGateSummaryService()
        gate = service.build_ranking_explain_gate_section("test_job")
        
        assert len(gate.evidence_refs) == 1
        evidence_ref = gate.evidence_refs[0]
        assert "ranking_explain_report.json" in evidence_ref
        assert "test_job" in evidence_ref
    
    @patch('control.explain_service._get_ranking_explain')
    def test_ranking_explain_gate_no_recompute(self, mock_get_ranking_explain):
        """Test ranking explain gate does NOT import ranking_explain_builder (no recompute)."""
        # This test ensures we're not violating the "no recompute" constraint
        mock_get_ranking_explain.return_value = {
            "available": False,
            "message": "Ranking explain report not found"
        }
        
        service = ConsolidatedGateSummaryService()
        
        # The method should only read the artifact, not recompute
        gate = service.build_ranking_explain_gate_section("test_job")
        
        assert gate is not None
        
        # Verify ranking_explain_builder is not in the service's imports
        import sys
        service_module = sys.modules['gui.services.consolidated_gate_summary_service']
        service_source = service_module.__file__
        
        # Read the source file to check for imports
        with open(service_source, 'r', encoding='utf-8') as f:
            source_content = f.read()
            
        # Should not import ranking_explain_builder
        # Check for actual import statements (not comments)
        lines = source_content.split('\n')
        has_ranking_explain_builder_import = False
        for line in lines:
            # Skip comments and empty lines
            stripped = line.strip()
            if stripped.startswith('#') or not stripped:
                continue
            # Check for import statements
            if ('from gui.services.ranking_explain_builder' in line or
                'import ranking_explain_builder' in line):
                # Make sure it's not in a comment
                if '#' in line:
                    # Check if the import is before the comment
                    comment_index = line.find('#')
                    import_part = line[:comment_index]
                    if ('from gui.services.ranking_explain_builder' in import_part or
                        'import ranking_explain_builder' in import_part):
                        has_ranking_explain_builder_import = True
                        break
                else:
                    has_ranking_explain_builder_import = True
                    break
        
        assert not has_ranking_explain_builder_import, (
            "Found ranking_explain_builder import - violates 'no recompute' constraint"
        )
        
        # Verify we're importing from control.explain_service instead
        assert 'from control.explain_service import _get_ranking_explain' in source_content
    
    def test_fetch_all_gates_with_job_id(self):
        """Test fetch_all_gates includes ranking explain gates when job_id provided."""
        service = ConsolidatedGateSummaryService()
        
        with patch.object(service, 'fetch_system_health_gates') as mock_system:
            with patch.object(service, 'fetch_gatekeeper_gates') as mock_gatekeeper:
                with patch.object(service, 'fetch_portfolio_admission_gates') as mock_admission:
                    with patch.object(service, 'build_ranking_explain_gate_section') as mock_ranking:
                        mock_system.return_value = [
                            GateItemV1(
                                gate_id="api_health",
                                gate_name="API Health",
                                status=GateStatus.PASS,
                                message="Test",
                                evaluator="gate_summary_service",
                            )
                        ]
                        mock_gatekeeper.return_value = []
                        mock_admission.return_value = []
                        mock_ranking.return_value = GateItemV1(
                            gate_id="ranking_explain",
                            gate_name="Ranking Explain",
                            status=GateStatus.WARN,
                            message="Test ranking explain",
                            evaluator="consolidated_gate_summary_service",
                        )
                        
                        # Test with job_id
                        gates_with_job = service.fetch_all_gates(job_id="test_job")
                        assert len(gates_with_job) == 2
                        ranking_gates = [g for g in gates_with_job if g.gate_id == "ranking_explain"]
                        assert len(ranking_gates) == 1
                        
                        # Test without job_id
                        gates_without_job = service.fetch_all_gates()
                        assert len(gates_without_job) == 1
                        ranking_gates = [g for g in gates_without_job if g.gate_id == "ranking_explain"]
                        assert len(ranking_gates) == 0
    
    def test_fetch_consolidated_summary_with_job_id(self):
        """Test fetch_consolidated_summary includes ranking explain gates when job_id provided."""
        service = ConsolidatedGateSummaryService()
        
        with patch.object(service, 'fetch_all_gates') as mock_fetch:
            mock_fetch.return_value = [
                GateItemV1(
                    gate_id="system_api_health",
                    gate_name="API Health",
                    status=GateStatus.PASS,
                    message="API health endpoint responds with status ok.",
                    evaluator="gate_summary_service",
                ),
                GateItemV1(
                    gate_id="ranking_explain",
                    gate_name="Ranking Explain",
                    status=GateStatus.WARN,
                    message="Moderate concentration risk detected",
                    evaluator="consolidated_gate_summary_service",
                ),
            ]
            
            # Test with job_id
            summary = service.fetch_consolidated_summary(job_id="test_job")
            
            assert isinstance(summary, GateSummaryV1)
            assert summary.total_gates == 2
            assert summary.counts["pass"] == 1
            assert summary.counts["warn"] == 1
            assert summary.overall_status == GateStatus.WARN  # Because there's a WARN


if __name__ == "__main__":
    pytest.main([__file__, "-v"])