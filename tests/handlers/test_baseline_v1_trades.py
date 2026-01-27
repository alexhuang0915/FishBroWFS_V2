import os
import sys
import subprocess
import tempfile
import unittest
from pathlib import Path
import numpy as np
from datetime import datetime, timedelta
import json

class TestBaselineV1Trades(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="fishbro_test_baseline_")
        self.addCleanup(self._tmp.cleanup)
        
        # Setup workspace root for path resolution
        self.workspace_root = Path("/home/fishbro/FishBroWFS_V2")
        
        self.outputs_root = Path(self._tmp.name) / "outputs"
        self.outputs_root.mkdir(parents=True)
        
        # Override outputs root
        os.environ["FISHBRO_OUTPUTS_ROOT"] = str(self.outputs_root)
        os.environ["FISHBRO_TEST_MODE"] = "1"
        
        self.env = {
            **os.environ,
            "PYTHONPATH": str(self.workspace_root / "src"),
        }

    def tearDown(self) -> None:
        os.environ.pop("FISHBRO_OUTPUTS_ROOT", None)
        os.environ.pop("FISHBRO_TEST_MODE", None)

    def test_baseline_v1_produces_trades(self) -> None:
        # Use import here to ensure they use the environment variable
        from control.supervisor import submit
        from control.supervisor.db import SupervisorDB, get_default_db_path
        from control.bars_store import write_npz_atomic, resampled_bars_path

        # 1. Create mock bars
        # Range: 2017-01-01 to 2020-03-31 (approx 3.25 years)
        start_ts = datetime(2017, 1, 1)
        end_ts = datetime(2020, 6, 1) # Enough to cover 2020Q1 OOS
        hours = int((end_ts - start_ts).total_seconds() / 3600)
        
        ts = np.array([np.datetime64(start_ts + timedelta(hours=i)) for i in range(hours)])
        n = len(ts)
        
        # Deterministic price: Sine wave + trend
        t_vals = np.linspace(0, 100, n)
        close = 10000.0 + 500.0 * np.sin(t_vals) + 10.0 * np.arange(n)
        open_ = close - 2.0
        high = close + 10.0
        low = close - 10.0
        volume = np.full(n, 1000.0)

        bars = {
            "ts": ts,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume
        }

        season_run = "2020Q2" 
        instrument = "CME.MNQ"
        tf_min = 60
        
        path = resampled_bars_path(self.outputs_root, season_run, instrument, str(tf_min))
        write_npz_atomic(path, bars)

        # 2. Submit job
        params = {
            "strategy_id": "baseline_v1",
            "instrument": instrument,
            "timeframe": f"{tf_min}m",
            "start_season": "2020Q1",
            "end_season": "2020Q1",
            "season": season_run,
        }
        job_id = submit("RUN_RESEARCH_WFS", params)

        # 3. Run worker
        cmd = [
            sys.executable,
            "-m",
            "control.supervisor.worker",
            "--db", str(get_default_db_path()),
            "--max-workers", "1",
            "--tick-interval", "0.05",
            "--max-jobs", "1",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, env=self.env)
        if proc.returncode != 0:
            print(proc.stdout)
            print(proc.stderr)
            self.fail("Worker failed")

        # 4. Assertions
        db = SupervisorDB(get_default_db_path())
        row = db.get_job_row(job_id)
        self.assertEqual(row.state, "SUCCEEDED")

        result_path = self.outputs_root / "artifacts" / "seasons" / season_run / "wfs" / job_id / "result.json"
        domain_result_path_txt = self.outputs_root / "artifacts" / "jobs" / job_id / "wfs_result_path.txt"
        
        self.assertTrue(result_path.exists())
        self.assertTrue(domain_result_path_txt.exists())
        self.assertEqual(domain_result_path_txt.read_text().strip(), str(result_path))
        
        with result_path.open("r") as f:
            res = json.load(f)
        
        raw_metrics = res["metrics"]["raw"]
        print(f"\n[Verified] Trades: {raw_metrics['trades']}, Net: {raw_metrics['net_profit']:.2f}")
        
        self.assertGreater(raw_metrics["trades"], 0)
        self.assertIn("net_profit", raw_metrics)
        self.assertIn("max_drawdown", raw_metrics)
        self.assertIn("grade", res["verdict"])
        
        self.assertTrue(len(res["windows"]) > 0)
        self.assertTrue(len(res["windows"][0]["oos_trades"]) > 0)

        # 5. Verify Report Builder
        from control.reporting.builders import build_strategy_report_v1
        report = build_strategy_report_v1(job_id)
        
        self.assertEqual(report.job_id, job_id)
        self.assertIsNotNone(report.headline_metrics.net_profit)
        self.assertIsNotNone(report.headline_metrics.max_drawdown)
        self.assertIsNotNone(report.series.equity)
        self.assertGreater(len(report.series.equity), 0)
        
        # Verify closure (Task 2)
        self.assertIsNotNone(report.series.drawdown)
        self.assertEqual(len(report.series.drawdown), len(report.series.equity))
        self.assertIsNotNone(report.distributions.returns_histogram)
        self.assertEqual(len(report.distributions.returns_histogram.bin_edges), 22) # 21 bins -> 22 edges
        self.assertEqual(len(report.distributions.returns_histogram.counts), 21)
        # Drawdown should be <= 0 and start at 0 once peak is established.
        self.assertAlmostEqual(report.series.drawdown[0].value, 0.0, places=9)
        self.assertTrue(all(p.value <= 1e-9 for p in report.series.drawdown))
        # Histogram should have some mass.
        self.assertGreater(sum(report.distributions.returns_histogram.counts), 0)

        # Verify Task 4: Metrics completeness
        self.assertIsNotNone(report.headline_metrics.profit_factor)
        self.assertIsNotNone(report.headline_metrics.sharpe)
        self.assertIsNotNone(report.headline_metrics.calmar)
        self.assertGreater(report.headline_metrics.profit_factor, 0)
        self.assertGreater(report.headline_metrics.trades, 0)

if __name__ == "__main__":
    unittest.main()
