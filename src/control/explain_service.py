from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, Optional, Sequence

from fastapi import HTTPException

from control.job_artifacts import artifact_url_if_exists, evidence_bundle_url, job_artifact_url, stdout_tail_url
from control.reporting.io import read_job_artifact
from control.supervisor import get_job as supervisor_get_job
from control.supervisor.models import JobRow
from gui.services.data_alignment_status import (
    ARTIFACT_NAME,
    resolve_data_alignment_status,
)
from gui.services.resource_status import (
    resolve_resource_status,
    RESOURCE_USAGE_ARTIFACT,
)
from gui.services.portfolio_admission_status import (
    resolve_portfolio_admission_status,
    ADMISSION_DECISION_FILE,
)
from gui.services.gate_reason_cards_registry import build_reason_cards_for_gate

CACHE_TTL_SECONDS = 2.0
DEBUG_DERIVED_FROM = ["jobs_db", "policy_check", "artifacts_index"]


@dataclass(frozen=True)
class _ExplainContext:
    job_id: str
    final_status: str
    policy_stage: str
    failure_code: str
    failure_message: str
    state_reason: str
    policy_overall_status: str
    policy_final_stage: str
    has_policy_check: bool


@dataclass
class _CacheEntry:
    signature: str
    payload: dict[str, Any]
    expires_at: float


_CACHE: Dict[str, _CacheEntry] = {}


def _build_signature(job: JobRow) -> str:
    return f"{job.job_id}:{job.state}:{job.updated_at}"


def _get_cache_entry(job_id: str, signature: str) -> tuple[Optional[_CacheEntry], float]:
    now = time.monotonic()
    entry = _CACHE.get(job_id)
    if entry and entry.signature == signature and entry.expires_at > now:
        return entry, now
    return None, now


def _record_cache_entry(job_id: str, signature: str, payload: dict[str, Any]) -> None:
    _CACHE[job_id] = _CacheEntry(
        signature=signature,
        payload=payload,
        expires_at=time.monotonic() + CACHE_TTL_SECONDS,
    )


def _set_cache_metadata(payload: dict[str, Any], hit: bool, ttl: float) -> None:
    cache_info = payload.setdefault("debug", {}).setdefault("cache", {})
    cache_info["hit"] = hit
    cache_info["ttl_s"] = max(0, int(ttl))


def _render_summary(template: str, context: _ExplainContext) -> str:
    fallback = "UNKNOWN"
    summary_map = {
        "job_id": context.job_id,
        "final_status": context.final_status,
        "failure_code": context.failure_code or fallback,
        "failure_message": context.failure_message or "No details provided",
        "policy_stage": context.policy_stage or context.policy_final_stage or "policy",
    }
    return template.format_map(summary_map)


def _match_keywords(value: str, keywords: Iterable[str]) -> bool:
    lowered = value.lower()
    return any(keyword.lower() in lowered for keyword in keywords)


def _matches_conditions(conditions: Dict[str, Any], context: _ExplainContext) -> bool:
    if not conditions:
        return True
    if final_statuses := conditions.get("final_status_in"):
        if context.final_status not in final_statuses:
            return False
    if policy_stages := conditions.get("policy_stage_in"):
        if context.policy_stage not in policy_stages:
            return False
    if failure_codes := conditions.get("failure_code_in"):
        if context.failure_code not in failure_codes:
            return False
    if overall := conditions.get("policy_overall_status_in"):
        if context.policy_overall_status not in overall:
            return False
    if keywords := conditions.get("failure_message_keywords"):
        combined = f"{context.failure_message} {context.state_reason}"
        if not _match_keywords(combined, keywords):
            return False
    if "has_policy_check" in conditions:
        if context.has_policy_check != conditions["has_policy_check"]:
            return False
    return True


