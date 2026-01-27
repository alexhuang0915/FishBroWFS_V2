import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import patch

from control.matrix_select_cli import main as select_main
from control.matrix_summary_cli import main as summary_main

def load_json(path: Path) -> Any:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

class TestMatrixSelectCli(unittest.TestCase):
    def test_selection_logic(self):
        with TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            outputs_root = tmpdir_path / "outputs"
            artifacts_root = outputs_root / "artifacts"
            
            auto_run_id = "auto_2026Q1_20260126_120000"
            run_dir = artifacts_root / "auto_runs" / auto_run_id
            run_dir.mkdir(parents=True)
            
            # 1. Create mock WFS results
            seasons_dir = artifacts_root / "seasons" / "2026Q1" / "wfs"
            seasons_dir.mkdir(parents=True)
            
            def create_wfs_res(job_id, d1, d2, grade, score, trades, missing=0.0):
                res_path = seasons_dir / job_id / "result.json"
                res_path.parent.mkdir(parents=True)
                with res_path.open("w") as f:
                    json.dump({
                        "meta": {"instrument": d1, "strategy_family": "base", "timeframe": "60m"},
                        "config": {"data": {"data1": d1, "data2": d2, "timeframe": "60m"}},
                        "metrics": {
                            "scores": {"total_weighted": score},
                            "raw": {"trades": trades, "pass_rate": 0.5, "data2_missing_ratio_pct": missing}
                        },
                        "verdict": {"grade": grade, "is_tradable": True},
                        "windows": [{"oos_metrics": {"data2_missing_ratio_pct": missing}}]
                    }, f)
                
                # Link in job evidence
                job_ev = artifacts_root / "jobs" / job_id
                job_ev.mkdir(parents=True)
                (job_ev / "wfs_result_path.txt").write_text(str(res_path))

            # Mix of results
            create_wfs_res("job1", "CME.MNQ", "CFE.VX", "A", 80.0, 50)
            create_wfs_res("job2", "CME.MNQ", "CME.6J", "B", 85.0, 40) # Higher score but lower grade
            create_wfs_res("job3", "CME.ES", "CFE.VX", "A", 70.0, 30)
            create_wfs_res("job4", "CME.ES", "CME.6J", "A", 90.0, 60, missing=10.0)

            # 2. Create manifest
            manifest = {
                "plan": {"season": "2026Q1"},
                "steps": [
                    {"name": "RUN_RESEARCH_WFS", "states": {"job1": "SUCCEEDED", "job2": "SUCCEEDED", "job3": "SUCCEEDED", "job4": "SUCCEEDED"}}
                ]
            }
            with (run_dir / "manifest.json").open("w") as f:
                json.dump(manifest, f)

            with patch("control.job_artifacts.get_outputs_root", return_value=outputs_root), \
                 patch("control.matrix_summary_cli.get_artifacts_root", return_value=artifacts_root), \
                 patch("control.matrix_select_cli.get_artifacts_root", return_value=artifacts_root):
                
                # 3. Generate summary first
                with patch("sys.argv", ["prog", "--auto-run", auto_run_id]):
                    summary_main()
                
                self.assertTrue((run_dir / "matrix_summary.json").exists())

                # 4. Test selection with defaults
                with patch("sys.argv", ["prog", "--auto-run", auto_run_id]):
                    select_main()
                
                selection = load_json(run_dir / "selection.json")
                # Default sort: score DESC.
                # job4 (90), job2 (85), job1 (80), job3 (70)
                self.assertEqual(selection["selected_job_ids"], ["job4", "job2", "job1", "job3"])

                # 5. Test selection with grade filter
                with patch("sys.argv", ["prog", "--auto-run", auto_run_id, "--filter-grade", "A"]):
                    select_main()
                selection = load_json(run_dir / "selection.json")
                # job2 is "B", filter it out.
                # job4 (90), job1 (80), job3 (70)
                self.assertEqual(selection["selected_job_ids"], ["job4", "job1", "job3"])

                # 6. Test selection with top-k per data1
                with patch("sys.argv", ["prog", "--auto-run", auto_run_id, "--top-k-per-data1", "1"]):
                    select_main()
                selection = load_json(run_dir / "selection.json")
                # CME.ES (job4=90, job3=70) -> job4
                # CME.MNQ (job2=85, job1=80) -> job2
                # Resulting order: job4, job2 (sorted by score DESC initially)
                self.assertEqual(selection["selected_job_ids"], ["job4", "job2"])

                # 7. Test max missing ratio
                with patch("sys.argv", ["prog", "--auto-run", auto_run_id, "--max-missing-ratio", "5.0"]):
                    select_main()
                selection = load_json(run_dir / "selection.json")
                # job4 has 10.0 missing, filter it out.
                # job2 (85), job1 (80), job3 (70)
                self.assertEqual(selection["selected_job_ids"], ["job2", "job1", "job3"])

if __name__ == "__main__":
    unittest.main()
