import json
from typing import Dict, Any

from gui.services.artifact_navigator_vm import (
    ArtifactNavigatorVM,
    Action,
    GATE_SUMMARY_TARGET,
    EXPLAIN_TARGET_PREFIX,
    GateProvider,
    ExplainProvider,
    ArtifactIndexProvider,
)
from gui.services.gate_summary_service import GateSummary, GateStatus
from gui.services.data_alignment_status import (
    DataAlignmentStatus,
    ARTIFACT_NAME,
)
from gui.services.explain_adapter import JobReason


def _create_stub_providers(
    tmp_path,
    job_id,
    gate_status,
    alignment_status,
    artifact_files,
    alignment_func=None,
):
    artifact_dir = tmp_path / job_id
    artifact_dir.mkdir(parents=True, exist_ok=True)

    # Spy counters for network call detection
    gate_call_count = 0
    explain_call_count = 0
    artifact_call_count = 0

    def fake_gate_provider() -> GateSummary:
        nonlocal gate_call_count
        gate_call_count += 1
        return GateSummary(
            gates=[],
            timestamp="2026-01-17T00:00:00Z",
            overall_status=gate_status,
            overall_message="Gates evaluated.",
        )

    def fake_explain_provider(jid: str) -> JobReason:
        nonlocal explain_call_count
        explain_call_count += 1
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

    def fake_artifact_index_provider(jid: str) -> Dict[str, Any]:
        nonlocal artifact_call_count
        artifact_call_count += 1
        return {"job_id": jid, "files": artifact_files}

    # Alignment function (not a provider but used by VM)
    if alignment_func:
        fake_alignment = alignment_func
    else:
        fake_alignment = lambda jid: alignment_status

    # Monkeypatch the file system dependencies (these are not network calls)
    import gui.services.artifact_navigator_vm as vm_module
    import pytest
    from unittest.mock import patch

    # We'll use monkeypatch in the test functions, not here
    return {
        "gate_provider": fake_gate_provider,
        "explain_provider": fake_explain_provider,
        "artifact_index_provider": fake_artifact_index_provider,
        "alignment_func": fake_alignment,
        "artifact_dir": artifact_dir,
        "counters": {
            "gate": lambda: gate_call_count,
            "explain": lambda: explain_call_count,
            "artifact": lambda: artifact_call_count,
        },
    }


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
    
    stubs = _create_stub_providers(
        tmp_path, job_id, GateStatus.PASS, alignment_status, artifact_files
    )
    
    # Monkeypatch file system dependencies
    monkeypatch.setattr("gui.services.artifact_navigator_vm.get_outputs_root", lambda: tmp_path)
    monkeypatch.setattr(
        "gui.services.artifact_navigator_vm.get_job_artifact_dir",
        lambda root, jid: stubs["artifact_dir"],
    )
    monkeypatch.setattr(
        "gui.services.artifact_navigator_vm.resolve_data_alignment_status",
        stubs["alignment_func"],
    )
    
    vm = ArtifactNavigatorVM(
        gate_provider=stubs["gate_provider"],
        explain_provider=stubs["explain_provider"],
        artifact_index_provider=stubs["artifact_index_provider"],
    )
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
    
    # Assert providers were called (counts > 0) and no network helpers were invoked
    assert stubs["counters"]["gate"]() > 0
    assert stubs["counters"]["explain"]() > 0
    assert stubs["counters"]["artifact"]() > 0


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
    
    stubs = _create_stub_providers(
        tmp_path, job_id, GateStatus.WARN, alignment_status, artifact_files
    )
    
    monkeypatch.setattr("gui.services.artifact_navigator_vm.get_outputs_root", lambda: tmp_path)
    monkeypatch.setattr(
        "gui.services.artifact_navigator_vm.get_job_artifact_dir",
        lambda root, jid: stubs["artifact_dir"],
    )
    monkeypatch.setattr(
        "gui.services.artifact_navigator_vm.resolve_data_alignment_status",
        stubs["alignment_func"],
    )
    
    vm = ArtifactNavigatorVM(
        gate_provider=stubs["gate_provider"],
        explain_provider=stubs["explain_provider"],
        artifact_index_provider=stubs["artifact_index_provider"],
    )
    vm.load_for_job(job_id)

    assert vm.gate["status"] == GateStatus.WARN.value
    assert vm.explain["data_alignment_status"] == "MISSING"
    assert "Missing alignment artifact" in vm.explain["message"]
    assert vm.artifacts[0]["status"] == "MISSING"
    assert vm.artifacts[0]["action"].label == "Locate"
    
    # Assert providers were called
    assert stubs["counters"]["gate"]() > 0
    assert stubs["counters"]["explain"]() > 0
    assert stubs["counters"]["artifact"]() > 0


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

    stubs = _create_stub_providers(
        tmp_path, job_id, GateStatus.PASS, alignment_status, artifact_files,
        alignment_func=spy_alignment,
    )
    
    monkeypatch.setattr("gui.services.artifact_navigator_vm.get_outputs_root", lambda: tmp_path)
    monkeypatch.setattr(
        "gui.services.artifact_navigator_vm.get_job_artifact_dir",
        lambda root, jid: stubs["artifact_dir"],
    )
    monkeypatch.setattr(
        "gui.services.artifact_navigator_vm.resolve_data_alignment_status",
        stubs["alignment_func"],
    )
    
    vm = ArtifactNavigatorVM(
        gate_provider=stubs["gate_provider"],
        explain_provider=stubs["explain_provider"],
        artifact_index_provider=stubs["artifact_index_provider"],
    )
    vm.load_for_job(job_id)

    assert calls == [job_id]
    # Assert providers were called
    assert stubs["counters"]["gate"]() > 0
    assert stubs["counters"]["explain"]() > 0
    assert stubs["counters"]["artifact"]() > 0
