from textual import on
from textual.screen import Screen
from textual.widgets import Header, Static, Button
from textual.containers import Vertical

from gui.tui.widgets.nav_bar import NavBar

class BaseScreen(Screen):
    """Common layout for all TUI screens."""
    SCREEN_NAME = "" # Override in subclasses
    
    def compose(self):
        yield Header(show_clock=True)
        yield NavBar(id="nav_bar")
        yield from self.main_compose()

    def on_mount(self) -> None:
        """Called when the screen is mounted."""
        # Update NavBar highlighting
        try:
            nav = self.query_one(NavBar)
            nav.set_active(self.SCREEN_NAME)
        except Exception:
            pass

    def main_compose(self):
        """Override this in subclasses."""
        return []

    @on(Button.Pressed)
    def handle_nav_click(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if not button_id or not button_id.startswith("nav_"):
            return
            
        screen_name = button_id.replace("nav_", "")
        if screen_name:
            self.app.switch_screen(screen_name)
