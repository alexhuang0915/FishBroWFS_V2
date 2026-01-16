import json
from pathlib import Path

from gui.services.data_alignment_status import (
    ARTIFACT_NAME,
    MISSING_MESSAGE,
    resolve_data_alignment_status,
)


def _write_alignment_report(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as handle:
        json.dump(data, handle)


def test_resolver_returns_ok(tmp_path, monkeypatch):
    outputs_root = tmp_path / "outputs"
    monkeypatch.setenv("FISHBRO_OUTPUTS_ROOT", str(outputs_root))

    job_id = "ok-job"
    artifact_path = outputs_root / "jobs" / job_id / ARTIFACT_NAME
    _write_alignment_report(
        artifact_path,
        {
            "forward_fill_ratio": 0.25,
            "dropped_rows": 2,
            "forward_filled_rows": 12,
        },
    )

    status = resolve_data_alignment_status(job_id)

    assert status.status == "OK"
    assert status.metrics["forward_fill_ratio"] == 0.25
    assert status.metrics["dropped_rows"] == 2
    assert status.metrics["forward_filled_rows"] == 12
    assert status.message == "data_alignment_report.json is available"


def test_resolver_handles_missing_artifact(tmp_path, monkeypatch):
    outputs_root = tmp_path / "outputs"
    monkeypatch.setenv("FISHBRO_OUTPUTS_ROOT", str(outputs_root))

    job_id = "missing-job"
    status = resolve_data_alignment_status(job_id)

    assert status.status == "MISSING"
    assert status.metrics == {}
    assert status.message == MISSING_MESSAGE
