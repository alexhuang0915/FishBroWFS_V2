"""Tests for strategy rotation governance (KEEP/KILL/FREEZE)."""

import json
import tempfile
from pathlib import Path
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock, Mock
import pytest

from control.strategy_rotation import (
    StrategyGovernance,
    Decision,
    DecisionStatus,
    UsageMetrics,
)


class TestDecision:
    """Test Decision dataclass."""
    
    def test_decision_creation(self):
        """Test basic Decision creation."""
        decision = Decision(
            strategy_id="s1",
            status=DecisionStatus.KEEP,
            timestamp=datetime.now(timezone.utc),
            reason="Active usage",
            evidence=["research/log1.json", "tests/test_s1.py"],
        )
        
        assert decision.strategy_id == "s1"
        assert decision.status == DecisionStatus.KEEP
        assert isinstance(decision.timestamp, datetime)
        assert decision.reason == "Active usage"
        assert decision.evidence == ["research/log1.json", "tests/test_s1.py"]
        assert decision.previous_status is None
    
    def test_decision_to_dict(self):
        """Test serialization to dictionary."""
        timestamp = datetime.now(timezone.utc)
        decision = Decision(
            strategy_id="s1",
            status=DecisionStatus.KILL,
            timestamp=timestamp,
            reason="Unused for 100 days",
            evidence=["research/log1.json"],
            previous_status=DecisionStatus.KEEP,
        )
        
        data = decision.to_dict()
        
        assert data["strategy_id"] == "s1"
        assert data["status"] == "KILL"
        assert data["timestamp"] == timestamp.isoformat()
        assert data["reason"] == "Unused for 100 days"
        assert data["evidence"] == ["research/log1.json"]
        assert data["previous_status"] == "KEEP"
    
    def test_decision_from_dict(self):
        """Test deserialization from dictionary."""
        timestamp = datetime.now(timezone.utc)
        data = {
            "strategy_id": "s2",
            "status": "FREEZE",
            "timestamp": timestamp.isoformat(),
            "reason": "Experimental",
            "evidence": ["configs/strategies/s2/baseline.yaml"],
            "previous_status": None,
        }
        
        decision = Decision.from_dict(data)
        
        assert decision.strategy_id == "s2"
        assert decision.status == DecisionStatus.FREEZE
        assert decision.timestamp == timestamp
        assert decision.reason == "Experimental"
        assert decision.evidence == ["configs/strategies/s2/baseline.yaml"]
        assert decision.previous_status is None


class TestUsageMetrics:
    """Test UsageMetrics dataclass."""
    
    def test_usage_metrics_creation(self):
        """Test basic UsageMetrics creation."""
        last_used = datetime.now(timezone.utc) - timedelta(days=30)
        metrics = UsageMetrics(
            strategy_id="s1",
            last_used=last_used,
            research_usage_count=5,
            test_passing=True,
            config_exists=True,
            documentation_exists=True,
            days_since_last_use=30,
        )
        
        assert metrics.strategy_id == "s1"
        assert metrics.last_used == last_used
        assert metrics.research_usage_count == 5
        assert metrics.test_passing is True
        assert metrics.config_exists is True
        assert metrics.documentation_exists is True
        assert metrics.days_since_last_use == 30
    
    def test_usage_metrics_to_dict(self):
        """Test serialization to dictionary."""
        last_used = datetime.now(timezone.utc) - timedelta(days=30)
        metrics = UsageMetrics(
            strategy_id="s1",
            last_used=last_used,
            research_usage_count=5,
            test_passing=True,
            config_exists=True,
            documentation_exists=False,
            days_since_last_use=30,
        )
        
        data = metrics.to_dict()
        
        assert data["strategy_id"] == "s1"
        assert data["last_used"] == last_used.isoformat()
        assert data["research_usage_count"] == 5
        assert data["test_passing"] is True
        assert data["config_exists"] is True
        assert data["documentation_exists"] is False
        assert data["days_since_last_use"] == 30


