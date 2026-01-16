from unittest.mock import Mock

import pytest

from gui.services.gate_summary_service import GateSummaryService, GateResult, GateStatus


def _mock_job_entry(job_id: str, created_at: str):
    return {"job_id": job_id, "created_at": created_at, "status": "SUCCEEDED"}


def test_data_alignment_gate_warns_at_high_ratio(monkeypatch):
    mock_client = Mock()
    mock_client.get_jobs.return_value = [_mock_job_entry("job-1", "2026-01-01T00:00:00Z")]

    monkeypatch.setattr(
        "gui.services.gate_summary_service.artifact_url_if_exists",
        lambda job_id, filename: "/artifacts/data_alignment_report.json"
        if filename == "data_alignment_report.json"
        else None,
    )

    def read_job_artifact(job_id: str, filename: str):
        if filename == "data_alignment_report.json":
            return {"forward_fill_ratio": 0.75, "dropped_rows": 5}
        return None

    monkeypatch.setattr(
        "gui.services.gate_summary_service.read_job_artifact",
        read_job_artifact,
    )

    service = GateSummaryService(client=mock_client)
    gate = service._fetch_data_alignment_gate()

    assert gate.status == GateStatus.WARN
    assert "Forward fill ratio" in gate.message
    assert gate.actions and gate.actions[0]["url"] == "/artifacts/data_alignment_report.json"


def test_data_alignment_gate_warns_when_artifact_missing(monkeypatch):
    mock_client = Mock()
    mock_client.get_jobs.return_value = [_mock_job_entry("job-2", "2026-01-02T00:00:00Z")]

    monkeypatch.setattr(
        "gui.services.gate_summary_service.artifact_url_if_exists",
        lambda *_: None,
    )

    monkeypatch.setattr(
        "gui.services.gate_summary_service.read_job_artifact",
        lambda *_: None,
    )

    service = GateSummaryService(client=mock_client)
    gate = service._fetch_data_alignment_gate()

    assert gate.status == GateStatus.WARN
    assert "not available" in gate.message.lower()
