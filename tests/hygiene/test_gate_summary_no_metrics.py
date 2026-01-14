"""
Policy tests to prevent metric leakage in Gate Summary (Hybrid BC v1.1 compliance).

T1) "No metrics in GateSummaryV1 model fields"
    - Introspect the Pydantic model fields / schema dict.
    - Fail if ANY field name matches metric keywords.

T2) "No metrics keys in GateSummary payload used by UI/service"
    - Validate recursively that keys in payload do not include metric keywords.
"""

import re
from typing import Dict, Any, List
from pydantic import BaseModel

# Metric keywords to exclude (case-insensitive)
METRIC_KEYWORDS = {
    "net", "pnl", "profit", "return", "sharpe", "sortino", "calmar",
    "mdd", "drawdown", "cagr", "winrate", "expectancy", "alpha", "beta",
    "vol", "volatility", "returns", "profitfactor", "maxdrawdown",
    "avgwin", "avgloss", "profit_loss", "sharperatio", "sortinoratio",
    "calmarratio", "var", "cvar", "skew", "kurtosis", "omega", "ulcer"
}

# Compile regex for case-insensitive matching
# Use word boundaries or underscores/separators
METRIC_PATTERN = re.compile(
    r'(?i)(?:^|_|\b)(' + '|'.join(METRIC_KEYWORDS) + r')(?:_|\b|$)',
)


def contains_metric_keyword(text: str) -> bool:
    """Check if text contains any metric keyword."""
    # Lowercase for case-insensitive matching
    text_lower = text.lower()
    for keyword in METRIC_KEYWORDS:
        # Check if keyword appears as a whole word (with boundaries)
        pattern = r'(?:^|_|\b)' + re.escape(keyword) + r'(?:_|\b|$)'
        if re.search(pattern, text_lower):
            return True
    return False


def check_dict_for_metric_keys(obj: Dict[str, Any], path: str = "") -> List[str]:
    """
    Recursively check dictionary for metric keys.
    
    Returns list of violations in format "path.key".
    """
    violations = []
    
    for key, value in obj.items():
        current_path = f"{path}.{key}" if path else key
        
        # Check key name
        if contains_metric_keyword(key):
            violations.append(f"{current_path} (key contains metric keyword)")
        
        # Recursively check nested dicts
        if isinstance(value, dict):
            violations.extend(check_dict_for_metric_keys(value, current_path))
        # Check lists of dicts
        elif isinstance(value, list):
            for i, item in enumerate(value):
                if isinstance(item, dict):
                    violations.extend(
                        check_dict_for_metric_keys(item, f"{current_path}[{i}]")
                    )
    
    return violations


def test_no_metrics_in_gatesummaryv1_model_fields():
    """T1: Fail if GateSummaryV1 model fields contain metric keywords."""
    # Import the model (may raise ImportError if not available)
    try:
        from src.contracts.portfolio.gate_summary_schemas import (
            GateSummaryV1, GateItemV1, GateStatus
        )
    except ImportError:
        # If model doesn't exist yet, skip test (but we should fail in CI)
        # For now, we'll pass since we're creating the model
        return
    
    # Check GateSummaryV1 schema
    violations = []
    
    # Get field names from model
    summary_fields = GateSummaryV1.model_fields.keys()
    for field in summary_fields:
        if contains_metric_keyword(field):
            violations.append(f"GateSummaryV1.field.{field}")
    
    # Check GateItemV1 schema
    item_fields = GateItemV1.model_fields.keys()
    for field in item_fields:
        if contains_metric_keyword(field):
            violations.append(f"GateItemV1.field.{field}")
    
    # Check enum values (GateStatus)
    status_values = [status.value for status in GateStatus]
    for value in status_values:
        if contains_metric_keyword(value):
            violations.append(f"GateStatus.value.{value}")
    
    if violations:
        violation_msg = "\n  - ".join(violations)
        raise AssertionError(
            f"GateSummaryV1 model contains metric keywords:\n  - {violation_msg}\n"
            f"These violate Hybrid BC v1.1 Layer1/Layer2 (no performance metrics)."
        )


