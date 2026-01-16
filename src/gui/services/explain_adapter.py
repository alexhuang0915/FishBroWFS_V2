from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional

from gui.services.explain_cache import get_cache_instance, ExplainCache
from gui.services.supervisor_client import SupervisorClient, get_client, SupervisorClientError

FALLBACK_SUMMARY = "Explain unavailable; open policy evidence if present."


@dataclass
class JobReason:
    job_id: str
    summary: str
    action_hint: str
    decision_layer: str
    human_tag: str
    recoverable: bool
    evidence_urls: Dict[str, Optional[str]]
    fallback: bool


class ExplainAdapter:
    """Adapter that surfaces Explain SSOT payloads for UI consumption."""

    def __init__(
        self,
        client: Optional[SupervisorClient] = None,
        cache: Optional[ExplainCache] = None,
    ):
        self.client = client or get_client()
        self.cache = cache or get_cache_instance()

    def get_job_reason(self, job_id: str) -> JobReason:
        """Return a normalized JobReason built from Explain SSOT."""
        try:
            payload = self.cache.get(job_id)
        except SupervisorClientError:
            return self._fallback_reason(job_id)

        evidence = payload.get("evidence") or {}
        return JobReason(
            job_id=job_id,
            summary=payload.get("summary", FALLBACK_SUMMARY),
            action_hint=payload.get("action_hint", "") or "",
            decision_layer=payload.get("decision_layer", "UNKNOWN"),
            human_tag=payload.get("human_tag", "UNKNOWN"),
            recoverable=bool(payload.get("recoverable", False)),
            evidence_urls={
                "policy_check_url": evidence.get("policy_check_url"),
                "manifest_url": evidence.get("manifest_url"),
                "inputs_fingerprint_url": evidence.get("inputs_fingerprint_url"),
            },
            fallback=False,
        )

    def _fallback_reason(self, job_id: str) -> JobReason:
        evidence_urls = {
            "policy_check_url": f"/api/v1/jobs/{job_id}/artifacts/policy_check.json",
            "manifest_url": None,
            "inputs_fingerprint_url": None,
        }
        return JobReason(
            job_id=job_id,
            summary=FALLBACK_SUMMARY,
            action_hint="",
            decision_layer="UNKNOWN",
            human_tag="UNKNOWN",
            recoverable=False,
            evidence_urls=evidence_urls,
            fallback=True,
        )

    def fallback_reason(self, job_id: str) -> JobReason:
        """Public fallback path for consumers that cannot reach Explain SSOT."""
        return self._fallback_reason(job_id)
