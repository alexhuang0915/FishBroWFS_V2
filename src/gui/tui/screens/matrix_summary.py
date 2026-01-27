from __future__ import annotations

import json
from pathlib import Path
from typing import Any, List

from textual import on
from textual.app import ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widgets import Label, DataTable, Button, Static

from gui.tui.screens.base import BaseScreen
from gui.tui.services.bridge import Bridge
from core.paths import get_artifacts_root

class MatrixSummaryScreen(BaseScreen):
    """Screen for viewing matrix run summaries."""
    SCREEN_NAME = "matrix_summary"

    BINDINGS = [
        ("r", "refresh", "Reload"),
        ("e", "export_selection", "Export Selection"),
        ("q", "pop_screen", "Back"),
        ("escape", "pop_screen", "Back"),
    ]

    def __init__(self, bridge: Bridge, auto_run_id: str | None = None, **kwargs):
        super().__init__(**kwargs)
        self.bridge = bridge
        self.auto_run_id = auto_run_id
        self._summary_data: dict | None = None

    def main_compose(self) -> ComposeResult:
        with Vertical():
            yield Label("MATRIX SUMMARY", id="title")
            yield Label("", id="subtitle", classes="hint")
            
            with Horizontal(id="controls"):
                yield Button("Refresh", id="refresh_btn")
                yield Button("Export Selection", id="export_btn", variant="success")
                yield Button("Back", id="back_btn", variant="primary")

            yield DataTable(id="summary_table")
            yield Static("", id="footer")

    def on_mount(self) -> None:
        super().on_mount()
        self._init_table()
        self._load_data()

    def _init_table(self) -> None:
        table = self.query_one("#summary_table", DataTable)
        table.clear(columns=True)
        table.add_column("Data2", key="data2")
        table.add_column("Grade", key="grade")
        table.add_column("Score", key="score")
        table.add_column("PassRate", key="pass_rate")
        table.add_column("Trades", key="trades")
        table.add_column("Missing%", key="missing")
        table.add_column("Update%", key="update")
        table.add_column("Hold%", key="hold")
        table.add_column("JobID", key="job_id")
        table.cursor_type = "row"

    def _load_data(self) -> None:
        if not self.auto_run_id:
            # Try to find latest auto-run
            auto_runs_dir = get_artifacts_root() / "auto_runs"
            if auto_runs_dir.exists():
                dirs = sorted([d.name for d in auto_runs_dir.iterdir() if d.is_dir() and d.name.startswith("auto_")])
                if dirs:
                    self.auto_run_id = dirs[-1]
        
        if not self.auto_run_id:
            self.query_one("#subtitle").update("No auto-run found.")
            return

        summary_path = get_artifacts_root() / "auto_runs" / self.auto_run_id / "matrix_summary.json"
        
        # If matrix_summary.json doesn't exist, we might need to run the CLI to generate it
        # But for now, let's assume it exists or show error
        if not summary_path.exists():
            # Try to generate it on the fly if we have auto_run_id
            import subprocess
            import sys
            try:
                subprocess.run([sys.executable, "-m", "control.matrix_summary_cli", "--auto-run", self.auto_run_id], check=False)
            except Exception:
                pass

        if not summary_path.exists():
            self.query_one("#subtitle").update(f"Matrix summary not found for {self.auto_run_id}")
            return

        try:
            with open(summary_path, "r") as f:
                self._summary_data = json.load(f)
            self._render_data()
        except Exception as e:
            self.query_one("#subtitle").update(f"Error loading summary: {e}")

    def _render_data(self) -> None:
        if not self._summary_data:
            return
        
        data = self._summary_data
        rows = data.get("rows", [])
        self.query_one("#subtitle").update(f"Run ID: {self.auto_run_id} | Season: {data.get('season')} | Count: {len(rows)}")

        table = self.query_one("#summary_table", DataTable)
        table.clear()
        
        for r in rows:
            table.add_row(
                str(r.get("data2") or "None"),
                str(r.get("grade") or "N/A"),
                f"{r.get('score_total_weighted', 0):.2f}" if r.get("score_total_weighted") is not None else "N/A",
                f"{r.get('pass_rate', 0):.2f}" if r.get("pass_rate") is not None else "N/A",
                str(r.get("trades", 0)),
                f"{r.get('data2_missing_ratio_pct', 0):.1f}%" if r.get("data2_missing_ratio_pct") is not None else "N/A",
                f"{r.get('data2_update_ratio_pct', 0):.1f}%" if r.get("data2_update_ratio_pct") is not None else "N/A",
                f"{r.get('data2_hold_ratio_pct', 0):.1f}%" if r.get("data2_hold_ratio_pct") is not None else "N/A",
                str(r.get("job_id") or "")[:8],
            )
        
        self.query_one("#footer").update("Press 'r' to reload. Click headers to sort (TODO).")

    def action_refresh(self) -> None:
        self._load_data()

    def action_export_selection(self) -> None:
        if not self.auto_run_id:
            self._set_footer("Error: No auto-run ID for selection.")
            return
        
        import subprocess
        import sys
        
        cmd = [sys.executable, "-m", "control.matrix_select_cli", "--auto-run", self.auto_run_id]
        # For TUI, we'll use some default filters or allow user to customize?
        # User request says "users can produce a deterministic 'selection' output without manually copying job_ids"
        # I'll use some reasonable defaults or just the base selection based on the current summary.
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if result.returncode == 0:
                self._set_footer(f"Selection exported to: {self.auto_run_id}/selection.json")
            else:
                self._set_footer(f"Export failed: {result.stderr or result.stdout}")
        except Exception as e:
            self._set_footer(f"Export error: {e}")

    def _set_footer(self, text: str) -> None:
        self.query_one("#footer", Static).update(text)

    @on(Button.Pressed, "#refresh_btn")
    def handle_refresh(self) -> None:
        self.action_refresh()

    @on(Button.Pressed, "#export_btn")
    def handle_export(self) -> None:
        self.action_export_selection()

    @on(Button.Pressed, "#back_btn")
    def handle_back(self) -> None:
        self.dismiss()
