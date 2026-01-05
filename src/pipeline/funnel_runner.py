
"""Funnel runner - orchestrates stage execution and artifact writing.

Runs funnel pipeline stages sequentially, writing artifacts for each stage.
Each stage gets its own run_id and run directory.
"""

from __future__ import annotations

import subprocess
# Subprocess usage: git info collection for audit trail.
# NOT UI ENTRYPOINT – only used by research pipeline via Supervisor jobs.
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from core.artifacts import write_run_artifacts
from core.audit_schema import AuditSchema, compute_params_effective
from core.config_hash import stable_config_hash
from core.config_snapshot import make_config_snapshot
from core.oom_gate import decide_oom_action
from core.paths import ensure_run_dir
from core.run_id import make_run_id
from core.winners_schema import WinnerItemV2, build_winners_v2_dict, is_winners_v2
from data.session.tzdb_info import get_tzdb_info
from pipeline.funnel_plan import build_default_funnel_plan
from pipeline.funnel_schema import FunnelResultIndex, FunnelStageIndex
from pipeline.runner_adapter import run_stage_job

# Phase 14: Governance observability via HTTP pull
try:
    from control.run_status import (
        set_running,
        update_status,
        set_done,
        set_failed,
        set_canceled,
    )
    RUN_STATUS_AVAILABLE = True
except ImportError:
    RUN_STATUS_AVAILABLE = False


def _convert_legacy_winners_to_v2(
    legacy_winners: dict,
    stage_name: str,
    run_id: str,
) -> dict:
    """
    Convert legacy winners (v1 schema) to v2 schema.
    
    Legacy format:
        {"topk": [{"param_id": ..., "proxy_value": ...}], "notes": {"schema": "v1", ...}}
        or {"topk": [{"param_id": ..., "net_profit": ..., "trades": ..., "max_dd": ...}], ...}
    
    Returns:
        Winners dict with v2 schema.
    """
    topk = legacy_winners.get("topk", [])
    notes = legacy_winners.get("notes", {})
    
    v2_items = []
    for item in topk:
        param_id = item.get("param_id")
        # Determine score: proxy_value or net_profit
        score = item.get("proxy_value", item.get("net_profit", 0.0))
        # Build metrics dict with all fields from item
        metrics = {k: v for k, v in item.items() if k != "param_id"}
        # Build source dict
        source = {
            "param_id": param_id,
            "run_id": run_id,
            "stage_name": stage_name,
        }
        v2_items.append(
            WinnerItemV2(
                candidate_id=f"unknown:{param_id}" if param_id is not None else "unknown:unknown",
                strategy_id="unknown",
                symbol="UNKNOWN",
                timeframe="UNKNOWN",
                params={},
                score=float(score),
                metrics=metrics,
                source=source,
            )
        )
    
    # Preserve any extra notes (excluding schema)
    extra_notes = {k: v for k, v in notes.items() if k != "schema"}
    
    return build_winners_v2_dict(
        stage_name=stage_name,
        run_id=run_id,
        topk=v2_items,
        notes=extra_notes,
    )


