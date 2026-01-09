
"""Portfolio artifacts writer.

Phase 8/11:
- Single source of truth: PortfolioSpec (dataclass) in spec.py
- Writer is IO-only: write portfolio_spec.json + portfolio_manifest.json + README.md
"""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .spec import PortfolioSpec


def _utc_now_z() -> str:
    """Return UTC timestamp ending with 'Z'."""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _json_dump(path: Path, obj: Any) -> None:
    path.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _spec_to_dict(spec: PortfolioSpec) -> dict:
    """Convert PortfolioSpec to a JSON-serializable dict deterministically."""
    if is_dataclass(spec):
        return asdict(spec)

    # Fallback if spec ever becomes pydantic-like
    if hasattr(spec, "model_dump"):
        return spec.model_dump()  # type: ignore[no-any-return]
    if hasattr(spec, "dict"):
        return spec.dict()  # type: ignore[no-any-return]

    raise TypeError(f"Unsupported spec type for serialization: {type(spec)}")


def _render_readme_md(*, spec: PortfolioSpec, manifest: dict) -> str:
    """Render README.md content that satisfies test contracts.
    
    Required sections (order matters for readability):
    # Portfolio: {portfolio_id}
    ## Purpose
    ## Inputs
    ## Legs
    ## Summary
    ## Reproducibility
    ## Files
    ## Warnings (optional but kept for compatibility)
    """
    portfolio_id = manifest.get("portfolio_id", getattr(spec, "portfolio_id", ""))
    season = manifest.get("season", "")

    inputs = manifest.get("inputs", {}) or {}
    counts = manifest.get("counts", {}) or {}
    warnings = manifest.get("warnings", {}) or {}

    decisions_log_path = inputs.get("decisions_log_path", "")
    decisions_log_sha1 = inputs.get("decisions_log_sha1", "")
    research_index_path = inputs.get("research_index_path", "")
    research_index_sha1 = inputs.get("research_index_sha1", "")

    total_decisions = counts.get("total_decisions", 0)
    keep_decisions = counts.get("keep_decisions", 0)
    num_legs_final = counts.get("num_legs_final", len(getattr(spec, "legs", []) or []))
    symbols_allowlist = manifest.get("symbols_allowlist", [])

    lines: list[str] = []
    lines.append(f"# Portfolio: {portfolio_id}")
    lines.append("")
    lines.append("## Purpose")
    lines.append(
        "This folder contains an **executable portfolio specification** generated from Research decisions "
        "(append-only decisions.log). It is designed to be deterministic and auditable."
    )
    lines.append("")

    lines.append("## Inputs")
    lines.append(f"- season: `{season}`")
    lines.append(f"- decisions_log_path: `{decisions_log_path}`")
    lines.append(f"- decisions_log_sha1: `{decisions_log_sha1}`")
    lines.append(f"- research_index_path: `{research_index_path}`")
    lines.append(f"- research_index_sha1: `{research_index_sha1}`")
    lines.append(f"- symbols_allowlist: `{symbols_allowlist}`")
    lines.append("")

    lines.append("## Legs")
    legs = getattr(spec, "legs", None) or []
    if legs:
        lines.append("| symbol | timeframe_min | session_profile | strategy_id | strategy_version | enabled | leg_id |")
        lines.append("|---|---:|---|---|---|---|---|")
        for leg in legs:
            # Support both dataclass and dict-like legs
            symbol = getattr(leg, "symbol", None) if not isinstance(leg, dict) else leg.get("symbol")
            timeframe_min = getattr(leg, "timeframe_min", None) if not isinstance(leg, dict) else leg.get("timeframe_min")
            session_profile = getattr(leg, "session_profile", None) if not isinstance(leg, dict) else leg.get("session_profile")
            strategy_id = getattr(leg, "strategy_id", None) if not isinstance(leg, dict) else leg.get("strategy_id")
            strategy_version = getattr(leg, "strategy_version", None) if not isinstance(leg, dict) else leg.get("strategy_version")
            enabled = getattr(leg, "enabled", None) if not isinstance(leg, dict) else leg.get("enabled")
            leg_id = getattr(leg, "leg_id", None) if not isinstance(leg, dict) else leg.get("leg_id")
            
            lines.append(
                f"| {symbol} | {timeframe_min} | {session_profile} | "
                f"{strategy_id} | {strategy_version} | {enabled} | {leg_id} |"
            )
    else:
        lines.append("_No legs (empty portfolio)._")
    lines.append("")

    lines.append("## Summary")
    lines.append(f"- portfolio_id: `{portfolio_id}`")
    lines.append(f"- version: `{getattr(spec, 'version', '')}`")
    lines.append(f"- total_decisions: `{total_decisions}`")
    lines.append(f"- keep_decisions: `{keep_decisions}`")
    lines.append(f"- num_legs_final: `{num_legs_final}`")
    lines.append("")

    lines.append("## Reproducibility")
    lines.append("To reproduce this portfolio exactly, you must use the same inputs and ordering rules:")
    lines.append("- decisions.log is append-only; **last decision wins** per run_id.")
    lines.append("- legs are filtered by symbols_allowlist.")
    lines.append("- legs are sorted deterministically before portfolio_id generation.")
    lines.append("- the input digests above (sha1) must match.")
    lines.append("")

    lines.append("## Files")
    lines.append("- `portfolio_spec.json`")
    lines.append("- `portfolio_manifest.json`")
    lines.append("- `README.md`")
    lines.append("")

    # Optional: keep warnings section for compatibility
    lines.append("## Warnings")
    lines.append(f"- missing_run_ids: {warnings.get('missing_run_ids', [])}")
    lines.append("")

    return "\n".join(lines)


def write_portfolio_artifacts(
    *,
    outputs_root: Path,
    season: str,
    spec: PortfolioSpec,
    manifest: dict,
) -> Path:
    """Write portfolio artifacts to outputs/seasons/{season}/portfolio/{portfolio_id}/

    Contract:
    - IO-only
    - Deterministic file content given (spec, manifest) except generated_at if caller omitted it
    """
    portfolio_id = getattr(spec, "portfolio_id", None)
    if not portfolio_id or not str(portfolio_id).strip():
        raise ValueError("spec.portfolio_id must be non-empty")

    out_dir = outputs_root / "seasons" / season / "portfolio" / str(portfolio_id)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Ensure generated_at exists
    if "generated_at" not in manifest or not str(manifest.get("generated_at", "")).strip():
        manifest = dict(manifest)
        manifest["generated_at"] = _utc_now_z()

    spec_dict = _spec_to_dict(spec)

    _json_dump(out_dir / "portfolio_spec.json", spec_dict)
    _json_dump(out_dir / "portfolio_manifest.json", manifest)

    readme = _render_readme_md(spec=spec, manifest=manifest)
    (out_dir / "README.md").write_text(readme, encoding="utf-8")

    return out_dir


