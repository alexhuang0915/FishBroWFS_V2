from textual.widgets import Static, Button
from textual.containers import Horizontal


class NavBar(Horizontal):
    """Top navigation bar with clickable shortcuts."""

    def compose(self):
        yield Button("  1 Data  ", id="nav_data_prepare", variant="default")
        yield Button("  2 Monitor  ", id="nav_monitor", variant="default")
        yield Button("  3 WFS  ", id="nav_wfs", variant="default")
        yield Button("  4 Portfolio  ", id="nav_portfolio", variant="default")
        yield Button("  5 System  ", id="nav_runtime", variant="default")
        yield Static("  |  [q] Quit  ", classes="nav_quit")
        # Spacer and status label removed - now in Header title

    def update_status(self, text: str) -> None:
        try:
            status = f"| {text}" if text else ""
            self.query_one("#nav_status", Static).update(status)
        except Exception:
            return

    def set_active(self, screen_name: str) -> None:
        """Highlight the button corresponding to active screen."""
        for btn in self.query(Button):
            if btn.id == f"nav_{screen_name}":
                btn.add_class("active")
            else:
                btn.remove_class("active")
