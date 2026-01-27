import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from control.matrix_summary_cli import main

class TestMatrixSummaryCli(unittest.TestCase):
    def test_auto_run_flow(self):
        with TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            outputs_root = tmpdir_path / "outputs"
            artifacts_root = outputs_root / "artifacts"
            
            auto_run_id = "auto_test_123"
            auto_run_dir = artifacts_root / "auto_runs" / auto_run_id
            auto_run_dir.mkdir(parents=True)
            
            # 1. Create fake manifest.json
            job_ids = ["job1", "job2", "job3"]
            manifest = {
                "plan": {"season": "2026Q1"},
                "steps": [
                    {
                        "name": "RUN_RESEARCH_WFS",
                        "states": {
                            "job1": "SUCCEEDED",
                            "job2": "SUCCEEDED",
                            "job3": "SUCCEEDED",
                            "job4": "FAILED"
                        }
                    }
                ]
            }
            with (auto_run_dir / "manifest.json").open("w") as f:
                json.dump(manifest, f)
            
            # 2. Create fake job results
            # job1: data1=A, grade=B, score=80
            # job2: data1=A, grade=A, score=90
            # job3: data1=B, grade=A, score=70
            
            for jid, data1, grade, score in [
                ("job1", "CME.MNQ", "B", 80.0),
                ("job2", "CME.MNQ", "A", 90.0),
                ("job3", "TWF.MXF", "A", 70.0)
            ]:
                job_dir = artifacts_root / "jobs" / jid
                job_dir.mkdir(parents=True)
                
                wfs_res_dir = artifacts_root / "seasons/2026Q1/wfs" / jid
                wfs_res_dir.mkdir(parents=True)
                wfs_res_path = wfs_res_dir / "result.json"
                
                # Job evidence path contract (preferred)
                (job_dir / "wfs_result_path.txt").write_text(str(wfs_res_path), encoding="utf-8")
                
                # WFS result
                wfs_data = {
                    "meta": {
                        "instrument": data1,
                        "timeframe": "60m",
                        "strategy_family": "regime_filter_v1"
                    },
                    "config": {
                        "data": {"data1": data1, "data2": "CFE.VX", "timeframe": "60m"}
                    },
                    "metrics": {
                        "raw": {"pass_rate": 0.5, "trades": 10},
                        "scores": {"total_weighted": score}
                    },
                    "verdict": {"grade": grade, "is_tradable": True},
                    "windows": [
                        {
                            "oos_metrics": {
                                "data2_missing_ratio_pct": 1.0,
                                "data2_update_ratio_pct": 2.0,
                                "data2_hold_ratio_pct": 97.0
                            }
                        },
                        {
                            "oos_metrics": {
                                "data2_missing_ratio_pct": 3.0,
                                "data2_update_ratio_pct": 4.0,
                                "data2_hold_ratio_pct": 93.0
                            }
                        }
                    ]
                }
                with wfs_res_path.open("w") as f:
                    json.dump(wfs_data, f)

            # Patch paths to use our temp outputs
            with patch("control.job_artifacts.get_outputs_root", return_value=outputs_root), \
                 patch("control.matrix_summary_cli.get_artifacts_root", return_value=artifacts_root):
                
                # Run CLI
                with patch("sys.argv", ["prog", "--auto-run", auto_run_id]):
                    ret = main()
                    self.assertEqual(ret, 0)
                
                # Assertions
                summary_path = auto_run_dir / "matrix_summary.json"
                self.assertTrue(summary_path.exists())
                
                with summary_path.open("r") as f:
                    summary = json.load(f)
                
                self.assertEqual(summary["version"], "1.0")
                self.assertEqual(len(summary["rows"]), 3)
                
                # Check sorting for CME.MNQ: job2 (A) should be before job1 (B)
                rows = summary["rows"]
                self.assertEqual(rows[0]["job_id"], "job2") # CME.MNQ Grade A
                self.assertEqual(rows[1]["job_id"], "job1") # CME.MNQ Grade B
                self.assertEqual(rows[2]["job_id"], "job3") # TWF.MXF
                
                # Check mean calculation
                self.assertEqual(rows[0]["data2_missing_ratio_pct"], 2.0) # (1+3)/2
                
                self.assertIn("CME.MNQ", summary["grouped"])
                self.assertEqual(summary["grouped"]["CME.MNQ"]["ranked_job_ids"], ["job2", "job1"])

    def test_latest_auto_run_flag(self):
        with TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            outputs_root = tmpdir_path / "outputs"
            artifacts_root = outputs_root / "artifacts"

            # Create two auto-runs; latest should be chosen alphabetically and by naming convention.
            auto_run_old = "auto_2026Q1_20260101_000000"
            auto_run_new = "auto_2026Q1_20260102_000000"
            (artifacts_root / "auto_runs" / auto_run_old).mkdir(parents=True)
            (artifacts_root / "auto_runs" / auto_run_new).mkdir(parents=True)

            def write_manifest(run_id: str, season: str, job_ids: list[str]) -> None:
                manifest = {
                    "plan": {"season": season},
                    "steps": [{"name": "RUN_RESEARCH_WFS", "states": {jid: "SUCCEEDED" for jid in job_ids}}],
                }
                with (artifacts_root / "auto_runs" / run_id / "manifest.json").open("w") as f:
                    json.dump(manifest, f)

            # Only NEW run has jobs; OLD is empty.
            write_manifest(auto_run_old, "2026Q1", [])
            write_manifest(auto_run_new, "2026Q1", ["job_new"])

            # Create job evidence + domain result for job_new
            job_dir = artifacts_root / "jobs" / "job_new"
            job_dir.mkdir(parents=True)
            wfs_res_dir = artifacts_root / "seasons/2026Q1/wfs" / "job_new"
            wfs_res_dir.mkdir(parents=True)
            wfs_res_path = wfs_res_dir / "result.json"
            (job_dir / "wfs_result_path.txt").write_text(str(wfs_res_path), encoding="utf-8")
            with wfs_res_path.open("w") as f:
                json.dump(
                    {
                        "meta": {"instrument": "CME.MNQ", "timeframe": "60m", "strategy_family": "baseline_v1"},
                        "config": {"data": {"data1": "CME.MNQ", "data2": "CFE.VX", "timeframe": "60m"}},
                        "metrics": {"raw": {"pass_rate": 0.0, "trades": 1}, "scores": {"total_weighted": 40.0}},
                        "verdict": {"grade": "D", "is_tradable": False},
                        "windows": [],
                    },
                    f,
                )

            with patch("control.job_artifacts.get_outputs_root", return_value=outputs_root), \
                 patch("control.matrix_summary_cli.get_artifacts_root", return_value=artifacts_root):
                with patch("sys.argv", ["prog", "--latest-auto-run"]):
                    ret = main()
                    self.assertEqual(ret, 0)

            # Must be written into the latest auto-run directory.
            self.assertTrue((artifacts_root / "auto_runs" / auto_run_new / "matrix_summary.json").exists())

if __name__ == "__main__":
    unittest.main()
