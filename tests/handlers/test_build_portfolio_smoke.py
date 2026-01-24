import os
import sys
import subprocess
import tempfile
import unittest
from pathlib import Path


class TestBuildPortfolioSmoke(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="fishbro_test_portfolio_")
        self.addCleanup(self._tmp.cleanup)
        self.outputs_root = Path(self._tmp.name) / "outputs"
        os.environ["FISHBRO_OUTPUTS_ROOT"] = str(self.outputs_root)
        os.environ["FISHBRO_TEST_MODE"] = "1"

    def tearDown(self) -> None:
        os.environ.pop("FISHBRO_OUTPUTS_ROOT", None)
        os.environ.pop("FISHBRO_TEST_MODE", None)

    def test_portfolio_from_wfs_candidate(self) -> None:
        from control.supervisor import submit
        from control.supervisor.db import get_default_db_path, SupervisorDB

        season = "2026Q1"
        # First, run WFS (synthetic) to generate a candidate result.
        wfs_job_id = submit(
            "RUN_RESEARCH_WFS",
            {
                "strategy_id": "s1_v1",
                "instrument": "CME.MNQ",
                "timeframe": "60m",
                "start_season": "2020Q1",
                "end_season": "2020Q2",
                "season": season,
                "dataset_id": "CME.MNQ",
            },
        )
        # Then build portfolio from that WFS result.
        portfolio_job_id = submit(
            "BUILD_PORTFOLIO_V2",
            {
                "season": season,
                "candidate_run_ids": [wfs_job_id],
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
            "2",
        ]
        subprocess.run(cmd, check=True, env={**os.environ, "PYTHONPATH": "src"})

        db = SupervisorDB(get_default_db_path())
        self.assertEqual(db.get_job_row(wfs_job_id).state, "SUCCEEDED")
        self.assertEqual(db.get_job_row(portfolio_job_id).state, "SUCCEEDED")

        # Domain portfolio artifacts must exist.
        # Handler chooses portfolio_id if absent; read it from job evidence.
        job_dir = self.outputs_root / "artifacts" / "jobs" / portfolio_job_id
        result = (job_dir / "result.json").read_text(encoding="utf-8", errors="ignore")
        self.assertTrue(result)

        # At least ensure the seasons/portfolios tree exists.
        portfolios_root = self.outputs_root / "artifacts" / "seasons" / season / "portfolios"
        self.assertTrue(portfolios_root.exists())
        self.assertTrue(any(portfolios_root.iterdir()), "portfolios directory must not be empty")


if __name__ == "__main__":
    unittest.main()
