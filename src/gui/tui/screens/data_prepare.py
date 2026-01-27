from textual import on
from textual.widgets import Label, Button, Static, Input, Select, Checkbox
from textual.containers import Vertical, Horizontal

from gui.tui.screens.base import BaseScreen
from gui.tui.services.bridge import Bridge
from gui.tui.widgets.job_monitor import JobMonitorPanel
from control.bars_store import resampled_bars_path
from core.paths import get_outputs_root
from core.season_context import current_season


class DataPrepareScreen(BaseScreen):
    """Data preparation submission screen (BUILD_BARS / BUILD_FEATURES)."""
    SCREEN_NAME = "data_prepare"

    def __init__(self, bridge: Bridge, **kwargs):
        super().__init__(**kwargs)
        self.bridge = bridge

    def on_mount(self) -> None:
        try:
            scope = self.query_one("#feature_scope", Select)
            if scope.value is Select.BLANK:
                scope.value = "all_packs"
        except Exception:
            pass

    def main_compose(self):
        with Horizontal():
            with Vertical(classes="form_panel"):
                yield Label("DATA PREPARE", id="title")

                with Horizontal():
                    yield Label("Dataset ID:", classes="label")
                    yield Input(placeholder="e.g. CFE.VX", id="dataset_id", classes="value")
                yield Label("The canonical symbol name for data fetching.", classes="hint")

                with Horizontal():
                    yield Label("Timeframes (min):", classes="label")
                    yield Input(value="60", id="timeframes", classes="value")
                yield Label("Comma-separated candle resolutions, e.g. 15,60,240.", classes="hint")

                with Horizontal():
                    yield Label("Season (opt):", classes="label")
                    yield Input(placeholder="e.g. 2026Q1 (optional)", id="season", classes="value")
                yield Label("Specific quarter to process. Defaults to current.", classes="hint")

                with Horizontal():
                    yield Label("Feature scope:", classes="label")
                    yield Select(
                        [
                            ("all_packs", "all_packs"),
                            ("baseline", "baseline"),
                        ],
                        id="feature_scope",
                        classes="value",
                    )
                yield Label("Used only for BUILD_FEATURES. all_packs = union of SSOT packs.", classes="hint")

                yield Checkbox("Force rebuild", id="force_rebuild")
                yield Checkbox("Purge dataset cache (DANGEROUS)", id="purge_before_build")

                with Horizontal():
                    yield Button("Submit BUILD_BARS", variant="primary", id="submit_build_bars")
                    yield Button("Submit BUILD_FEATURES", variant="default", id="submit_build_features")
                    yield Button("Purge Cache Only", variant="warning", id="purge_only")
                    yield Button("Purge Numba Cache", variant="warning", id="purge_numba")
                yield Static("", id="status")

            yield JobMonitorPanel(self.bridge, classes="monitor_panel")

    def _parse_timeframes(self) -> list[int] | None:
        raw = self.query_one("#timeframes", Input).value.strip()
        if not raw:
            return None
        try:
            tfs = [int(x.strip()) for x in raw.split(",") if x.strip()]
        except Exception:
            return None
        if not tfs or any(tf <= 0 for tf in tfs):
            return None
        return tfs

    def _bars_missing(self, dataset_id: str, season: str | None, timeframes: list[int]) -> list[str]:
        outputs_root = get_outputs_root()
        resolved_season = season or current_season()
        missing: list[str] = []
        for tf in timeframes:
            p = resampled_bars_path(outputs_root, resolved_season, dataset_id, str(int(tf)))
            if not p.exists():
                missing.append(str(p))
        return missing

    def _common_inputs(self) -> tuple[str, list[int], str | None, bool] | None:
        dataset_id = self.query_one("#dataset_id", Input).value.strip()
        season = self.query_one("#season", Input).value.strip()
        force_rebuild = self.query_one("#force_rebuild", Checkbox).value
        purge_before_build = self.query_one("#purge_before_build", Checkbox).value

        if not dataset_id:
            self.query_one("#status").update("Error: dataset_id is required.")
            return None

        tfs = self._parse_timeframes()
        if tfs is None:
            self.query_one("#status").update("Error: timeframes must be a comma-separated list of integers.")
            return None

        return (dataset_id, tfs, (season or None), bool(force_rebuild), bool(purge_before_build))

    @on(Button.Pressed, "#submit_build_bars")
    def handle_submit_build_bars(self):
        parsed = self._common_inputs()
        if parsed is None:
            return
        dataset_id, tfs, season, force_rebuild, purge_before_build = parsed

        try:
            job_id = self.bridge.submit_build_bars(
                dataset_id=dataset_id,
                timeframes=tfs,
                season=season,
                force_rebuild=force_rebuild,
                purge_before_build=purge_before_build,
            )
            self.query_one("#status").update(f"Submitted BUILD_BARS job: {job_id[:8]}...")
        except Exception as e:
            self.query_one("#status").update(f"Error: {e}")

    @on(Button.Pressed, "#submit_build_features")
    def handle_submit_build_features(self):
        parsed = self._common_inputs()
        if parsed is None:
            return
        dataset_id, tfs, season, force_rebuild, purge_before_build = parsed

        if purge_before_build:
            self.query_one("#status").update("Error: purge is not allowed for BUILD_FEATURES. Run BUILD_BARS with purge first.")
            return

        feature_scope = self.query_one("#feature_scope", Select).value
        if feature_scope is Select.BLANK:
            self.query_one("#status").update("Error: feature_scope is required.")
            return

        missing = self._bars_missing(dataset_id, season, tfs)
        if missing:
            self.query_one("#status").update(
                "Missing bars. Run BUILD_BARS first. Example missing: " + missing[0]
            )
            return

        try:
            job_id = self.bridge.submit_build_features(
                dataset_id=dataset_id,
                timeframes=tfs,
                season=season,
                feature_scope=str(feature_scope),
                force_rebuild=force_rebuild,
                purge_before_build=purge_before_build,
            )
            self.query_one("#status").update(f"Submitted BUILD_FEATURES job: {job_id[:8]}...")
        except Exception as e:
            self.query_one("#status").update(f"Error: {e}")

    @on(Button.Pressed, "#purge_only")
    def handle_purge_only(self):
        parsed = self._common_inputs()
        if parsed is None:
            return
        dataset_id, tfs, season, _, _ = parsed
        
        resolved_season = season or current_season()
        
        import subprocess
        import sys
        
        cmd = [sys.executable, "-m", "control.shared_cli", "purge", "--season", resolved_season, "--dataset-id", dataset_id, "--all"]
        # Use --all for simplicity in "Purge Cache Only" button.
        
        try:
            self.query_one("#status").update(f"Purging {dataset_id} for {resolved_season}...")
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if result.returncode == 0:
                self.query_one("#status").update(f"Purge complete: {result.stdout.strip()}")
            else:
                self.query_one("#status").update(f"Purge failed: {result.stderr or result.stdout}")
        except Exception as e:
            self.query_one("#status").update(f"Purge error: {e}")

    @on(Button.Pressed, "#purge_numba")
    def handle_purge_numba(self):
        import subprocess
        import sys

        cmd = [sys.executable, "-m", "control.shared_cli", "purge-numba"]
        try:
            self.query_one("#status").update("Purging Numba cache...")
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if result.returncode == 0:
                self.query_one("#status").update(f"Numba purge complete: {result.stdout.strip()}")
            else:
                self.query_one("#status").update(f"Numba purge failed: {result.stderr or result.stdout}")
        except Exception as e:
            self.query_one("#status").update(f"Numba purge error: {e}")
