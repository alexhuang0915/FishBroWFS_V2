"""
Deterministic reporting helpers for governance and scoring artifacts.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Tuple


def _current_iso_timestamp() -> str:
    """Return UTC timestamp formatted as YYYY-MM-DDTHH:MM:SSZ."""
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _write_json(path: Path, data: Dict[str, Any]) -> None:
    """Write JSON file with canonical formatting."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True, ensure_ascii=False)


def write_governance_and_scoring_artifacts(
    *,
    job_id: str,
    out_dir: Path,
    inputs: Dict[str, Any],
    raw: Dict[str, Any],
    final: Dict[str, Any],
    guards: Dict[str, Any],
    governance: Dict[str, Any],
) -> Tuple[Path, Path]:
    """
    Emit governance summary and scoring breakdown artifacts for a WFS job.

    The files are written under `out_dir`, which is expected to be
    `outputs/jobs/<job_id>/`.
    """
    created_at = _current_iso_timestamp()

    note_entries = []
    note_entries.extend(governance.get("notes", []))
    note_entries.extend(guards.get("notes", []))

    summary_payload: Dict[str, Any] = {
        "schema_version": "1.0",
        "job_id": job_id,
        "created_at": created_at,
        "policy_enforced": governance.get("policy_enforced", False),
        "compliance_passed": governance.get("compliance_passed", True),
        "mode": governance.get("mode", {}),
        "gates": governance.get("gates", {}),
        "inputs": governance.get("inputs", inputs),
        "metrics": governance.get("metrics", raw),
        "links": governance.get("links", {"scoring_breakdown": "scoring_breakdown.json"}),
    }

    breakdown_payload: Dict[str, Any] = {
        "schema_version": "1.0",
        "job_id": job_id,
        "created_at": created_at,
        "final": final,
        "raw": raw,
        "guards": {
            "edge_gate": guards.get("edge_gate", {}),
            "cliff_gate": guards.get("cliff_gate", {}),
        },
        "notes": note_entries,
    }

    summary_path = out_dir / "governance_summary.json"
    scoring_path = out_dir / "scoring_breakdown.json"

    _write_json(summary_path, summary_payload)
    _write_json(scoring_path, breakdown_payload)

    return summary_path, scoring_path
