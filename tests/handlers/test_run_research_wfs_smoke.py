import os
import sys
import subprocess
import tempfile
import unittest
from pathlib import Path


class TestRunResearchWFSSmoke(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="fishbro_test_wfs_")
        self.addCleanup(self._tmp.cleanup)
        self.outputs_root = Path(self._tmp.name) / "outputs"
        os.environ["FISHBRO_OUTPUTS_ROOT"] = str(self.outputs_root)

    def tearDown(self) -> None:
        os.environ.pop("FISHBRO_OUTPUTS_ROOT", None)
        os.environ.pop("FISHBRO_TEST_MODE", None)

    def test_missing_bars_fail_closed(self) -> None:
        from control.supervisor import submit
        from control.supervisor.db import SupervisorDB, get_default_db_path

        os.environ["FISHBRO_TEST_MODE"] = "0"
        params = {
            "strategy_id": "s1_v1",
            "instrument": "CME.MNQ",
            "timeframe": "60m",
            "start_season": "2020Q1",
            "end_season": "2020Q2",
            "season": "2026Q1",
            "dataset_id": "CME.MNQ",
        }
        job_id = submit("RUN_RESEARCH_WFS", params)

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

        db = SupervisorDB(get_default_db_path())
        row = db.get_job_row(job_id)
        self.assertIsNotNone(row)
        self.assertEqual(row.state, "FAILED")

        err = (self.outputs_root / "artifacts" / "jobs" / job_id / "error.txt").read_text(encoding="utf-8", errors="ignore")
        self.assertIn("Missing bars", err)

    def test_test_mode_succeeds_synthetic(self) -> None:
        from control.supervisor import submit
        from control.supervisor.db import SupervisorDB, get_default_db_path

        os.environ["FISHBRO_TEST_MODE"] = "1"
        params = {
            "strategy_id": "s1_v1",
            "instrument": "CME.MNQ",
            "timeframe": "60m",
            "start_season": "2020Q1",
            "end_season": "2020Q2",
            "season": "2026Q1",
            "dataset_id": "CME.MNQ",
        }
        job_id = submit("RUN_RESEARCH_WFS", params)

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

        db = SupervisorDB(get_default_db_path())
        row = db.get_job_row(job_id)
        self.assertIsNotNone(row)
        self.assertEqual(row.state, "SUCCEEDED")

        domain_path = self.outputs_root / "artifacts" / "seasons" / "2026Q1" / "wfs" / job_id / "result.json"
        self.assertTrue(domain_path.exists())


if __name__ == "__main__":
    unittest.main()
