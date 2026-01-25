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
        self._readiness_index: dict = {}

    def on_mount(self):
        super().on_mount()
        self._data2_pool = self.bridge.get_instruments()
        self._readiness_index = self.bridge.get_readiness_index()
        
        self._refresh_strategy_options()
        self._refresh_instrument_options()
        self._refresh_data2_pool_options()
        self._auto_range_if_possible()
        self._refresh_recent_data2_options()
        self._update_window_count()

    def _refresh_strategy_options(self) -> None:
        try:
            strategies = self.bridge.get_strategies()
            selector = self.query_one("#strategy_pool", Select)
            options = [(x, x) for x in strategies] if strategies else [("none", Select.BLANK)]
            selector.set_options(options)
            if strategies:
                selector.value = strategies[0]
        except Exception:
            return

    def _refresh_instrument_options(self) -> None:
        try:
            instruments_info = self._readiness_index.get("instruments", {})
            selector = self.query_one("#instrument", Select)
            
            # Show all configured instruments, but label those not ready
            options: list[tuple[str, str]] = []
            for instr in self._data2_pool:
                is_ready = bool(instruments_info.get(instr, {}).get("timeframes"))
                label = instr if is_ready else f"{instr} (No Data)"
                options.append((label, instr))
            
            selector.set_options(options)
            if options:
                # Default to MNQ if available
                mnq = next((val for lbl, val in options if val == "CME.MNQ"), options[0][1])
                selector.value = mnq
        except Exception:
            return

    def _refresh_timeframe_options(self, instrument: str) -> None:
        try:
            selector = self.query_one("#timeframe_pool", Select)
            if not instrument or instrument is Select.BLANK:
                selector.set_options([("Select Instrument First", Select.BLANK)])
                return

            instruments_info = self._readiness_index.get("instruments", {})
            info = instruments_info.get(instrument, {})
            tfs = sorted(info.get("timeframes", {}).keys(), key=lambda x: int(x) if x.isdigit() else 999)
            
            options = [(f"{tf}m", f"{tf}m") for tf in tfs]
            if not options:
                options = [("No Timeframes Ready", Select.BLANK)]
            
            selector.set_options(options)
            if options and options[0][1] is not Select.BLANK:
                selector.value = options[0][1]
        except Exception:
            return

    @on(Select.Changed, "#instrument")
    def _on_instrument_changed(self, event: Select.Changed) -> None:
        if event.value and event.value is not Select.BLANK:
            self._refresh_timeframe_options(str(event.value))
            # Clear timeframe list when instrument changes since they belong to the instrument
            self._set_timeframe_list([])
            self._auto_range_if_possible()

    def _refresh_data2_pool_options(self) -> None:
        try:
            instruments_info = self._readiness_index.get("instruments", {})
            
            selector = self.query_one("#data2_pool", Select)
            
            options: list[tuple[str, str]] = []
            ready_options: list[tuple[str, str]] = []
            missing_options: list[tuple[str, str]] = []
            
            for instr in self._data2_pool:
                info = instruments_info.get(instr, {})
                # Heuristic: if it has any timeframes, it's "ready" enough for DATA2 use
                is_ready = bool(info.get("timeframes"))
                
                label = f"{instr} (Ready)" if is_ready else f"{instr} (Missing)"
                if is_ready:
                    ready_options.append((label, instr))
                else:
                    missing_options.append((label, instr))
            
            options = ready_options + missing_options
            if not options:
                options = [("none", Select.BLANK)]
                
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

    def _parse_list(self, input_id: str) -> list[str]:
        raw = self.query_one(f"#{input_id}", Input).value.strip()
        items = [x.strip() for x in raw.split(",") if x.strip()]
        out: list[str] = []
        for item in items:
            if item not in out:
                out.append(item)
        return out

    def _set_list(self, input_id: str, items: list[str]) -> None:
        self.query_one(f"#{input_id}", Input).value = ", ".join(items)

    def _parse_strategy_list(self) -> list[str]:
        return self._parse_list("strategy_list")

    def _set_strategy_list(self, items: list[str]) -> None:
        self._set_list("strategy_list", items)

    def _parse_data2_list(self) -> list[str]:
        return self._parse_list("data2_list")

    def _set_data2_list(self, items: list[str]) -> None:
        self._set_list("data2_list", items)

    def _parse_timeframe_list(self) -> list[str]:
        return self._parse_list("timeframe_list")

    def _set_timeframe_list(self, items: list[str]) -> None:
        self._set_list("timeframe_list", items)

    def _add_strategy_items(self, items: list[str]) -> None:
        if not items:
            return
        current = self._parse_strategy_list()
        added = 0
        for item in items:
            if item and item != Select.BLANK and item not in current:
                current.append(item)
                added += 1
        self._set_strategy_list(current)
        if added:
            self.query_one("#status").update(f"Added {added} Strategies.")

    def _add_timeframe_items(self, items: list[str]) -> None:
        if not items:
            return
        current = self._parse_timeframe_list()
        added = 0
        for item in items:
            if item and item != Select.BLANK and item not in current:
                current.append(item)
                added += 1
        self._set_timeframe_list(current)
        if added:
            self.query_one("#status").update(f"Added {added} Timeframes.")
            self._auto_range_if_possible()

    def _add_data2_items(self, items: list[str]) -> None:
        if not items:
            return
        instrument_widget = self.query_one("#instrument", Select)
        instrument = str(instrument_widget.value) if instrument_widget.value and instrument_widget.value is not Select.BLANK else ""
        
        current = self._parse_data2_list()
        added = 0
        for item in items:
            item = item.strip()
            if not item:
                continue
            if instrument and item == instrument:
                continue
            if item not in current:
                current.append(item)
                added += 1
        self._set_data2_list(current)
        if added:
            self.query_one("#status").update(f"Added {added} DATA2 items.")

    def _auto_range_if_possible(self) -> None:
        # Auto-fill start/end seasons using instrument bars range
        try:
            start_input = self.query_one("#start_season", Input)
            end_input = self.query_one("#end_season", Input)
            if start_input.value.strip() or end_input.value.strip():
                return

            instrument_widget = self.query_one("#instrument", Select)
            instrument = str(instrument_widget.value) if instrument_widget.value and instrument_widget.value is not Select.BLANK else ""
            
            timeframes = self._parse_timeframe_list()
            if not timeframes:
                # Fallback to current pool selection if list empty
                tf_pool = self.query_one("#timeframe_pool", Select)
                if tf_pool.value and tf_pool.value is not Select.BLANK:
                    timeframes = [str(tf_pool.value)]
            
            season = self.query_one("#season", Input).value.strip()
            
            if not instrument or not season or not timeframes or timeframes[0] == "No Timeframes Ready":
                return

            timeframe = timeframes[0] # Use first one for range detection
            tf_min = int(timeframe.lower().replace("m", "").replace("h", ""))
            if timeframe.lower().endswith("h"):
                tf_min *= 60

            seasons = self.bridge.get_bar_season_range(instrument, season, tf_min)
            if not seasons and season == "current":
                latest = self.bridge.get_latest_season_with_bars(instrument, tf_min)
                if latest:
                    seasons = self.bridge.get_bar_season_range(instrument, latest, tf_min)
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
        with Vertical(classes="full_panel"):
            yield Label("RUN_RESEARCH_WFS (Batch Simulation)", id="title")
            
            with Horizontal():
                # Column 1: Strategy & Primary Data
                with Vertical(classes="half_panel"):
                    yield Label("PRIMARY SPECIFICATION", classes="section_title")
                    
                    with Horizontal(classes="field_row"):
                        yield Label("Strategy List:", classes="label")
                        yield Input(placeholder="comma-sep strategy IDs", id="strategy_list", classes="value")
                    yield Label("Active strategies for this run.", classes="hint")
                    
                    with Horizontal(classes="field_row"):
                        yield Label("Strategy Pool:", classes="label")
                        yield Select([], id="strategy_pool", classes="value")
                        yield Button("Add", id="add_strategy")
                        yield Button("Add All", id="add_all_strategy")
                        yield Button("Clear", id="clear_strategy")
                    yield Label("Register existing strategies from catalog.", classes="hint")

                    with Horizontal(classes="field_row"):
                        yield Label("Main Instrument:", classes="label")
                        yield Select([], id="instrument", classes="value")
                    yield Label("Primary instrument for backtesting.", classes="hint")

                    with Horizontal(classes="field_row"):
                        yield Label("Timeframes:", classes="label")
                        yield Input(placeholder="e.g. 60m, 120m", id="timeframe_list", classes="value")
                    yield Label("Resolutions to simulate.", classes="hint")
                    
                    with Horizontal(classes="field_row"):
                        yield Label("Timeframe Pool:", classes="label")
                        yield Select([], id="timeframe_pool", classes="value")
                        yield Button("Add", id="add_timeframe")
                        yield Button("Add All", id="add_all_timeframe")
                        yield Button("Clear", id="clear_timeframe")

                    with Horizontal(classes="field_row"):
                        yield Label("Target Season:", classes="label")
                        yield Input(value="current", id="season", classes="value")
                    yield Label("Execution Season context.", classes="hint")

                    with Horizontal(classes="field_row"):
                        yield Label("Start Season:", classes="label")
                        yield Input(value="", id="start_season", classes="value")
                    yield Label("Beginning of backtest period.", classes="hint")

                    with Horizontal(classes="field_row"):
                        yield Label("End Season:", classes="label")
                        yield Input(value="", id="end_season", classes="value")
                    yield Label("End of backtest period.", classes="hint")
                    
                    yield Button("Auto Range from Bars", id="auto_range")

                # Column 2: Data2 & System Config
                with Vertical(classes="half_panel"):
                    yield Label("SECONDARY DATA & SYSTEM", classes="section_title")
                    
                    with Horizontal(classes="field_row"):
                        yield Label("Data2 List:", classes="label")
                        yield Input(placeholder="comma-separated symbols", id="data2_list", classes="value")
                    yield Label("Additional datasets for cross-analysis.", classes="hint")

                    with Horizontal(classes="field_row"):
                        yield Label("Data2 Pool:", classes="label")
                        options = [(x, x) for x in self._data2_pool] if self._data2_pool else [("none", Select.BLANK)]
                        yield Select(options, id="data2_pool", classes="value")
                        yield Button("Add", id="add_data2")
                        yield Button("Add All", id="add_all_data2")
                        yield Button("Clear", id="clear_data2")
                    yield Label("Pick from available instruments.", classes="hint")

                    with Horizontal(classes="field_row"):
                        yield Label("Recent Data2:", classes="label")
                        recent = self.bridge.get_recent_data2(limit=20)
                        recent_options = [(x, x) for x in recent] if recent else [("none", Select.BLANK)]
                        yield Select(recent_options, id="data2_recent", classes="value")
                        yield Button("Add Recent", id="add_recent_data2")
                    yield Label("Quick selection of frequently used Data2.", classes="hint")
                    
                    with Horizontal(classes="field_row"):
                        yield Label("Worker Count:", classes="label")
                        yield Input(placeholder="optional int", id="workers", classes="value")
                    yield Label("Degree of parallelism.", classes="hint")

                    with Horizontal(classes="field_row"):
                        yield Label("Window Count:", classes="label")
                        yield Static("", id="window_count", classes="value")
                    yield Label("Calculated quarters in simulation.", classes="hint")

                    yield Button("Submit RUN_RESEARCH_WFS Job", variant="primary", id="submit_wfs")
                    yield Static("", id="status")

    def handle_submit(self):
        strategies = self._parse_strategy_list()
        if not strategies:
            strat_pool = self.query_one("#strategy_pool", Select)
            if strat_pool.value and strat_pool.value is not Select.BLANK:
                strategies = [str(strat_pool.value)]

        instrument_widget = self.query_one("#instrument", Select)
        instrument = str(instrument_widget.value) if instrument_widget.value and instrument_widget.value is not Select.BLANK else ""
        
        timeframes = self._parse_timeframe_list()
        if not timeframes:
            # Fallback to current pool selection if list empty
            tf_pool = self.query_one("#timeframe_pool", Select)
            if tf_pool.value and tf_pool.value is not Select.BLANK:
                timeframes = [str(tf_pool.value)]

        season = self.query_one("#season", Input).value.strip()
        start_season = self.query_one("#start_season", Input).value.strip()
        end_season = self.query_one("#end_season", Input).value.strip()
        workers_raw = self.query_one("#workers", Input).value.strip()
        data2_list = self._parse_data2_list()

        if not all([strategies, instrument, timeframes, season, start_season, end_season]):
            self.query_one("#status").update("Error: strategies/instrument/timeframes/season/start_season/end_season are required.")
            return

        workers = None
        if workers_raw:
            try:
                workers = int(workers_raw)
            except Exception:
                self.query_one("#status").update("Error: workers must be an integer.")
                return

        try:
            job_ids: list[str] = []
            
            # Combine Strategies x Timeframes x Data2 list for batch submission
            active_data2 = data2_list if data2_list else [None]
            
            for strategy_id in strategies:
                for tf in timeframes:
                    if tf == "No Timeframes Ready" or tf == Select.BLANK:
                        continue
                        
                    for data2 in active_data2:
                        job_id = self.bridge.submit_run_research_wfs(
                            strategy_id=strategy_id,
                            instrument=instrument,
                            timeframe=tf,
                            start_season=start_season,
                            end_season=end_season,
                            dataset_id=None,
                            dataset=None,
                            workers=workers,
                            season=season,
                            data2_dataset_id=data2,
                        )
                        job_ids.append(job_id)
            
            if not job_ids:
                self.query_one("#status").update("Error: No valid jobs created. Check strategies/timeframes.")
                return

            if data2_list:
                self.bridge.record_recent_data2(data2_list)
                self._refresh_recent_data2_options()

            if len(job_ids) == 1:
                self.query_one("#status").update(f"Submitted RUN_RESEARCH_WFS job: {job_ids[0][:8]}...")
            else:
                short = ", ".join([jid[:8] for jid in job_ids[:5]])
                extra = f" (+{len(job_ids) - 5} more)" if len(job_ids) > 5 else ""
                self.query_one("#status").update(
                    f"Submitted {len(job_ids)} jobs: {short}{extra}"
                )
        except Exception as e:
            self.query_one("#status").update(f"Error: {e}")

    @on(Button.Pressed, "#add_strategy")
    def handle_add_strategy(self):
        selector = self.query_one("#strategy_pool", Select)
        selected = selector.value
        if selected is Select.BLANK or not selected:
            self.query_one("#status").update("No Strategy selected.")
            return
        self._add_strategy_items([str(selected)])

    @on(Button.Pressed, "#add_all_strategy")
    def handle_add_all_strategy(self):
        strategies = self.bridge.get_strategies()
        if not strategies:
            self.query_one("#status").update("No strategies available.")
            return
        self._add_strategy_items(strategies)

    @on(Button.Pressed, "#clear_strategy")
    def handle_clear_strategy(self):
        self._set_strategy_list([])
        self.query_one("#status").update("Cleared Strategy list.")

    @on(Button.Pressed, "#auto_range")
    def handle_auto_range(self):
        instrument_widget = self.query_one("#instrument", Select)
        instrument = str(instrument_widget.value) if instrument_widget.value and instrument_widget.value is not Select.BLANK else ""
        
        timeframes = self._parse_timeframe_list()
        if not timeframes:
            tf_pool = self.query_one("#timeframe_pool", Select)
            if tf_pool.value and tf_pool.value is not Select.BLANK:
                timeframes = [str(tf_pool.value)]
                
        season = self.query_one("#season", Input).value.strip()

        if not instrument or not season or not timeframes or timeframes[0] == "No Timeframes Ready":
            self.query_one("#status").update("Error: instrument/season/timeframe required for auto range.")
            return

        timeframe = timeframes[0]
        try:
            tf_min = int(timeframe.lower().replace("m", "").replace("h", ""))
            if timeframe.lower().endswith("h"):
                tf_min *= 60
        except Exception:
            self.query_one("#status").update("Error: invalid timeframe format for auto range.")
            return

        seasons = self.bridge.get_bar_season_range(instrument, season, tf_min)
        if not seasons and season == "current":
            latest = self.bridge.get_latest_season_with_bars(instrument, tf_min)
            if latest:
                seasons = self.bridge.get_bar_season_range(instrument, latest, tf_min)
                if seasons:
                    self.query_one("#season", Input).value = latest
        if not seasons:
            self.query_one("#status").update("No bars found for that instrument/season/timeframe.")
            return

        start_season, end_season = seasons
        self.query_one("#start_season", Input).value = start_season
        self.query_one("#end_season", Input).value = end_season
        self.query_one("#status").update(f"Auto range set to {start_season} → {end_season}")
        self._update_window_count()

    @on(Button.Pressed, "#add_timeframe")
    def handle_add_timeframe(self):
        selector = self.query_one("#timeframe_pool", Select)
        selected = selector.value
        if selected is Select.BLANK or not selected:
            self.query_one("#status").update("No Timeframe selected.")
            return
        self._add_timeframe_items([str(selected)])

    @on(Button.Pressed, "#add_all_timeframe")
    def handle_add_all_timeframe(self):
        instrument_widget = self.query_one("#instrument", Select)
        instrument = str(instrument_widget.value) if instrument_widget.value and instrument_widget.value is not Select.BLANK else ""
        if not instrument:
            self.query_one("#status").update("Select Instrument first.")
            return
            
        instruments_info = self._readiness_index.get("instruments", {})
        info = instruments_info.get(instrument, {})
        tfs = sorted(info.get("timeframes", {}).keys(), key=lambda x: int(x) if x.isdigit() else 999)
        if not tfs:
            self.query_one("#status").update("No Timeframes available for this instrument.")
            return
            
        self._add_timeframe_items([f"{tf}m" for tf in tfs])

    @on(Button.Pressed, "#clear_timeframe")
    def handle_clear_timeframe(self):
        self._set_timeframe_list([])
        self.query_one("#status").update("Cleared Timeframe list.")

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