TAXONOMY_RULES: Sequence[Dict[str, Any]] = [
    {
        "name": "governance_frozen",
        "conditions": {
            "failure_message_keywords": ["frozen", "governance", "season is frozen"]
        },
        "decision_layer": "GOVERNANCE",
        "human_tag": "FROZEN",
        "recoverable": False,
        "summary_template": "Governance freeze prevented job execution ({failure_message}).",
        "action_hint": "Wait until governance window opens (e.g. unfreeze) then resubmit.",
    },
    {
        "name": "policy_preflight",
        "conditions": {"final_status_in": {"REJECTED"}, "policy_stage_in": {"preflight"}},
        "decision_layer": "POLICY",
        "human_tag": "VIOLATION",
        "recoverable": True,
        "summary_template": "Policy preflight rejected the job ({failure_code}).",
        "action_hint": "Adjust parameters to allowed values and resubmit.",
    },
    {
        "name": "policy_postflight",
        "conditions": {"final_status_in": {"FAILED"}, "policy_stage_in": {"postflight"}},
        "decision_layer": "POLICY",
        "human_tag": "VIOLATION",
        "recoverable": True,
        "summary_template": "Policy postflight failed ({failure_code}).",
        "action_hint": "Adjust parameters to allowed values and resubmit.",
    },
    {
        "name": "policy_success",
        "conditions": {
            "final_status_in": {"SUCCEEDED"},
            "policy_overall_status_in": {"PASS"},
        },
        "decision_layer": "POLICY",
        "human_tag": "UNKNOWN",
        "recoverable": False,
        "summary_template": "Job succeeded and policy checks passed.",
        "action_hint": "No action required; consider re-running if audit evidence is required.",
    },
    {
        "name": "artifact_corruption",
        "conditions": {
            "final_status_in": {"FAILED"},
            "failure_code_in": {
                "POLICY_MISSING_OUTPUT",
                "POLICY_MISSING_JOB_DIR",
                "POLICY_OUTPUT_PATH_VIOLATION",
            },
        },
        "decision_layer": "ARTIFACT",
        "human_tag": "CORRUPTED",
        "recoverable": True,
        "summary_template": "Artifacts missing or corrupted ({failure_code}).",
        "action_hint": "Re-run upstream job or inspect artifacts; ensure required outputs exist.",
    },
    {
        "name": "input_malformed",
        "conditions": {
            "final_status_in": {"REJECTED", "FAILED"},
            "failure_message_keywords": ["invalid", "missing", "malformed"],
        },
        "decision_layer": "INPUT",
        "human_tag": "MALFORMED",
        "recoverable": True,
        "summary_template": "Job input is malformed ({failure_message}).",
        "action_hint": "Fix missing/invalid fields and resubmit.",
    },
    {
        "name": "system_failure",
        "conditions": {
            "final_status_in": {"FAILED"},
            "failure_code_in": {"HANDLER_EXCEPTION"},
        },
        "decision_layer": "SYSTEM",
        "human_tag": "INFRA_FAILURE",
        "recoverable": True,
        "summary_template": "System failure occurred ({failure_message}).",
        "action_hint": "Retry later; if persistent, contact system owner.",
    },
    {
        "name": "success_missing_policy",
        "conditions": {"final_status_in": {"SUCCEEDED"}, "has_policy_check": False},
        "decision_layer": "UNKNOWN",
        "human_tag": "UNKNOWN",
        "recoverable": False,
        "summary_template": "Job succeeded but policy evidence is unavailable.",
        "action_hint": "No action required; consider re-running if audit evidence is required.",
    },
    {
        "name": "unknown",
        "conditions": {},
        "decision_layer": "UNKNOWN",
        "human_tag": "UNKNOWN",
        "recoverable": False,
        "summary_template": "Status {final_status}; monitor logs for more details.",
        "action_hint": "No action required; consider re-running if audit evidence is required.",
    },
]


def _select_rule(context: _ExplainContext) -> Dict[str, Any]:
    for rule in TAXONOMY_RULES:
        if _matches_conditions(rule.get("conditions", {}), context):
            return rule
    return TAXONOMY_RULES[-1]


