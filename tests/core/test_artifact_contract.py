import json
import os
import sys
import subprocess
import tempfile
import unittest
from pathlib import Path


class TestArtifactContract(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="fishbro_test_artifacts_")
        self.addCleanup(self._tmp.cleanup)
        self.outputs_root = Path(self._tmp.name) / "outputs"
        os.environ["FISHBRO_OUTPUTS_ROOT"] = str(self.outputs_root)
        os.environ["FISHBRO_TEST_MODE"] = "1"

    def tearDown(self) -> None:
        os.environ.pop("FISHBRO_OUTPUTS_ROOT", None)
        os.environ.pop("FISHBRO_TEST_MODE", None)

    def test_wfs_domain_result_and_job_pointer(self) -> None:
        from control.supervisor import submit
        from control.supervisor.db import get_default_db_path

        params = {
            "strategy_id": "regime_filter_v1",
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

        domain_path = self.outputs_root / "artifacts" / "seasons" / "2026Q1" / "wfs" / job_id / "result.json"
        self.assertTrue(domain_path.exists(), "domain result.json must exist")

        payload = json.loads(domain_path.read_text(encoding="utf-8"))
        self.assertEqual(payload.get("version"), "1.0")
        self.assertIn("meta", payload)
        self.assertIn("windows", payload)
        self.assertIn("series", payload)

        # Job evidence must include pointer to domain path.
        job_dir = self.outputs_root / "artifacts" / "jobs" / job_id
        ptr = (job_dir / "wfs_result_path.txt").read_text(encoding="utf-8").strip()
        self.assertEqual(Path(ptr).resolve(), domain_path.resolve())


if __name__ == "__main__":
    unittest.main()
