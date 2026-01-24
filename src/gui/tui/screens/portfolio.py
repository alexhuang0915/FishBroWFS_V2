from textual import on
from textual.widgets import Label, Button, Static, Input, Select
from textual.containers import Vertical, Horizontal

from gui.tui.screens.base import BaseScreen
from gui.tui.services.bridge import Bridge
from gui.tui.widgets.job_monitor import JobMonitorPanel


class PortfolioScreen(BaseScreen):
    """BUILD_PORTFOLIO_V2 submission screen."""
    SCREEN_NAME = "portfolio"

    def __init__(self, bridge: Bridge, **kwargs):
        super().__init__(**kwargs)
        self.bridge = bridge

    def main_compose(self):
        with Horizontal():
            with Vertical(classes="form_panel"):
                yield Label("BUILD_PORTFOLIO_V2", id="title")

                with Horizontal():
                    yield Label("Season:", classes="label")
                    yield Input(value="2026Q1", id="season", classes="value")

                with Horizontal():
                    yield Label("Candidate Run IDs:", classes="label")
                    yield Input(placeholder="comma-separated WFS job_ids", id="candidate_run_ids", classes="value")

                with Horizontal():
                    yield Label("Recent WFS Jobs:", classes="label")
                    recent = self.bridge.get_recent_job_ids("RUN_RESEARCH_WFS", limit=10)
                    options = [(jid[:8], jid) for jid in recent] if recent else [("none", Select.BLANK)]
                    yield Select(options, id="recent_wfs_jobs", classes="value")
                    yield Button("Add", id="add_recent_wfs")
                    yield Button("Copy", id="copy_recent_wfs")
                    yield Button("Copy Latest", id="copy_latest_wfs")

                with Horizontal():
                    yield Label("Portfolio ID (opt):", classes="label")
                    yield Input(placeholder="optional", id="portfolio_id", classes="value")

                with Horizontal():
                    yield Label("Allowlist (opt):", classes="label")
                    yield Input(placeholder="comma-separated symbols (optional)", id="allowlist", classes="value")

                with Horizontal():
                    yield Label("Timeframe (opt):", classes="label")
                    yield Input(placeholder="e.g. 60m", id="timeframe", classes="value")

                yield Button("Submit BUILD_PORTFOLIO_V2", variant="primary", id="submit_portfolio")
                yield Static("", id="status")

            yield JobMonitorPanel(self.bridge, classes="monitor_panel")

    @on(Button.Pressed, "#submit_portfolio")
    def handle_submit(self):
        season = self.query_one("#season", Input).value.strip()
        run_ids_raw = self.query_one("#candidate_run_ids", Input).value.strip()
        portfolio_id = self.query_one("#portfolio_id", Input).value.strip()
        allowlist = self.query_one("#allowlist", Input).value.strip()
        timeframe = self.query_one("#timeframe", Input).value.strip()

        if not season:
            self.query_one("#status").update("Error: season is required.")
            return
        if not run_ids_raw:
            self.query_one("#status").update("Error: candidate_run_ids is required (comma-separated).")
            return

        candidate_run_ids = [x.strip() for x in run_ids_raw.split(",") if x.strip()]
        if not candidate_run_ids:
            self.query_one("#status").update("Error: candidate_run_ids is empty.")
            return

        try:
            job_id = self.bridge.submit_build_portfolio(
                season=season,
                candidate_run_ids=candidate_run_ids,
                portfolio_id=portfolio_id or None,
                allowlist=allowlist or None,
                timeframe=timeframe or None,
            )
            self.query_one("#status").update(f"Submitted BUILD_PORTFOLIO_V2 job: {job_id[:8]}...")
        except Exception as e:
            self.query_one("#status").update(f"Error: {e}")

    @on(Button.Pressed, "#add_recent_wfs")
    def handle_add_recent(self):
        selector = self.query_one("#recent_wfs_jobs", Select)
        selected = selector.value
        if selected is Select.BLANK:
            self.query_one("#status").update("No recent WFS job selected.")
            return

        entry = str(selected)
        input_box = self.query_one("#candidate_run_ids", Input)
        current = input_box.value.strip()
        if not current:
            input_box.value = entry
        else:
            # Append if not already present
            parts = [p.strip() for p in current.split(",") if p.strip()]
            if entry not in parts:
                parts.append(entry)
                input_box.value = ", ".join(parts)

    @on(Button.Pressed, "#copy_recent_wfs")
    def handle_copy_recent(self):
        selector = self.query_one("#recent_wfs_jobs", Select)
        selected = selector.value
        if selected is Select.BLANK:
            self.query_one("#status").update("No recent WFS job selected.")
            return
        if hasattr(self.app, "_clipboard_set"):
            self.app._clipboard_set(str(selected))
            self.query_one("#status").update("Copied selected WFS job id.")

    @on(Button.Pressed, "#copy_latest_wfs")
    def handle_copy_latest(self):
        recent = self.bridge.get_recent_job_ids("RUN_RESEARCH_WFS", limit=1)
        if not recent:
            self.query_one("#status").update("No recent WFS jobs.")
            return
        latest = recent[0]
        if hasattr(self.app, "_clipboard_set"):
            self.app._clipboard_set(latest)
            self.query_one("#status").update("Copied latest WFS job id.")