def build_job_explain(job_id: str) -> dict[str, Any]:
    job = supervisor_get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    signature = _build_signature(job)
    cache_entry, now = _get_cache_entry(job_id, signature)
    if cache_entry:
        ttl_remaining = cache_entry.expires_at - now
        _set_cache_metadata(cache_entry.payload, True, ttl_remaining)
        return cache_entry.payload

    policy_check = read_job_artifact(job_id, "policy_check.json") or {}
    final_reason = policy_check.get("final_reason", {}) or {}

    context = _ExplainContext(
        job_id=job.job_id,
        final_status=job.state,
        policy_stage=(job.policy_stage or final_reason.get("policy_stage", "") or "").lower(),
        failure_code=(job.failure_code or final_reason.get("failure_code", "") or "").upper(),
        failure_message=(job.failure_message or final_reason.get("failure_message", "") or "").strip(),
        state_reason=(job.state_reason or "").strip(),
        policy_overall_status=(policy_check.get("overall_status") or "").upper(),
        policy_final_stage=(final_reason.get("policy_stage") or "").lower(),
        has_policy_check=bool(policy_check),
    )

    rule = _select_rule(context)
    summary = _render_summary(rule["summary_template"], context)

    alignment_status = resolve_data_alignment_status(job.job_id)
    alignment_url = artifact_url_if_exists(job.job_id, ARTIFACT_NAME) or job_artifact_url(
        job.job_id, ARTIFACT_NAME
    )
    
    # Build reason cards for data alignment using registry
    data_alignment_reason_cards = build_reason_cards_for_gate("data_alignment", job.job_id)
    data_alignment_reason_cards_dict = [card.__dict__ for card in data_alignment_reason_cards]
    
    if alignment_status.status == "OK":
        ratio = alignment_status.metrics.get("forward_fill_ratio")
        dropped = alignment_status.metrics.get("dropped_rows", 0)
        ratio_text = f"{ratio:.0%}" if isinstance(ratio, (int, float)) else "N/A"
        summary = (
            f"{summary} Data Alignment held-to-last {ratio_text} of bars; "
            f"dropped {dropped} rows."
        )
    else:
        summary = f"{summary} Data Alignment missing: {alignment_status.message}."

    # Resource / OOM status and reason cards
    resource_status = resolve_resource_status(job.job_id)
    resource_url = artifact_url_if_exists(job.job_id, RESOURCE_USAGE_ARTIFACT) or job_artifact_url(
        job.job_id, RESOURCE_USAGE_ARTIFACT
    )
    resource_reason_cards = build_reason_cards_for_gate("resource", job.job_id)
    resource_reason_cards_dict = [card.__dict__ for card in resource_reason_cards]

    # Portfolio Admission status and reason cards
    admission_status = resolve_portfolio_admission_status(job.job_id)
    admission_url = artifact_url_if_exists(job.job_id, ADMISSION_DECISION_FILE) or job_artifact_url(
        job.job_id, ADMISSION_DECISION_FILE
    )
    admission_reason_cards = build_reason_cards_for_gate("portfolio_admission", job.job_id)
    admission_reason_cards_dict = [card.__dict__ for card in admission_reason_cards]

    evidence = {
        "policy_check_url": artifact_url_if_exists(job_id, "policy_check.json"),
        "manifest_url": artifact_url_if_exists(job_id, "manifest.json"),
        "inputs_fingerprint_url": artifact_url_if_exists(job_id, "inputs_fingerprint.json"),
        "stdout_tail_url": stdout_tail_url(job_id),
        "evidence_bundle_url": evidence_bundle_url(job_id),
        "data_alignment_url": alignment_url,
        "resource_url": resource_url,
        "admission_url": admission_url,
    }

    policy_stage_value = context.policy_stage or context.policy_final_stage

    # Build gate_reason_cards mapping for all gates
    gate_keys = [
        "api_health",
        "api_readiness",
        "supervisor_db_ssot",
        "worker_execution_reality",
        "registry_surface",
        "policy_enforcement",
        "data_alignment",
        "resource",
        "portfolio_admission",
        "slippage_stress",
        "control_actions",
        "shared_build",
    ]
    
    gate_reason_cards: dict[str, list[dict[str, Any]]] = {}
    for gate_key in gate_keys:
        cards = build_reason_cards_for_gate(gate_key, job.job_id)
        gate_reason_cards[gate_key] = [card.__dict__ for card in cards]

    payload: dict[str, Any] = {
        "schema_version": "1.0",
        "job_id": job.job_id,
        "job_type": str(job.job_type),
        "final_status": context.final_status,
        "decision_layer": rule["decision_layer"],
        "human_tag": rule["human_tag"],
        "recoverable": rule["recoverable"],
        "summary": summary,
        "action_hint": rule["action_hint"],
        "codes": {
            "failure_code": context.failure_code,
            "policy_stage": policy_stage_value,
            "http_status": 200,
        },
        "evidence": evidence,
        "data_alignment_status": asdict(alignment_status),
        "data_alignment_reason_cards": data_alignment_reason_cards_dict,
        "resource_status": asdict(resource_status),
        "resource_reason_cards": resource_reason_cards_dict,
        "admission_status": asdict(admission_status),
        "admission_reason_cards": admission_reason_cards_dict,
        "gate_reason_cards": gate_reason_cards,
        "debug": {
            "derived_from": DEBUG_DERIVED_FROM,
            "cache": {"hit": False, "ttl_s": int(CACHE_TTL_SECONDS)},
        },
    }

    _record_cache_entry(job_id, signature, payload)
    return payload
