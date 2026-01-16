from unittest.mock import Mock

from gui.services.data_alignment_status import (
    ARTIFACT_NAME,
    DataAlignmentStatus,
    MISSING_MESSAGE,
)
from gui.services.gate_summary_service import GateSummaryService, GateStatus


def _mock_job_entry(job_id: str, created_at: str):
    return {"job_id": job_id, "created_at": created_at, "status": "SUCCEEDED"}


def _stub_alignment_status(
    status: str, metrics: dict[str, float], message: str = "data_alignment_report.json is available"
) -> DataAlignmentStatus:
    return DataAlignmentStatus(
        status=status,
        artifact_relpath=ARTIFACT_NAME,
        artifact_abspath=f"/tmp/{status}/{ARTIFACT_NAME}",
        message=message,
        metrics=metrics,
    )


def test_data_alignment_gate_warns_at_high_ratio(monkeypatch):
    mock_client = Mock()
    mock_client.get_jobs.return_value = [_mock_job_entry("job-1", "2026-01-01T00:00:00Z")]

    monkeypatch.setattr(
        "gui.services.gate_summary_service.resolve_data_alignment_status",
        lambda job_id: _stub_alignment_status(
            status="OK",
            metrics={"forward_fill_ratio": 0.75, "dropped_rows": 5, "forward_filled_rows": 10},
        ),
    )
    monkeypatch.setattr(
        "gui.services.gate_summary_service.artifact_url_if_exists",
        lambda *_: None,
    )
    monkeypatch.setattr(
        "gui.services.gate_summary_service.job_artifact_url",
        lambda job_id, filename: f"/api/v1/jobs/{job_id}/artifacts/{filename}",
    )

    service = GateSummaryService(client=mock_client)
    gate = service._fetch_data_alignment_gate()

    assert gate.status == GateStatus.WARN
    assert "Forward fill ratio" in gate.message
    assert gate.actions and gate.actions[0]["url"] == "/api/v1/jobs/job-1/artifacts/data_alignment_report.json"


def test_data_alignment_gate_warns_when_artifact_missing(monkeypatch):
    mock_client = Mock()
    mock_client.get_jobs.return_value = [_mock_job_entry("job-2", "2026-01-02T00:00:00Z")]

    monkeypatch.setattr(
        "gui.services.gate_summary_service.resolve_data_alignment_status",
        lambda job_id: _stub_alignment_status(
            status="MISSING",
            metrics={},
            message=MISSING_MESSAGE,
        ),
    )
    monkeypatch.setattr(
        "gui.services.gate_summary_service.artifact_url_if_exists",
        lambda *_: None,
    )
    monkeypatch.setattr(
        "gui.services.gate_summary_service.job_artifact_url",
        lambda job_id, filename: f"/api/v1/jobs/{job_id}/artifacts/{filename}",
    )

    service = GateSummaryService(client=mock_client)
    gate = service._fetch_data_alignment_gate()

    assert gate.status == GateStatus.WARN
    assert gate.message == MISSING_MESSAGE
    assert gate.details.get("status") == "MISSING"
    assert gate.actions and gate.actions[0]["url"] == "/api/v1/jobs/job-2/artifacts/data_alignment_report.json"
