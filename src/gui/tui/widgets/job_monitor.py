import json

from textual import events

from textual.widgets import DataTable, Label
from textual.containers import Vertical
from textual import on

from gui.tui.services.bridge import Bridge


class JobMonitorPanel(Vertical):
    """Right-side live job monitor panel."""

    def __init__(self, bridge: Bridge, **kwargs):
        super().__init__(**kwargs)
        self.bridge = bridge
        self._job_order: list[str] = []

    def compose(self):
        yield Label("Live Jobs", id="monitor_title")
        yield DataTable(id="monitor_table", cursor_type="row")
    def on_mount(self):
        table = self.query_one("#monitor_table", DataTable)
        table.add_columns("Job ID", "Type", "Data2", "State", "Progress", "Elapsed", "Updated")
        self.refresh_jobs()
        self.set_interval(2.0, self.refresh_jobs)

    def on_key(self, event) -> None:
        if event.key == "R":
            self._open_report_from_cursor()

    def refresh_jobs(self):
        try:
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            
            jobs = self.bridge.get_recent_jobs(limit=15)
            table = self.query_one("#monitor_table", DataTable)
            table.clear()
            for j in jobs:
                # Elapsed calculation
                try:
                    start_dt = datetime.fromisoformat(j.created_at.replace("Z", "+00:00"))
                    if j.state in ("SUCCEEDED", "FAILED", "ABORTED"):
                        end_dt = datetime.fromisoformat(j.updated_at.replace("Z", "+00:00"))
                        dur = end_dt - start_dt
                    else:
                        dur = now - start_dt
                    elapsed_str = f"{int(dur.total_seconds()) // 60}m {int(dur.total_seconds()) % 60}s"
                except:
                    elapsed_str = "-"

                table.add_row(
                    j.job_id[:8],
                    str(j.job_type),
                    self._extract_data2(j),
                    j.state,
                    self._format_progress(j.progress),
                    elapsed_str,
                    (j.updated_at or "")[:19].replace("T", " "),
                    key=j.job_id
                )
        except Exception:
            pass


    @on(DataTable.RowSelected, "#monitor_table")
    def _open_artifacts(self, event: DataTable.RowSelected) -> None:
        # Allow "Enter" / row select to drill into artifacts/report from any screen.
        try:
            job_id = str(event.row_key.value)
            if hasattr(self.app, "open_job_artifacts"):
                self.app.open_job_artifacts(job_id)
        except Exception:
            return

    def _open_report_from_cursor(self) -> None:
        try:
            table = self.query_one("#monitor_table", DataTable)
            row_key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key
            job_id = str(row_key.value) if hasattr(row_key, "value") else str(row_key)
            if hasattr(self.app, "open_job_report"):
                self.app.open_job_report(job_id)
        except Exception:
            return

    def _update_status(self, text: str) -> None:
        try:
            screen = self.app.screen
            status = screen.query_one("#status", Label)
            status.update(text)
        except Exception:
            return

    @staticmethod
    def _format_progress(progress: float | None) -> str:
        if progress is None:
            return ""
        try:
            return f"{int(float(progress) * 100)}%"
        except Exception:
            return ""

    @staticmethod
    def _extract_data2(job) -> str:
        try:
            spec = json.loads(job.spec_json or "{}")
            params = spec.get("params", {})
            return str(params.get("data2_dataset_id") or "")
        except Exception:
            return ""