def _get_git_info(repo_root: Path | None = None) -> tuple[str, bool]:
    """
    Get git SHA and dirty status.
    
    Args:
        repo_root: Optional path to repo root
        
    Returns:
        Tuple of (git_sha, dirty_repo)
    """
    if repo_root is None:
        repo_root = Path.cwd()
    
    try:
        # Get git SHA (short, 12 chars)
        result = subprocess.run(
            ["git", "rev-parse", "--short=12", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        git_sha = result.stdout.strip()
        
        # Check if repo is dirty
        result_status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
        dirty_repo = len(result_status.stdout.strip()) > 0
        
        return git_sha, dirty_repo
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return "unknown", True


def run_funnel(cfg: dict, outputs_root: Path) -> FunnelResultIndex:
    """
    Run funnel pipeline with three stages.
    
    Each stage:
    1. Generates new run_id
    2. Creates run directory
    3. Builds AuditSchema
    4. Runs stage job (via adapter)
    5. Writes artifacts
    
    Args:
        cfg: Configuration dictionary containing:
            - season: Season identifier
            - dataset_id: Dataset identifier
            - bars: Number of bars
            - params_total: Total parameters
            - param_subsample_rate: Base subsample rate for Stage 0
            - open_, high, low, close: OHLC arrays
            - params_matrix: Parameter matrix
            - commission, slip, order_qty: Trading parameters
            - topk_stage0, topk_stage1: Optional top-K counts
            - git_sha, dirty_repo, created_at: Optional audit fields
        outputs_root: Root outputs directory
    
    Returns:
        FunnelResultIndex with plan and stage execution indices
    """
    # Phase 14: Set initial run status
    if RUN_STATUS_AVAILABLE:
        try:
            # Create a composite run_id for the entire funnel
            from core.run_id import make_run_id as make_composite_id
            funnel_run_id = make_composite_id(prefix="funnel")
            set_running(
                run_id=funnel_run_id,
                message=f"Starting funnel: {cfg.get('season', 'unknown')} / {cfg.get('dataset_id', 'unknown')}"
            )
        except Exception:
            # If status update fails, continue without it (best-effort)
            pass
    
    # Build funnel plan
    plan = build_default_funnel_plan(cfg)
    
    # Get git info if not provided
    git_sha = cfg.get("git_sha")
    dirty_repo = cfg.get("dirty_repo")
    if git_sha is None or dirty_repo is None:
        repo_root = cfg.get("repo_root")
        if repo_root:
            repo_root = Path(repo_root)
        git_sha, dirty_repo = _get_git_info(repo_root)
    
    created_at = cfg.get("created_at")
    if created_at is None:
        created_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    
    season = cfg["season"]
    dataset_id = cfg["dataset_id"]
    bars = int(cfg["bars"])
    params_total = int(cfg["params_total"])
    
    stage_indices: list[FunnelStageIndex] = []
    prev_winners: list[dict[str, Any]] = []
    
    # Define stage names for status updates
    stage_names = {
        "stage0_coarse": "Stage 0: Coarse exploration",
        "stage1_topk": "Stage 1: Top-K refinement",
        "stage2_confirm": "Stage 2: Full confirmation"
    }
    
    for i, spec in enumerate(plan.stages):
        stage_num = i + 1
        total_stages = len(plan.stages)
        
        # Phase 14: Update status for stage start
        if RUN_STATUS_AVAILABLE:
            try:
                stage_display = stage_names.get(str(spec.name.value), f"Stage {stage_num}")
                progress = int((stage_num - 1) / total_stages * 80)  # 0-80% for stages
                update_status(
                    progress=progress,
                    step="load_data" if stage_num == 1 else "backtest_kernel",
                    message=f"{stage_display}: {spec.param_subsample_rate:.1%} subsample"
                )
            except Exception:
                pass
        # Generate run_id for this stage
        run_id = make_run_id(prefix=str(spec.name.value))
        
        # Create run directory
        run_dir = ensure_run_dir(outputs_root, season, run_id)
        
        # Build stage config (runtime: includes ndarrays for runner_adapter)
        stage_cfg = dict(cfg)
        stage_cfg["stage_name"] = str(spec.name.value)
        stage_cfg["param_subsample_rate"] = float(spec.param_subsample_rate)
        stage_cfg["topk"] = spec.topk
        
        # Pass previous stage winners to Stage2
        if spec.name.value == "stage2_confirm" and prev_winners:
            stage_cfg["prev_stage_winners"] = prev_winners
        
        # OOM Gate: Check memory limits before running stage
        mem_limit_mb = float(cfg.get("mem_limit_mb", 2048.0))
        allow_auto_downsample = cfg.get("allow_auto_downsample", True)
        auto_downsample_step = float(cfg.get("auto_downsample_step", 0.5))
        auto_downsample_min = float(cfg.get("auto_downsample_min", 0.02))
        
        gate_result = decide_oom_action(
            stage_cfg,
            mem_limit_mb=mem_limit_mb,
            allow_auto_downsample=allow_auto_downsample,
            auto_downsample_step=auto_downsample_step,
            auto_downsample_min=auto_downsample_min,
        )
        
        # Handle gate actions
        if gate_result["action"] == "BLOCK":
            # Phase 14: Update status for failure
            if RUN_STATUS_AVAILABLE:
                try:
                    set_failed(f"OOM Gate BLOCKED stage {spec.name.value}: {gate_result['reason']}")
                except Exception:
                    pass
            raise RuntimeError(
                f"OOM Gate BLOCKED stage {spec.name.value}: {gate_result['reason']}"
            )
        
        # Planned subsample for this stage (before gate adjustment)
        planned_subsample = float(spec.param_subsample_rate)
        final_subsample = gate_result["final_subsample"]
        
        # SSOT: Use new_cfg from gate_result (never mutate original stage_cfg)
        stage_cfg = gate_result["new_cfg"]
        
        # Use final_subsample for all calculations
        effective_subsample = final_subsample
        
        # Create sanitized snapshot (for hash and artifacts, excludes ndarrays)
        # Snapshot must reflect final subsample (after auto-downsample if any)
        stage_snapshot = make_config_snapshot(stage_cfg)
        
        # Compute config hash (only on sanitized snapshot)
        config_hash = stable_config_hash(stage_snapshot)
        
        # Compute params_effective with final subsample
        params_effective = compute_params_effective(params_total, effective_subsample)
        
        # Build AuditSchema (must use final subsample)
        audit = AuditSchema(
            run_id=run_id,
            created_at=created_at,
            git_sha=git_sha,
            dirty_repo=bool(dirty_repo),
            param_subsample_rate=effective_subsample,  # Use final subsample
            config_hash=config_hash,
            season=season,
            dataset_id=dataset_id,
            bars=bars,
            params_total=params_total,
            params_effective=params_effective,
            artifact_version="v1",
        )
        
        # Phase 14: Update status for kernel execution
        if RUN_STATUS_AVAILABLE:
            try:
                progress = int((stage_num - 0.5) / total_stages * 80)  # Mid-stage progress
                update_status(
                    progress=progress,
                    step="backtest_kernel",
                    message=f"Running {spec.name.value} kernel"
                )
            except Exception:
                pass
        
        # Run stage job (adapter returns data only, no file I/O)
        # Use stage_cfg which has final subsample (after auto-downsample if any)
        stage_out = run_stage_job(stage_cfg)
        
        # Extract metrics and winners
        stage_metrics = dict(stage_out.get("metrics", {}))
        stage_winners = stage_out.get("winners", {"topk": [], "notes": {"schema": "v1"}})

        # Ensure metrics include required fields
        stage_metrics["param_subsample_rate"] = effective_subsample  # Use final subsample
        stage_metrics["params_effective"] = params_effective
        stage_metrics["params_total"] = params_total
        stage_metrics["bars"] = bars
        stage_metrics["stage_name"] = str(spec.name.value)

        # Add OOM gate fields (mandatory for audit)
        stage_metrics["oom_gate_action"] = gate_result["action"]
        stage_metrics["oom_gate_reason"] = gate_result["reason"]
        stage_metrics["mem_est_mb"] = gate_result["estimates"]["mem_est_mb"]
        stage_metrics["mem_limit_mb"] = mem_limit_mb
        stage_metrics["ops_est"] = gate_result["estimates"]["ops_est"]

        # Record planned subsample (before gate adjustment)
        stage_metrics["stage_planned_subsample"] = planned_subsample

        # If auto-downsample occurred, record original and final subsample
        if gate_result["action"] == "AUTO_DOWNSAMPLE":
            stage_metrics["oom_gate_original_subsample"] = planned_subsample
            stage_metrics["oom_gate_final_subsample"] = final_subsample

        # Save winners for next stage (must be legacy format)
        prev_winners = stage_winners.get("topk", [])

        # Convert stage_winners to v2 if needed
        if not is_winners_v2(stage_winners):
            stage_winners = _convert_legacy_winners_to_v2(
                stage_winners,
                stage_name=str(spec.name.value),
                run_id=run_id,
            )

        # Phase 6.6: Add tzdb metadata to manifest
        manifest_dict = audit.to_dict()
        tzdb_provider, tzdb_version = get_tzdb_info()
        manifest_dict["tzdb_provider"] = tzdb_provider
        manifest_dict["tzdb_version"] = tzdb_version

        # Add data_tz and exchange_tz if available in config
        # These come from session profile if session processing is used
        if "data_tz" in stage_cfg:
            manifest_dict["data_tz"] = stage_cfg["data_tz"]
        if "exchange_tz" in stage_cfg:
            manifest_dict["exchange_tz"] = stage_cfg["exchange_tz"]

        # Phase 7: Add strategy metadata if available
        if "strategy_id" in stage_cfg:
            import json
            import hashlib

            manifest_dict["strategy_id"] = stage_cfg["strategy_id"]

            if "strategy_version" in stage_cfg:
                manifest_dict["strategy_version"] = stage_cfg["strategy_version"]

            if "param_schema" in stage_cfg:
                param_schema = stage_cfg["param_schema"]
                # Compute hash of param_schema
                schema_json = json.dumps(param_schema, sort_keys=True)
                schema_hash = hashlib.sha1(schema_json.encode("utf-8")).hexdigest()
                manifest_dict["param_schema_hash"] = schema_hash

        # Write artifacts (unified artifact system)
        # Use sanitized snapshot (not runtime cfg with ndarrays)
        write_run_artifacts(
            run_dir=run_dir,
            manifest=manifest_dict,
            config_snapshot=stage_snapshot,
            metrics=stage_metrics,
            winners=stage_winners,
        )

        # Record stage index
        stage_indices.append(
            FunnelStageIndex(
                stage=spec.name,
                run_id=run_id,
                run_dir=str(run_dir.relative_to(outputs_root)),
            )
        )
    
    # Phase 14: Update status for successful completion
    if RUN_STATUS_AVAILABLE:
        try:
            set_done("Funnel completed successfully")
        except Exception:
            pass
    
    return FunnelResultIndex(plan=plan, stages=stage_indices)


