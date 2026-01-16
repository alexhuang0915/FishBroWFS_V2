from unittest.mock import MagicMock

import pytest

from control.explain_service import build_job_explain


@pytest.fixture(autouse=True)
def mock_job(monkeypatch):
    job = MagicMock(
        job_id="job-alignment",
        state="SUCCEEDED",
        policy_stage="",
        failure_code="",
        failure_message="",
        state_reason="",
    )
    monkeypatch.setattr("control.explain_service.supervisor_get_job", lambda job_id: job)
    monkeypatch.setattr(
        "control.explain_service.artifact_url_if_exists",
        lambda job_id, filename: (
            f"/api/v1/jobs/{job_id}/artifacts/{filename}"
            if filename == "data_alignment_report.json"
            else f"/api/v1/jobs/{job_id}/artifacts/{filename}"
        ),
    )

    def read_job_artifact(job_id: str, filename: str):
        if filename == "policy_check.json":
            return {"overall_status": "PASS"}
        if filename == "data_alignment_report.json":
            return {
                "forward_fill_ratio": 0.42,
                "dropped_rows": 3,
                "forward_filled_rows": 10,
            }
        return None

    monkeypatch.setattr("control.explain_service.read_job_artifact", read_job_artifact)


def test_explain_discloses_alignment_metrics():
    payload = build_job_explain("job-alignment")
    summary = payload.get("summary", "")
    assert "Data Alignment held-to-last" in summary
    evidence = payload.get("evidence", {})
    assert evidence.get("data_alignment_url") == "/api/v1/jobs/job-alignment/artifacts/data_alignment_report.json"
    alignment = payload.get("data_alignment", {})
    assert alignment.get("forward_fill_ratio") == 0.42
    assert alignment.get("dropped_rows") == 3
