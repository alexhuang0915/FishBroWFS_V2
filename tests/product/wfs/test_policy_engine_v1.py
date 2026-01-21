from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from contracts.wfs_policy import fingerprint_wfs_policy, load_wfs_policy
from wfs.policy_engine import apply_wfs_policy


def _policy_root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_default_policy_matches_existing_behavior():
    policy_path = _policy_root() / "configs" / "strategies" / "wfs" / "policy_v1_default.yaml"
    policy = load_wfs_policy(policy_path)

    raw = {"net_profit": 1000.0, "mdd": 100.0, "trades": 50}
    derived = {
        "min_avg_profit": 20.0,
        "trade_multiplier": 1.5,
        "robustness_factor": 1.0,
        "final_score": 15.0,
    }

    decision = apply_wfs_policy(policy=policy, raw=raw, derived=derived)

    assert decision.edge_gate["passed"] is True
    assert decision.cliff_gate["passed"] is True
    assert decision.notes[-1].startswith("Final score:")


def test_invalid_policy_raises_validation_error(tmp_path: Path):
    invalid_policy = tmp_path / "bad_policy.yaml"
    invalid_policy.write_text(
        "schema_version: \"1.0\"\n"
        "name: \"broken\"\n"
        "description: \"Missing gates\"\n"
        "modes:\n"
        "  mode_b_enabled: true\n"
        "  scoring_guards_enabled: true\n"
        "gates:\n"
        "  edge_gate:\n"
        "    enabled: true\n"
        "    metric: \"min_avg_profit\"\n"
        "    op: \"INVALID\"\n"
        "    threshold: 0.0\n"
        "    fail_reason: \"fail\"\n"
    )

    with pytest.raises(ValidationError):
        load_wfs_policy(invalid_policy)


def test_policy_fingerprint_is_stable():
    policy_path = _policy_root() / "configs" / "strategies" / "wfs" / "policy_v1_default.yaml"
    policy = load_wfs_policy(policy_path)
    fingerprint_a = fingerprint_wfs_policy(policy)
    fingerprint_b = fingerprint_wfs_policy(policy)
    assert fingerprint_a == fingerprint_b
    assert fingerprint_a.startswith("sha256:")
