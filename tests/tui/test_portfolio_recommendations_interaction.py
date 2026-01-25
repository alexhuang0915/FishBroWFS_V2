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

from textual.widgets import Input, DataTable

from gui.tui.app import FishBroTUI


class TestPortfolioRecommendationsInteraction(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="fishbro_portfolio_recs_")
        self.addCleanup(self._tmp.cleanup)
        self.outputs_root = Path(self._tmp.name) / "outputs"
        os.environ["FISHBRO_OUTPUTS_ROOT"] = str(self.outputs_root)

    async def asyncTearDown(self) -> None:
        os.environ.pop("FISHBRO_OUTPUTS_ROOT", None)

    async def test_load_toggle_and_save_selection(self) -> None:
        # Create a fake portfolio recommendations bundle and pointer in job evidence.
        season = "2026Q1"
        portfolio_id = "portfolio_test_0001"
        portfolio_dir = self.outputs_root / "artifacts" / "seasons" / season / "portfolios" / portfolio_id
        portfolio_dir.mkdir(parents=True, exist_ok=True)

        rec_path = portfolio_dir / "recommendations.json"
        rec_payload = {
            "version": "1.0",
            "portfolio_id": portfolio_id,
            "season": season,
            "candidate_run_ids": ["runA", "runB"],
            "recommended_run_ids": ["runA"],
            "default_selected_run_ids": ["runA", "runB"],
            "generated_at": "2026-01-24T00:00:00Z",
            "runs": [
                {
                    "run_id": "runA",
                    "instrument": "CME.MNQ",
                    "strategy_family": "s1",
                    "timeframe": "60m",
                    "grade": "B",
                    "is_tradable": True,
                    "hard_gates_triggered": [],
                    "score_total_weighted": 70.0,
                    "raw": {"pass_rate": 0.8, "trades": 120, "wfe": 0.7, "ulcer_index": 8.0, "max_underwater_days": 10},
                    "summary": "ok",
                },
                {
                    "run_id": "runB",
                    "instrument": "CME.MNQ",
                    "strategy_family": "s1",
                    "timeframe": "60m",
                    "grade": "D",
                    "is_tradable": False,
                    "hard_gates_triggered": ["pass_rate_min"],
                    "score_total_weighted": 30.0,
                    "raw": {"pass_rate": 0.2, "trades": 10, "wfe": 0.3, "ulcer_index": 25.0, "max_underwater_days": 100},
                    "summary": "bad",
                },
            ],
        }
        rec_path.write_text(json.dumps(rec_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        job_id = "build_portfolio_job_1"
        evidence_dir = self.outputs_root / "artifacts" / "jobs" / job_id
        evidence_dir.mkdir(parents=True, exist_ok=True)
        (evidence_dir / "portfolio_recommendations_path.txt").write_text(str(rec_path), encoding="utf-8")

        app = FishBroTUI()
        async with app.run_test() as pilot:
            app.switch_screen("portfolio")
            await pilot.pause(0.1)

            screen = app.screen
            await pilot.click("#open_recommendations")
            await pilot.pause(0.05)

            modal = app.screen
            modal.query_one("#portfolio_job_id", Input).value = job_id
            await pilot.click("#load_recommendations")
            await pilot.pause(0.05)

            table = modal.query_one("#recommendations_table", DataTable)
            self.assertEqual(len(table.rows), 2)

            # Toggle selection for first row and save.
            table.focus()
            await pilot.press("space")
            await pilot.pause(0.05)

            await pilot.click("#save_selection")
            await pilot.pause(0.05)

            sel_path = portfolio_dir / "portfolio_selection.json"
            self.assertTrue(sel_path.exists())
            saved = json.loads(sel_path.read_text(encoding="utf-8"))
            self.assertIn("selected_run_ids", saved)


if __name__ == "__main__":
    unittest.main()
