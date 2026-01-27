from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional, Callable, Tuple
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from control.supervisor import submit
from control.supervisor.supervisor import Supervisor
from control.supervisor.db import SupervisorDB, get_default_db_path
from control.job_artifacts import get_job_evidence_dir
from core.paths import get_artifacts_root, get_outputs_root

from .run_plan import AutoWfsPlan, auto_runs_root


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def _job_state(db: SupervisorDB, job_id: str) -> str | None:
    row = db.get_job_row(job_id)
    return str(row.state) if row else None


def _wait_jobs(
    *,
    db_path: Path,
    artifacts_root: Path,
    job_ids: list[str],
    max_workers: int,
    tick_interval: float = 0.2,
    timeout_sec: float | None = None,
) -> dict[str, str]:
    db = SupervisorDB(db_path)
    sup = Supervisor(db_path=db_path, max_workers=max_workers, tick_interval=tick_interval, artifacts_root=artifacts_root)
    started = time.time()
    try:
        while True:
            sup.tick()
            sup.reap_children()

            states: dict[str, str] = {}
            done = True
            for jid in job_ids:
                st = _job_state(db, jid) or "UNKNOWN"
                states[jid] = st
                if st not in {"SUCCEEDED", "FAILED", "ABORTED", "REJECTED", "ORPHANED"}:
                    done = False

            if done and not sup.children:
                return states

            if timeout_sec is not None and (time.time() - started) > timeout_sec:
                return states

            time.sleep(tick_interval)
    finally:
        sup.shutdown()


def _run_job_batch_with_retry(
    *,
    db_path: Path,
    artifacts_root: Path,
    max_workers: int,
    timeout_sec: float | None,
    job_configs: List[Tuple[str, Dict[str, Any]]],
    max_retries: int = 1
) -> Tuple[Dict[str, str], List[Dict[str, Any]]]:
    """
    Submits a batch of jobs and retries those that fail with retryable states.
    Returns (final_states, retry_log).
    """
    # Contract: retryable if state is ORPHANED or if it looks like a transient failure.
    # For now, we only retry ORPHANED.
    RETRYABLE_STATES = {"ORPHANED"}
    
    current_configs = list(job_configs)
    all_job_ids = []
    final_states = {}
    retry_log = []
    
    # Track which config index corresponds to which job_id
    config_to_job = {} # config_index -> job_id
    
    for attempt in range(max_retries + 1):
        if not current_configs:
            break
            
        remaining_indices = [i for i in range(len(job_configs)) if job_configs[i] in current_configs]
        batch_job_ids = []
        for config in current_configs:
            jid = submit(config[0], config[1])
            batch_job_ids.append(jid)
            all_job_ids.append(jid)

        # map remaining_indices to these jids
        for i, jid in enumerate(batch_job_ids):
            config_to_job[remaining_indices[i]] = jid

        states = _wait_jobs(
            db_path=db_path,
            artifacts_root=artifacts_root,
            job_ids=batch_job_ids,
            max_workers=max_workers,
            timeout_sec=timeout_sec,
        )
        final_states.update(states)
        
        # Determine what to retry
        next_configs = []
        for idx_in_batch, jid in enumerate(batch_job_ids):
            st = states.get(jid, "UNKNOWN")
            if st in RETRYABLE_STATES and attempt < max_retries:
                config_idx = remaining_indices[idx_in_batch]
                next_configs.append(job_configs[config_idx])
                retry_log.append({
                    "attempt": attempt,
                    "job_id": jid,
                    "state": st,
                    "action": "retry"
                })
        
        current_configs = next_configs
        if not current_configs:
            break
            
    return final_states, retry_log


