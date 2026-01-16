import json

from gui.services.artifact_navigator_vm import (
    ArtifactNavigatorVM,
    Action,
    GATE_SUMMARY_TARGET,
    EXPLAIN_TARGET_PREFIX,
)
from gui.services.gate_summary_service import GateSummary, GateStatus
from gui.services.data_alignment_status import (
    DataAlignmentStatus,
    ARTIFACT_NAME,
)
from gui.services.explain_adapter import JobReason


def _patch_dependencies(
    monkeypatch,
    tmp_path,
    job_id,
    gate_status,
    alignment_status,
    artifact_files,
    alignment_func=None,
):
    artifact_dir = tmp_path / job_id
    artifact_dir.mkdir(parents=True, exist_ok=True)

    def fake_gate_summary():
        return GateSummary(
            gates=[],
            timestamp="2026-01-17T00:00:00Z",
            overall_status=gate_status,
            overall_message="Gates evaluated.",
        )

    def fake_artifacts(jid):
        return {"job_id": jid, "files": artifact_files}

    def fake_reason(self, jid):
        return JobReason(
            job_id=jid,
            summary="Explain ready",
            action_hint="",
            decision_layer="UNKNOWN",
            human_tag="UNKNOWN",
            recoverable=True,
            evidence_urls={},
            fallback=False,
        )

    monkeypatch.setattr("gui.services.artifact_navigator_vm.fetch_gate_summary", fake_gate_summary)
    monkeypatch.setattr("gui.services.artifact_navigator_vm.ExplainAdapter.get_job_reason", fake_reason)
    monkeypatch.setattr("gui.services.artifact_navigator_vm.get_artifacts", fake_artifacts)
    if alignment_func:
        monkeypatch.setattr("gui.services.artifact_navigator_vm.resolve_data_alignment_status", alignment_func)
    else:
        monkeypatch.setattr(
            "gui.services.artifact_navigator_vm.resolve_data_alignment_status",
            lambda jid: alignment_status,
        )
    monkeypatch.setattr("gui.services.artifact_navigator_vm.get_outputs_root", lambda: tmp_path)
    monkeypatch.setattr("gui.services.artifact_navigator_vm.get_job_artifact_dir", lambda root, jid: artifact_dir)
    return artifact_dir


def test_artifact_present(monkeypatch, tmp_path):
    job_id = "job-present"
    alignment_path = tmp_path / job_id / ARTIFACT_NAME
    alignment_path.parent.mkdir(parents=True, exist_ok=True)
    alignment_path.write_text(json.dumps({"forward_fill_ratio": 0.75, "dropped_rows": 0, "forward_filled_rows": 0}))
    alignment_status = DataAlignmentStatus(
        status="OK",
        artifact_relpath=ARTIFACT_NAME,
        artifact_abspath=str(alignment_path),
        message="data_alignment_report.json is available",
        metrics={"forward_fill_ratio": 0.75, "dropped_rows": 0, "forward_filled_rows": 0},
    )
    artifact_files = [{"filename": ARTIFACT_NAME, "url": f"/api/v1/jobs/{job_id}/artifacts/{ARTIFACT_NAME}"}]
    _patch_dependencies(monkeypatch, tmp_path, job_id, GateStatus.PASS, alignment_status, artifact_files)

    vm = ArtifactNavigatorVM()
    vm.load_for_job(job_id)

    assert vm.gate["status"] == GateStatus.PASS.value
    assert vm.gate["actions"][0].target == GATE_SUMMARY_TARGET
    assert vm.explain["data_alignment_status"] == "OK"
    assert vm.explain["actions"][0].target.startswith(EXPLAIN_TARGET_PREFIX)
    assert len(vm.artifacts) == 1
    row = vm.artifacts[0]
    assert row["name"] == ARTIFACT_NAME
    assert row["status"] == "PRESENT"
    assert isinstance(row["action"], Action)
    assert row["action"].label == "Open"


def test_artifact_missing(monkeypatch, tmp_path):
    job_id = "job-missing"
    artifact_files = []
    alignment_status = DataAlignmentStatus(
        status="MISSING",
        artifact_relpath=ARTIFACT_NAME,
        artifact_abspath=str(tmp_path / job_id / ARTIFACT_NAME),
        message="Missing alignment artifact",
        metrics={},
    )
    _patch_dependencies(monkeypatch, tmp_path, job_id, GateStatus.WARN, alignment_status, artifact_files)

    vm = ArtifactNavigatorVM()
    vm.load_for_job(job_id)

    assert vm.gate["status"] == GateStatus.WARN.value
    assert vm.explain["data_alignment_status"] == "MISSING"
    assert "Missing alignment artifact" in vm.explain["message"]
    assert vm.artifacts[0]["status"] == "MISSING"
    assert vm.artifacts[0]["action"].label == "Locate"


def test_vm_uses_alignment_service(monkeypatch, tmp_path):
    job_id = "job-callcheck"
    artifact_files = []
    alignment_status = DataAlignmentStatus(
        status="OK",
        artifact_relpath=ARTIFACT_NAME,
        artifact_abspath=str(tmp_path / job_id / ARTIFACT_NAME),
        message="Available",
        metrics={},
    )
    calls = []

    def spy_alignment(jid):
        calls.append(jid)
        return alignment_status

    _patch_dependencies(
        monkeypatch,
        tmp_path,
        job_id,
        GateStatus.PASS,
        alignment_status,
        artifact_files,
        alignment_func=spy_alignment,
    )

    vm = ArtifactNavigatorVM()
    vm.load_for_job(job_id)

    assert calls == [job_id]
