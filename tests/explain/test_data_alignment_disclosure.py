from unittest.mock import MagicMock

import pytest

from gui.services.data_alignment_status import (
    ARTIFACT_NAME,
    DataAlignmentStatus,
    MISSING_MESSAGE,
)
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
    monkeypatch.setattr(
        "control.explain_service.job_artifact_url",
        lambda job_id, filename: f"/api/v1/jobs/{job_id}/artifacts/{filename}",
    )

    def read_job_artifact(job_id: str, filename: str):
        if filename == "policy_check.json":
            return {"overall_status": "PASS"}
        return None

    monkeypatch.setattr("control.explain_service.read_job_artifact", read_job_artifact)

    def resolve_status(job_id: str) -> DataAlignmentStatus:
        return DataAlignmentStatus(
            status="OK",
            artifact_relpath=ARTIFACT_NAME,
            artifact_abspath=f"/tmp/{job_id}/{ARTIFACT_NAME}",
            message="data_alignment_report.json is available",
            metrics={
                "forward_fill_ratio": 0.42,
                "dropped_rows": 3,
                "forward_filled_rows": 10,
            },
        )

    monkeypatch.setattr("control.explain_service.resolve_data_alignment_status", resolve_status)


def test_explain_discloses_alignment_metrics():
    payload = build_job_explain("job-alignment")
    summary = payload.get("summary", "")
    assert "Data Alignment held-to-last" in summary
    evidence = payload.get("evidence", {})
    assert (
        evidence.get("data_alignment_url")
        == "/api/v1/jobs/job-alignment/artifacts/data_alignment_report.json"
    )
    alignment = payload.get("data_alignment_status", {})
    assert alignment.get("status") == "OK"
    assert alignment.get("metrics", {}).get("forward_fill_ratio") == 0.42
    assert alignment.get("metrics", {}).get("dropped_rows") == 3


def test_explain_reports_missing_alignment(monkeypatch):
    def missing_status(job_id: str) -> DataAlignmentStatus:
        return DataAlignmentStatus(
            status="MISSING",
            artifact_relpath=ARTIFACT_NAME,
            artifact_abspath=f"/tmp/{job_id}/{ARTIFACT_NAME}",
            message=MISSING_MESSAGE,
            metrics={},
        )

    monkeypatch.setattr(
        "control.explain_service.resolve_data_alignment_status", missing_status
    )

    payload = build_job_explain("job-alignment")
    alignment = payload.get("data_alignment_status", {})
    assert alignment.get("status") == "MISSING"
    assert alignment.get("message") == MISSING_MESSAGE
    assert alignment.get("metrics") == {}
    assert "missing" in payload.get("summary", "").lower()
