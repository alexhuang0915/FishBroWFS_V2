import json
import os
import re
from pathlib import Path

import pytest

from control.supervisor import submit
from control.supervisor.db import SupervisorDB
from control.supervisor.models import JobSpec, JobStatus, JobType
from control.policy_enforcement import PolicyEnforcementError
from control.subprocess_exec import run_python_module


def _set_outputs_root(tmp_path: Path, monkeypatch) -> Path:
    outputs_root = tmp_path / "outputs"
    outputs_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("FISHBRO_OUTPUTS_ROOT", str(outputs_root))
    return outputs_root


def _read_policy_check(outputs_root: Path, job_id: str) -> dict:
    with open(outputs_root / "jobs" / job_id / "policy_check.json", "r") as f:
        return json.load(f)


def test_preflight_rejects_invalid_season(tmp_path: Path, monkeypatch):
    outputs_root = _set_outputs_root(tmp_path, monkeypatch)
    with pytest.raises(PolicyEnforcementError) as exc:
        submit(
            "RUN_RESEARCH_V2",
            {
                "strategy_id": "S1",
                "start_date": "2025-01-01",
                "end_date": "2025-01-31",
                "season": "",
                "timeframe": "60m",
            },
            {},
        )

    db = SupervisorDB(outputs_root / "jobs_v2.db")
    job = db.get_job_row(exc.value.job_id)
    assert job is not None
    assert job.state == JobStatus.REJECTED
    assert job.failure_code == "POLICY_REJECT_MISSING_SEASON"
    assert job.policy_stage == "preflight"
    assert job.failure_message == exc.value.result.message

    policy_check = _read_policy_check(outputs_root, job.job_id)
    assert policy_check["overall_status"] == "FAIL"
    assert policy_check["final_reason"]["policy_stage"] == "preflight"
    assert policy_check["final_reason"]["failure_code"] == "POLICY_REJECT_MISSING_SEASON"
    assert len(policy_check["preflight"]) == 1
    entry = policy_check["preflight"][0]
    assert entry["status"] == "FAIL"
    assert entry["code"] == "POLICY_REJECT_MISSING_SEASON"


def test_postflight_missing_output_paths_fail(tmp_path: Path, monkeypatch):
    outputs_root = _set_outputs_root(tmp_path, monkeypatch)
    db = SupervisorDB(outputs_root / "jobs_v2.db")
    spec = JobSpec(job_type=JobType.PING, params={"sleep_sec": 0.0}, metadata={})
    job_id = db.submit_job(spec)
    db.fetch_next_queued_job()
    (outputs_root / "jobs" / job_id).mkdir(parents=True, exist_ok=True)

    db.mark_succeeded(job_id, {"ok": True, "output_files": ["missing.txt"]})

    job = db.get_job_row(job_id)
    assert job is not None
    assert job.state == JobStatus.FAILED
    assert job.failure_code == "POLICY_MISSING_OUTPUT"
    assert job.policy_stage == "postflight"

    policy_check = _read_policy_check(outputs_root, job_id)
    assert policy_check["overall_status"] == "FAIL"
    assert policy_check["final_reason"]["policy_stage"] == "postflight"
    assert policy_check["postflight"][0]["code"] == "POLICY_MISSING_OUTPUT"


def test_cli_submit_respects_policy(tmp_path: Path, monkeypatch):
    outputs_root = _set_outputs_root(tmp_path, monkeypatch)
    params = {
        "strategy_id": "S1",
        "instrument": "MNQ",
        "timeframe": "60m",
        "run_mode": "research",
        "season": "",
    }
    result = run_python_module(
        "control.supervisor.cli",
        [
            "--db",
            str(outputs_root / "jobs_v2.db"),
            "submit",
            "--job-type",
            "RUN_RESEARCH_V2",
            "--params-json",
            json.dumps({**params, "start_date": "2025-01-01", "end_date": "2025-01-31"}),
        ],
        cwd=Path(__file__).resolve().parents[2],
    )

    assert result.returncode == 1
    assert "policy enforcement failed" in result.stderr.lower()
    match = re.search(r"Job recorded as ([\w-]+)", result.stderr)
    assert match is not None
    job_id = match.group(1)
    db = SupervisorDB(outputs_root / "jobs_v2.db")
    job = db.get_job_row(job_id)
    assert job is not None
    assert job.state == JobStatus.REJECTED
    assert job.failure_code == "POLICY_REJECT_MISSING_SEASON"
