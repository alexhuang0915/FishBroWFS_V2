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

def _write_tiny_raw_csv_with_old_prefix(path: Path) -> None:
    rows = [
        "Date,Time,Open,High,Low,Close,TotalVolume",
        "2018-12-31,23:59:00,1,1,1,1,1",
        "2019-01-01,00:00:00,2,2,2,2,2",
        "2020-01-01,00:00:00,3,3,3,3,3",
        "2020-01-01,00:01:00,4,4,4,4,4",
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

    def test_build_bars_smoke(self) -> None:
        from control.supervisor import submit
        from control.supervisor.db import get_default_db_path

        dataset_id = "CME.MNQ"
        season = "2026Q1"
        raw_path = self.raw_root / "raw" / f"{dataset_id}_SUBSET.txt"
        _write_tiny_raw_csv(raw_path)

        job_id = submit(
            "BUILD_BARS",
            {"dataset_id": dataset_id, "timeframes": [60], "season": season, "force_rebuild": True},
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
        cache_root = Path(os.environ.get("FISHBRO_CACHE_ROOT", Path(self.outputs_root).parent / "cache"))
        resampled = cache_root / "shared" / season / dataset_id / "bars" / "resampled_60m.npz"
        self.assertTrue(resampled.exists(), "resampled_60m.npz must exist")

        # Job evidence must exist.
        job_dir = self.outputs_root / "artifacts" / "jobs" / job_id
        self.assertTrue((job_dir / "manifest.json").exists())

    def test_build_bars_resample_anchor_clip(self) -> None:
        import numpy as np

        from control.supervisor import submit
        from control.supervisor.db import get_default_db_path

        dataset_id = "CME.MNQ"
        season = "2026Q1"
        raw_path = self.raw_root / "raw" / f"{dataset_id}_SUBSET.txt"
        _write_tiny_raw_csv_with_old_prefix(raw_path)

        job_id = submit(
            "BUILD_BARS",
            {"dataset_id": dataset_id, "timeframes": [60], "season": season, "force_rebuild": True},
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

        cache_root = Path(os.environ.get("FISHBRO_CACHE_ROOT", Path(self.outputs_root).parent / "cache"))
        resampled = cache_root / "shared" / season / dataset_id / "bars" / "resampled_60m.npz"
        self.assertTrue(resampled.exists(), "resampled_60m.npz must exist")

        data = dict(np.load(resampled, allow_pickle=False))
        ts = data["ts"].astype("datetime64[s]")
        self.assertTrue(len(ts) > 0)
        self.assertGreaterEqual(ts[0], np.datetime64("2019-01-01T00:00:00", "s"))

        job_dir = self.outputs_root / "artifacts" / "jobs" / job_id
        self.assertTrue((job_dir / "manifest.json").exists())

    def test_build_bars_incremental_smoke(self) -> None:
        from control.supervisor import submit
        from control.supervisor.db import get_default_db_path

        dataset_id = "CME.MNQ"
        season = "2026Q1"
        raw_path = self.raw_root / "raw" / f"{dataset_id}_SUBSET.txt"
        _write_tiny_raw_csv(raw_path)

        job_id = submit(
            "BUILD_BARS",
            {"dataset_id": dataset_id, "timeframes": [60], "season": season, "force_rebuild": False},
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

        cache_root = Path(os.environ.get("FISHBRO_CACHE_ROOT", Path(self.outputs_root).parent / "cache"))
        resampled = cache_root / "shared" / season / dataset_id / "bars" / "resampled_60m.npz"
        self.assertTrue(resampled.exists(), "resampled_60m.npz must exist")

        job_dir = self.outputs_root / "artifacts" / "jobs" / job_id
        self.assertTrue((job_dir / "manifest.json").exists())

    def test_build_bars_purge_shared_dir_smoke(self) -> None:
        from control.supervisor import submit
        from control.supervisor.db import get_default_db_path

        dataset_id = "CME.MNQ"
        season = "2026Q1"
        raw_path = self.raw_root / "raw" / f"{dataset_id}_SUBSET.txt"
        _write_tiny_raw_csv(raw_path)

        cache_root = Path(os.environ.get("FISHBRO_CACHE_ROOT", Path(self.outputs_root).parent / "cache"))
        shared_dir = cache_root / "shared" / season / dataset_id
        shared_dir.mkdir(parents=True, exist_ok=True)
        junk = shared_dir / "junk.txt"
        junk.write_text("old\n", encoding="utf-8")

        job_id = submit(
            "BUILD_BARS",
            {
                "dataset_id": dataset_id,
                "timeframes": [60],
                "season": season,
                "force_rebuild": True,
                "purge_before_build": True,
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

        self.assertFalse(junk.exists(), "junk marker must be purged")

        resampled = cache_root / "shared" / season / dataset_id / "bars" / "resampled_60m.npz"
        self.assertTrue(resampled.exists(), "resampled_60m.npz must exist after purge+build")

        job_dir = self.outputs_root / "artifacts" / "jobs" / job_id
        self.assertTrue((job_dir / "manifest.json").exists())

    def test_build_data_full_all_packs_features_smoke(self) -> None:
        from control.supervisor import submit
        from control.supervisor.db import get_default_db_path

        dataset_id = "CME.MNQ"
        season = "2026Q1"
        raw_path = self.raw_root / "raw" / f"{dataset_id}_SUBSET.txt"
        _write_tiny_raw_csv(raw_path)

        bars_job_id = submit(
            "BUILD_BARS",
            {"dataset_id": dataset_id, "timeframes": [60], "season": season, "force_rebuild": True},
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

        features_job_id = submit(
            "BUILD_FEATURES",
            {
                "dataset_id": dataset_id,
                "timeframes": [60],
                "season": season,
                "force_rebuild": True,
                "feature_scope": "all_packs",
            },
        )

        subprocess.run(cmd, check=True, env={**os.environ, "PYTHONPATH": "src"})

        cache_root = Path(os.environ.get("FISHBRO_CACHE_ROOT", Path(self.outputs_root).parent / "cache"))
        features_npz = cache_root / "shared" / season / dataset_id / "features" / "features_60m.npz"
        self.assertTrue(features_npz.exists(), "features_60m.npz must exist")

        # Spot-check one data1_v1_full feature key exists.
        import numpy as np

        data = dict(np.load(features_npz, allow_pickle=False))
        self.assertIn("sma_20", data)

        bars_job_dir = self.outputs_root / "artifacts" / "jobs" / bars_job_id
        self.assertTrue((bars_job_dir / "manifest.json").exists())
        features_job_dir = self.outputs_root / "artifacts" / "jobs" / features_job_id
        self.assertTrue((features_job_dir / "manifest.json").exists())


if __name__ == "__main__":
    unittest.main()
