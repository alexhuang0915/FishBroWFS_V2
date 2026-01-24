import json

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
        table.add_column("Job ID", key="job_id")
        table.add_column("Type", key="job_type")
        table.add_column("Data2", key="data2")
        table.add_column("State", key="state")
        table.add_column("Progress", key="progress")
        table.add_column("Phase", key="phase")
        table.add_column("Updated", key="updated_at")
        self.refresh_jobs()
        self.set_interval(1.0, self.refresh_jobs)

    def refresh_jobs(self):
        table = self.query_one("#monitor_table", DataTable)
        jobs = self.bridge.get_recent_jobs(limit=30)
        job_ids = [job.job_id for job in jobs]

        if job_ids != self._job_order:
            table.clear()
            for job in jobs:
                table.add_row(
                    job.job_id[:8],
                    str(job.job_type),
                    self._extract_data2(job),
                    job.state,
                    self._format_progress(job.progress),
                    job.phase or "",
                    (job.updated_at or "")[:19].replace("T", " "),
                    key=job.job_id,
                )
            self._job_order = job_ids
            return

        for job in jobs:
            table.update_cell(job.job_id, "data2", self._extract_data2(job))
            table.update_cell(job.job_id, "state", job.state)
            table.update_cell(job.job_id, "progress", self._format_progress(job.progress))
            table.update_cell(job.job_id, "phase", job.phase or "")
            table.update_cell(job.job_id, "updated_at", (job.updated_at or "")[:19].replace("T", " "))

    @on(DataTable.RowSelected, "#monitor_table")
    def _open_artifacts(self, event: DataTable.RowSelected) -> None:
        # Allow "Enter" / row select to drill into artifacts from any screen.
        try:
            job_id = str(event.row_key.value)
            if hasattr(self.app, "open_job_artifacts"):
                self.app.open_job_artifacts(job_id)
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
