
"""Artifact writer for unified run output.

Provides consistent artifact structure for all runs, with mandatory
subsample rate visibility.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from core.winners_schema import build_winners_v2_dict, is_winners_v2
from gui.services.ranking_explain_builder import (
    build_and_write_ranking_explain_report,
    RankingExplainContext,
)
from wfs.scoring_guards import ScoringGuardConfig


def _write_json(path: Path, obj: Any) -> None:
    """
    Write object to JSON file with fixed format.
    
    Uses sort_keys=True and fixed separators for reproducibility.
    
    Args:
        path: Path to JSON file
        obj: Object to serialize
    """
    path.write_text(
        json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def write_run_artifacts(
    run_dir: Path,
    manifest: Dict[str, Any],
    config_snapshot: Dict[str, Any],
    metrics: Dict[str, Any],
    winners: Dict[str, Any] | None = None,
    plateau_candidates: List[Dict[str, Any]] | None = None,
    warnings: List[str] | None = None,
) -> None:
    """
    Write all standard artifacts for a run.
    
    Creates the following files:
    - manifest.json: Full AuditSchema data
    - config_snapshot.json: Original/normalized config
    - metrics.json: Performance metrics
    - winners.json: Top-K results (v2 schema only)
    - README.md: Human-readable summary
    - logs.txt: Execution logs (empty initially)
    
    Args:
        run_dir: Run directory path (will be created if needed)
        manifest: Manifest data (AuditSchema as dict)
        config_snapshot: Configuration snapshot
        metrics: Performance metrics (must include param_subsample_rate visibility)
        winners: Optional winners dict. If None, uses empty v2 schema.
            Must follow v2 schema (see core.winners_schema).
            Legacy winners are no longer supported.
        plateau_candidates: Optional list of broad candidates for plateau stage.
        warnings: Optional list of runtime warnings (ranking explain reason codes).
    """
    run_dir.mkdir(parents=True, exist_ok=True)
    
    # Write manifest.json (full AuditSchema)
    _write_json(run_dir / "manifest.json", manifest)
    
    # Write config_snapshot.json
    _write_json(run_dir / "config_snapshot.json", config_snapshot)
    
    # Write metrics.json (must include param_subsample_rate visibility)
    _write_json(run_dir / "metrics.json", metrics)
    
    # Write winners.json (v2 schema only)
    if winners is None:
        winners = build_winners_v2_dict(
            stage_name=metrics.get("stage_name", "unknown"),
            run_id=manifest.get("run_id", "unknown"),
            topk=[],
        )
    
    # Ensure winners are v2 schema; legacy winners are not allowed.
    if not is_winners_v2(winners):
        raise ValueError(
            f"Winners dict does not conform to v2 schema. "
            f"Legacy winners conversion removed. "
            f"Got keys: {list(winners.keys())}"
        )
    
    _write_json(run_dir / "winners.json", winners)
    
    # Write plateau_candidates.json if provided
    if plateau_candidates:
        plateau_artifact = {
            "plateau_candidates": plateau_candidates,
            "metadata": {
                "source_stage": metrics.get("stage_name", "unknown"),
                "count": len(plateau_candidates),
                "schema_version": "v1",
            }
        }
        _write_json(run_dir / "plateau_candidates.json", plateau_artifact)
    
    # Write README.md (human-readable summary)
    # Must prominently display param_subsample_rate
    readme_lines = [
        "# FishBroWFS_V2 Run",
        "",
        f"- run_id: {manifest.get('run_id')}",
        f"- git_sha: {manifest.get('git_sha')}",
        f"- param_subsample_rate: {manifest.get('param_subsample_rate')}",
        f"- season: {manifest.get('season')}",
        f"- dataset_id: {manifest.get('dataset_id')}",
        f"- bars: {manifest.get('bars')}",
        f"- params_total: {manifest.get('params_total')}",
        f"- params_effective: {manifest.get('params_effective')}",
        f"- config_hash: {manifest.get('config_hash')}",
    ]
    
    # Add OOM gate information if present in metrics
    if "oom_gate_action" in metrics:
        readme_lines.extend([
            "",
            "## OOM Gate",
            "",
            f"- action: {metrics.get('oom_gate_action')}",
            f"- reason: {metrics.get('oom_gate_reason')}",
            f"- mem_est_mb: {metrics.get('mem_est_mb', 0):.1f}",
            f"- mem_limit_mb: {metrics.get('mem_limit_mb', 0):.1f}",
            f"- ops_est: {metrics.get('ops_est', 0)}",
        ])
        
        # If auto-downsample occurred, show original and final
        if metrics.get("oom_gate_action") == "AUTO_DOWNSAMPLE":
            readme_lines.extend([
                f"- original_subsample: {metrics.get('oom_gate_original_subsample', 0)}",
                f"- final_subsample: {metrics.get('oom_gate_final_subsample', 0)}",
            ])
    
    readme = "\n".join(readme_lines)
    (run_dir / "README.md").write_text(readme, encoding="utf-8")
    
    # Write logs.txt (empty initially)
    (run_dir / "logs.txt").write_text("", encoding="utf-8")
    
    # DP6 Phase I: Generate ranking explain artifact if winners exist or if explicit warnings
    if (winners and winners.get("topk")) or warnings:
        try:
            # Determine context based on stage name
            stage_name = metrics.get("stage_name", "").lower()
            if "final" in stage_name or "selection" in stage_name:
                context = RankingExplainContext.FINAL_SELECTION
            else:
                context = RankingExplainContext.CANDIDATE
            
            # Use default scoring guard config
            scoring_config = ScoringGuardConfig()
            
            # Build and write ranking explain report
            success = build_and_write_ranking_explain_report(
                job_dir=run_dir,
                context=context,
                scoring_guard_cfg=scoring_config,

                warnings=warnings,
            )
            
            if not success:
                # Log warning but don't fail the artifact writing
                warning_path = run_dir / "ranking_explain_warning.txt"
                warning_path.write_text(
                    "Failed to generate ranking_explain_report.json artifact\n",
                    encoding="utf-8"
                )
        except Exception as e:
            # Catch all exceptions to ensure artifact writing doesn't fail
            # due to ranking explain generation issues
            error_path = run_dir / "ranking_explain_error.txt"
            error_path.write_text(
                f"Error generating ranking_explain_report.json: {str(e)}\n",
                encoding="utf-8"
            )


