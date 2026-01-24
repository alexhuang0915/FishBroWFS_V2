"""
Policy enforcement helpers for the control plane.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Literal, Sequence

from contracts.supervisor.evidence_schemas import now_iso
from control.artifacts import write_json_atomic
from core.paths import get_outputs_root
from core.paths import get_jobs_dir
from control.supervisor.models import JobSpec, JobType

PolicyStage = Literal["preflight", "postflight"]


@dataclass(frozen=True)
class PolicyResult:
    allowed: bool
    code: str
    message: str
    details: Dict[str, Any]
    stage: PolicyStage


class PolicyEnforcementError(Exception):
    """Raised when a policy check rejects a job submission."""

    def __init__(self, job_id: str, result: PolicyResult):
        self._job_id = job_id
        self.result = result
        super().__init__(f"{result.stage} policy violation ({result.code}): {result.message}")

    @property
    def job_id(self) -> str:
        return self._job_id


def _allowed(stage: PolicyStage) -> PolicyResult:
    return PolicyResult(
        allowed=True,
        code="POLICY_OK",
        message="Policy enforcement passed",
        details={},
        stage=stage,
    )


def _forbidden(stage: PolicyStage, code: str, message: str, details: Dict[str, Any] | None = None) -> PolicyResult:
    return PolicyResult(
        allowed=False,
        code=code,
        message=message,
        details=details or {},
        stage=stage,
    )


def _extract_param(spec: JobSpec, key: str) -> Any:
    value = spec.params.get(key)
    if value:
        return value
    override = spec.params.get("params_override")
    if isinstance(override, dict):
        nested = override.get(key)
        if nested:
            return nested
    return spec.metadata.get(key)


def evaluate_preflight(spec: JobSpec) -> PolicyResult:
    """Run fast, deterministic checks before launching a worker."""
    if spec.job_type in {
        JobType.RUN_RESEARCH_WFS,
    }:
        season = _extract_param(spec, "season")
        if not season:
            return _forbidden(
                "preflight",
                "POLICY_REJECT_MISSING_SEASON",
                "season is required for research jobs",
                {"params_keys": list(spec.params.keys()), "metadata": spec.metadata},
            )

        timeframe = _extract_param(spec, "timeframe")
        if not timeframe:
            return _forbidden(
                "preflight",
                "POLICY_REJECT_MISSING_TIMEFRAME",
                "timeframe is required for research jobs",
                {"params_keys": list(spec.params.keys())},
            )

        # Enforce stable, local-only formats (no HTTP assumptions).
        import re

        # Season: allow YYYYQ# only. (UI may use 'current' but must resolve before submit.)
        if not re.fullmatch(r"\d{4}Q[1-4]", str(season).strip()):
            return _forbidden(
                "preflight",
                "POLICY_REJECT_INVALID_SEASON_FORMAT",
                "season must match YYYYQ#",
                {"season": season},
            )

        # Timeframe: allow integer minutes or e.g. 60m / 2h
        tf = str(timeframe).strip().lower()
        if not re.fullmatch(r"\d+([mh])?", tf):
            return _forbidden(
                "preflight",
                "POLICY_REJECT_INVALID_TIMEFRAME_FORMAT",
                "timeframe must be like '60m', '2h', or integer minutes",
                {"timeframe": timeframe},
            )

    return _allowed("preflight")


def evaluate_postflight(job_id: str, result: Dict[str, Any]) -> PolicyResult:
    """Validate artifacts/output after the worker completed."""
    job_dir = get_jobs_dir() / job_id
    declared = result.get("output_files", [])
    if declared:
        if not job_dir.exists():
            return _forbidden(
                "postflight",
                "POLICY_MISSING_JOB_DIR",
                "Job artifact directory missing after execution",
                {"job_dir": str(job_dir)},
            )
        missing = []
        for rel in declared:
            candidate = (job_dir / Path(rel)).resolve()
            try:
                candidate.relative_to(job_dir.resolve())
            except Exception:
                return _forbidden(
                    "postflight",
                    "POLICY_OUTPUT_PATH_VIOLATION",
                    "Worker declared output path outside canonical job directory",
                    {"path": rel},
                )
            if not candidate.exists():
                missing.append(str(rel))
        if missing:
            return _forbidden(
                "postflight",
                "POLICY_MISSING_OUTPUT",
                "Declared output artifacts missing",
                {"missing": missing},
            )

    return _allowed("postflight")


POLICY_CHECK_FILENAME = "policy_check.json"
POLICY_CHECK_SCHEMA_VERSION = "1.0"
LOGGER = logging.getLogger(__name__)


def _policy_result_entry(result: PolicyResult) -> Dict[str, Any]:
    """Convert a PolicyResult into the canonical policy_check entry."""
    return {
        "status": "PASS" if result.allowed else "FAIL",
        "code": result.code,
        "policy_name": result.code,
        "passed": result.allowed,
        "message": result.message,
        "details": result.details or {},
        "stage": result.stage,
        "checked_at": now_iso(),
    }


def _read_existing_policy_check(job_dir: Path) -> Dict[str, Any]:
    """Read existing policy_check.json payload, if present."""
    path = job_dir / POLICY_CHECK_FILENAME
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        LOGGER.warning("Unable to read existing policy_check.json for %s: %s", job_dir, exc)
        return {}


def _overall_status(preflight: Sequence[Dict[str, Any]], postflight: Sequence[Dict[str, Any]]) -> str:
    """Determine overall PASS/FAIL status for the policy check."""
    combined = list(preflight) + list(postflight)
    for entry in combined:
        if entry.get("status") == "FAIL":
            return "FAIL"
    return "PASS"


def write_policy_check_artifact(
    job_id: str,
    job_type: str,
    *,
    preflight_results: Sequence[PolicyResult] | None = None,
    postflight_results: Sequence[PolicyResult] | None = None,
    final_reason: Dict[str, Any] | None = None,
    extra_paths: Sequence[Path] | None = None,
) -> None:
    """
    Write/overwrite the canonical policy_check.json artifact for a job.

    This is idempotent and preserves the original creation timestamp if present.
    """
    job_dir = get_jobs_dir() / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    existing = _read_existing_policy_check(job_dir)

    created_utc = existing.get("created_utc") or now_iso()
    preflight_payload = existing.get("preflight", [])
    postflight_payload = existing.get("postflight", [])
    final_reason_payload = existing.get("final_reason", {
        "policy_stage": "",
        "failure_code": "",
        "failure_message": "",
        "failure_details": {},
    })

    if preflight_results is not None:
        preflight_payload = [_policy_result_entry(r) for r in preflight_results]
    if postflight_results is not None:
        postflight_payload = [_policy_result_entry(r) for r in postflight_results]
    if final_reason is not None:
        final_reason_payload = {
            "policy_stage": final_reason.get("policy_stage", ""),
            "failure_code": final_reason.get("failure_code", ""),
            "failure_message": final_reason.get("failure_message", ""),
            "failure_details": final_reason.get("failure_details") or {},
        }

    overall = _overall_status(preflight_payload, postflight_payload)
    job_type_value = str(job_type)

    bundle = {
        "schema_version": POLICY_CHECK_SCHEMA_VERSION,
        "job_id": job_id,
        "job_type": job_type_value,
        "created_utc": created_utc,
        "overall_status": overall,
        "preflight": preflight_payload,
        "postflight": postflight_payload,
        "final_reason": final_reason_payload,
    }

    write_json_atomic(job_dir / POLICY_CHECK_FILENAME, bundle)
    if extra_paths:
        for extra_path in extra_paths:
            target = Path(extra_path) / POLICY_CHECK_FILENAME
            write_json_atomic(target, bundle)
