import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from control.api import app
from control.policy_enforcement import PolicyEnforcementError, PolicyResult, write_policy_check_artifact
from control.supervisor import submit
from control.supervisor.db import SupervisorDB
from control.supervisor.models import JobType
from core.paths import get_outputs_root


VALID_PAYLOAD = {
    "strategy_id": "S1",
    "instrument": "CME.MNQ",
    "timeframe": "60m",
    "run_mode": "research",
    "season": "2025",
    "start_date": "2025-01-01",
    "end_date": "2025-01-15",
}


@pytest.fixture
def outputs_root(tmp_path: Path, monkeypatch) -> Path:
    outputs_root = tmp_path / "outputs"
    outputs_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("FISHBRO_OUTPUTS_ROOT", str(outputs_root))
    return outputs_root


@pytest.fixture
def task_client(outputs_root: Path) -> TestClient:
    client = TestClient(app)
    yield client


def test_job_explain_schema(task_client: TestClient):
    job_id = submit("RUN_RESEARCH_V2", dict(VALID_PAYLOAD))
    response = task_client.get(f"/api/v1/jobs/{job_id}/explain")
    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == "1.0"
    assert payload["job_type"] == "RUN_RESEARCH_V2"
    assert payload["final_status"] == "QUEUED"


def test_rejected_preflight_includes_policy_stage(task_client: TestClient):
    with pytest.raises(PolicyEnforcementError) as exc:
        submit("RUN_RESEARCH_V2", {**VALID_PAYLOAD, "season": ""})
    job_id = exc.value.job_id
    response = task_client.get(f"/api/v1/jobs/{job_id}/explain")
    assert response.status_code == 200
    body = response.json()
    assert body["final_status"] == "REJECTED"
    assert body["decision_layer"] == "POLICY"
    assert body["human_tag"] == "VIOLATION"
    assert body["recoverable"] is True
    assert body["codes"]["policy_stage"] == "preflight"
    assert body["evidence"]["policy_check_url"] is not None


def test_postflight_failure_returns_policy_layer(task_client: TestClient, outputs_root: Path):
    job_id = submit("RUN_RESEARCH_V2", dict(VALID_PAYLOAD))
    db = SupervisorDB(get_outputs_root() / "jobs_v2.db")
    next_job = db.fetch_next_queued_job()
    assert next_job == job_id
    db.mark_failed(
        job_id,
        "Missing outputs",
        failure_code="POLICY_MISSING_OUTPUT",
        failure_message="Missing output artifact",
        policy_stage="postflight",
    )
    policy_result = PolicyResult(
        allowed=False,
        code="POLICY_MISSING_OUTPUT",
        message="Missing output artifact",
        details={},
        stage="postflight",
    )
    write_policy_check_artifact(
        job_id,
        JobType.RUN_RESEARCH_V2.value,
        postflight_results=[policy_result],
        final_reason={
            "policy_stage": "postflight",
            "failure_code": "POLICY_MISSING_OUTPUT",
            "failure_message": "Missing output artifact",
            "failure_details": {},
        },
    )
    response = task_client.get(f"/api/v1/jobs/{job_id}/explain")
    assert response.status_code == 200
    body = response.json()
    assert body["final_status"] == "FAILED"
    assert body["decision_layer"] == "POLICY"
    assert body["codes"]["policy_stage"] == "postflight"
    assert body["recoverable"] is True
    assert body["evidence"]["policy_check_url"] is not None


def test_succeeded_job_returns_policy_pass(task_client: TestClient, outputs_root: Path):
    job_id = submit("RUN_RESEARCH_V2", dict(VALID_PAYLOAD))
    db = SupervisorDB(get_outputs_root() / "jobs_v2.db")
    next_job = db.fetch_next_queued_job()
    assert next_job == job_id
    db.mark_succeeded(job_id, {"ok": True, "output_files": []})
    response = task_client.get(f"/api/v1/jobs/{job_id}/explain")
    assert response.status_code == 200
    body = response.json()
    assert body["final_status"] == "SUCCEEDED"
    assert body["decision_layer"] == "POLICY"
    assert body["human_tag"] == "UNKNOWN"
    assert body["recoverable"] is False
    assert body["summary"].startswith("Job succeeded and policy checks passed.")
    assert body["action_hint"].startswith("No action required")
    assert body["evidence"]["policy_check_url"] is not None


def test_explain_payload_has_no_metric_keys(task_client: TestClient):
    job_id = submit("RUN_RESEARCH_V2", dict(VALID_PAYLOAD))
    response = task_client.get(f"/api/v1/jobs/{job_id}/explain")
    assert response.status_code == 200
    payload = response.json()
    disallowed = {"score", "net_profit", "max_drawdown", "trades", "win_rate", "metrics"}
    serialized = json.dumps(payload).lower()
    for key in disallowed:
        assert key not in serialized
