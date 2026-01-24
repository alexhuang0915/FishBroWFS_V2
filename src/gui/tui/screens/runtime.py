import json
from textual.widgets import Label, Static
from textual.containers import Vertical, Horizontal, ScrollableContainer
from gui.tui.screens.base import BaseScreen
from gui.tui.services.bridge import Bridge
from gui.tui.widgets.job_monitor import JobMonitorPanel
from core.paths import get_runtime_root

class RuntimeIndexScreen(BaseScreen):
    """Runtime Readiness Matrix screen."""
    SCREEN_NAME = "runtime"
    
    def __init__(self, bridge: Bridge, **kwargs):
        super().__init__(**kwargs)
        self.bridge = bridge

    def main_compose(self):
        with Horizontal():
            with Vertical(classes="form_panel"):
                yield Label("Runtime Readiness Index", id="title")
                with ScrollableContainer():
                    yield Static(id="index_content", markup=True)

            yield JobMonitorPanel(self.bridge, classes="monitor_panel")

    def on_mount(self):
        super().on_mount()
        self.refresh_index()
        self.set_interval(5.0, self.refresh_index)

    def refresh_index(self):
        index_path = get_runtime_root() / "bar_prepare_index.json"
        content_widget = self.query_one("#index_content")
        
        if not index_path.exists():
            content_widget.update("[red]bar_prepare_index.json not found.[/red]")
            return

        try:
            with open(index_path, "r") as f:
                data = json.load(f)
            
            # Simple formatted view
            pretty = json.dumps(data, indent=2)
            content_widget.update(f"[green]Ready[/green]\n\n{pretty}")
        except Exception as e:
            content_widget.update(f"[red]Error reading index: {e}[/red]")
