from textual import on
from textual.widgets import Label, Button, Static, Input
from textual.containers import Vertical, Horizontal

from gui.tui.screens.base import BaseScreen
from gui.tui.services.bridge import Bridge
from gui.tui.widgets.job_monitor import JobMonitorPanel


class AdminScreen(BaseScreen):
    """Admin / utility screen (placeholder)."""
    SCREEN_NAME = "admin"

    def __init__(self, bridge: Bridge, **kwargs):
        super().__init__(**kwargs)
        self.bridge = bridge

    def main_compose(self):
        with Horizontal():
            with Vertical(classes="form_panel"):
                yield Label("Admin (Removed)", id="title")
                yield Static("Admin utilities removed in Local Research OS mode.", id="status")

            yield JobMonitorPanel(self.bridge, classes="monitor_panel")

    # Admin actions removed in Local Research OS mode.
