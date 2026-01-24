import os
import tempfile
import unittest
from pathlib import Path

from textual.widgets import Input, Select, Static

from gui.tui.app import FishBroTUI
from control.supervisor import submit


class TestTUISubmitFlows(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="fishbro_tui_flow_")
        self.addCleanup(self._tmp.cleanup)
        self.outputs_root = Path(self._tmp.name) / "outputs"
        self.raw_root = Path(self._tmp.name) / "FishBroData"
        self.raw_root.mkdir(parents=True, exist_ok=True)
        os.environ["FISHBRO_OUTPUTS_ROOT"] = str(self.outputs_root)
        os.environ["FISHBRO_RAW_ROOT"] = str(self.raw_root)

    async def asyncTearDown(self) -> None:
        os.environ.pop("FISHBRO_OUTPUTS_ROOT", None)
        os.environ.pop("FISHBRO_RAW_ROOT", None)

    async def _get_status_text(self, app: FishBroTUI) -> str:
        status = app.screen.query_one("#status", Static)
        content = getattr(status, "_Static__content", "")
        return str(content) if content is not None else ""

    async def test_build_data_submit_flow(self) -> None:
        app = FishBroTUI()
        async with app.run_test() as pilot:
            app.switch_screen("data_prepare")
            await pilot.pause(0.1)

            screen = app.screen
            screen.query_one("#dataset_id", Input).value = "CME.MNQ"
            screen.query_one("#timeframe_min", Input).value = "60"
            screen.query_one("#mode", Select).value = "BARS_ONLY"
            screen.query_one("#season", Input).value = "2026Q1"

            await pilot.click("#submit_build_data")
            await pilot.pause(0.05)

            status = await self._get_status_text(app)
            self.assertIn("Submitted BUILD_DATA job", status)

    async def test_wfs_submit_flow(self) -> None:
        app = FishBroTUI()
        async with app.run_test() as pilot:
            app.switch_screen("wfs")
            await pilot.pause(0.1)

            screen = app.screen
            screen.query_one("#strategy_id", Input).value = "s1_v1"
            screen.query_one("#instrument", Input).value = "CME.MNQ"
            screen.query_one("#timeframe", Input).value = "60m"
            screen.query_one("#dataset_id", Input).value = "CME.MNQ"
            screen.query_one("#season", Input).value = "2026Q1"
            screen.query_one("#start_season", Input).value = "2026Q1"
            screen.query_one("#end_season", Input).value = "2026Q1"

            await pilot.click("#submit_wfs")
            await pilot.pause(0.05)

            status = await self._get_status_text(app)
            self.assertIn("Submitted RUN_RESEARCH_WFS job", status)

    async def test_portfolio_submit_flow(self) -> None:
        wfs_job_id = submit(
            "RUN_RESEARCH_WFS",
            {
                "strategy_id": "s1_v1",
                "instrument": "CME.MNQ",
                "timeframe": "60m",
                "dataset_id": "CME.MNQ",
                "season": "2026Q1",
                "start_season": "2026Q1",
                "end_season": "2026Q1",
            },
        )

        app = FishBroTUI()
        async with app.run_test() as pilot:
            app.switch_screen("portfolio")
            await pilot.pause(0.1)

            screen = app.screen
            screen.query_one("#season", Input).value = "2026Q1"
            screen.query_one("#candidate_run_ids", Input).value = wfs_job_id

            await pilot.click("#submit_portfolio")
            await pilot.pause(0.05)

            status = await self._get_status_text(app)
            self.assertIn("Submitted BUILD_PORTFOLIO_V2 job", status)


if __name__ == "__main__":
    unittest.main()
