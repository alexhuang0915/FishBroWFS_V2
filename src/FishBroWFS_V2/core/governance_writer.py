"""Governance writer for decision artifacts.

Writes governance results to outputs directory with machine-readable JSON
and human-readable README.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from FishBroWFS_V2.core.governance_schema import GovernanceReport
from FishBroWFS_V2.core.schemas.governance import Decision
from FishBroWFS_V2.core.run_id import make_run_id


def write_governance_artifacts(
    governance_dir: Path,
    report: GovernanceReport,
) -> None:
    """
    Write governance artifacts to directory.
    
    Creates:
    - governance.json: Machine-readable governance report
    - README.md: Human-readable summary
    - evidence_index.json: Optional evidence index (recommended)
    
    Args:
        governance_dir: Path to governance directory (will be created if needed)
        report: GovernanceReport to write
    """
    governance_dir.mkdir(parents=True, exist_ok=True)
    
    # Write governance.json (machine-readable SSOT)
    governance_dict = report.to_dict()
    governance_path = governance_dir / "governance.json"
    with governance_path.open("w", encoding="utf-8") as f:
        json.dump(
            governance_dict,
            f,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        f.write("\n")
    
    # Write README.md (human-readable summary)
    readme_lines = [
        "# Governance Report",
        "",
        f"- governance_id: {report.metadata.get('governance_id')}",
        f"- season: {report.metadata.get('season')}",
        f"- created_at: {report.metadata.get('created_at')}",
        f"- git_sha: {report.metadata.get('git_sha')}",
        "",
        "## Decision Summary",
        "",
    ]
    
    decisions = report.metadata.get("decisions", {})
    readme_lines.extend([
        f"- KEEP: {decisions.get('KEEP', 0)}",
        f"- FREEZE: {decisions.get('FREEZE', 0)}",
        f"- DROP: {decisions.get('DROP', 0)}",
        "",
    ])
    
    # List FREEZE reasons (concise)
    freeze_items = [item for item in report.items if item.decision is Decision.FREEZE]
    if freeze_items:
        readme_lines.extend([
            "## FREEZE Reasons",
            "",
        ])
        for item in freeze_items:
            reasons_str = "; ".join(item.reasons)
            readme_lines.append(f"- {item.candidate_id}: {reasons_str}")
        readme_lines.append("")
    
    # Subsample/params_effective summary
    readme_lines.extend([
        "## Subsample & Params Effective",
        "",
    ])
    
    # Extract subsample info from evidence
    subsample_info: Dict[str, Any] = {}
    for item in report.items:
        for ev in item.evidence:
            stage = ev.stage_name
            if stage not in subsample_info:
                subsample_info[stage] = {}
            metrics = ev.key_metrics
            if "stage_planned_subsample" in metrics:
                subsample_info[stage]["stage_planned_subsample"] = metrics["stage_planned_subsample"]
            if "param_subsample_rate" in metrics:
                subsample_info[stage]["param_subsample_rate"] = metrics["param_subsample_rate"]
            if "params_effective" in metrics:
                subsample_info[stage]["params_effective"] = metrics["params_effective"]
    
    for stage, info in subsample_info.items():
        readme_lines.append(f"### {stage}")
        if "stage_planned_subsample" in info:
            readme_lines.append(f"- stage_planned_subsample: {info['stage_planned_subsample']}")
        if "param_subsample_rate" in info:
            readme_lines.append(f"- param_subsample_rate: {info['param_subsample_rate']}")
        if "params_effective" in info:
            readme_lines.append(f"- params_effective: {info['params_effective']}")
        readme_lines.append("")
    
    readme = "\n".join(readme_lines)
    readme_path = governance_dir / "README.md"
    readme_path.write_text(readme, encoding="utf-8")
    
    # Write evidence_index.json (optional but recommended)
    evidence_index = {
        "governance_id": report.metadata.get("governance_id"),
        "evidence_by_candidate": {
            item.candidate_id: [
                {
                    "run_id": ev.run_id,
                    "stage_name": ev.stage_name,
                    "artifact_paths": ev.artifact_paths,
                }
                for ev in item.evidence
            ]
            for item in report.items
        },
    }
    evidence_index_path = governance_dir / "evidence_index.json"
    with evidence_index_path.open("w", encoding="utf-8") as f:
        json.dump(
            evidence_index,
            f,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        f.write("\n")
