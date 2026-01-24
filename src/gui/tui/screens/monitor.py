from textual import on
from textual.widgets import Label, Button, Static, Input, ListItem, ListView, RichLog
from textual.containers import Vertical, Horizontal

from gui.tui.screens.base import BaseScreen
from gui.tui.services.bridge import Bridge
from gui.tui.widgets.job_monitor import JobMonitorPanel


def _artifact_priority(name: str) -> tuple[int, str]:
    n = (name or "").lower()
    if n in {"error.txt", "policy_check.json"}:
        return (0, n)
    if "stderr" in n:
        return (1, n)
    if "stdout" in n:
        return (2, n)
    if n.endswith("_manifest.json") or n.endswith("manifest.json"):
        return (3, n)
    if "result" in n:
        return (4, n)
    return (9, n)


class MonitorScreen(BaseScreen):
    """Monitor + Artifacts: left artifacts/logs, right live jobs."""
    SCREEN_NAME = "monitor"

    BINDINGS = [
        ("r", "refresh", "Refresh"),
        ("t", "tail", "Tail"),
    ]

    def __init__(self, bridge: Bridge, **kwargs):
        super().__init__(**kwargs)
        self.bridge = bridge
        self._selected_job_id: str | None = None
        self._selected_artifact: str | None = None

    def main_compose(self):
        with Horizontal():
            with Vertical(classes="form_panel"):
                yield Label("Monitor + Artifacts", id="title")
                yield Label(
                    "Select a job on the right (Enter) to load artifacts.\n"
                    "Select a file on the left and press 't' or Tail to refresh.",
                    classes="hint",
                )

                with Horizontal():
                    yield Label("Job ID:", classes="label")
                    yield Input(placeholder="auto from right table, or paste here", id="job_id", classes="value")
                    yield Button("Load", id="load_job", variant="primary")

                with Horizontal():
                    yield Label("Tail lines:", classes="label")
                    yield Input(value="200", id="tail_lines", classes="value")
                    yield Button("Tail", id="tail_btn")
                    yield Button("Copy Job ID", id="copy_job_id")

                with Horizontal():
                    with Vertical(id="artifact_list_container"):
                        yield Label("Artifacts", classes="section_title")
                        yield ListView(id="artifact_list")
                    with Vertical(id="log_container"):
                        yield Label("Preview", classes="section_title")
                        yield RichLog(id="log_viewer", highlight=True, markup=True)

                yield Static("", id="status")

            yield JobMonitorPanel(self.bridge, classes="monitor_panel")

    def on_mount(self):
        super().on_mount()
        # Put focus on the jobs table for immediate navigation.
        try:
            self.query_one("#monitor_table").focus()
        except Exception:
            pass

    def set_job_id(self, job_id: str) -> None:
        job_id = (job_id or "").strip()
        if not job_id:
            return
        self._selected_job_id = job_id
        self.query_one("#job_id", Input).value = job_id
        self._reload_artifacts()

    def _reload_artifacts(self) -> None:
        job_id = (self._selected_job_id or "").strip()
        if not job_id:
            return

        artifacts = self.bridge.get_job_artifacts(job_id)
        artifacts = sorted(artifacts, key=_artifact_priority)

        list_view = self.query_one("#artifact_list", ListView)
        list_view.clear()
        for art in artifacts:
            list_view.append(ListItem(Label(art), name=art))

        self._selected_artifact = artifacts[0] if artifacts else None
        if self._selected_artifact:
            try:
                # Select first item so preview works without extra keys.
                list_view.index = 0
            except Exception:
                pass
            self._refresh_preview()
            self.query_one("#status").update(f"Loaded {len(artifacts)} artifacts for {job_id[:8]}...")
        else:
            self.query_one("#log_viewer", RichLog).clear()
            self.query_one("#status").update("No artifacts found for that job.")

    def _refresh_preview(self) -> None:
        if not self._selected_job_id or not self._selected_artifact:
            return

        lines_raw = self.query_one("#tail_lines", Input).value.strip()
        try:
            lines = int(lines_raw) if lines_raw else 200
        except Exception:
            lines = 200

        preview = self.bridge.get_log_tail(self._selected_job_id, self._selected_artifact, lines=lines)
        viewer = self.query_one("#log_viewer", RichLog)
        viewer.clear()
        viewer.write(preview)

    def action_refresh(self):
        self._reload_artifacts()

    def action_tail(self):
        self._refresh_preview()

    @on(Button.Pressed, "#load_job")
    def _on_load_job(self):
        job_id = self.query_one("#job_id", Input).value.strip()
        if not job_id:
            self.query_one("#status").update("Error: job_id is required.")
            return
        self.set_job_id(job_id)

    @on(Button.Pressed, "#tail_btn")
    def _on_tail_btn(self):
        self._refresh_preview()

    @on(Button.Pressed, "#copy_job_id")
    def _on_copy_job_id(self):
        job_id = (self._selected_job_id or "").strip()
        if not job_id:
            self.query_one("#status").update("No job selected.")
            return
        if hasattr(self.app, "_clipboard_set"):
            self.app._clipboard_set(job_id)
            self.query_one("#status").update("Copied job id.")

    @on(ListView.Selected, "#artifact_list")
    def _on_artifact_selected(self, event: ListView.Selected):
        self._selected_artifact = event.item.name
        self._refresh_preview()

