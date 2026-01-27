from __future__ import annotations

import json
import logging
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..job_handler import BaseJobHandler, JobContext
from contracts.supervisor.build_portfolio import BuildPortfolioPayload
from control.artifacts import write_json_atomic
from control.job_artifacts import get_job_evidence_dir
from core.paths import get_artifacts_root

logger = logging.getLogger(__name__)


class BuildPortfolioHandler(BaseJobHandler):
    """BUILD_PORTFOLIO_V2 handler for packaging portfolio artifacts from WFS results."""

    def validate_params(self, params: Dict[str, Any]) -> None:
        try:
            payload = BuildPortfolioPayload(**params)
            payload.validate()
        except Exception as e:
            raise ValueError(f"Invalid build_portfolio payload: {e}")

    def execute(self, params: Dict[str, Any], context: JobContext) -> Dict[str, Any]:
        payload = BuildPortfolioPayload(**params)
        payload.validate()

        if context.is_abort_requested():
            return {
                "ok": False,
                "job_type": "BUILD_PORTFOLIO_V2",
                "aborted": True,
                "reason": "user_abort_preinvoke",
                "payload": params,
            }

        outputs_root = get_artifacts_root()
        if payload.outputs_root:
            # Optional override for advanced users/tests.
            outputs_root = Path(payload.outputs_root)

        portfolio_id = payload.portfolio_id or self._compute_portfolio_id(payload.season, payload.candidate_run_ids or [])
        portfolio_dir = outputs_root / "seasons" / payload.season / "portfolios" / portfolio_id
        portfolio_dir.mkdir(parents=True, exist_ok=True)
        write_json_atomic(portfolio_dir / "payload.json", params)

        context.heartbeat(progress=0.1, phase="locating_wfs_results")
        try:
            result = self._execute_portfolio(payload, context, outputs_root, portfolio_dir, portfolio_id)
            self._write_domain_manifest(context.job_id, payload, portfolio_dir, outputs_root, portfolio_id, result)
            return {
                "ok": True,
                "job_type": "BUILD_PORTFOLIO_V2",
                "payload": params,
                "portfolio_id": portfolio_id,
                "portfolio_dir": str(portfolio_dir),
                "manifest_path": str(portfolio_dir / "manifest.json"),
                "result": result,
            }
        except Exception as e:
            logger.error(f"Failed to execute portfolio build: {e}")
            logger.error(traceback.format_exc())
            error_path = Path(context.artifacts_dir) / "error.txt"
            error_path.write_text(f"{e}\n\n{traceback.format_exc()}")
            raise

    def _compute_portfolio_id(self, season: str, run_ids: List[str]) -> str:
        import hashlib

        blob = ",".join(sorted(run_ids)).encode("utf-8")
        return f"portfolio_{season}_{hashlib.sha256(blob).hexdigest()[:12]}"

    def _locate_wfs_result_paths(self, outputs_root: Path, season: str, run_ids: List[str]) -> Dict[str, Path]:
        resolved: Dict[str, Path] = {}
        for run_id in run_ids:
            p = outputs_root / "seasons" / season / "wfs" / run_id / "result.json"
            if p.exists():
                resolved[run_id] = p
                continue

            # Fallback: convenience copy in job evidence
            job_dir = get_job_evidence_dir(run_id)
            p2 = job_dir / "wfs_result.json"
            if p2.exists():
                resolved[run_id] = p2
        return resolved

    def _execute_portfolio(
        self,
        payload: BuildPortfolioPayload,
        context: JobContext,
        outputs_root: Path,
        portfolio_dir: Path,
        portfolio_id: str,
    ) -> Dict[str, Any]:
        run_ids = list(payload.candidate_run_ids or [])
        if not run_ids:
            raise ValueError("candidate_run_ids is required for BUILD_PORTFOLIO_V2 in Phase-1 wiring closure.")

        resolved = self._locate_wfs_result_paths(outputs_root, payload.season, run_ids)
        missing = [rid for rid in run_ids if rid not in resolved]
        if missing:
            raise FileNotFoundError(f"Missing WFS result.json for run_ids: {missing[:10]}")

        context.heartbeat(progress=0.45, phase="loading_results")
        loaded: Dict[str, Dict[str, Any]] = {}
        recommended: List[str] = []
        for rid, path in resolved.items():
            data = json.loads(path.read_text())
            loaded[rid] = data
            if bool(((data.get("verdict") or {}).get("is_tradable"))):
                recommended.append(rid)

        context.heartbeat(progress=0.7, phase="writing_portfolio_artifacts")
        # Advisory mode: do not block; default selection includes all candidates.
        selected = sorted(run_ids)
        portfolio_config = {
            "version": "0.1",
            "season": payload.season,
            "portfolio_id": portfolio_id,
            "candidate_run_ids": run_ids,
            "selected_run_ids": selected,
            "recommended_run_ids": sorted(recommended),
            "timeframe": payload.timeframe,
            "allowlist": payload.allowlist,
            "note": "Advisory portfolio bundle (no automatic blocking).",
        }
        write_json_atomic(portfolio_dir / "portfolio_config.json", portfolio_config)

        portfolio_manifest = {
            "version": "0.1",
            "portfolio_id": portfolio_id,
            "season": payload.season,
            "run_count": len(run_ids),
            "selected_count": len(selected),
            "selected_run_ids": selected,
            "recommended_count": len(recommended),
            "recommended_run_ids": sorted(recommended),
            "source_results": {rid: str(p) for rid, p in resolved.items()},
        }
        write_json_atomic(portfolio_dir / "portfolio_manifest.json", portfolio_manifest)

        results_dir = portfolio_dir / "wfs_results"
        results_dir.mkdir(parents=True, exist_ok=True)
        for rid, data in loaded.items():
            write_json_atomic(results_dir / f"{rid}.json", data)

        # Recommendations are derived from per-run WFS result.json (advisory only).
        recs: list[dict[str, Any]] = []
        for rid in sorted(run_ids):
            data = loaded.get(rid) or {}
            meta = data.get("meta") or {}
            cfg_data = (data.get("config") or {}).get("data") or {}
            verdict = data.get("verdict") or {}
            metrics = data.get("metrics") or {}
            raw = metrics.get("raw") or {}
            scores = metrics.get("scores") or {}
            recs.append(
                {
                    "run_id": rid,
                    "instrument": meta.get("instrument"),
                    "data2": cfg_data.get("data2"),
                    "strategy_family": meta.get("strategy_family"),
                    "timeframe": meta.get("timeframe"),
                    "grade": verdict.get("grade"),
                    "is_tradable": bool(verdict.get("is_tradable")),
                    "hard_gates_triggered": list(metrics.get("hard_gates_triggered") or []),
                    "score_total_weighted": scores.get("total_weighted"),
                    "raw": {
                        "pass_rate": raw.get("pass_rate"),
                        "trades": raw.get("trades"),
                        "wfe": raw.get("wfe"),
                        "ulcer_index": raw.get("ulcer_index"),
                        "max_underwater_days": raw.get("max_underwater_days"),
                    },
                    "summary": verdict.get("summary"),
                }
            )

        recommendations = {
            "version": "1.0",
            "portfolio_id": portfolio_id,
            "season": payload.season,
            "candidate_run_ids": run_ids,
            "recommended_run_ids": sorted(recommended),
            "default_selected_run_ids": selected,
            "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "runs": recs,
        }
        rec_path = portfolio_dir / "recommendations.json"
        write_json_atomic(rec_path, recommendations)

        # Write path contract to job evidence for TUI/Bridge access
        evidence_dir = Path(context.artifacts_dir)
        (evidence_dir / "portfolio_manifest_path.txt").write_text(str(portfolio_dir / "manifest.json"))
        (evidence_dir / "portfolio_recommendations_path.txt").write_text(str(rec_path))

        context.heartbeat(progress=0.95, phase="done")
        return {
            "ok": True,
            "portfolio_id": portfolio_id,
            "portfolio_dir": str(portfolio_dir),
            "portfolio_config_path": str(portfolio_dir / "portfolio_config.json"),
            "portfolio_manifest_path": str(portfolio_dir / "portfolio_manifest.json"),
            "selected_run_ids": selected,
            "recommended_run_ids": sorted(recommended),
            "recommendations_path": str(rec_path),
        }

    def _write_domain_manifest(
        self,
        job_id: str,
        payload: BuildPortfolioPayload,
        portfolio_dir: Path,
        outputs_root: Path,
        portfolio_id: str,
        result: Dict[str, Any],
    ) -> None:
        manifest = {
            "job_id": job_id,
            "job_type": "build_portfolio_v2",
            "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "input_fingerprint": {
                "season": payload.season,
                "allowlist": payload.allowlist,
                "candidate_run_ids": payload.candidate_run_ids,
                "timeframe": payload.timeframe,
                "params_hash": payload.compute_input_fingerprint(),
            },
            "portfolio_id": portfolio_id,
            "portfolio_directory": str(portfolio_dir),
            "outputs_root": str(outputs_root),
            "result": result,
            "manifest_version": "1.0",
        }
        write_json_atomic(portfolio_dir / "manifest.json", manifest)


build_portfolio_handler = BuildPortfolioHandler()
