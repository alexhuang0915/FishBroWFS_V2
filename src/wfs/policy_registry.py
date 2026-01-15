"""
Policy registry helper to list available WFS policy YAMLs.
"""

from __future__ import annotations

import hashlib

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List

from pydantic import ValidationError
import yaml

from contracts.wfs_policy import fingerprint_wfs_policy, load_wfs_policy


@dataclass(frozen=True)
class PolicyRegistryEntry:
    selector: str
    name: str
    version: str
    hash: str
    source: str
    resolved_source: str
    modes: Dict[str, bool]
    gates: Dict[str, Dict[str, object]]
    description: str


def _selector_from_name(filename: str) -> str:
    if filename == "policy_v1_default.yaml":
        return "default"
    if filename == "policy_v1_red_team.yaml":
        return "red_team"
    return filename


def list_wfs_policies(*, repo_root: Path) -> List[PolicyRegistryEntry]:
    """
    Enumerate WFS policies under configs/strategies/wfs.
    """
    wfs_dir = repo_root / "configs" / "strategies" / "wfs"
    if not wfs_dir.exists():
        return []

    entries: List[PolicyRegistryEntry] = []
    for child in sorted(wfs_dir.glob("*.yaml")):
        selector = _selector_from_name(child.name)
        try:
            policy = load_wfs_policy(child)
            modes = {
                "mode_b_enabled": policy.modes.mode_b_enabled,
                "scoring_guards_enabled": policy.modes.scoring_guards_enabled,
            }
            gates = {
                "edge_gate": {
                    "metric": policy.gates.edge_gate.metric,
                    "op": policy.gates.edge_gate.op,
                    "threshold": policy.gates.edge_gate.threshold,
                    "enabled": policy.gates.edge_gate.enabled,
                    "fail_reason": policy.gates.edge_gate.fail_reason,
                },
                "cliff_gate": {
                    "metric": policy.gates.cliff_gate.metric,
                    "op": policy.gates.cliff_gate.op,
                    "threshold": policy.gates.cliff_gate.threshold,
                    "enabled": policy.gates.cliff_gate.enabled,
                    "fail_reason": policy.gates.cliff_gate.fail_reason,
                },
            }
            entry_hash = fingerprint_wfs_policy(policy)
            name = policy.name
            version = policy.schema_version
            description = policy.description
        except ValidationError:
            text = child.read_text(encoding="utf-8")
            data = yaml.safe_load(text) or {}
            modes = {
                "mode_b_enabled": bool(data.get("mode_b", {}).get("enabled", False)),
                "scoring_guards_enabled": bool(data.get("scoring_guards", {}).get("enabled", False)),
            }
            gates = {
                "edge_gate": {
                    "metric": "unknown",
                    "op": ">=",
                    "threshold": 0.0,
                    "enabled": False,
                    "fail_reason": data.get("minimum_edge_gate", {}).get("description", ""),
                },
                "cliff_gate": {
                    "metric": "unknown",
                    "op": ">=",
                    "threshold": 0.0,
                    "enabled": False,
                    "fail_reason": data.get("cliff_gate", {}).get("description", ""),
                },
            }
            entry_hash = f"sha256:{hashlib.sha256(text.encode('utf-8')).hexdigest()}"
            name = data.get("name") or data.get("description") or child.stem
            version = str(data.get("schema_version") or data.get("version") or "1.0")
            description = data.get("description", "")

        entry = PolicyRegistryEntry(
            selector=selector,
            name=name,
            version=version,
            hash=entry_hash,
            source=str(child.relative_to(repo_root)),
            resolved_source=str(child.resolve()),
            modes=modes,
            gates=gates,
            description=description,
        )
        entries.append(entry)

    def sort_key(e: PolicyRegistryEntry):
        if e.selector == "default":
            return (0, e.selector)
        if e.selector == "red_team":
            return (1, e.selector)
        return (2, e.selector)

    return sorted(entries, key=sort_key)