def run_auto_wfs(
    *,
    plan: AutoWfsPlan,
    dry_run: bool = False,
    timeout_sec: float | None = None,
) -> dict:
    """
    Full automation (deterministic default):
      BUILD_BARS (data1+data2) -> RUN_RESEARCH_WFS -> BUILD_PORTFOLIO_V2 -> (optional) FINALIZE_PORTFOLIO_V1

    Notes:
    - This runs on the local Supervisor DB and will also process any other queued jobs in the same DB.
      Use environment isolation (FISHBRO_OUTPUTS_ROOT/FISHBRO_CACHE_ROOT) if you need a clean queue.
    """
    outputs_root = get_outputs_root()
    artifacts_root = get_artifacts_root()
    db_path = get_default_db_path()

    run_id = f"auto_{plan.season}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    run_dir = auto_runs_root() / run_id

    manifest: dict = {
        "version": "1.0",
        "run_id": run_id,
        "generated_at": _now_utc(),
        "outputs_root": str(outputs_root),
        "artifacts_root": str(artifacts_root),
        "db_path": str(db_path),
        "plan": asdict(plan),
        "steps": [],
    }

    # Dry-run preview (matrix expansion) for fast verification without executing jobs.
    wfs_preview: list[dict] = []
    for strategy_id in plan.strategy_ids:
        for instrument in plan.instrument_ids:
            data2_candidates = plan.data2_candidates_by_instrument.get(instrument) or []
            for tf_min in plan.timeframes_min:
                timeframe = f"{int(tf_min)}m"
                targets = data2_candidates or [None]
                for data2 in targets:
                    wfs_preview.append(
                        {
                            "strategy_id": strategy_id,
                            "instrument": instrument,
                            "timeframe": timeframe,
                            "data2_dataset_id": data2,
                        }
                    )

    manifest["preview"] = {
        "required_datasets": sorted(plan.required_datasets),
        "planned_wfs_job_count": len(wfs_preview),
        "planned_wfs_jobs_head": wfs_preview[:20],
    }

    # Record current queue snapshot for auditability.
    try:
        db = SupervisorDB(db_path)
        with db._connect() as conn:  # type: ignore[attr-defined]
            q = conn.execute("SELECT job_id, job_type FROM jobs WHERE state = 'QUEUED' ORDER BY created_at DESC LIMIT 20").fetchall()
            r = conn.execute("SELECT job_id, job_type FROM jobs WHERE state = 'RUNNING' ORDER BY created_at DESC LIMIT 20").fetchall()
        manifest["queue_snapshot"] = {
            "queued_count": len(q),
            "running_count": len(r),
            "queued_head": [{"job_id": row["job_id"], "job_type": row["job_type"]} for row in q],
            "running_head": [{"job_id": row["job_id"], "job_type": row["job_type"]} for row in r],
        }
    except Exception:
        manifest["queue_snapshot"] = None

    if plan.mode == "llm":
        # Placeholder: LLM mode requires an external provider integration (not implemented here).
        manifest["llm_mode"] = {"enabled": True, "provider": None, "note": "Not implemented; falling back to deterministic orchestration."}
    _write_json(run_dir / "manifest.json", manifest)

    if dry_run:
        manifest["dry_run"] = True
        _write_json(run_dir / "manifest.json", manifest)
        return manifest

    # 1) BUILD_BARS (data1 + data2)
    build_bars_configs = []
    for dataset_id in sorted(plan.required_datasets):
        build_bars_configs.append((
            "BUILD_BARS",
            {
                "season": plan.season,
                "dataset_id": dataset_id,
                "timeframes": plan.timeframes_min,
                "force_rebuild": False,
            }
        ))

    states, retry_log = _run_job_batch_with_retry(
        db_path=db_path,
        artifacts_root=artifacts_root,
        max_workers=plan.max_workers,
        timeout_sec=timeout_sec,
        job_configs=build_bars_configs,
        max_retries=1
    )
    
    manifest["steps"].append({
        "name": "BUILD_BARS", 
        "job_ids": list(states.keys()), 
        "states": states,
        "retry_log": retry_log
    })
    _write_json(run_dir / "manifest.json", manifest)

    # Fail-closed: if any bars job failed, stop here.
    if any(s != "SUCCEEDED" for s in states.values()):
        manifest["ok"] = False
        manifest["error"] = "BUILD_BARS failed"
        
        # If timeout happened, record it
        if timeout_sec is not None and any(st not in {"SUCCEEDED", "FAILED", "ABORTED", "REJECTED", "ORPHANED"} for st in states.values()):
            manifest["error"] = "BUILD_BARS timeout"
            
        _write_json(run_dir / "manifest.json", manifest)
        return manifest

    # 2) RUN_RESEARCH_WFS
    wfs_configs = []
    for strategy_id in plan.strategy_ids:
        for instrument in plan.instrument_ids:
            data2_candidates = plan.data2_candidates_by_instrument.get(instrument) or []
            for tf_min in plan.timeframes_min:
                timeframe = f"{int(tf_min)}m"
                targets = data2_candidates or [None]
                for data2 in targets:
                    params = {
                        "strategy_id": strategy_id,
                        "instrument": instrument,
                        "dataset_id": instrument,
                        "timeframe": timeframe,
                        "start_season": plan.start_season,
                        "end_season": plan.end_season,
                        "season": plan.season,
                        "workers": 1,
                    }
                    if data2:
                        params["data2_dataset_id"] = data2
                    wfs_configs.append(("RUN_RESEARCH_WFS", params))

    wfs_states, wfs_retry_log = _run_job_batch_with_retry(
        db_path=db_path,
        artifacts_root=artifacts_root,
        max_workers=plan.max_workers,
        timeout_sec=timeout_sec,
        job_configs=wfs_configs,
        max_retries=1
    )
    
    manifest["steps"].append({
        "name": "RUN_RESEARCH_WFS", 
        "job_ids": list(wfs_states.keys()), 
        "states": wfs_states,
        "retry_log": wfs_retry_log
    })
    _write_json(run_dir / "manifest.json", manifest)

    if timeout_sec is not None and any(st not in {"SUCCEEDED", "FAILED", "ABORTED", "REJECTED", "ORPHANED"} for st in wfs_states.values()):
        manifest["ok"] = False
        manifest["error"] = "Timeout waiting for WFS jobs"
        _write_json(run_dir / "manifest.json", manifest)
        return manifest

    if timeout_sec is not None and any(st not in {"SUCCEEDED", "FAILED", "ABORTED", "REJECTED", "ORPHANED"} for st in wfs_states.values()):
        manifest["ok"] = False
        manifest["error"] = "Timeout waiting for WFS jobs"
        _write_json(run_dir / "manifest.json", manifest)
        return manifest

    succeeded_wfs = [jid for jid, st in wfs_states.items() if st == "SUCCEEDED"]
    if not succeeded_wfs:
        manifest["ok"] = False
        manifest["error"] = "No WFS jobs succeeded"
        _write_json(run_dir / "manifest.json", manifest)
        return manifest

    # 3) BUILD_PORTFOLIO_V2
    portfolio_job = submit(
        "BUILD_PORTFOLIO_V2",
        {
            "season": plan.season,
            "candidate_run_ids": succeeded_wfs,
            "portfolio_id": f"auto_{run_id}",
        },
    )
    port_states = _wait_jobs(
        db_path=db_path,
        artifacts_root=artifacts_root,
        job_ids=[portfolio_job],
        max_workers=plan.max_workers,
        timeout_sec=timeout_sec,
    )
    manifest["steps"].append({"name": "BUILD_PORTFOLIO_V2", "job_ids": [portfolio_job], "states": port_states})
    _write_json(run_dir / "manifest.json", manifest)

    if port_states.get(portfolio_job) != "SUCCEEDED":
        manifest["ok"] = False
        manifest["error"] = "BUILD_PORTFOLIO_V2 failed"
        _write_json(run_dir / "manifest.json", manifest)
        return manifest

    # 4) Auto selection + finalize (optional)
    if plan.auto_finalize:
        ev = get_job_evidence_dir(portfolio_job)
        rec_txt = ev / "portfolio_recommendations_path.txt"
        if rec_txt.exists():
            rec_path = Path(rec_txt.read_text(encoding="utf-8").strip())
        else:
            rec_path = None

        selection_ids: list[str] = succeeded_wfs
        portfolio_dir: Path | None = None
        if rec_path and rec_path.exists():
            data = json.loads(rec_path.read_text(encoding="utf-8")) or {}
            portfolio_dir = rec_path.parent
            if plan.select_policy == "recommended":
                selection_ids = [str(x) for x in (data.get("recommended_run_ids") or []) if str(x).strip()]
                if not selection_ids:
                    selection_ids = succeeded_wfs
        # Write selection file directly (same as Bridge, but without GUI dependency).
        if portfolio_dir:
            payload = {"version": "1.0", "selected_run_ids": selection_ids, "updated_at": _now_utc()}
            _write_json(portfolio_dir / "portfolio_selection.json", payload)

        finalize_job = submit("FINALIZE_PORTFOLIO_V1", {"season": plan.season, "portfolio_id": f"auto_{run_id}"})
        fin_states = _wait_jobs(
            db_path=db_path,
            artifacts_root=artifacts_root,
            job_ids=[finalize_job],
            max_workers=plan.max_workers,
            timeout_sec=timeout_sec,
        )
        manifest["steps"].append({"name": "FINALIZE_PORTFOLIO_V1", "job_ids": [finalize_job], "states": fin_states})
        _write_json(run_dir / "manifest.json", manifest)

    manifest["ok"] = True
    _write_json(run_dir / "manifest.json", manifest)
    return manifest
