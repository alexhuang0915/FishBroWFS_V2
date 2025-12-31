"""Strategy rotation governance (KEEP/KILL/FREEZE).

Phase 5: Strategy lifecycle management with automated governance decisions.

Decision Criteria:
- KEEP: Actively used in recent research, passing tests, documented
- KILL: Unused for >90 days, failing tests, deprecated design
- FREEZE: Experimental, under evaluation, not ready for production
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Dict, List, Optional, Any, TypedDict, Literal
import hashlib

from control.artifacts import write_json_atomic


class DecisionStatus(StrEnum):
    """Strategy governance decision status."""
    KEEP = "KEEP"
    KILL = "KILL"
    FREEZE = "FREEZE"


@dataclass
class UsageMetrics:
    """Metrics for strategy usage analysis."""
    
    strategy_id: str
    last_used: Optional[datetime] = None
    research_usage_count: int = 0
    test_passing: bool = True
    config_exists: bool = False
    documentation_exists: bool = False
    days_since_last_use: Optional[int] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        result = {
            "strategy_id": self.strategy_id,
            "research_usage_count": self.research_usage_count,
            "test_passing": self.test_passing,
            "config_exists": self.config_exists,
            "documentation_exists": self.documentation_exists,
        }
        if self.last_used:
            result["last_used"] = self.last_used.isoformat()
        if self.days_since_last_use is not None:
            result["days_since_last_use"] = self.days_since_last_use
        return result


@dataclass
class Decision:
    """Governance decision for a strategy."""
    
    strategy_id: str
    status: DecisionStatus
    timestamp: datetime
    reason: str
    evidence: List[str] = field(default_factory=list)
    previous_status: Optional[DecisionStatus] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "strategy_id": self.strategy_id,
            "status": self.status.value,
            "timestamp": self.timestamp.isoformat(),
            "reason": self.reason,
            "evidence": self.evidence,
            "previous_status": self.previous_status.value if self.previous_status else None,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> Decision:
        """Create Decision from dictionary."""
        return cls(
            strategy_id=data["strategy_id"],
            status=DecisionStatus(data["status"]),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            reason=data["reason"],
            evidence=data.get("evidence", []),
            previous_status=DecisionStatus(data["previous_status"]) if data.get("previous_status") else None,
        )


class StrategyGovernance:
    """Strategy governance manager for KEEP/KILL/FREEZE decisions."""
    
    def __init__(self, registry=None, outputs_root: Optional[Path] = None):
        """Initialize governance manager.
        
        Args:
            registry: Strategy registry instance (if None, uses module-level registry functions)
            outputs_root: Root directory for governance outputs (defaults to outputs/strategy_governance/)
        """
        self.registry = registry  # Can be None, we'll use module functions
        
        if outputs_root is None:
            self.outputs_root = Path("outputs") / "strategy_governance"
        else:
            self.outputs_root = outputs_root
        
        self.decisions: Dict[str, Decision] = {}  # strategy_id -> Decision
        self.usage_metrics: Dict[str, UsageMetrics] = {}
        
        # Ensure outputs directory exists
        self.outputs_root.mkdir(parents=True, exist_ok=True)
    
    def _analyze_research_usage(self) -> Dict[str, datetime]:
        """Analyze research logs to find strategy usage.
        
        Returns:
            Dictionary mapping strategy_id to last usage datetime
        """
        usage = {}
        research_dir = Path("outputs") / "research"
        
        if not research_dir.exists():
            return usage
        
        # Look for research logs containing strategy references
        # This is a simplified implementation - in practice would parse actual logs
        for log_file in research_dir.rglob("*.json"):
            try:
                with open(log_file, "r") as f:
                    data = json.load(f)
                    # Look for strategy_id in research logs
                    if "strategy_id" in data:
                        strategy_id = data["strategy_id"]
                        timestamp_str = data.get("timestamp", "")
                        if timestamp_str:
                            try:
                                timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                                # Keep the most recent timestamp
                                if strategy_id not in usage or timestamp > usage[strategy_id]:
                                    usage[strategy_id] = timestamp
                            except ValueError:
                                pass
            except (json.JSONDecodeError, IOError):
                continue
        
        return usage
    
    def _analyze_test_results(self) -> Dict[str, bool]:
        """Analyze test results to determine if strategies are passing.
        
        Returns:
            Dictionary mapping strategy_id to test passing status (True/False)
        """
        test_results = {}
        
        # Check for test files related to strategies
        test_dir = Path("tests") / "strategy"
        if test_dir.exists():
            # Simplified: assume strategies with test files are passing
            # In practice would parse pytest output
            for test_file in test_dir.glob("test_*.py"):
                content = test_file.read_text()
                # Look for strategy references in test files
                import re
                for match in re.finditer(r"(s1|s2|s3|sma_cross|breakout_channel|mean_revert)", content, re.IGNORECASE):
                    strategy_id = match.group(0).lower()
                    test_results[strategy_id] = True
        
        return test_results
    
    def _analyze_config_usage(self) -> Dict[str, bool]:
        """Check if strategies have configuration files.
        
        Returns:
            Dictionary mapping strategy_id to config existence status
        """
        config_exists = {}
        config_dir = Path("configs") / "strategies"
        
        if config_dir.exists():
            for strategy_dir in config_dir.iterdir():
                if strategy_dir.is_dir():
                    strategy_id = strategy_dir.name
                    # Check for baseline.yaml or features.json
                    baseline = strategy_dir / "baseline.yaml"
                    features = strategy_dir / "features.json"
                    config_exists[strategy_id] = baseline.exists() or features.exists()
        
        return config_exists
    
    def analyze_usage(self) -> Dict[str, UsageMetrics]:
        """Analyze strategy usage across research logs, tests, and configs.
        
        Returns:
            Dictionary mapping strategy_id to UsageMetrics
        """
        # Get all registered strategies
        from strategy.registry import list_strategies
        strategies = list_strategies()
        
        # Collect analysis data
        research_usage = self._analyze_research_usage()
        test_results = self._analyze_test_results()
        config_usage = self._analyze_config_usage()
        
        # Current time for age calculation
        now = datetime.now(timezone.utc)
        
        metrics = {}
        for spec in strategies:
            strategy_id = spec.strategy_id
            
            # Research usage
            last_used = research_usage.get(strategy_id)
            usage_count = 1 if strategy_id in research_usage else 0
            
            # Test results
            test_passing = test_results.get(strategy_id, False)
            
            # Config existence
            config_exists = config_usage.get(strategy_id, False)
            
            # Documentation check (simplified)
            doc_exists = False
            doc_path = Path("docs") / "strategies" / f"{strategy_id}.md"
            if doc_path.exists():
                doc_exists = True
            
            # Calculate days since last use
            days_since_last_use = None
            if last_used:
                delta = now - last_used
                days_since_last_use = delta.days
            
            metrics[strategy_id] = UsageMetrics(
                strategy_id=strategy_id,
                last_used=last_used,
                research_usage_count=usage_count,
                test_passing=test_passing,
                config_exists=config_exists,
                documentation_exists=doc_exists,
                days_since_last_use=days_since_last_use,
            )
        
        self.usage_metrics = metrics
        return metrics
    
    def _make_decision_for_strategy(self, strategy_id: str, metrics: UsageMetrics) -> Decision:
        """Make KEEP/KILL/FREEZE decision for a single strategy.
        
        Args:
            strategy_id: Strategy identifier
            metrics: Usage metrics for the strategy
            
        Returns:
            Decision object with status and reasoning
        """
        now = datetime.now(timezone.utc)
        previous_decision = self.decisions.get(strategy_id)
        
        # Decision criteria
        reasons = []
        evidence = []
        
        # Check for KILL criteria
        kill_reasons = []
        if metrics.days_since_last_use is not None and metrics.days_since_last_use > 90:
            kill_reasons.append(f"Unused for {metrics.days_since_last_use} days")
            evidence.append(f"last_used: {metrics.last_used}")
        
        if not metrics.test_passing:
            kill_reasons.append("Failing tests")
            evidence.append("test_status: failing")
        
        if kill_reasons:
            status = DecisionStatus.KILL
            reason = f"KILL: {', '.join(kill_reasons)}"
            return Decision(
                strategy_id=strategy_id,
                status=status,
                timestamp=now,
                reason=reason,
                evidence=evidence,
                previous_status=previous_decision.status if previous_decision else None,
            )
        
        # Check for FREEZE criteria
        freeze_reasons = []
        if metrics.research_usage_count == 0:
            freeze_reasons.append("No research usage")
            evidence.append("research_usage_count: 0")
        
        if not metrics.config_exists:
            freeze_reasons.append("No configuration")
            evidence.append("config_exists: false")
        
        if freeze_reasons:
            status = DecisionStatus.FREEZE
            reason = f"FREEZE: {', '.join(freeze_reasons)}"
            return Decision(
                strategy_id=strategy_id,
                status=status,
                timestamp=now,
                reason=reason,
                evidence=evidence,
                previous_status=previous_decision.status if previous_decision else None,
            )
        
        # Default: KEEP
        keep_reasons = []
        if metrics.research_usage_count > 0:
            keep_reasons.append(f"Used in {metrics.research_usage_count} research runs")
        
        if metrics.test_passing:
            keep_reasons.append("Passing tests")
        
        if metrics.config_exists:
            keep_reasons.append("Has configuration")
        
        if metrics.documentation_exists:
            keep_reasons.append("Documented")
        
        status = DecisionStatus.KEEP
        reason = f"KEEP: {', '.join(keep_reasons) if keep_reasons else 'Active and healthy'}"
        
        return Decision(
            strategy_id=strategy_id,
            status=status,
            timestamp=now,
            reason=reason,
            evidence=evidence,
            previous_status=previous_decision.status if previous_decision else None,
        )
    
    def make_decisions(self) -> List[Decision]:
        """Apply decision criteria to generate KEEP/KILL/FREEZE decisions.
        
        Returns:
            List of Decision objects for all strategies
        """
        # Ensure usage metrics are analyzed
        if not self.usage_metrics:
            self.analyze_usage()
        
        decisions = []
        for strategy_id, metrics in self.usage_metrics.items():
            decision = self._make_decision_for_strategy(strategy_id, metrics)
            self.decisions[strategy_id] = decision
            decisions.append(decision)
        
        return decisions
    
    def save_decisions(self, filename: Optional[str] = None) -> Path:
        """Save decisions to JSON file.
        
        Args:
            filename: Optional filename (defaults to timestamp-based name)
            
        Returns:
            Path to saved file
        """
        if not self.decisions:
            self.make_decisions()
        
        # Create timestamp-based filename
        if filename is None:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            filename = f"governance_decisions_{timestamp}.json"
        
        output_path = self.outputs_root / filename
        
        # Prepare data for serialization
        data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "decisions": [decision.to_dict() for decision in self.decisions.values()],
            "summary": {
                "total": len(self.decisions),
                "keep": sum(1 for d in self.decisions.values() if d.status == DecisionStatus.KEEP),
                "kill": sum(1 for d in self.decisions.values() if d.status == DecisionStatus.KILL),
                "freeze": sum(1 for d in self.decisions.values() if d.status == DecisionStatus.FREEZE),
            }
        }
        
        # Write atomically
        write_json_atomic(output_path, data)
        return output_path
    
    def load_decisions(self, filepath: Path) -> None:
        """Load decisions from JSON file.
        
        Args:
            filepath: Path to JSON file containing decisions
        """
        with open(filepath, "r") as f:
            data = json.load(f)
        
        self.decisions.clear()
        for decision_data in data.get("decisions", []):
            decision = Decision.from_dict(decision_data)
            self.decisions[decision.strategy_id] = decision
    
    def generate_report(self) -> dict:
        """Generate comprehensive governance report.
        
        Returns:
            Dictionary with report data
        """
        if not self.decisions:
            self.make_decisions()
        
        # Analyze decisions
        keep_count = sum(1 for d in self.decisions.values() if d.status == DecisionStatus.KEEP)
        kill_count = sum(1 for d in self.decisions.values() if d.status == DecisionStatus.KILL)
        freeze_count = sum(1 for d in self.decisions.values() if d.status == DecisionStatus.FREEZE)
        
        # Find strategies needing attention
        attention_needed = []
        for decision in self.decisions.values():
            if decision.status == DecisionStatus.KILL:
                attention_needed.append({
                    "strategy_id": decision.strategy_id,
                    "status": decision.status.value,
                    "reason": decision.reason,
                    "action": "Consider removal or refactoring"
                })
            elif decision.status == DecisionStatus.FREEZE:
                attention_needed.append({
                    "strategy_id": decision.strategy_id,
                    "status": decision.status.value,
                    "reason": decision.reason,
                    "action": "Evaluate for promotion to KEEP or removal"
                })
        
        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "summary": {
                "total_strategies": len(self.decisions),
                "keep": keep_count,
                "kill": kill_count,
                "freeze": freeze_count,
            },
            "decisions": [decision.to_dict() for decision in self.decisions.values()],
            "attention_needed": attention_needed,
            "recommendations": [
                f"Review {kill_count} KILL strategies for potential removal",
                f"Evaluate {freeze_count} FREEZE strategies for promotion or removal",
                f"Maintain {keep_count} KEEP strategies with regular monitoring"
            ]
        }
        
        return report
    
    def save_report(self, filename: Optional[str] = None) -> Path:
        """Save governance report to JSON file.
        
        Args:
            filename: Optional filename (defaults to timestamp-based name)
            
        Returns:
            Path to saved report file
        """
        report = self.generate_report()
        
        if filename is None:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            filename = f"governance_report_{timestamp}.json"
        
        output_path = self.outputs_root / filename
        write_json_atomic(output_path, report)
        return output_path


# Note: The strategy registry uses module-level functions (list_strategies, get, etc.)
# rather than a registry instance. The StrategyGovernance class works with these
# module functions directly.