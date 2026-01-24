import os
import sys
import subprocess
import tempfile
import unittest
from pathlib import Path


def _write_tiny_raw_csv(path: Path) -> None:
    # Minimal schema supported by core.data.raw_ingest.ingest_raw_txt()
    # Columns are case-insensitive; shared_build normalizes to lower.
    rows = [
        "Date,Time,Open,High,Low,Close,TotalVolume",
        "2020-01-01,00:00:00,1,2,0.5,1.5,100",
        "2020-01-01,00:01:00,1.5,2.5,1,2,120",
        "2020-01-01,00:02:00,2,3,1.5,2.5,110",
        "2020-01-01,00:03:00,2.5,3.2,2.2,3.0,90",
        "2020-01-01,00:04:00,3.0,3.5,2.8,3.2,80",
    ]
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


class TestBuildDataSmoke(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="fishbro_test_build_data_")
        self.addCleanup(self._tmp.cleanup)
        self.outputs_root = Path(self._tmp.name) / "outputs"
        self.raw_root = Path(self._tmp.name) / "FishBroData"
        (self.raw_root / "raw").mkdir(parents=True, exist_ok=True)

        os.environ["FISHBRO_OUTPUTS_ROOT"] = str(self.outputs_root)
        os.environ["FISHBRO_RAW_ROOT"] = str(self.raw_root)

    def tearDown(self) -> None:
        os.environ.pop("FISHBRO_OUTPUTS_ROOT", None)
        os.environ.pop("FISHBRO_RAW_ROOT", None)

    def test_build_data_bars_only_smoke(self) -> None:
        from control.supervisor import submit
        from control.supervisor.db import get_default_db_path

        dataset_id = "CME.MNQ"
        season = "2026Q1"
        raw_path = self.raw_root / "raw" / f"{dataset_id}_SUBSET.txt"
        _write_tiny_raw_csv(raw_path)

        job_id = submit(
            "BUILD_DATA",
            {
                "dataset_id": dataset_id,
                "timeframe_min": 60,
                "mode": "BARS_ONLY",
                "season": season,
                "force_rebuild": True,
            },
        )

        cmd = [
            sys.executable,
            "-m",
            "control.supervisor.worker",
            "--db",
            str(get_default_db_path()),
            "--max-workers",
            "1",
            "--tick-interval",
            "0.05",
            "--max-jobs",
            "1",
        ]
        subprocess.run(cmd, check=True, env={**os.environ, "PYTHONPATH": "src"})

        # Smoke: resampled bars should exist (at least 60m).
        resampled = self.outputs_root / "shared" / season / dataset_id / "bars" / "resampled_60m.npz"
        self.assertTrue(resampled.exists(), "resampled_60m.npz must exist")

        # Job evidence must exist.
        job_dir = self.outputs_root / "artifacts" / "jobs" / job_id
        self.assertTrue((job_dir / "manifest.json").exists())


if __name__ == "__main__":
    unittest.main()
