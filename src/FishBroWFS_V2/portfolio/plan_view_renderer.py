
"""Plan view renderer for generating human-readable portfolio plan views with hardening guarantees.

Features:
- Zero-write guarantee for read paths
- Tamper evidence via hash chains
- Idempotent writes with mtime preservation
- Controlled mutation scope (only 4 view files)
"""
from __future__ import annotations

import hashlib
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional

from FishBroWFS_V2.contracts.portfolio.plan_models import PortfolioPlan, SourceRef
from FishBroWFS_V2.contracts.portfolio.plan_view_models import PortfolioPlanView
from FishBroWFS_V2.control.artifacts import canonical_json_bytes, compute_sha256, write_json_atomic
from FishBroWFS_V2.utils.write_scope import create_plan_view_scope


def _compute_inputs_sha256(plan_dir: Path) -> Dict[str, str]:
    """Compute SHA256 of plan package files that exist.
    
    Returns:
        Dict mapping filename to sha256 for files that exist:
        - portfolio_plan.json
        - plan_manifest.json
        - plan_metadata.json
        - plan_checksums.json
    """
    inputs = {}
    plan_files = [
        "portfolio_plan.json",
        "plan_manifest.json",
        "plan_metadata.json",
        "plan_checksums.json",
    ]
    
    for filename in plan_files:
        file_path = plan_dir / filename
        if file_path.exists():
            try:
                sha256 = compute_sha256(file_path.read_bytes())
                inputs[filename] = sha256
            except OSError:
                # Skip if cannot read
                pass
    
    return inputs


