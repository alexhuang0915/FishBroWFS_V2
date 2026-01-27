from __future__ import annotations

from pathlib import Path

from textual import on
from textual.screen import ModalScreen
from textual.containers import Vertical, Horizontal
from textual.widgets import Label, Button, Static, Input, DataTable

from gui.tui.services.bridge import Bridge


class PortfolioRecommendationsModal(ModalScreen):
    """Advisory portfolio recommendations viewer with checkbox selection."""

    def __init__(self, bridge: Bridge, **kwargs):
        super().__init__(**kwargs)
        self.bridge = bridge
        self._loaded_portfolio_dir: Path | None = None
        self._selected_run_ids: set[str] = set()

    def compose(self):
        with Vertical(classes="modal_panel"):
            yield Label("Portfolio Recommendations (Advisory)", id="title")

            with Horizontal():
                yield Label("Portfolio Job:", classes="label")
                yield Input(placeholder="BUILD_PORTFOLIO_V2 job_id", id="portfolio_job_id", classes="value")
                yield Button("Load", id="load_recommendations")
                yield Button("Close", id="close")

            with Horizontal():
                yield Button("Select All", id="select_all")
                yield Button("Select None", id="select_none")
                yield Button("Save Selection", variant="success", id="save_selection")
                yield Button("Finalize", variant="primary", id="finalize_portfolio")

            yield Static("", id="status")
            yield Static("Space=toggle selection on row.", classes="hint")

            table = DataTable(id="recommendations_table")
            table.cursor_type = "row"
            yield table

    def on_mount(self) -> None:
        table = self.query_one("#recommendations_table", DataTable)
        table.add_columns(
            "Sel",
            "Run",
            "Data2",
            "Grade",
            "Tradable",
            "Score",
            "pass_rate",
            "trades",
            "wfe",
            "ulcer",
            "uw_days",
            "gates",
        )

    @on(Button.Pressed, "#close")
    def handle_close(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#load_recommendations")
    def handle_load_recommendations(self) -> None:
        job_id = self.query_one("#portfolio_job_id", Input).value.strip()
        if not job_id:
            self.query_one("#status").update("Error: portfolio job_id is required.")
            return

        payload = self.bridge.read_portfolio_recommendations_for_job(job_id)
        err = payload.get("error")
        if err:
            self.query_one("#status").update(f"Error: {err}")
            return

        data = payload.get("data") or {}
        self._loaded_portfolio_dir = payload.get("portfolio_dir")

        default_selected = data.get("default_selected_run_ids") or data.get("candidate_run_ids") or []
        self._selected_run_ids = {str(x) for x in default_selected}

        runs = data.get("runs") or []
        table = self.query_one("#recommendations_table", DataTable)
        table.clear()
        for item in runs:
            if not isinstance(item, dict):
                continue
            rid = str(item.get("run_id") or "")
            if not rid:
                continue
            data2 = str(item.get("data2") or "").strip() or "-"
            raw = item.get("raw") or {}
            gates = item.get("hard_gates_triggered") or []
            score = item.get("score_total_weighted")
            score_s = f"{float(score):.1f}" if score is not None else "N/A"

            table.add_row(
                "[x]" if rid in self._selected_run_ids else "[ ]",
                rid[:8],
                data2,
                str(item.get("grade") or ""),
                "Y" if bool(item.get("is_tradable")) else "N",
                score_s,
                _fmt(raw.get("pass_rate"), 2),
                _fmt(raw.get("trades"), 0),
                _fmt(raw.get("wfe"), 2),
                _fmt(raw.get("ulcer_index"), 1),
                _fmt(raw.get("max_underwater_days"), 0),
                ",".join([str(x) for x in gates]) if gates else "",
                key=rid,
            )

        self.query_one("#status").update(f"Loaded {len(table.rows)} runs.")

    @on(Button.Pressed, "#select_all")
    def handle_select_all(self) -> None:
        table = self.query_one("#recommendations_table", DataTable)
        self._selected_run_ids = {str(k) for k in table.rows.keys()}
        self._refresh_selection_column()

    @on(Button.Pressed, "#select_none")
    def handle_select_none(self) -> None:
        self._selected_run_ids = set()
        self._refresh_selection_column()

    @on(Button.Pressed, "#save_selection")
    def handle_save_selection(self) -> None:
        if not self._loaded_portfolio_dir:
            self.query_one("#status").update("Error: load recommendations first.")
            return
        out = self.bridge.write_portfolio_selection(self._loaded_portfolio_dir, sorted(self._selected_run_ids))
        if not out.get("ok"):
            self.query_one("#status").update(f"Error: {out.get('error')}")
            return
        self.query_one("#status").update(f"Saved selection ({len(self._selected_run_ids)} runs).")

    @on(Button.Pressed, "#finalize_portfolio")
    def handle_finalize_portfolio(self) -> None:
        if not self._loaded_portfolio_dir:
            self.query_one("#status").update("Error: load recommendations first.")
            return

        # Read season/portfolio_id from recommendations.json when available.
        job_id = self.query_one("#portfolio_job_id", Input).value.strip()
        payload = self.bridge.read_portfolio_recommendations_for_job(job_id) if job_id else {}
        data = payload.get("data") or {}
        season = str(data.get("season") or "").strip()
        portfolio_id = str(data.get("portfolio_id") or "").strip()
        if not season or not portfolio_id:
            # Fallback: infer from path structure .../seasons/<season>/portfolios/<portfolio_id>/
            try:
                p = Path(self._loaded_portfolio_dir)
                portfolio_id = p.name
                season = p.parent.parent.name  # seasons/<season>/portfolios/<portfolio_id>
            except Exception:
                season = season or ""
                portfolio_id = portfolio_id or ""

        if not season or not portfolio_id:
            self.query_one("#status").update("Error: cannot infer season/portfolio_id for finalize.")
            return

        try:
            fin_job = self.bridge.submit_finalize_portfolio(season=season, portfolio_id=portfolio_id)
            self.query_one("#status").update(f"Submitted FINALIZE_PORTFOLIO_V1 job: {fin_job[:8]}...")
        except Exception as exc:
            self.query_one("#status").update(f"Error: {exc}")

    def on_key(self, event) -> None:  # type: ignore[override]
        if event.key != "space":
            return
        table = self.query_one("#recommendations_table", DataTable)
        if self.focused is not table:
            return
        try:
            cell_key = table.coordinate_to_cell_key(table.cursor_coordinate)
            rid = str(cell_key.row_key)
        except Exception:
            return
        if not rid:
            return
        if rid in self._selected_run_ids:
            self._selected_run_ids.remove(rid)
        else:
            self._selected_run_ids.add(rid)
        self._refresh_selection_column()

    def _refresh_selection_column(self) -> None:
        table = self.query_one("#recommendations_table", DataTable)
        for rid in table.rows.keys():
            try:
                table.update_cell(rid, 0, "[x]" if str(rid) in self._selected_run_ids else "[ ]")
            except Exception:
                continue


def _fmt(value, digits: int) -> str:
    if value is None:
        return "N/A"
    try:
        if digits == 0:
            return str(int(float(value)))
        return f"{float(value):.{digits}f}"
    except Exception:
        return "N/A"
