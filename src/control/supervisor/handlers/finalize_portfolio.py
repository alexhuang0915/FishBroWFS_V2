from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from ..job_handler import BaseJobHandler, JobContext
from contracts.supervisor.finalize_portfolio import FinalizePortfolioPayload
from control.artifacts import write_json_atomic
from core.paths import get_artifacts_root

logger = logging.getLogger(__name__)


class FinalizePortfolioHandler(BaseJobHandler):
    """FINALIZE_PORTFOLIO_V1 handler: turns portfolio_selection.json into final_manifest.json."""

    def validate_params(self, params: Dict[str, Any]) -> None:
        try:
            payload = FinalizePortfolioPayload(**params)
            payload.validate()
        except Exception as exc:
            raise ValueError(f"Invalid finalize_portfolio payload: {exc}")

    def execute(self, params: Dict[str, Any], context: JobContext) -> Dict[str, Any]:
        payload = FinalizePortfolioPayload(**params)
        payload.validate()

        if context.is_abort_requested():
            return {
                "ok": False,
                "job_type": "FINALIZE_PORTFOLIO_V1",
                "aborted": True,
                "reason": "user_abort_preinvoke",
                "payload": params,
            }

        artifacts_root = get_artifacts_root()
        if payload.outputs_root:
            # Optional override for advanced users/tests.
            artifacts_root = Path(payload.outputs_root).resolve() / "artifacts"

        portfolio_dir = artifacts_root / "seasons" / payload.season / "portfolios" / payload.portfolio_id
        if not portfolio_dir.exists():
            raise FileNotFoundError(f"portfolio_dir not found: {portfolio_dir}")

        selection_path = portfolio_dir / "portfolio_selection.json"
        if not selection_path.exists():
            raise FileNotFoundError(f"portfolio_selection.json not found: {selection_path}")
        selection = json.loads(selection_path.read_text(encoding="utf-8")) or {}
        selected_run_ids = selection.get("selected_run_ids") or []
        if not isinstance(selected_run_ids, list):
            raise ValueError("portfolio_selection.json selected_run_ids must be a list")
        selected_run_ids = [str(x) for x in selected_run_ids if str(x).strip()]

        recommendations_path = portfolio_dir / "recommendations.json"
        recommendations = {}
        if recommendations_path.exists():
            try:
                recommendations = json.loads(recommendations_path.read_text(encoding="utf-8")) or {}
            except Exception:
                recommendations = {}

        candidate_run_ids = recommendations.get("candidate_run_ids") or []
        if not isinstance(candidate_run_ids, list):
            candidate_run_ids = []
        recommended_run_ids = recommendations.get("recommended_run_ids") or []
        if not isinstance(recommended_run_ids, list):
            recommended_run_ids = []

        # Final manifest is an immutable record of the user's selection.
        final_manifest = {
            "version": "1.0",
            "portfolio_id": payload.portfolio_id,
            "season": payload.season,
            "finalized_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "portfolio_directory": str(portfolio_dir),
            "selection_path": str(selection_path),
            "recommendations_path": str(recommendations_path) if recommendations_path.exists() else None,
            "candidate_run_ids": [str(x) for x in candidate_run_ids],
            "recommended_run_ids": [str(x) for x in recommended_run_ids],
            "selected_run_ids": selected_run_ids,
        }

        final_path = portfolio_dir / "final_manifest.json"
        write_json_atomic(final_path, final_manifest)

        # Job evidence pointers for TUI/Bridge access
        evidence_dir = Path(context.artifacts_dir)
        (evidence_dir / "portfolio_final_manifest_path.txt").write_text(str(final_path), encoding="utf-8")
        (evidence_dir / "portfolio_dir_path.txt").write_text(str(portfolio_dir), encoding="utf-8")

        return {
            "ok": True,
            "job_type": "FINALIZE_PORTFOLIO_V1",
            "payload": params,
            "portfolio_id": payload.portfolio_id,
            "season": payload.season,
            "portfolio_dir": str(portfolio_dir),
            "final_manifest_path": str(final_path),
            "selected_count": len(selected_run_ids),
        }


finalize_portfolio_handler = FinalizePortfolioHandler()

