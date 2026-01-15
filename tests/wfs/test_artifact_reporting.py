import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from contracts.research_wfs.result_schema import TimeRange, WindowResult
from control.supervisor.job_handler import JobContext
from control.supervisor.handlers.run_research_wfs import RunResearchWFSHandler
from wfs.artifact_reporting import write_governance_and_scoring_artifacts


def test_write_governance_and_scoring_artifacts_creates_files(tmp_path: Path):
    """Ensure the helper emits both JSON artifacts with the right schema."""
    inputs = {
        "instrument": "MNQ",
        "timeframe": "60m",
        "run_mode": "wfs",
        "season": "2026Q1",
    }
    raw = {"net_profit": 1200.0, "mdd": 180.0, "trades": 40}
    final = {"final_score": 8.5, "robustness_factor": 0.92, "trade_multiplier": 2.1}
    guards = {
        "edge_gate": {"passed": True, "threshold": 5.0, "value": 30.0},
        "cliff_gate": {"passed": True, "threshold": 0.7, "value": 0.92},
        "notes": ["Edge gate satisfied", "Cliff gate satisfied"],
    }
    governance = {
        "policy_enforced": True,
        "compliance_passed": True,
        "mode": {"mode_b_enabled": False, "scoring_guards_enabled": True},
        "gates": {"edge_gate_passed": True, "cliff_gate_passed": True, "reasons": []},
        "inputs": inputs,
        "metrics": raw,
        "links": {"scoring_breakdown": "scoring_breakdown.json"},
        "notes": guards["notes"],
    }

    summary_path, breakdown_path = write_governance_and_scoring_artifacts(
        job_id="test_job",
        out_dir=tmp_path,
        inputs=inputs,
        raw=raw,
        final=final,
        guards=guards,
        governance=governance,
    )

    assert summary_path.exists()
    assert breakdown_path.exists()

    summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary_payload["schema_version"] == "1.0"
    assert summary_payload["job_id"] == "test_job"
    assert summary_payload["mode"]["scoring_guards_enabled"] is True

    breakdown_payload = json.loads(breakdown_path.read_text(encoding="utf-8"))
    assert breakdown_payload["schema_version"] == "1.0"
    assert breakdown_payload["guards"]["edge_gate"]["passed"] is True
    assert breakdown_payload["final"]["final_score"] == 8.5


def test_run_research_wfs_handler_emits_governance_artifacts(tmp_path: Path, monkeypatch):
    """Handler should write the new governance/scoring artifacts during execution."""
    job_id = "wfs-artifact-job"
    artifacts_dir = tmp_path / job_id
    db = MagicMock()
    db.is_abort_requested.return_value = False
    handler = RunResearchWFSHandler()

    # Stub window execution to minimize runtime
    mock_window = WindowResult(
        season="2025Q4",
        is_range=TimeRange(start="2022-10-01T00:00:00Z", end="2025-09-30T23:59:59Z"),
        oos_range=TimeRange(start="2025-10-01T00:00:00Z", end="2025-12-31T23:59:59Z"),
        best_params={"param1": 1.0},
        is_metrics={"net": 1000.0, "mdd": 200.0, "trades": 20},
        oos_metrics={"net": 500.0, "mdd": 120.0, "trades": 20},
        pass_=True,
        fail_reasons=[],
    )

    monkeypatch.setattr(
        RunResearchWFSHandler,
        "_execute_wfs_windows",
        lambda self, **kwargs: (
            [mock_window],
            [[{"t": "2025-01-01T00:00:00Z", "v": 0.0}]],
            [[{"t": "2025-01-01T00:00:00Z", "v": 0.0}]],
            [[{"t": "2025-01-01T00:00:00Z", "v": 0.0}]],
        ),
    )

    metrics = {
        "rf": 2.8,
        "wfe": 0.7,
        "ecr": 2.2,
        "trades": 40,
        "pass_rate": 0.75,
        "ulcer_index": 4.5,
        "max_underwater_days": 8,
        "net_profit": 1500.0,
        "max_dd": 200.0,
    }
    monkeypatch.setattr(RunResearchWFSHandler, "_aggregate_metrics", lambda self, windows: metrics)

    context = JobContext(job_id, db, str(artifacts_dir))
    params = {
        "strategy_id": "S1",
        "instrument": "MNQ",
        "timeframe": "60m",
        "run_mode": "wfs",
        "season": "2026Q1",
        "start_season": "2023Q1",
        "end_season": "2026Q1",
    }

    result = handler.execute(params, context)

    assert result["ok"] is True

    summary_path = artifacts_dir / "governance_summary.json"
    breakdown_path = artifacts_dir / "scoring_breakdown.json"
    assert summary_path.exists()
    assert breakdown_path.exists()

    summary_payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary_payload["job_id"] == job_id
    assert summary_payload["schema_version"] == "1.0"
    assert summary_payload["gates"]["edge_gate_passed"] is True

    breakdown_payload = json.loads(breakdown_path.read_text(encoding="utf-8"))
    assert breakdown_payload["raw"]["trades"] == 40
    assert "cliff_gate" in breakdown_payload["guards"]
