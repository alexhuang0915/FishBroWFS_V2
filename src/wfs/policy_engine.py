"""
Interpreter for WFS policy definitions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict

from contracts.wfs_policy import WfsPolicyV1, fingerprint_wfs_policy


OperatorFunc = Callable[[float, float], bool]

_OPERATORS: Dict[str, OperatorFunc] = {
    "<=": lambda v, t: v <= t,
    ">=": lambda v, t: v >= t,
    "==": lambda v, t: v == t,
    "<": lambda v, t: v < t,
    ">": lambda v, t: v > t,
}


@dataclass(frozen=True)
class PolicyDecision:
    policy_name: str
    policy_version: str
    policy_hash: str
    mode_b_enabled: bool
    scoring_guards_enabled: bool
    edge_gate: Dict[str, Any]
    cliff_gate: Dict[str, Any]
    notes: list[str]


def _get_metric_value(metric: str, raw: Dict[str, Any], derived: Dict[str, Any]) -> float:
    value = derived.get(metric)
    if value is None:
        value = raw.get(metric, 0.0)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _evaluate_gate(gate_policy, raw, derived):
    if not gate_policy.enabled:
        return True, gate_policy.threshold, 0.0, ""

    value = _get_metric_value(gate_policy.metric, raw, derived)
    comparator = _OPERATORS.get(gate_policy.op)
    if comparator is None:
        raise ValueError(f"Unsupported operator: {gate_policy.op}")

    passed = comparator(value, gate_policy.threshold)
    reason = "" if passed else gate_policy.fail_reason
    return passed, gate_policy.threshold, value, reason


def apply_wfs_policy(
    *,
    policy: WfsPolicyV1,
    raw: dict[str, Any],
    derived: dict[str, Any],
) -> PolicyDecision:
    """
    Apply a WFS policy to raw/derived metrics.
    """
    edge_passed, edge_threshold, edge_value, edge_reason = _evaluate_gate(
        policy.gates.edge_gate, raw, derived
    )
    cliff_passed, cliff_threshold, cliff_value, cliff_reason = _evaluate_gate(
        policy.gates.cliff_gate, raw, derived
    )

    notes = []
    if edge_reason:
        notes.append(edge_reason)
    if cliff_reason:
        notes.append(cliff_reason)

    if policy.scoring.notes_enabled:
        final_score_value = _get_metric_value(
            policy.scoring.final_score_metric, raw, derived
        )
        notes.append(f"Final score: {final_score_value:.2f}")

    policy_hash = fingerprint_wfs_policy(policy)

    return PolicyDecision(
        policy_name=policy.name,
        policy_version=policy.schema_version,
        policy_hash=policy_hash,
        mode_b_enabled=policy.modes.mode_b_enabled,
        scoring_guards_enabled=policy.modes.scoring_guards_enabled,
        edge_gate={
            "passed": edge_passed,
            "threshold": edge_threshold,
            "value": edge_value,
            "metric": policy.gates.edge_gate.metric,
            "reason": edge_reason,
        },
        cliff_gate={
            "passed": cliff_passed,
            "threshold": cliff_threshold,
            "value": cliff_value,
            "metric": policy.gates.cliff_gate.metric,
            "reason": cliff_reason,
        },
        notes=notes,
    )
