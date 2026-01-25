import os
import tempfile
import unittest
from pathlib import Path
import sys

repo_root = Path(__file__).resolve().parents[2]
src_path = repo_root / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

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

    async def test_build_bars_submit_flow(self) -> None:
        app = FishBroTUI()
        async with app.run_test() as pilot:
            app.switch_screen("data_prepare")
            await pilot.pause(0.1)

            screen = app.screen
            screen.query_one("#dataset_id", Input).value = "CME.MNQ"
            screen.query_one("#timeframes", Input).value = "60"
            screen.query_one("#season", Input).value = "2026Q1"

            await pilot.click("#submit_build_bars")
            await pilot.pause(0.05)

            status = await self._get_status_text(app)
            self.assertIn("Submitted BUILD_BARS job", status)

    async def test_build_features_requires_bars_prompt_only(self) -> None:
        app = FishBroTUI()
        async with app.run_test() as pilot:
            app.switch_screen("data_prepare")
            await pilot.pause(0.1)

            screen = app.screen
            screen.query_one("#dataset_id", Input).value = "CME.MNQ"
            screen.query_one("#timeframes", Input).value = "60"
            screen.query_one("#season", Input).value = "2026Q1"
            screen.query_one("#feature_scope", Select).value = "all_packs"

            # Call handler directly; screen can be scrollable in CI and pilot click may miss.
            screen.handle_submit_build_features()
            await pilot.pause(0.2)

            status = await self._get_status_text(app)
            self.assertIn("Missing bars. Run BUILD_BARS first.", status)

    async def test_build_features_rejects_purge_in_ui(self) -> None:
        app = FishBroTUI()
        async with app.run_test() as pilot:
            app.switch_screen("data_prepare")
            await pilot.pause(0.1)

            screen = app.screen
            screen.query_one("#dataset_id", Input).value = "CME.MNQ"
            screen.query_one("#timeframes", Input).value = "60"
            screen.query_one("#season", Input).value = "2026Q1"
            screen.query_one("#feature_scope", Select).value = "all_packs"
            # Purge should only be allowed for BUILD_BARS.
            from textual.widgets import Checkbox

            screen.query_one("#purge_before_build", Checkbox).value = True

            screen.handle_submit_build_features()
            await pilot.pause(0.2)

            status = await self._get_status_text(app)
            self.assertIn("purge is not allowed for BUILD_FEATURES", status)

    async def test_wfs_submit_flow(self) -> None:
        app = FishBroTUI()
        async with app.run_test() as pilot:
            app.switch_screen("wfs")
            await pilot.pause(0.1)

            screen = app.screen
            screen.query_one("#strategy_list", Input).value = "regime_filter_v1"
            screen.query_one("#instrument", Select).value = "CME.MNQ"
            screen.query_one("#timeframe_list", Input).value = "60m"
            screen.query_one("#season", Input).value = "2026Q1"
            screen.query_one("#start_season", Input).value = "2026Q1"
            screen.query_one("#end_season", Input).value = "2026Q1"

            # Screen is scrollable; calling handler directly avoids pilot OutOfBounds.
            screen.handle_submit()
            await pilot.pause(0.05)

            status = await self._get_status_text(app)
            self.assertIn("Submitted RUN_RESEARCH_WFS job", status)

    async def test_portfolio_submit_flow(self) -> None:
        wfs_job_id = submit(
            "RUN_RESEARCH_WFS",
            {
                "strategy_id": "regime_filter_v1",
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
