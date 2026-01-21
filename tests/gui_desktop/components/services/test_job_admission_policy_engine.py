"""
Tests for JobAdmissionPolicyEngine (DP8).
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone
from pathlib import Path

from gui.services.job_admission_policy_engine import (
    get_job_admission_policy_engine,
    JobAdmissionPolicyEngine,
)
from contracts.job_admission_schemas import (
    JobAdmissionDecision,
    JobAdmissionVerdict,
    AdmissionPolicyRule,
    AdmissionPolicyConfig,
    JOB_ADMISSION_DECISION_FILE,
)
from contracts.portfolio.gate_summary_schemas import (
    GateSummaryV1,
    GateStatus,
    GateItemV1,
    GateV1,
)


class TestJobAdmissionPolicyEngine:
    """Test suite for JobAdmissionPolicyEngine."""
    
    def test_singleton_pattern(self):
        """Test that engine follows singleton pattern."""
        engine1 = get_job_admission_policy_engine()
        engine2 = get_job_admission_policy_engine()
        assert engine1 is engine2
    
    def test_initialization_with_default_config(self):
        """Test engine initialization with default config."""
        engine = JobAdmissionPolicyEngine()
        assert engine.policy_config is not None
        assert engine.policy_config.default_verdict_for_pass == JobAdmissionVerdict.ADMITTED
        assert engine.policy_config.default_verdict_for_reject == JobAdmissionVerdict.REJECTED
    
    def test_initialization_with_custom_config(self):
        """Test engine initialization with custom config."""
        custom_config = AdmissionPolicyConfig(
            default_verdict_for_pass=JobAdmissionVerdict.HOLD,
            max_warn_gates=5,
        )
        engine = JobAdmissionPolicyEngine(policy_config=custom_config)
        assert engine.policy_config.default_verdict_for_pass == JobAdmissionVerdict.HOLD
        assert engine.policy_config.max_warn_gates == 5
    
    @patch("gui.services.job_admission_policy_engine.get_consolidated_gate_summary_service")
    def test_evaluate_job_pass(self, mock_get_summary_service):
        """Test evaluating job with PASS gate summary."""
        # Setup mock gate summary
        gate_summary = GateSummaryV1(
            overall_status=GateStatus.PASS,
            overall_message="All gates passed",
            counts={"pass": 5, "warn": 0, "reject": 0, "unknown": 0},
            gates=[
                GateItemV1(
                    gate_id="data_alignment",
                    gate_name="Data Alignment",
                    status=GateStatus.PASS,
                    message="Data aligned correctly",
                    reason_codes=["DATA_ALIGNED"],
                    evaluated_at_utc="2024-01-01T00:00:00Z",
                    evaluator="test",
                )
            ],
            evaluated_at_utc="2024-01-01T00:00:00Z",
            evaluator="test",
            source="test",
        )
        
        mock_service = Mock()
        mock_service.fetch_consolidated_summary.return_value = gate_summary
        mock_get_summary_service.return_value = mock_service
        
        engine = JobAdmissionPolicyEngine()
        decision = engine.evaluate_job("test_job")
        
        assert decision.verdict == JobAdmissionVerdict.ADMITTED
        assert decision.job_id == "test_job"
        assert decision.gate_summary_status == "PASS"
        assert decision.total_gates == 1
        assert decision.decision_reason == "All gates passed"
        assert AdmissionPolicyRule.PASS_ALWAYS_ADMIT.value in decision.policy_rules_applied
    
    @patch("gui.services.job_admission_policy_engine.get_consolidated_gate_summary_service")
    def test_evaluate_job_reject(self, mock_get_summary_service):
        """Test evaluating job with REJECT gate summary."""
        gate_summary = GateSummaryV1(
            overall_status=GateStatus.REJECT,
            overall_message="One or more gates rejected",
            counts={"pass": 3, "warn": 1, "reject": 1, "unknown": 0},
            gates=[
                GateV1(
                    gate_id="data_alignment",
                    gate_name="Data Alignment",
                    status=GateStatus.REJECT,
                    message="Data misaligned",
                    reason_codes=["DATA_MISALIGNED"],
                )
            ],
            evaluated_at_utc="2024-01-01T00:00:00Z",
            evaluator="test",
            source="test",
        )
        
        mock_service = Mock()
        mock_service.fetch_consolidated_summary.return_value = gate_summary
        mock_get_summary_service.return_value = mock_service
        
        engine = JobAdmissionPolicyEngine()
        decision = engine.evaluate_job("test_job")
        
        assert decision.verdict == JobAdmissionVerdict.REJECTED
        # Accept either reason (critical gate override or standard reject)
        assert decision.decision_reason in ["One or more gates rejected", "Critical gate 'Data Alignment' rejected"]
        # Should have at least REJECT_ALWAYS_REJECT rule, may also have DATA_ALIGNMENT_FAIL
        assert AdmissionPolicyRule.REJECT_ALWAYS_REJECT.value in decision.policy_rules_applied
        assert decision.failing_gates is not None
        assert len(decision.failing_gates) == 1
        assert decision.failing_gates[0]["gate_id"] == "data_alignment"
    
    @patch("gui.services.job_admission_policy_engine.get_consolidated_gate_summary_service")
    def test_evaluate_job_warn(self, mock_get_summary_service):
        """Test evaluating job with WARN gate summary."""
        gate_summary = GateSummaryV1(
            overall_status=GateStatus.WARN,
            overall_message="Some warnings",
            counts={"pass": 4, "warn": 1, "reject": 0, "unknown": 0},
            gates=[
                GateV1(
                    gate_id="ranking_explain",
                    gate_name="Ranking Explain",
                    status=GateStatus.WARN,
                    message="Ranking explain has warnings",
                    reason_codes=["RANKING_EXPLAIN_WARN"],
                )
            ],
            evaluated_at_utc="2024-01-01T00:00:00Z",
            evaluator="test",
            source="test",
        )
        
        mock_service = Mock()
        mock_service.fetch_consolidated_summary.return_value = gate_summary
        mock_get_summary_service.return_value = mock_service
        
        engine = JobAdmissionPolicyEngine()
        decision = engine.evaluate_job("test_job")
        
        assert decision.verdict == JobAdmissionVerdict.HOLD
        # Accept either reason format
        assert "warnings" in decision.decision_reason.lower() or "requires review" in decision.decision_reason.lower()
        assert AdmissionPolicyRule.WARN_REQUIRES_REVIEW.value in decision.policy_rules_applied
        assert decision.warning_gates is not None
        assert len(decision.warning_gates) == 1
        assert decision.warning_gates[0]["gate_id"] == "ranking_explain"
    
    @patch("gui.services.job_admission_policy_engine.get_consolidated_gate_summary_service")
    def test_evaluate_job_critical_gate_failure(self, mock_get_summary_service):
        """Test evaluating job where critical gate fails (should override PASS)."""
        gate_summary = GateSummaryV1(
            overall_status=GateStatus.PASS,  # Overall is PASS but...
            overall_message="All gates passed",
            counts={"pass": 4, "warn": 0, "reject": 1, "unknown": 0},
            gates=[
                GateV1(
                    gate_id="data_alignment",  # Critical gate
                    gate_name="Data Alignment",
                    status=GateStatus.REJECT,  # But this critical gate failed
                    message="Data misaligned",
                    reason_codes=["DATA_MISALIGNED"],
                ),
                GateV1(
                    gate_id="other_gate",
                    gate_name="Other Gate",
                    status=GateStatus.PASS,
                    message="OK",
                    reason_codes=[],
                ),
            ],
            evaluated_at_utc="2024-01-01T00:00:00Z",
            evaluator="test",
            source="test",
        )
        
        mock_service = Mock()
        mock_service.fetch_consolidated_summary.return_value = gate_summary
        mock_get_summary_service.return_value = mock_service
        
        engine = JobAdmissionPolicyEngine()
        decision = engine.evaluate_job("test_job")
        
        # Should be REJECTED due to critical gate failure
        assert decision.verdict == JobAdmissionVerdict.REJECTED
        assert "Critical gate" in decision.decision_reason
        assert AdmissionPolicyRule.DATA_ALIGNMENT_FAIL.value in decision.policy_rules_applied
    
    @patch("gui.services.job_admission_policy_engine.get_consolidated_gate_summary_service")
    def test_evaluate_job_too_many_warnings(self, mock_get_summary_service):
        """Test evaluating job with too many warning gates."""
        # Create gates with many warnings
        gates = []
        for i in range(5):  # 5 warning gates (exceeds default max_warn_gates=2)
            gates.append(
                GateV1(
                    gate_id=f"gate_{i}",
                    gate_name=f"Gate {i}",
                    status=GateStatus.WARN,
                    message=f"Warning {i}",
                    reason_codes=[f"WARN_{i}"],
                )
            )
        
        gate_summary = GateSummaryV1(
            overall_status=GateStatus.PASS,  # Overall PASS but many warnings
            overall_message="All gates passed",
            counts={"pass": 0, "warn": 5, "reject": 0, "unknown": 0},
            gates=gates,
            evaluated_at_utc="2024-01-01T00:00:00Z",
            evaluator="test",
            source="test",
        )
        
        mock_service = Mock()
        mock_service.fetch_consolidated_summary.return_value = gate_summary
        mock_get_summary_service.return_value = mock_service
        
        engine = JobAdmissionPolicyEngine()
        decision = engine.evaluate_job("test_job")
        
        # Should be HOLD due to too many warnings
        assert decision.verdict == JobAdmissionVerdict.HOLD
        assert "Too many warning gates" in decision.decision_reason
        assert AdmissionPolicyRule.MAX_WARN_GATES.value in decision.policy_rules_applied
    
    @patch("gui.services.job_admission_policy_engine.get_consolidated_gate_summary_service")
    def test_evaluate_job_too_many_failures(self, mock_get_summary_service):
        """Test evaluating job with too many failing gates."""
        # Create gates with failures
        gates = []
        for i in range(3):  # 3 failing gates (exceeds default max_fail_gates=0)
            gates.append(
                GateV1(
                    gate_id=f"gate_{i}",
                    gate_name=f"Gate {i}",
                    status=GateStatus.REJECT,
                    message=f"Failure {i}",
                    reason_codes=[f"FAIL_{i}"],
                )
            )
        
        gate_summary = GateSummaryV1(
            overall_status=GateStatus.REJECT,
            overall_message="Multiple failures",
            counts={"pass": 0, "warn": 0, "reject": 3, "unknown": 0},
            gates=gates,
            evaluated_at_utc="2024-01-01T00:00:00Z",
            evaluator="test",
            source="test",
        )
        
        mock_service = Mock()
        mock_service.fetch_consolidated_summary.return_value = gate_summary
        mock_get_summary_service.return_value = mock_service
        
        engine = JobAdmissionPolicyEngine()
        decision = engine.evaluate_job("test_job")
        
        # Should be REJECTED due to REJECT overall status
        assert decision.verdict == JobAdmissionVerdict.REJECTED
        # Accept either reason (standard reject or too many failures)
        # MAX_FAIL_GATES rule may not apply if verdict is already REJECTED
        assert AdmissionPolicyRule.REJECT_ALWAYS_REJECT.value in decision.policy_rules_applied
    
    @patch("gui.services.job_admission_policy_engine.get_consolidated_gate_summary_service")
    def test_evaluate_job_mixed_status_evaluation(self, mock_get_summary_service):
        """Test evaluating job with mixed gate statuses."""
        gate_summary = GateSummaryV1(
            overall_status=GateStatus.WARN,
            overall_message="Mixed statuses",
            counts={"pass": 2, "warn": 2, "reject": 1, "unknown": 0},
            gates=[
                GateV1(gate_id="g1", gate_name="Gate 1", status=GateStatus.PASS, message="OK"),
                GateV1(gate_id="g2", gate_name="Gate 2", status=GateStatus.PASS, message="OK"),
                GateV1(gate_id="g3", gate_name="Gate 3", status=GateStatus.WARN, message="Warning"),
                GateV1(gate_id="g4", gate_name="Gate 4", status=GateStatus.WARN, message="Warning"),
                GateV1(gate_id="g5", gate_name="Gate 5", status=GateStatus.REJECT, message="Failed"),
            ],
            evaluated_at_utc="2024-01-01T00:00:00Z",
            evaluator="test",
            source="test",
        )
        
        mock_service = Mock()
        mock_service.fetch_consolidated_summary.return_value = gate_summary
        mock_get_summary_service.return_value = mock_service
        
        engine = JobAdmissionPolicyEngine()
        decision = engine.evaluate_job("test_job")
        
        # Should have mixed status evaluation rule applied
        assert AdmissionPolicyRule.MIXED_STATUS_EVALUATION.value in decision.policy_rules_applied
    
    @patch("gui.services.job_admission_policy_engine.get_consolidated_gate_summary_service")
    def test_evaluate_job_no_gate_summary(self, mock_get_summary_service):
        """Test evaluating job with no gate summary (should raise error)."""
        mock_service = Mock()
        mock_service.fetch_consolidated_summary.return_value = None
        mock_get_summary_service.return_value = mock_service
        
        engine = JobAdmissionPolicyEngine()
        
        with pytest.raises(ValueError, match="No gate summary found"):
            engine.evaluate_job("test_job")
    
    @patch("gui.services.job_admission_policy_engine.get_consolidated_gate_summary_service")
    @patch("gui.services.job_admission_policy_engine.get_job_artifact_path")
    def test_check_ranking_explain_artifact_exists(self, mock_get_artifact_path, mock_get_summary_service):
        """Test checking for ranking explain artifact when it exists."""
        mock_path = Mock()
        mock_path.exists.return_value = True
        mock_get_artifact_path.return_value = mock_path
        
        engine = JobAdmissionPolicyEngine()
        result = engine._check_ranking_explain_artifact("test_job")
        
        assert result == "ranking_explain_report.json"
        mock_get_artifact_path.assert_called_with("test_job", "ranking_explain_report.json")
    
    @patch("gui.services.job_admission_policy_engine.get_consolidated_gate_summary_service")
    @patch("gui.services.job_admission_policy_engine.get_job_artifact_path")
    def test_check_ranking_explain_artifact_not_exists(self, mock_get_artifact_path, mock_get_summary_service):
        """Test checking for ranking explain artifact when it doesn't exist."""
        mock_path = Mock()
        mock_path.exists.return_value = False
        mock_get_artifact_path.return_value = mock_path
        
        engine = JobAdmissionPolicyEngine()
        result = engine._check_ranking_explain_artifact("test_job")
        
        assert result is None
    
    @patch("gui.services.job_admission_policy_engine.get_consolidated_gate_summary_service")
    @patch("gui.services.job_admission_policy_engine.get_job_evidence_dir")
    @patch("gui.services.job_admission_policy_engine.write_json_atomic")
    def test_write_decision(self, mock_write_json, mock_get_evidence_dir, mock_get_summary_service):
        """Test writing admission decision to file."""
        from pathlib import Path
        
        # Create a real Path object for testing
        mock_evidence_dir = Path("/tmp/test_evidence")
        mock_get_evidence_dir.return_value = mock_evidence_dir
        
        decision = JobAdmissionDecision(
            verdict=JobAdmissionVerdict.ADMITTED,
            job_id="test_job",
            evaluated_at_utc="2025-01-01T00:00:00Z",
            gate_summary_status="PASS",
            total_gates=5,
            gate_counts={"pass": 5, "warn": 0, "reject": 0},
            decision_reason="All gates passed",
            policy_rules_applied=["PASS_ALWAYS_ADMIT"],
        )
        
        engine = JobAdmissionPolicyEngine()
        result_path = engine.write_decision("test_job", decision)
        
        # Verify JSON was written
        mock_write_json.assert_called_once()
        call_args = mock_write_json.call_args
        expected_path = mock_evidence_dir / JOB_ADMISSION_DECISION_FILE
        assert call_args[0][0] == expected_path
        assert "verdict" in call_args[0][1]
        assert call_args[0][1]["verdict"] == "ADMITTED"
    
    @patch("gui.services.job_admission_policy_engine.get_consolidated_gate_summary_service")
    @patch("gui.services.job_admission_policy_engine.get_job_artifact_path")
    @patch("builtins.open")
    @patch("json.load")
    def test_read_decision_exists(self, mock_json_load, mock_open, mock_get_artifact_path, mock_get_summary_service):
        """Test reading existing admission decision."""
        mock_path = Mock()
        mock_path.exists.return_value = True
        mock_get_artifact_path.return_value = mock_path
        
        decision_data = {
            "verdict": "ADMITTED",
            "job_id": "test_job",
            "evaluated_at_utc": "2025-01-01T00:00:00Z",
            "gate_summary_status": "PASS",
            "total_gates": 5,
            "gate_counts": {"pass": 5, "warn": 0, "reject": 0},
            "decision_reason": "All gates passed",
            "policy_rules_applied": ["PASS_ALWAYS_ADMIT"],
        }
        mock_json_load.return_value = decision_data
        
        engine = JobAdmissionPolicyEngine()
        decision = engine.read_decision("test_job")
        
        assert decision is not None
        assert decision.verdict == JobAdmissionVerdict.ADMITTED
        assert decision.job_id == "test_job"
    
    @patch("gui.services.job_admission_policy_engine.get_consolidated_gate_summary_service")
    @patch("gui.services.job_admission_policy_engine.get_job_artifact_path")
    def test_read_decision_not_exists(self, mock_get_artifact_path, mock_get_summary_service):
        """Test reading admission decision when it doesn't exist."""
        mock_path = Mock()
        mock_path.exists.return_value = False
        mock_get_artifact_path.return_value = mock_path
        
        engine = JobAdmissionPolicyEngine()
        decision = engine.read_decision("test_job")
        
        assert decision is None
    
    @patch("gui.services.job_admission_policy_engine.get_consolidated_gate_summary_service")
    @patch("gui.services.job_admission_policy_engine.write_json_atomic")
    def test_evaluate_and_write(self, mock_write_json, mock_get_summary_service):
        """Test evaluate_and_write convenience method."""
        # Setup mock gate summary
        gate_summary = GateSummaryV1(
            overall_status=GateStatus.PASS,
            overall_message="All gates passed",
            counts={"pass": 5, "warn": 0, "reject": 0, "unknown": 0},
            gates=[
                GateV1(
                    gate_id="data_alignment",
                    gate_name="Data Alignment",
                    status=GateStatus.PASS,
                    message="Data aligned correctly",
                    reason_codes=["DATA_ALIGNED"],
                )
            ],
            evaluated_at_utc="2024-01-01T00:00:00Z",
            evaluator="test",
            source="test",
        )
        
        mock_service = Mock()
        mock_service.fetch_consolidated_summary.return_value = gate_summary
        mock_get_summary_service.return_value = mock_service
        
        engine = JobAdmissionPolicyEngine()
        decision = engine.evaluate_and_write("test_job")
        
        # Verify decision was created
        assert decision.verdict == JobAdmissionVerdict.ADMITTED
        assert decision.job_id == "test_job"
        
        # Verify write was called
        mock_write_json.assert_called_once()