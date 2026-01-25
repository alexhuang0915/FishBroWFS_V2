import os
import json
import tempfile
import unittest
from pathlib import Path
import sys

repo_root = Path(__file__).resolve().parents[2]
src_path = repo_root / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

from textual.widgets import Input, Static, DataTable

from gui.tui.app import FishBroTUI


class TestReportViewerLayoutV1(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="fishbro_report_viewer_")
        self.addCleanup(self._tmp.cleanup)
        self.outputs_root = Path(self._tmp.name) / "outputs"
        os.environ["FISHBRO_OUTPUTS_ROOT"] = str(self.outputs_root)

    async def asyncTearDown(self) -> None:
        os.environ.pop("FISHBRO_OUTPUTS_ROOT", None)

    def _write_wfs_fixture(self, job_id: str) -> Path:
        job_dir = self.outputs_root / "artifacts" / "jobs" / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        wfs_dir = self.outputs_root / "artifacts" / "seasons" / "2026Q1" / "wfs" / job_id
        wfs_dir.mkdir(parents=True, exist_ok=True)

        result_path = wfs_dir / "result.json"
        result = {
            "version": "1.0",
            "meta": {
                "instrument": "CME.MNQ",
                "timeframe": "60m",
                "start_season": "2026Q1",
                "end_season": "2026Q2",
            },
            "verdict": {"grade": "B", "is_tradable": True, "summary": "ok"},
            "metrics": {
                "raw": {
                    "pass_rate": 0.75,
                    "max_drawdown": -0.12,
                    "trades": 120,
                    "wfe": 0.85,
                },
                "scores": {"quality": 0.8},
                "hard_gates_triggered": [],
            },
            "windows": [
                {
                    "season": "2026Q1",
                    "pass_": True,
                    "is_metrics": {"net_profit": 1000, "max_drawdown": -0.08, "trades": 60},
                    "oos_metrics": {"net_profit": 300, "max_drawdown": -0.05, "trades": 20},
                    "fail_reasons": [],
                },
                {
                    "season": "2026Q2",
                    "pass_": False,
                    "is_metrics": {"net_profit": 500, "max_drawdown": -0.2, "trades": 40},
                    "oos_metrics": {"net_profit": -50, "max_drawdown": -0.15, "trades": 10},
                    "fail_reasons": ["oos_net_nonpositive"],
                },
            ],
        }
        result_path.write_text(json.dumps(result), encoding="utf-8")

        (job_dir / "wfs_result_path.txt").write_text(str(result_path), encoding="utf-8")
        return result_path

    @staticmethod
    def _static_text(widget: Static) -> str:
        return str(getattr(widget, "_Static__content", "") or "")

    async def test_report_viewer_layout_v1(self) -> None:
        job_id = "test-job-123"
        self._write_wfs_fixture(job_id)

        app = FishBroTUI()
        async with app.run_test() as pilot:
            app.switch_screen("report")
            await pilot.pause(0.1)

            screen = app.screen
            screen.query_one("#job_id", Input).value = job_id
            # Screen is scrollable; calling handler directly avoids pilot click edge cases.
            screen.handle_load_report()
            await pilot.pause(0.1)

            grade = self._static_text(screen.query_one("#verdict_grade", Static))
            is_tradable = self._static_text(screen.query_one("#verdict_is_tradable", Static))
            summary = self._static_text(screen.query_one("#verdict_summary", Static))
            self.assertTrue(grade)
            self.assertTrue(is_tradable)
            self.assertTrue(summary)

            perf = self._static_text(screen.query_one("#card_perf", Static))
            risk = self._static_text(screen.query_one("#card_risk", Static))
            ratios = self._static_text(screen.query_one("#card_ratios", Static))
            self.assertIn("N/A", perf)
            self.assertIn("N/A", risk)
            self.assertIn("N/A", ratios)

            table = screen.query_one("#windows_table", DataTable)
            self.assertEqual(table.row_count, 2)

            # Reload shouldn't crash
            await pilot.press("r")
            await pilot.pause(0.05)


if __name__ == "__main__":
    unittest.main()
