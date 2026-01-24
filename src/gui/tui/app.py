import sys
from pathlib import Path

from textual.app import App

# Add 'src' to sys.path to support direct execution from repo root
src_path = str(Path(__file__).resolve().parents[2])
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from gui.tui.screens.monitor import MonitorScreen
from gui.tui.screens.data_prepare import DataPrepareScreen
from gui.tui.screens.admin import AdminScreen
from gui.tui.screens.wfs import WFSScreen
from gui.tui.screens.portfolio import PortfolioScreen
from gui.tui.screens.runtime import RuntimeIndexScreen
from gui.tui.services.bridge import Bridge

class FishBroTUI(App):
    """FishBroWFS TUI Control Station."""
    
    CSS_PATH = "styles.tcss"
    BINDINGS = [
        ("1", "switch_screen('data_prepare')", "Data"),
        ("2", "switch_screen('monitor')", "Monitor"),
        ("3", "switch_screen('wfs')", "WFS"),
        ("4", "switch_screen('portfolio')", "Portfolio"),
        ("5", "switch_screen('runtime')", "System/Index"),
        ("7", "switch_screen('admin')", "Admin"),
        ("ctrl+c", "copy_field", "Copy"),
        ("ctrl+v", "paste_field", "Paste"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.bridge = Bridge()

    def on_mount(self):
        self.install_screen(DataPrepareScreen(self.bridge), name="data_prepare")
        self.install_screen(MonitorScreen(self.bridge), name="monitor")
        self.install_screen(AdminScreen(self.bridge), name="admin")
        self.install_screen(WFSScreen(self.bridge), name="wfs")
        self.install_screen(PortfolioScreen(self.bridge), name="portfolio")
        self.install_screen(RuntimeIndexScreen(self.bridge), name="runtime")
        self.push_screen("monitor")
        self.set_interval(2.0, self._refresh_nav_status)
        self.call_later(self._refresh_nav_status)

    def open_job_artifacts(self, job_id: str) -> None:
        # Central router so any screen can jump to Monitor and show artifacts for a job.
        self.switch_screen("monitor")
        self.call_later(self._set_monitor_job, job_id)

    def _set_monitor_job(self, job_id: str) -> None:
        try:
            screen = self.get_screen("monitor")
            if hasattr(screen, "set_job_id"):
                screen.set_job_id(job_id)
        except Exception:
            return

    def _refresh_nav_status(self) -> None:
        try:
            snap = self.bridge.get_worker_snapshot()
            status_text = f"S:{snap.get('supervisors', 0)} W:{snap.get('active', 0)} B:{snap['busy']} I:{snap['idle']} Q:{snap['queued']} R:{snap['running']}"
            self.title = f"FishBroTUI  |  {status_text}"
            
            # Still call update_status on nav_bar just in case we want to show it there too, 
            # but the title is our primary visible status now.
            try:
                self.screen.query_one("#nav_bar").update_status(status_text)
            except:
                pass
        except Exception as e:
            self.log(f"Status refresh error: {e}")
            return



    def _clipboard_get(self) -> str:
        try:
            import pyperclip
            return pyperclip.paste() or ""
        except Exception:
            return ""

    def _clipboard_set(self, value: str) -> None:
        try:
            import pyperclip
            pyperclip.copy(value)
        except Exception:
            pass

    def action_copy_field(self) -> None:
        from textual.widgets import Input, DataTable

        focused = self.focused
        if isinstance(focused, Input):
            self._clipboard_set(focused.value or "")
            return
        if isinstance(focused, DataTable):
            # Copy selected row key (e.g., job_id) when focus is on a job table.
            try:
                cell_key = focused.coordinate_to_cell_key(focused.cursor_coordinate)
                self._clipboard_set(str(cell_key.row_key))
            except Exception:
                return

    def action_paste_field(self) -> None:
        from textual.widgets import Input

        focused = self.focused
        if isinstance(focused, Input):
            clip = self._clipboard_get()
            if clip:
                focused.value = (focused.value or "") + clip

if __name__ == "__main__":
    app = FishBroTUI()
    app.run()
