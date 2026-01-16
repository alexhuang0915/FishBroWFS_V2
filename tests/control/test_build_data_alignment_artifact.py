import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from control.supervisor.handlers.build_data import BuildDataHandler


def _write_npz(path: Path, arrays: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(path, **arrays)


def _create_bars(path: Path):
    ts = np.array(
        [np.datetime64(f"2026-01-01T00:0{minute}:00") for minute in range(5)],
        dtype="datetime64[s]",
    )
    arrays = {
        "ts": ts,
        "open": np.arange(5),
        "high": np.arange(1, 6),
        "low": np.arange(0, 5),
        "close": np.arange(1, 6),
        "volume": np.ones(5, dtype=int) * 10,
    }
    _write_npz(path, arrays)


class DummyContext:
    def __init__(self, job_id: str, artifacts_dir: Path):
        self.job_id = job_id
        self.artifacts_dir = str(artifacts_dir)

    def heartbeat(self, *_, **__):
        pass

    def is_abort_requested(self):
        return False


def test_build_data_alignment_artifact(tmp_path: Path, monkeypatch):
    outputs_root = tmp_path / "outputs"
    monkeypatch.setenv("FISHBRO_OUTPUTS_ROOT", str(outputs_root))

    season = "2026Q1"
    timeframe = 60
    data1_dataset = "CME.MNQ.60m.2020-2024"
    data2_dataset = "CME.ES.60m.2020-2024"

    normalized_path = outputs_root / "shared" / season / data2_dataset / "bars" / "normalized_bars.npz"
    resampled_path = (
        outputs_root
        / "shared"
        / season
        / data1_dataset
        / "bars"
        / f"resampled_{timeframe}m.npz"
    )

    _create_bars(normalized_path)
    _create_bars(resampled_path)

    artifacts_dir = tmp_path / "handler_artifacts"
    artifacts_dir.mkdir()

    def fake_prepare(*args, **kwargs):
        return {
            "success": True,
            "data1_report": {"fingerprint_path": "/tmp/data1.json"},
            "data2_reports": {
                data2_dataset: {"fingerprint_path": "/tmp/data2.json", "success": True}
            },
        }

    handler = BuildDataHandler()
    params = {
        "dataset_id": data1_dataset,
        "timeframe_min": timeframe,
        "mode": "FULL",
        "season": season,
    }
    context = DummyContext(job_id="alignment-job", artifacts_dir=artifacts_dir)

    with patch("control.prepare_orchestration.prepare_with_data2_enforcement", side_effect=fake_prepare):
        handler.execute(params, context)

    job_artifact_dir = outputs_root / "jobs" / context.job_id
    report_path = job_artifact_dir / "data_alignment_report.json"
    assert report_path.exists()

    report = json.loads(report_path.read_text())
    required_keys = {
        "job_id",
        "instrument",
        "timeframe",
        "trade_date_roll_time_local",
        "timezone",
        "input_rows",
        "output_rows",
        "dropped_rows",
        "forward_filled_rows",
        "forward_fill_ratio",
        "generated_at",
    }
    assert required_keys.issubset(report.keys())
