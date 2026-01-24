from textual import on
from textual.widgets import Label, Button, Static, Input, Select
from textual.containers import Vertical, Horizontal

from gui.tui.screens.base import BaseScreen
from gui.tui.services.bridge import Bridge
from gui.tui.widgets.job_monitor import JobMonitorPanel


class WFSScreen(BaseScreen):
    """RUN_RESEARCH_WFS submission screen."""
    SCREEN_NAME = "wfs"

    def __init__(self, bridge: Bridge, **kwargs):
        super().__init__(**kwargs)
        self.bridge = bridge
        self._data2_pool: list[str] = []

    def on_mount(self):
        super().on_mount()
        self._data2_pool = self.bridge.get_instruments()
        self._refresh_data2_pool_options()
        self._auto_range_if_possible()
        self._refresh_recent_data2_options()
        self._update_window_count()

    def _refresh_data2_pool_options(self) -> None:
        try:
            selector = self.query_one("#data2_pool", Select)
            options = [(x, x) for x in self._data2_pool] if self._data2_pool else [("none", Select.BLANK)]
            selector.set_options(options)
        except Exception:
            return

    def _refresh_recent_data2_options(self) -> None:
        try:
            recent = self.bridge.get_recent_data2(limit=20)
            selector = self.query_one("#data2_recent", Select)
            options = [(x, x) for x in recent] if recent else [("none", Select.BLANK)]
            selector.set_options(options)
        except Exception:
            return

    def _parse_data2_list(self) -> list[str]:
        raw = self.query_one("#data2_list", Input).value.strip()
        items = [x.strip() for x in raw.split(",") if x.strip()]
        out: list[str] = []
        for item in items:
            if item not in out:
                out.append(item)
        return out

    def _set_data2_list(self, items: list[str]) -> None:
        self.query_one("#data2_list", Input).value = ", ".join(items)

    def _add_data2_items(self, items: list[str]) -> None:
        if not items:
            return
        dataset_id = self.query_one("#dataset_id", Input).value.strip()
        current = self._parse_data2_list()
        added = 0
        for item in items:
            item = item.strip()
            if not item:
                continue
            if dataset_id and item == dataset_id:
                continue
            if item not in current:
                current.append(item)
                added += 1
        self._set_data2_list(current)
        if added:
            self.query_one("#status").update(f"Added {added} DATA2 items.")

    def _auto_range_if_possible(self) -> None:
        # Auto-fill start/end seasons using data1 bars range
        try:
            start_input = self.query_one("#start_season", Input)
            end_input = self.query_one("#end_season", Input)
            if start_input.value.strip() or end_input.value.strip():
                return

            dataset_id = self.query_one("#dataset_id", Input).value.strip()
            season = self.query_one("#season", Input).value.strip()
            timeframe = self.query_one("#timeframe", Input).value.strip()
            if not dataset_id or not season or not timeframe:
                return

            tf_min = int(timeframe.lower().replace("m", "").replace("h", "")) if timeframe else 60
            if timeframe.lower().endswith("h"):
                tf_min *= 60

            seasons = self.bridge.get_bar_season_range(dataset_id, season, tf_min)
            if not seasons and season == "current":
                latest = self.bridge.get_latest_season_with_bars(dataset_id, tf_min)
                if latest:
                    seasons = self.bridge.get_bar_season_range(dataset_id, latest, tf_min)
                    if seasons:
                        self.query_one("#season", Input).value = latest

            if not seasons:
                return

            start_season, end_season = seasons
            start_input.value = start_season
            end_input.value = end_season
            self.query_one("#status").update(f"Auto range set to {start_season} → {end_season}")
            self._update_window_count()
        except Exception:
            return

    def main_compose(self):
        with Horizontal():
            with Vertical(classes="form_panel"):
                yield Label("RUN_RESEARCH_WFS", id="title")

                with Horizontal():
                    yield Label("Strategy ID:", classes="label")
                    yield Input(value="s1_v1", id="strategy_id", classes="value")

                with Horizontal():
                    yield Label("Instrument:", classes="label")
                    yield Input(value="CME.MNQ", id="instrument", classes="value")

                with Horizontal():
                    yield Label("Timeframe:", classes="label")
                    yield Input(value="60m", id="timeframe", classes="value")

                with Horizontal():
                    yield Label("Dataset ID:", classes="label")
                    yield Input(value="CME.MNQ", id="dataset_id", classes="value")

                with Horizontal():
                    yield Label("Season (outputs):", classes="label")
                    yield Input(value="current", id="season", classes="value")

                with Horizontal():
                    yield Label("Start Season:", classes="label")
                    yield Input(value="", id="start_season", classes="value")

                with Horizontal():
                    yield Label("End Season:", classes="label")
                    yield Input(value="", id="end_season", classes="value")

                yield Label("DATA2 (optional):", classes="section_title")
                with Horizontal():
                    yield Label("Data2 List:", classes="label")
                    yield Input(placeholder="comma-separated (optional)", id="data2_list", classes="value")

                with Horizontal():
                    yield Label("Data2 Pool:", classes="label")
                    options = [(x, x) for x in self._data2_pool] if self._data2_pool else [("none", Select.BLANK)]
                    yield Select(options, id="data2_pool", classes="value")
                    yield Button("Add", id="add_data2")
                    yield Button("Add All", id="add_all_data2")
                    yield Button("Clear", id="clear_data2")

                with Horizontal():
                    yield Label("Recent Data2:", classes="label")
                    recent = self.bridge.get_recent_data2(limit=20)
                    recent_options = [(x, x) for x in recent] if recent else [("none", Select.BLANK)]
                    yield Select(recent_options, id="data2_recent", classes="value")
                    yield Button("Add Recent", id="add_recent_data2")

                yield Button("Auto Range from Bars", id="auto_range")
                with Horizontal():
                    yield Label("Dataset (opt):", classes="label")
                    yield Input(placeholder="optional", id="dataset", classes="value")

                with Horizontal():
                    yield Label("Workers (opt):", classes="label")
                    yield Input(placeholder="optional int", id="workers", classes="value")

                with Horizontal():
                    yield Label("Window Count:", classes="label")
                    yield Static("", id="window_count", classes="value")

                yield Button("Submit RUN_RESEARCH_WFS", variant="primary", id="submit_wfs")
                yield Static("", id="status")

            yield JobMonitorPanel(self.bridge, classes="monitor_panel")

    @on(Button.Pressed, "#submit_wfs")
    def handle_submit(self):
        strategy_id = self.query_one("#strategy_id", Input).value.strip()
        instrument = self.query_one("#instrument", Input).value.strip()
        timeframe = self.query_one("#timeframe", Input).value.strip()
        dataset_id = self.query_one("#dataset_id", Input).value.strip()
        season = self.query_one("#season", Input).value.strip()
        start_season = self.query_one("#start_season", Input).value.strip()
        end_season = self.query_one("#end_season", Input).value.strip()
        dataset = self.query_one("#dataset", Input).value.strip()
        workers_raw = self.query_one("#workers", Input).value.strip()
        data2_list = self._parse_data2_list()

        if not all([strategy_id, instrument, timeframe, season, start_season, end_season]):
            self.query_one("#status").update("Error: strategy_id/instrument/timeframe/season/start_season/end_season are required.")
            return

        workers = None
        if workers_raw:
            try:
                workers = int(workers_raw)
            except Exception:
                self.query_one("#status").update("Error: workers must be an integer.")
                return

        try:
            if not data2_list:
                job_id = self.bridge.submit_run_research_wfs(
                    strategy_id=strategy_id,
                    instrument=instrument,
                    timeframe=timeframe,
                    start_season=start_season,
                    end_season=end_season,
                    dataset_id=dataset_id or None,
                    dataset=dataset or None,
                    workers=workers,
                    season=season,
                    data2_dataset_id=None,
                )
                self.query_one("#status").update(f"Submitted RUN_RESEARCH_WFS job: {job_id[:8]}...")
            else:
                job_ids: list[str] = []
                for data2 in data2_list:
                    job_id = self.bridge.submit_run_research_wfs(
                        strategy_id=strategy_id,
                        instrument=instrument,
                        timeframe=timeframe,
                        start_season=start_season,
                        end_season=end_season,
                        dataset_id=dataset_id or None,
                        dataset=dataset or None,
                        workers=workers,
                        season=season,
                        data2_dataset_id=data2,
                    )
                    job_ids.append(job_id)
                self.bridge.record_recent_data2(data2_list)
                self._refresh_recent_data2_options()
                short = ", ".join([jid[:8] for jid in job_ids[:5]])
                extra = f" (+{len(job_ids) - 5} more)" if len(job_ids) > 5 else ""
                self.query_one("#status").update(
                    f"Submitted {len(job_ids)} RUN_RESEARCH_WFS jobs: {short}{extra}"
                )
        except Exception as e:
            self.query_one("#status").update(f"Error: {e}")

    @on(Button.Pressed, "#auto_range")
    def handle_auto_range(self):
        dataset_id = self.query_one("#dataset_id", Input).value.strip()
        season = self.query_one("#season", Input).value.strip()
        timeframe = self.query_one("#timeframe", Input).value.strip()

        if not dataset_id or not season or not timeframe:
            self.query_one("#status").update("Error: dataset_id/season/timeframe required for auto range.")
            return

        try:
            tf_min = int(timeframe.lower().replace("m", "").replace("h", "")) if timeframe else 60
            if timeframe.lower().endswith("h"):
                tf_min *= 60
        except Exception:
            self.query_one("#status").update("Error: invalid timeframe format for auto range.")
            return

        seasons = self.bridge.get_bar_season_range(dataset_id, season, tf_min)
        if not seasons and season == "current":
            latest = self.bridge.get_latest_season_with_bars(dataset_id, tf_min)
            if latest:
                seasons = self.bridge.get_bar_season_range(dataset_id, latest, tf_min)
                if seasons:
                    self.query_one("#season", Input).value = latest
        if not seasons:
            self.query_one("#status").update("No bars found for that dataset/season/timeframe.")
            return

        start_season, end_season = seasons
        self.query_one("#start_season", Input).value = start_season
        self.query_one("#end_season", Input).value = end_season
        self.query_one("#status").update(f"Auto range set to {start_season} → {end_season}")
        self._update_window_count()

    def _update_window_count(self) -> None:
        try:
            start = self.query_one("#start_season", Input).value.strip()
            end = self.query_one("#end_season", Input).value.strip()
            if not start or not end:
                self.query_one("#window_count", Static).update("")
                return
            sy, sq = int(start[:4]), int(start[5])
            ey, eq = int(end[:4]), int(end[5])
            count = (ey - sy) * 4 + (eq - sq) + 1
            if count < 0:
                count = 0
            self.query_one("#window_count", Static).update(str(count))
        except Exception:
            self.query_one("#window_count", Static).update("")

    @on(Input.Changed, "#start_season")
    @on(Input.Changed, "#end_season")
    def _on_season_change(self):
        self._update_window_count()

    @on(Button.Pressed, "#add_data2")
    def handle_add_data2(self):
        selector = self.query_one("#data2_pool", Select)
        selected = selector.value
        if selected is Select.BLANK:
            self.query_one("#status").update("No DATA2 selected.")
            return
        self._add_data2_items([str(selected)])

    @on(Button.Pressed, "#add_all_data2")
    def handle_add_all_data2(self):
        self._add_data2_items(self._data2_pool)

    @on(Button.Pressed, "#clear_data2")
    def handle_clear_data2(self):
        self._set_data2_list([])
        self.query_one("#status").update("Cleared DATA2 list.")

    @on(Button.Pressed, "#add_recent_data2")
    def handle_add_recent_data2(self):
        selector = self.query_one("#data2_recent", Select)
        selected = selector.value
        if selected is Select.BLANK:
            self.query_one("#status").update("No recent DATA2 selected.")
            return
        self._add_data2_items([str(selected)])
