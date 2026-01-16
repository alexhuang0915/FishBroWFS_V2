from unittest.mock import Mock

import pytest

from gui.services.explain_adapter import ExplainAdapter, FALLBACK_SUMMARY, JobReason
from gui.services.supervisor_client import SupervisorClientError


class DummyCache:
    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def get(self, job_id: str):
        self.calls += 1
        return self.payload


class RaisingCache:
    def get(self, job_id: str):
        raise SupervisorClientError(status_code=500, message="boom", error_type="server")


def test_explain_adapter_returns_job_reason():
    payload = {
        "summary": "Some summary",
        "action_hint": "Re-run with corrected params",
        "decision_layer": "POLICY",
        "human_tag": "VIOLATION",
        "recoverable": True,
        "evidence": {
            "policy_check_url": "/api/v1/jobs/j1/artifacts/policy_check.json",
            "manifest_url": "/api/v1/jobs/j1/artifacts/manifest.json",
            "inputs_fingerprint_url": "/api/v1/jobs/j1/artifacts/inputs_fingerprint.json",
        },
    }
    cache = DummyCache(payload)
    adapter = ExplainAdapter(cache=cache)

    reason = adapter.get_job_reason("j1")

    assert isinstance(reason, JobReason)
    assert reason.summary == payload["summary"]
    assert reason.action_hint == payload["action_hint"]
    assert reason.decision_layer == "POLICY"
    assert reason.human_tag == "VIOLATION"
    assert reason.recoverable is True
    assert reason.evidence_urls["policy_check_url"] == payload["evidence"]["policy_check_url"]
    assert reason.fallback is False
    assert cache.calls == 1


def test_explain_adapter_fallback():
    adapter = ExplainAdapter(cache=RaisingCache())
    reason = adapter.get_job_reason("j2")
    assert reason.summary == FALLBACK_SUMMARY
    assert reason.action_hint == ""
    assert reason.decision_layer == "UNKNOWN"
    assert reason.human_tag == "UNKNOWN"
    assert reason.recoverable is False
    assert reason.evidence_urls["policy_check_url"].startswith("/api/v1/jobs/j2/")
    assert reason.fallback is True


def test_explain_adapter_uses_cache_once():
    payload = {"summary": "cached"}
    cache = DummyCache(payload)
    adapter = ExplainAdapter(cache=cache)

    adapter.get_job_reason("j3")
    adapter.get_job_reason("j3")

    assert cache.calls == 2
