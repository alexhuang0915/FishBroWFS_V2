from textual import on
from textual.widgets import Label, Button, Static, Input, Select, Checkbox
from textual.containers import Vertical, Horizontal

from gui.tui.screens.base import BaseScreen
from gui.tui.services.bridge import Bridge
from gui.tui.widgets.job_monitor import JobMonitorPanel


class DataPrepareScreen(BaseScreen):
    """BUILD_DATA submission screen."""
    SCREEN_NAME = "data_prepare"

    def __init__(self, bridge: Bridge, **kwargs):
        super().__init__(**kwargs)
        self.bridge = bridge

    def main_compose(self):
        with Horizontal():
            with Vertical(classes="form_panel"):
                yield Label("BUILD_DATA", id="title")

                with Horizontal():
                    yield Label("Dataset ID:", classes="label")
                    yield Input(placeholder="e.g. CFE.VX", id="dataset_id", classes="value")

                with Horizontal():
                    yield Label("Timeframe (min):", classes="label")
                    yield Input(value="60", id="timeframe_min", classes="value")

                with Horizontal():
                    yield Label("Mode:", classes="label")
                    yield Select(
                        [
                            ("FULL", "FULL"),
                            ("BARS_ONLY", "BARS_ONLY"),
                            ("FEATURES_ONLY", "FEATURES_ONLY"),
                        ],
                        id="mode",
                        classes="value",
                    )

                with Horizontal():
                    yield Label("Season (opt):", classes="label")
                    yield Input(placeholder="e.g. 2026Q1 (optional)", id="season", classes="value")

                yield Checkbox("Force rebuild", id="force_rebuild")
                yield Button("Submit BUILD_DATA", variant="primary", id="submit_build_data")
                yield Static("", id="status")

            yield JobMonitorPanel(self.bridge, classes="monitor_panel")

    @on(Button.Pressed, "#submit_build_data")
    def handle_submit(self):
        dataset_id = self.query_one("#dataset_id", Input).value.strip()
        timeframe_raw = self.query_one("#timeframe_min", Input).value.strip()
        mode = self.query_one("#mode", Select).value
        season = self.query_one("#season", Input).value.strip()
        force_rebuild = self.query_one("#force_rebuild", Checkbox).value

        if not dataset_id:
            self.query_one("#status").update("Error: dataset_id is required.")
            return
        if mode is Select.BLANK:
            self.query_one("#status").update("Error: mode is required.")
            return

        try:
            timeframe_min = int(timeframe_raw)
        except Exception:
            self.query_one("#status").update("Error: timeframe_min must be an integer.")
            return

        try:
            job_id = self.bridge.submit_build_data(
                dataset_id=dataset_id,
                timeframe_min=timeframe_min,
                mode=str(mode),
                season=season or None,
                force_rebuild=bool(force_rebuild),
            )
            self.query_one("#status").update(f"Submitted BUILD_DATA job: {job_id[:8]}...")
        except Exception as e:
            self.query_one("#status").update(f"Error: {e}")