class TestStrategyGovernance:
    """Test StrategyGovernance class."""
    
    def setup_method(self):
        """Create temp directory for outputs."""
        self.temp_dir = tempfile.mkdtemp()
        self.outputs_root = Path(self.temp_dir) / "strategy_governance"
    
    def teardown_method(self):
        """Clean up temp directory."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_init_with_custom_outputs(self):
        """Test initialization with custom outputs directory."""
        governance = StrategyGovernance(outputs_root=self.outputs_root)
        
        assert governance.outputs_root == self.outputs_root
        assert governance.decisions == {}
        assert governance.usage_metrics == {}
        assert self.outputs_root.exists()
    
    def test_init_with_default_outputs(self):
        """Test initialization with default outputs directory."""
        with patch("pathlib.Path.mkdir") as mock_mkdir:
            governance = StrategyGovernance()
            
            # Default path should be outputs/strategy_governance
            assert "outputs" in str(governance.outputs_root)
            assert "strategy_governance" in str(governance.outputs_root)
            mock_mkdir.assert_called_once_with(parents=True, exist_ok=True)
    
    @patch("strategy.registry.list_strategies")
    @patch("control.strategy_rotation.StrategyGovernance._analyze_research_usage")
    @patch("control.strategy_rotation.StrategyGovernance._analyze_test_results")
    @patch("control.strategy_rotation.StrategyGovernance._analyze_config_usage")
    def test_analyze_usage(
        self,
        mock_config_usage,
        mock_test_results,
        mock_research_usage,
        mock_list_strategies,
    ):
        """Test usage analysis."""
        # Mock strategy specs
        mock_spec1 = Mock(strategy_id="s1")
        mock_spec2 = Mock(strategy_id="s2")
        mock_list_strategies.return_value = [mock_spec1, mock_spec2]
        
        # Mock analysis results
        mock_research_usage.return_value = {
            "s1": datetime.now(timezone.utc) - timedelta(days=10),
        }
        mock_test_results.return_value = {
            "s1": True,
            "s2": False,
        }
        mock_config_usage.return_value = {
            "s1": True,
            "s2": False,
        }
        
        governance = StrategyGovernance(outputs_root=self.outputs_root)
        metrics = governance.analyze_usage()
        
        assert len(metrics) == 2
        assert "s1" in metrics
        assert "s2" in metrics
        
        # Check s1 metrics
        s1_metrics = metrics["s1"]
        assert s1_metrics.strategy_id == "s1"
        assert s1_metrics.last_used is not None
        assert s1_metrics.research_usage_count == 1
        assert s1_metrics.test_passing is True
        assert s1_metrics.config_exists is True
        assert s1_metrics.days_since_last_use == 10
        
        # Check s2 metrics
        s2_metrics = metrics["s2"]
        assert s2_metrics.strategy_id == "s2"
        assert s2_metrics.last_used is None
        assert s2_metrics.research_usage_count == 0
        assert s2_metrics.test_passing is False
        assert s2_metrics.config_exists is False
    
    def test_make_decisions_for_strategy_kill(self):
        """Test decision logic for KILL criteria."""
        governance = StrategyGovernance(outputs_root=self.outputs_root)
        
        # Create metrics that should trigger KILL
        metrics = UsageMetrics(
            strategy_id="s1",
            last_used=datetime.now(timezone.utc) - timedelta(days=100),  # > 90 days
            research_usage_count=0,
            test_passing=False,  # Failing tests
            config_exists=False,
            documentation_exists=False,
            days_since_last_use=100,
        )
        
        decision = governance._make_decision_for_strategy("s1", metrics)
        
        assert decision.strategy_id == "s1"
        assert decision.status == DecisionStatus.KILL
        assert "Unused for 100 days" in decision.reason
        assert "Failing tests" in decision.reason
    
    def test_make_decisions_for_strategy_freeze(self):
        """Test decision logic for FREEZE criteria."""
        governance = StrategyGovernance(outputs_root=self.outputs_root)
        
        # Create metrics that should trigger FREEZE (no usage, no config)
        metrics = UsageMetrics(
            strategy_id="s2",
            last_used=None,
            research_usage_count=0,  # No research usage
            test_passing=True,
            config_exists=False,  # No configuration
            documentation_exists=False,
            days_since_last_use=None,
        )
        
        decision = governance._make_decision_for_strategy("s2", metrics)
        
        assert decision.strategy_id == "s2"
        assert decision.status == DecisionStatus.FREEZE
        assert "No research usage" in decision.reason
        assert "No configuration" in decision.reason
    
    def test_make_decisions_for_strategy_keep(self):
        """Test decision logic for KEEP criteria."""
        governance = StrategyGovernance(outputs_root=self.outputs_root)
        
        # Create metrics that should trigger KEEP
        metrics = UsageMetrics(
            strategy_id="s3",
            last_used=datetime.now(timezone.utc) - timedelta(days=10),
            research_usage_count=5,
            test_passing=True,
            config_exists=True,
            documentation_exists=True,
            days_since_last_use=10,
        )
        
        decision = governance._make_decision_for_strategy("s3", metrics)
        
        assert decision.strategy_id == "s3"
        assert decision.status == DecisionStatus.KEEP
        assert "Used in 5 research runs" in decision.reason
        assert "Passing tests" in decision.reason
    
    @patch("control.strategy_rotation.StrategyGovernance.analyze_usage")
    def test_make_decisions(self, mock_analyze_usage):
        """Test making decisions for all strategies."""
        # Mock usage metrics
        metrics = {
            "s1": UsageMetrics(
                strategy_id="s1",
                last_used=datetime.now(timezone.utc) - timedelta(days=100),
                research_usage_count=0,
                test_passing=False,
                config_exists=False,
                documentation_exists=False,
                days_since_last_use=100,
            ),
            "s2": UsageMetrics(
                strategy_id="s2",
                last_used=None,
                research_usage_count=0,
                test_passing=True,
                config_exists=True,
                documentation_exists=False,
                days_since_last_use=None,
            ),
        }
        
        # Create governance instance and set metrics directly
        governance = StrategyGovernance(outputs_root=self.outputs_root)
        governance.usage_metrics = metrics
        
        decisions = governance.make_decisions()
        
        assert len(decisions) == 2
        assert any(d.strategy_id == "s1" and d.status == DecisionStatus.KILL for d in decisions)
        assert any(d.strategy_id == "s2" and d.status == DecisionStatus.FREEZE for d in decisions)
        
        # Check that decisions are stored
        assert "s1" in governance.decisions
        assert "s2" in governance.decisions
    
    def test_save_and_load_decisions(self):
        """Test saving and loading decisions."""
        governance = StrategyGovernance(outputs_root=self.outputs_root)
        
        # Create some decisions
        decision1 = Decision(
            strategy_id="s1",
            status=DecisionStatus.KEEP,
            timestamp=datetime.now(timezone.utc),
            reason="Active",
            evidence=["log1.json"],
        )
        decision2 = Decision(
            strategy_id="s2",
            status=DecisionStatus.KILL,
            timestamp=datetime.now(timezone.utc),
            reason="Unused",
            evidence=["log2.json"],
        )
        
        governance.decisions = {
            "s1": decision1,
            "s2": decision2,
        }
        
        # Save decisions
        output_path = governance.save_decisions("test_decisions.json")
        assert output_path.exists()
        
        # Create new governance instance and load decisions
        governance2 = StrategyGovernance(outputs_root=self.outputs_root)
        governance2.load_decisions(output_path)
        
        assert len(governance2.decisions) == 2
        assert "s1" in governance2.decisions
        assert "s2" in governance2.decisions
        
        loaded_decision1 = governance2.decisions["s1"]
        assert loaded_decision1.strategy_id == "s1"
        assert loaded_decision1.status == DecisionStatus.KEEP
        assert loaded_decision1.reason == "Active"
    
    @patch("control.strategy_rotation.write_json_atomic")
    def test_save_decisions_creates_file(self, mock_write_json):
        """Test that save_decisions creates JSON file."""
        governance = StrategyGovernance(outputs_root=self.outputs_root)
        
        # Create a decision
        decision = Decision(
            strategy_id="s1",
            status=DecisionStatus.KEEP,
            timestamp=datetime.now(timezone.utc),
            reason="Test",
            evidence=[],
        )
        governance.decisions = {"s1": decision}
        
        # Save decisions
        output_path = governance.save_decisions()
        
        # Check that write_json_atomic was called
        mock_write_json.assert_called_once()
        
        # Check the call arguments
        call_path = mock_write_json.call_args[0][0]
        call_data = mock_write_json.call_args[0][1]
        
        assert "test_decisions" not in str(call_path)  # Should use timestamp
        assert "decisions" in call_data
        assert "summary" in call_data
        assert call_data["summary"]["total"] == 1
        assert call_data["summary"]["keep"] == 1
    
    def test_generate_report(self):
        """Test report generation."""
        governance = StrategyGovernance(outputs_root=self.outputs_root)
        
        # Create decisions
        decision1 = Decision(
            strategy_id="s1",
            status=DecisionStatus.KEEP,
            timestamp=datetime.now(timezone.utc),
            reason="Active usage",
            evidence=[],
        )
        decision2 = Decision(
            strategy_id="s2",
            status=DecisionStatus.KILL,
            timestamp=datetime.now(timezone.utc),
            reason="Unused for 100 days",
            evidence=[],
        )
        decision3 = Decision(
            strategy_id="s3",
            status=DecisionStatus.FREEZE,
            timestamp=datetime.now(timezone.utc),
            reason="Experimental",
            evidence=[],
        )
        
        governance.decisions = {
            "s1": decision1,
            "s2": decision2,
            "s3": decision3,
        }
        
        report = governance.generate_report()
        
        assert "generated_at" in report
        assert "summary" in report
        assert "decisions" in report
        assert "attention_needed" in report
        assert "recommendations" in report
        
        summary = report["summary"]
        assert summary["total_strategies"] == 3
        assert summary["keep"] == 1
        assert summary["kill"] == 1
        assert summary["freeze"] == 1
        
        # Check attention needed includes KILL and FREEZE
        attention = report["attention_needed"]
        assert len(attention) == 2  # KILL and FREEZE
        assert any(item["strategy_id"] == "s2" for item in attention)
        assert any(item["strategy_id"] == "s3" for item in attention)
    
    @patch("control.strategy_rotation.write_json_atomic")
    def test_save_report(self, mock_write_json):
        """Test saving report to file."""
        governance = StrategyGovernance(outputs_root=self.outputs_root)
        
        # Mock generate_report
        mock_report = {
            "generated_at": "2024-01-01T00:00:00Z",
            "summary": {"total": 1},
            "decisions": [],
            "attention_needed": [],
            "recommendations": [],
        }
        
        with patch.object(governance, "generate_report", return_value=mock_report):
            output_path = governance.save_report("test_report.json")
            
            # Check that write_json_atomic was called
            mock_write_json.assert_called_once()
            
            # Check the call arguments
            call_path = mock_write_json.call_args[0][0]
            call_data = mock_write_json.call_args[0][1]
            
            assert call_path.name == "test_report.json"
            assert call_data == mock_report


class TestIntegration:
    """Integration tests with mock registry."""
    
    @patch("strategy.registry.list_strategies")
    def test_full_workflow(self, mock_list_strategies):
        """Test full governance workflow."""
        # Mock strategy specs
        mock_spec1 = Mock(strategy_id="s1")
        mock_spec2 = Mock(strategy_id="s2")
        mock_list_strategies.return_value = [mock_spec1, mock_spec2]
        
        # Create temp directory
        temp_dir = tempfile.mkdtemp()
        outputs_root = Path(temp_dir) / "governance"
        
        try:
            # Create governance instance
            governance = StrategyGovernance(outputs_root=outputs_root)
            
            # Mock analysis methods
            with patch.object(governance, "_analyze_research_usage") as mock_research:
                with patch.object(governance, "_analyze_test_results") as mock_tests:
                    with patch.object(governance, "_analyze_config_usage") as mock_config:
                        # Setup mock returns
                        mock_research.return_value = {
                            "s1": datetime.now(timezone.utc) - timedelta(days=10),
                        }
                        mock_tests.return_value = {
                            "s1": True,
                            "s2": True,
                        }
                        mock_config.return_value = {
                            "s1": True,
                            "s2": False,
                        }
                        
                        # Analyze usage
                        metrics = governance.analyze_usage()
                        
                        assert len(metrics) == 2
                        assert "s1" in metrics
                        assert "s2" in metrics
                        
                        # Make decisions
                        decisions = governance.make_decisions()
                        
                        assert len(decisions) == 2
                        
                        # s1 should be KEEP (has usage, tests pass, has config)
                        s1_decision = next(d for d in decisions if d.strategy_id == "s1")
                        assert s1_decision.status == DecisionStatus.KEEP
                        
                        # s2 should be FREEZE (no usage, no config)
                        s2_decision = next(d for d in decisions if d.strategy_id == "s2")
                        assert s2_decision.status == DecisionStatus.FREEZE
                        
                        # Save decisions
                        decisions_path = governance.save_decisions()
                        assert decisions_path.exists()
                        
                        # Generate report
                        report = governance.generate_report()
                        assert "summary" in report
                        assert report["summary"]["total_strategies"] == 2
                        
                        # Save report
                        report_path = governance.save_report()
                        assert report_path.exists()
                        
                        # Load decisions into new instance
                        governance2 = StrategyGovernance(outputs_root=outputs_root)
                        governance2.load_decisions(decisions_path)
                        
                        assert len(governance2.decisions) == 2
                        assert "s1" in governance2.decisions
                        assert "s2" in governance2.decisions
        finally:
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)


def test_decision_status_enum():
    """Test DecisionStatus enum values."""
    assert DecisionStatus.KEEP.value == "KEEP"
    assert DecisionStatus.KILL.value == "KILL"
    assert DecisionStatus.FREEZE.value == "FREEZE"
    
    # Test string conversion
    assert str(DecisionStatus.KEEP) == "KEEP"
    assert DecisionStatus("KEEP") == DecisionStatus.KEEP
    assert DecisionStatus("KILL") == DecisionStatus.KILL
    assert DecisionStatus("FREEZE") == DecisionStatus.FREEZE


if __name__ == "__main__":
    pytest.main([__file__, "-v"])