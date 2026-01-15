"""
Pydantic v2 models for WFS governance/scoring policies.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

Operator = Literal["<=", ">=", "==", "<", ">"]


class GatePolicyV1(BaseModel):
    """Definition of a single gate policy."""

    enabled: bool
    metric: str
    op: Operator
    threshold: float
    fail_reason: str

    model_config = ConfigDict(extra="forbid")


class ScorePolicyV1(BaseModel):
    """Definition of scoring metadata."""

    final_score_metric: str
    notes_enabled: bool = Field(default=True)

    model_config = ConfigDict(extra="forbid")


class GuardPolicyV1(BaseModel):
    """Mode-level guard toggles."""

    mode_b_enabled: bool
    scoring_guards_enabled: bool

    model_config = ConfigDict(extra="forbid")


class GatesV1(BaseModel):
    """Aggregates edge and cliff gate policies."""

    edge_gate: GatePolicyV1
    cliff_gate: GatePolicyV1

    model_config = ConfigDict(extra="forbid")


class WfsPolicyV1(BaseModel):
    """
    Root policy model for WFS governance.
    """

    schema_version: Literal["1.0"]
    name: str
    description: str
    modes: GuardPolicyV1
    gates: GatesV1
    scoring: ScorePolicyV1

    model_config = ConfigDict(extra="forbid")


def load_wfs_policy(path: Path) -> WfsPolicyV1:
    """
    Load a WFS policy from YAML and validate it.
    """
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"Policy file not found: {path}") from exc
    return WfsPolicyV1.model_validate(data)


def fingerprint_wfs_policy(policy: WfsPolicyV1) -> str:
    """
    Produce a stable hash for a policy.
    """
    canonical = json.dumps(
        policy.model_dump(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"