def _write_if_changed(path: Path, content_bytes: bytes) -> bool:
    """Write bytes to file only if content differs.
    
    Args:
        path: Target file path.
        content_bytes: Bytes to write.
    
    Returns:
        True if file was written (content changed), False if unchanged.
    """
    if path.exists():
        existing_bytes = path.read_bytes()
        if existing_bytes == content_bytes:
            # Content identical, preserve mtime
            return False
    
    # Write atomically using temp file
    with tempfile.NamedTemporaryFile(
        mode="wb",
        dir=path.parent,
        prefix=f".{path.name}.tmp.",
        delete=False,
    ) as f:
        f.write(content_bytes)
        tmp_path = Path(f.name)
    
    try:
        tmp_path.replace(path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise
    
    return True


def render_plan_view(plan: PortfolioPlan, top_n: int = 50) -> PortfolioPlanView:
    """Render human-readable view from portfolio plan.
    
    This is a pure function that does NOT write to disk.
    
    Args:
        plan: PortfolioPlan instance.
        top_n: Number of top candidates to include.
    
    Returns:
        PortfolioPlanView with human-readable representation.
    """
    # Sort candidates by weight descending
    weight_map = {w.candidate_id: w.weight for w in plan.weights}
    candidates_with_weights = []
    
    for candidate in plan.universe:
        weight = weight_map.get(candidate.candidate_id, 0.0)
        candidates_with_weights.append((candidate, weight))
    
    # Sort by weight descending
    candidates_with_weights.sort(key=lambda x: x[1], reverse=True)
    
    # Prepare top candidates
    top_candidates = []
    for candidate, weight in candidates_with_weights[:top_n]:
        top_candidates.append({
            "candidate_id": candidate.candidate_id,
            "strategy_id": candidate.strategy_id,
            "dataset_id": candidate.dataset_id,
            "score": candidate.score,
            "weight": weight,
            "season": candidate.season,
            "source_batch": candidate.source_batch,
            "source_export": candidate.source_export,
        })
    
    # Prepare source info
    source_info = {
        "season": plan.source.season,
        "export_name": plan.source.export_name,
        "export_manifest_sha256": plan.source.export_manifest_sha256,
        "candidates_sha256": plan.source.candidates_sha256,
    }
    
    # Prepare config summary
    config_summary = {}
    if isinstance(plan.config, dict):
        config_summary = {
            "max_per_strategy": plan.config.get("max_per_strategy"),
            "max_per_dataset": plan.config.get("max_per_dataset"),
            "min_weight": plan.config.get("min_weight"),
            "max_weight": plan.config.get("max_weight"),
            "bucket_by": plan.config.get("bucket_by"),
        }
    
    # Prepare universe stats
    universe_stats = {
        "total_candidates": plan.summaries.total_candidates,
        "total_weight": plan.summaries.total_weight,
        "num_selected": len(plan.weights),
        "concentration_herfindahl": plan.summaries.concentration_herfindahl,
    }
    
    # Prepare weight distribution
    weight_distribution = {
        "min_weight": min(w.weight for w in plan.weights) if plan.weights else 0.0,
        "max_weight": max(w.weight for w in plan.weights) if plan.weights else 0.0,
        "mean_weight": sum(w.weight for w in plan.weights) / len(plan.weights) if plan.weights else 0.0,
        "weight_std": None,  # Could compute if needed
    }
    
    # Prepare constraints report
    constraints_report = {
        "max_per_strategy_truncated": plan.constraints_report.max_per_strategy_truncated,
        "max_per_dataset_truncated": plan.constraints_report.max_per_dataset_truncated,
        "max_weight_clipped": plan.constraints_report.max_weight_clipped,
        "min_weight_clipped": plan.constraints_report.min_weight_clipped,
        "renormalization_applied": plan.constraints_report.renormalization_applied,
        "renormalization_factor": plan.constraints_report.renormalization_factor,
    }
    
    return PortfolioPlanView(
        plan_id=plan.plan_id,
        generated_at_utc=plan.generated_at_utc,
        source=source_info,
        config_summary=config_summary,
        universe_stats=universe_stats,
        weight_distribution=weight_distribution,
        top_candidates=top_candidates,
        constraints_report=constraints_report,
        metadata={
            "render_timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "top_n": top_n,
            "view_version": "1.0",
        },
    )


def write_plan_view_files(plan_dir: Path, view: PortfolioPlanView) -> None:
    """
    Controlled mutation only:
      - plan_view.json
      - plan_view.md
      - plan_view_checksums.json
      - plan_view_manifest.json
    
    Idempotent + atomic.
    """
    # Create write scope for plan view files
    scope = create_plan_view_scope(plan_dir)
    
    # Helper to write a file with scope validation
    def write_scoped(rel_path: str, content_bytes: bytes) -> bool:
        scope.assert_allowed_rel(rel_path)
        return _write_if_changed(plan_dir / rel_path, content_bytes)
    
    # 1. Write plan_view.json
    view_json_bytes = canonical_json_bytes(view.model_dump())
    write_scoped("plan_view.json", view_json_bytes)
    
    # 2. Write plan_view.md (markdown summary)
    md_content = _generate_markdown(view)
    md_bytes = md_content.encode("utf-8")
    write_scoped("plan_view.md", md_bytes)
    
    # 3. Compute checksums for view files
    view_files = ["plan_view.json", "plan_view.md"]
    checksums = {}
    for filename in view_files:
        file_path = plan_dir / filename
        if file_path.exists():
            checksums[filename] = compute_sha256(file_path.read_bytes())
    
    # Write plan_view_checksums.json
    checksums_bytes = canonical_json_bytes(checksums)
    write_scoped("plan_view_checksums.json", checksums_bytes)
    
    # 4. Build and write manifest
    inputs_sha256 = _compute_inputs_sha256(plan_dir)
    
    # Build files listing (sorted by rel_path asc)
    files = []
    for filename in view_files:
        file_path = plan_dir / filename
        if file_path.exists():
            files.append({
                "rel_path": filename,
                "sha256": compute_sha256(file_path.read_bytes())
            })
    # Also include checksums file itself
    checksums_file = "plan_view_checksums.json"
    checksums_path = plan_dir / checksums_file
    if checksums_path.exists():
        files.append({
            "rel_path": checksums_file,
            "sha256": compute_sha256(checksums_path.read_bytes())
        })
    
    # Sort by rel_path
    files.sort(key=lambda x: x["rel_path"])
    
    # Compute files_sha256 (concatenated hashes)
    concatenated = "".join(f["sha256"] for f in files)
    files_sha256 = compute_sha256(concatenated.encode("utf-8"))
    
    manifest = {
        "manifest_type": "view",
        "manifest_version": "1.0",
        "id": view.plan_id,
        "plan_id": view.plan_id,
        "generated_at_utc": view.generated_at_utc,
        "source": view.source,
        "inputs": inputs_sha256,
        "view_checksums": checksums,
        "view_files": view_files,
        "files": files,
        "files_sha256": files_sha256,
    }
    
    # Compute manifest hash (excluding the hash field)
    manifest_canonical = canonical_json_bytes(manifest)
    manifest_sha256 = compute_sha256(manifest_canonical)
    manifest["manifest_sha256"] = manifest_sha256
    
    # Write manifest
    manifest_bytes = canonical_json_bytes(manifest)
    write_scoped("plan_view_manifest.json", manifest_bytes)


def _generate_markdown(view: PortfolioPlanView) -> str:
    """Generate markdown summary of plan view."""
    lines = []
    
    lines.append(f"# Portfolio Plan: {view.plan_id}")
    lines.append(f"**Generated at:** {view.generated_at_utc}")
    lines.append("")
    
    lines.append("## Source")
    lines.append(f"- Season: {view.source.get('season', 'N/A')}")
    lines.append(f"- Export: {view.source.get('export_name', 'N/A')}")
    lines.append(f"- Manifest SHA256: `{view.source.get('export_manifest_sha256', 'N/A')[:16]}...`")
    lines.append("")
    
    lines.append("## Configuration Summary")
    for key, value in view.config_summary.items():
        lines.append(f"- {key}: {value}")
    lines.append("")
    
    lines.append("## Universe Statistics")
    lines.append(f"- Total candidates: {view.universe_stats.get('total_candidates', 0)}")
    lines.append(f"- Selected candidates: {view.universe_stats.get('num_selected', 0)}")
    lines.append(f"- Total weight: {view.universe_stats.get('total_weight', 0.0):.4f}")
    lines.append(f"- Concentration (Herfindahl): {view.universe_stats.get('concentration_herfindahl', 0.0):.4f}")
    lines.append("")
    
    lines.append("## Weight Distribution")
    lines.append(f"- Min weight: {view.weight_distribution.get('min_weight', 0.0):.6f}")
    lines.append(f"- Max weight: {view.weight_distribution.get('max_weight', 0.0):.6f}")
    lines.append(f"- Mean weight: {view.weight_distribution.get('mean_weight', 0.0):.6f}")
    lines.append("")
    
    lines.append("## Top Candidates")
    lines.append("| Rank | Candidate ID | Strategy | Dataset | Score | Weight |")
    lines.append("|------|-------------|----------|---------|-------|--------|")
    
    for i, candidate in enumerate(view.top_candidates[:20], 1):
        lines.append(
            f"| {i} | {candidate['candidate_id'][:12]}... | "
            f"{candidate['strategy_id']} | {candidate['dataset_id']} | "
            f"{candidate['score']:.3f} | {candidate['weight']:.6f} |"
        )
    
    if len(view.top_candidates) > 20:
        lines.append(f"... and {len(view.top_candidates) - 20} more candidates")
    
    lines.append("")
    
    lines.append("## Constraints Report")
    if view.constraints_report.get("max_per_strategy_truncated"):
        lines.append(f"- Strategies truncated: {len(view.constraints_report['max_per_strategy_truncated'])}")
    if view.constraints_report.get("max_per_dataset_truncated"):
        lines.append(f"- Datasets truncated: {len(view.constraints_report['max_per_dataset_truncated'])}")
    if view.constraints_report.get("max_weight_clipped"):
        lines.append(f"- Max weight clipped: {len(view.constraints_report['max_weight_clipped'])} candidates")
    if view.constraints_report.get("min_weight_clipped"):
        lines.append(f"- Min weight clipped: {len(view.constraints_report['min_weight_clipped'])} candidates")
    
    if view.constraints_report.get("renormalization_applied"):
        lines.append(f"- Renormalization applied: Yes (factor: {view.constraints_report.get('renormalization_factor', 1.0):.6f})")
    
    lines.append("")
    lines.append("---")
    lines.append(f"*View generated at {view.metadata.get('render_timestamp_utc', 'N/A')}*")
    
    return "\n".join(lines)


