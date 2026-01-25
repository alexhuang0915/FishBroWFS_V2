import os
import json
import tempfile
import unittest
from pathlib import Path
import sys
import subprocess


class TestFinalizePortfolioContract(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="fishbro_test_finalize_portfolio_")
        self.addCleanup(self._tmp.cleanup)
        self.outputs_root = Path(self._tmp.name) / "outputs"
        os.environ["FISHBRO_OUTPUTS_ROOT"] = str(self.outputs_root)
        os.environ["FISHBRO_TEST_MODE"] = "1"

    def tearDown(self) -> None:
        os.environ.pop("FISHBRO_OUTPUTS_ROOT", None)
        os.environ.pop("FISHBRO_TEST_MODE", None)

    def test_finalize_writes_final_manifest(self) -> None:
        from control.supervisor import submit
        from control.supervisor.db import get_default_db_path

        season = "2026Q1"
        portfolio_id = "portfolio_test_1234"
        portfolio_dir = self.outputs_root / "artifacts" / "seasons" / season / "portfolios" / portfolio_id
        portfolio_dir.mkdir(parents=True, exist_ok=True)

        # Create minimal recommendations + selection files.
        (portfolio_dir / "recommendations.json").write_text(
            json.dumps(
                {
                    "version": "1.0",
                    "portfolio_id": portfolio_id,
                    "season": season,
                    "candidate_run_ids": ["runA", "runB"],
                    "recommended_run_ids": ["runA"],
                    "default_selected_run_ids": ["runA", "runB"],
                    "runs": [],
                    "generated_at": "2026-01-24T00:00:00Z",
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        (portfolio_dir / "portfolio_selection.json").write_text(
            json.dumps({"version": "1.0", "selected_run_ids": ["runA"]}, indent=2, sort_keys=True),
            encoding="utf-8",
        )

        job_id = submit("FINALIZE_PORTFOLIO_V1", {"season": season, "portfolio_id": portfolio_id})

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

        final_path = portfolio_dir / "final_manifest.json"
        self.assertTrue(final_path.exists(), "final_manifest.json must exist")
        payload = json.loads(final_path.read_text(encoding="utf-8"))
        self.assertEqual(payload.get("portfolio_id"), portfolio_id)
        self.assertEqual(payload.get("season"), season)
        self.assertEqual(payload.get("selected_run_ids"), ["runA"])

        # Job evidence pointer should exist.
        job_dir = self.outputs_root / "artifacts" / "jobs" / job_id
        ptr = (job_dir / "portfolio_final_manifest_path.txt").read_text(encoding="utf-8").strip()
        self.assertEqual(Path(ptr).resolve(), final_path.resolve())


if __name__ == "__main__":
    unittest.main()