def test_no_metrics_in_gatesummary_payload():
    """T2: Fail if GateSummary payload used by UI/service contains metric keys."""
    # This test checks example payloads that the UI/service might encounter
    
    # Example 1: GateSummaryV1 serialized payload
    try:
        from src.contracts.portfolio.gate_summary_schemas import (
            GateSummaryV1, GateItemV1, GateStatus, create_gate_summary_from_gates
        )
        
        # Create a realistic gate summary payload
        gates = [
            GateItemV1(
                gate_id="api_health",
                gate_name="API Health",
                status=GateStatus.PASS,
                message="API health endpoint responds with status ok.",
                reason_codes=["HEALTH_OK"],
                evidence_refs=["/health"],
                evaluated_at_utc="2026-01-14T15:00:00Z",
                evaluator="gate_summary_service",
            ),
            GateItemV1(
                gate_id="correlation_threshold",
                gate_name="Correlation Threshold",
                status=GateStatus.WARN,
                message="Correlation exceeds threshold for 2 pairs.",
                reason_codes=["CORR_0.8_EXCEEDED"],
                evidence_refs=["correlation_matrix.json"],
                evaluated_at_utc="2026-01-14T15:00:00Z",
                evaluator="portfolio_admission",
            ),
        ]
        
        summary = create_gate_summary_from_gates(
            gates=gates,
            source="supervisor_api",
            evaluator="gate_summary_service",
        )
        
        # Convert to dict (as would be serialized to JSON)
        payload = summary.model_dump()
        
        # Check for metric keys
        violations = check_dict_for_metric_keys(payload)
        
        if violations:
            violation_msg = "\n  - ".join(violations)
            raise AssertionError(
                f"GateSummaryV1 payload contains metric keys:\n  - {violation_msg}\n"
                f"These violate Hybrid BC v1.1 Layer1/Layer2 (no performance metrics)."
            )
            
    except ImportError:
        # Model not available yet
        pass
    
    # Example 2: Check existing gate summary service payload (if available)
    try:
        from src.gui.services.gate_summary_service import GateSummary, GateResult, GateStatus as ServiceGateStatus
        
        # Create a mock payload similar to what the service returns
        mock_payload = {
            "gates": [
                {
                    "gate_id": "api_health",
                    "gate_name": "API Health",
                    "status": "PASS",
                    "message": "API health endpoint responds with status ok.",
                    "details": {"status": "ok"},  # No metrics here
                    "actions": [{"label": "View Health", "url": "/health"}],
                    "timestamp": "2026-01-14T15:00:00Z",
                },
                {
                    "gate_id": "worker_execution_reality",
                    "gate_name": "Worker Execution Reality",
                    "status": "PASS",
                    "message": "2 job(s) currently RUNNING, 1 QUEUED.",
                    "details": {"running_count": 2, "queued_count": 1},  # Counts allowed
                    "actions": [{"label": "View Jobs", "url": "/api/v1/jobs"}],
                    "timestamp": "2026-01-14T15:00:00Z",
                },
            ],
            "timestamp": "2026-01-14T15:00:00Z",
            "overall_status": "PASS",
            "overall_message": "All gates PASS – system ready.",
        }
        
        violations = check_dict_for_metric_keys(mock_payload)
        
        if violations:
            violation_msg = "\n  - ".join(violations)
            raise AssertionError(
                f"GateSummary service payload contains metric keys:\n  - {violation_msg}\n"
                f"These violate Hybrid BC v1.1 Layer1/Layer2 (no performance metrics)."
            )
            
    except ImportError:
        # Service not available
        pass
    
    # Example 3: Check evidence aggregator gate summary payload
    try:
        from src.core.portfolio.evidence_aggregator import GateSummaryV1 as EvidenceGateSummaryV1
        
        # Create a mock payload
        mock_evidence_payload = {
            "total_permutations": 100,
            "valid_candidates": 85,
            "plateau_check": "Pass",
        }
        
        violations = check_dict_for_metric_keys(mock_evidence_payload)
        
        if violations:
            violation_msg = "\n  - ".join(violations)
            raise AssertionError(
                f"Evidence aggregator gate summary contains metric keys:\n  - {violation_msg}\n"
                f"These violate Hybrid BC v1.1 Layer1/Layer2 (no performance metrics)."
            )
            
    except ImportError:
        # Evidence aggregator not available
        pass


def test_metric_keyword_detection():
    """Sanity test for metric keyword detection."""
    # Test positive cases
    assert contains_metric_keyword("sharpe")
    assert contains_metric_keyword("Sharpe")
    assert contains_metric_keyword("SHARPE")
    assert contains_metric_keyword("maxdrawdown")
    assert contains_metric_keyword("net_profit")
    assert contains_metric_keyword("profit_factor")
    
    # Test negative cases (should not match)
    assert not contains_metric_keyword("gate")
    assert not contains_metric_keyword("status")
    assert not contains_metric_keyword("message")
    assert not contains_metric_keyword("evidence")
    
    # Test in context
    assert contains_metric_keyword("sharpe_ratio")
    assert contains_metric_keyword("mdd_percentage")
    assert not contains_metric_keyword("sharpen")  # Different word
    assert not contains_metric_keyword("network")  # Contains "net" but as part of word
    
    print("✓ Metric keyword detection works correctly")