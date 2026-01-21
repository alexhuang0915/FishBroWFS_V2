from unittest.mock import Mock

from gui.services.data_alignment_status import (
    ARTIFACT_NAME,
    DataAlignmentStatus,
    MISSING_MESSAGE,
    DATA_ALIGNMENT_MISSING,
    DATA_ALIGNMENT_HIGH_FORWARD_FILL_RATIO,
    DATA_ALIGNMENT_DROPPED_ROWS,
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
    # Mock the registry to return expected cards
    monkeypatch.setattr(
        "gui.services.gate_summary_service.build_reason_cards_for_gate",
        lambda gate_key, job_id: [
            Mock(code=DATA_ALIGNMENT_HIGH_FORWARD_FILL_RATIO, severity="WARN", action_target=f"/tmp/OK/{ARTIFACT_NAME}"),
            Mock(code=DATA_ALIGNMENT_DROPPED_ROWS, severity="WARN", action_target=f"/tmp/OK/{ARTIFACT_NAME}"),
        ]
    )

    service = GateSummaryService(client=mock_client)
    gate = service._fetch_data_alignment_gate()

    assert gate.status == GateStatus.WARN
    assert "Forward fill ratio" in gate.message
    assert gate.actions and gate.actions[0]["url"] == "/api/v1/jobs/job-1/artifacts/data_alignment_report.json"
    # Check reason cards
    assert "reason_cards" in gate.details
    reason_cards = gate.details["reason_cards"]
    # With the mock, we get 2 cards
    assert len(reason_cards) == 2
    # Check card codes
    codes = [card["code"] for card in reason_cards]
    assert DATA_ALIGNMENT_HIGH_FORWARD_FILL_RATIO in codes
    assert DATA_ALIGNMENT_DROPPED_ROWS in codes
    # Check action target matches artifact path
    for card in reason_cards:
        assert card["action_target"] == f"/tmp/OK/{ARTIFACT_NAME}"


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
    # Mock the registry to return expected card
    monkeypatch.setattr(
        "gui.services.gate_summary_service.build_reason_cards_for_gate",
        lambda gate_key, job_id: [
            Mock(code=DATA_ALIGNMENT_MISSING, severity="WARN", action_target=f"/tmp/MISSING/{ARTIFACT_NAME}"),
        ]
    )

    service = GateSummaryService(client=mock_client)
    gate = service._fetch_data_alignment_gate()

    assert gate.status == GateStatus.WARN
    assert gate.message == MISSING_MESSAGE
    assert gate.details.get("status") == "MISSING"
    assert gate.actions and gate.actions[0]["url"] == "/api/v1/jobs/job-2/artifacts/data_alignment_report.json"
    # Check reason cards
    assert "reason_cards" in gate.details
    reason_cards = gate.details["reason_cards"]
    assert len(reason_cards) == 1
    card = reason_cards[0]
    assert card["code"] == DATA_ALIGNMENT_MISSING
    assert card["severity"] == "WARN"
    assert card["action_target"] == f"/tmp/MISSING/{ARTIFACT_NAME}"
