from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from textual import on
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, DataTable, Input, Label, ListItem, ListView, Static

from gui.tui.screens.base import BaseScreen
from gui.tui.services.bridge import Bridge


class ReportScreen(BaseScreen):
    """Report viewer for existing WFS artifacts (no recompute)."""

    SCREEN_NAME = "report"

    BINDINGS = [
        ("r", "refresh", "Reload"),
        ("R", "report", "Open Report"),
        ("j", "cursor_down", "Down"),
        ("k", "cursor_up", "Up"),
        ("enter", "toggle_detail", "Detail"),
        ("/", "focus_filter", "Filter"),
        ("o", "open_folder", "Open Folder"),
    ]

    def __init__(self, bridge: Bridge, **kwargs):
        super().__init__(**kwargs)
        self.bridge = bridge
        self._selected_job_id: str | None = None
        self._report_path: Path | None = None
        self._report_data: dict | None = None
        self._windows_rows: list[dict[str, Any]] = []
        self._filtered_rows: list[dict[str, Any]] = []
        self._detail_open = False

    def main_compose(self):
        with Horizontal():
            with Vertical(id="report_sidebar"):
                yield Label("HISTORY", id="title")
                yield Label("Select from recent WFS runs.", classes="hint")
                yield Input(placeholder="filter runs...", id="run_filter")
                yield ListView(id="run_list")
                yield Button("Refresh List", id="refresh_runs")

                yield Label("MANUAL DISCOVERY", classes="section_title")
                yield Input(placeholder="paste job UUID...", id="job_id")
                yield Button("Load Analysis", id="load_report", variant="primary")
                yield Label("Direct access via Job ID.", classes="hint")

            with Vertical(id="report_body"):
                yield Label("WFS PERFORMANCE ANALYSIS", id="report_title")
                yield Label("", id="report_subtitle", classes="hint")

                with Horizontal(id="section_a"):
                    with Vertical(classes="report_card"):
                        yield Label("VERDICT", classes="section_title")
                        yield Static("", id="verdict_grade")
                        yield Static("", id="verdict_is_tradable")
                        yield Static("", id="verdict_summary")
                    with Vertical(classes="report_card"):
                        yield Label("RISK FLAGS", classes="section_title")
                        yield Static("", id="risk_flags")
                    with Vertical(classes="report_card"):
                        yield Label("SNAPSHOT", classes="section_title")
                        yield Static("", id="data_snapshot")
                        yield Static("", id="data_range")
                        yield Static("", id="windows_total")

                with Horizontal(id="section_b"):
                    with Vertical(classes="report_card"):
                        yield Label("PERFORMANCE", classes="section_title")
                        yield Static("", id="card_perf")
                    with Vertical(classes="report_card"):
                        yield Label("RISK METRICS", classes="section_title")
                        yield Static("", id="card_risk")
                    with Vertical(classes="report_card"):
                        yield Label("RATIOS", classes="section_title")
                        yield Static("", id="card_ratios")

                with Horizontal(id="section_c"):
                    with Vertical(id="robust_panel"):
                        yield Label("ROBUSTNESS SUMMARY", classes="section_title")
                        yield Static("", id="robust_summary")
                        yield Label("FAIL REASONS", classes="section_title")
                        yield Static("", id="fail_reasons")
                    with Vertical(id="windows_panel"):
                        yield Label("WINDOWS LIST", classes="section_title")
                        yield Input(placeholder="Search by season or status...", id="window_filter")
                        yield DataTable(id="windows_table", cursor_type="row")
                        yield Static("", id="window_detail")

                yield Static("", id="footer")

    def on_mount(self):
        super().on_mount()
        self._init_table()
        self._refresh_run_list()
        try:
            self.query_one("#job_id", Input).focus()
        except Exception:
            pass

    def _init_table(self) -> None:
        table = self.query_one("#windows_table", DataTable)
        table.clear(columns=True)
        table.add_column("#", key="index")
        table.add_column("Season", key="season")
        table.add_column("Pass", key="pass")
        table.add_column("IS Net", key="is_net")
        table.add_column("IS MDD", key="is_mdd")
        table.add_column("IS Trades", key="is_trades")
        table.add_column("OOS Net", key="oos_net")
        table.add_column("OOS MDD", key="oos_mdd")
        table.add_column("OOS Trades", key="oos_trades")
        table.add_column("Fail Reason", key="fail_reason")

    def set_job_id(self, job_id: str) -> None:
        job_id = (job_id or "").strip()
        if not job_id:
            return
        self._selected_job_id = job_id
        self.query_one("#job_id", Input).value = job_id
        self._load_report()

    def action_refresh(self):
        self._load_report()

    def action_report(self):
        job_id = (self._selected_job_id or "").strip()
        if job_id:
            self._load_report()

    def action_cursor_down(self):
        table = self.query_one("#windows_table", DataTable)
        try:
            table.action_cursor_down()
        except Exception:
            pass
        self._update_detail_if_open()

    def action_cursor_up(self):
        table = self.query_one("#windows_table", DataTable)
        try:
            table.action_cursor_up()
        except Exception:
            pass
        self._update_detail_if_open()

    def action_toggle_detail(self):
        self._detail_open = not self._detail_open
        self._update_detail_if_open(force=True)

    def action_focus_filter(self):
        try:
            self.query_one("#window_filter", Input).focus()
        except Exception:
            pass

    def action_open_folder(self):
        if not self._report_path:
            return
        target = self._report_path.parent
        try:
            if os.name == "nt":
                os.startfile(str(target))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(target)])
            else:
                subprocess.Popen(["xdg-open", str(target)])
            self._set_footer(f"Opened folder: {target}")
        except Exception:
            self._set_footer("Failed to open folder.")

    @on(Button.Pressed, "#load_report")
    def handle_load_report(self):
        job_id = self.query_one("#job_id", Input).value.strip()
        if not job_id:
            self._set_footer("Error: job_id is required.")
            return
        self.set_job_id(job_id)

    @on(Button.Pressed, "#refresh_runs")
    def handle_refresh_runs(self):
        self._refresh_run_list()

    @on(ListView.Selected, "#run_list")
    def handle_run_selected(self, event: ListView.Selected):
        job_id = event.item.name or ""
        if job_id:
            self.set_job_id(job_id)

    @on(Input.Changed, "#run_filter")
    def handle_run_filter(self, event: Input.Changed):
        self._refresh_run_list(event.value)

    @on(Input.Changed, "#window_filter")
    def handle_window_filter(self, event: Input.Changed):
        self._render_windows_table(filter_text=event.value)

    def _refresh_run_list(self, filter_text: str | None = None) -> None:
        runs = self.bridge.get_recent_job_ids("RUN_RESEARCH_WFS", limit=50)
        filt = (filter_text or "").strip().lower()
        if filt:
            runs = [r for r in runs if filt in r.lower()]
        view = self.query_one("#run_list", ListView)
        view.clear()
        for job_id in runs:
            view.append(ListItem(Label(job_id), name=job_id))

    def _load_report(self) -> None:
        job_id = (self._selected_job_id or "").strip()
        if not job_id:
            return

        payload = self.bridge.read_wfs_report_for_job(job_id)
        err = payload.get("error")
        if err:
            self._report_data = None
            self._report_path = None
            self._set_footer(f"Error: {err}")
            self._clear_report()
            return

        self._report_data = payload.get("data")
        self._report_path = payload.get("path")
        self._render_report()

    def _render_report(self) -> None:
        data = self._report_data or {}
        meta = data.get("meta") or {}
        verdict = data.get("verdict") or {}
        metrics = data.get("metrics") or {}
        raw = metrics.get("raw") or {}
        windows = data.get("windows") or []

        title = f"Report  |  job_id={self._selected_job_id or 'N/A'}"
        self.query_one("#report_title", Label).update(title)
        subtitle = f"{meta.get('instrument', 'N/A')}  {meta.get('timeframe', 'N/A')}  {meta.get('start_season', 'N/A')}→{meta.get('end_season', 'N/A')}"
        self.query_one("#report_subtitle", Label).update(subtitle)

        self.query_one("#verdict_grade", Static).update(f"Grade: {self._fmt(verdict.get('grade'))}")
        self.query_one("#verdict_is_tradable", Static).update(f"is_tradable: {self._fmt(verdict.get('is_tradable'))}")
        self.query_one("#verdict_summary", Static).update(f"Summary: {self._fmt(verdict.get('summary'))}")

        flags = self._extract_flags(metrics)
        self.query_one("#risk_flags", Static).update(self._fmt_list(flags, empty_text="No risk flags."))

        instrument = meta.get("instrument") or data.get("config", {}).get("instrument") or "N/A"
        timeframe = meta.get("timeframe") or data.get("config", {}).get("data", {}).get("timeframe") or "N/A"
        self.query_one("#data_snapshot", Static).update(f"{instrument}  |  {timeframe}")

        range_text = self._season_range(meta)
        self.query_one("#data_range", Static).update(f"Range: {range_text}")
        self.query_one("#windows_total", Static).update(f"windows_total: {len(windows)}")

        self.query_one("#card_perf", Static).update(
            self._fmt_kv(
                [
                    ("Net Profit", self._pick(raw, ["net_profit", "net", "pnl", "profit"])),
                    ("Annualized Return", self._pick(raw, ["annualized_return", "cagr", "ann_return"])),
                    ("Expectancy / Avg Trade", self._pick(raw, ["expectancy", "avg_trade", "avg_trade_pnl"])),
                    ("Total Trades", self._pick(raw, ["trades", "total_trades"])),
                ]
            )
        )
        self.query_one("#card_risk", Static).update(
            self._fmt_kv(
                [
                    ("Max Drawdown", self._pick(raw, ["max_drawdown", "mdd", "max_dd"])),
                    ("Drawdown Duration", self._pick(raw, ["max_underwater_days", "dd_duration"])),
                    ("Volatility", self._pick(raw, ["volatility", "stdev", "std_dev"])),
                    ("Downside Risk", self._pick(raw, ["downside_risk", "semi_deviation", "downside_dev"])),
                ]
            )
        )
        self.query_one("#card_ratios", Static).update(
            self._fmt_kv(
                [
                    ("Sharpe", self._pick(raw, ["sharpe"])),
                    ("Sortino", self._pick(raw, ["sortino"])),
                    ("Calmar", self._pick(raw, ["calmar"])),
                    ("Profit Factor", self._pick(raw, ["profit_factor"])),
                ]
            )
        )

        self._windows_rows = self._build_windows_rows(windows)
        self._render_windows_table()

        summary = {
            "Pass Rate": self._pass_rate_text(raw, windows),
            "WFE": self._fmt(self._pick(raw, ["wfe"])),
            "ECR": self._fmt(self._pick(raw, ["ecr"])),
            "Window Range": self._season_range(meta),
            "Top Fail Reason": self._top_fail_reason(windows),
        }
        self.query_one("#robust_summary", Static).update(self._fmt_kv(summary.items()))
        self.query_one("#fail_reasons", Static).update(self._fmt_fail_reasons(windows))

        self._set_footer(self._footer_text())

    def _clear_report(self) -> None:
        for key in [
            "#verdict_grade",
            "#verdict_is_tradable",
            "#verdict_summary",
            "#risk_flags",
            "#data_snapshot",
            "#data_range",
            "#windows_total",
            "#card_perf",
            "#card_risk",
            "#card_ratios",
            "#robust_summary",
            "#fail_reasons",
            "#window_detail",
        ]:
            try:
                self.query_one(key, Static).update("")
            except Exception:
                pass
        self.query_one("#windows_table", DataTable).clear()

    def _render_windows_table(self, filter_text: str | None = None) -> None:
        table = self.query_one("#windows_table", DataTable)
        table.clear()
        rows = self._windows_rows
        filt = (filter_text or "").strip().lower()
        if filt:
            rows = [r for r in rows if filt in (r.get("season") or "").lower() or filt in (r.get("fail_reason") or "").lower()]
        self._filtered_rows = rows
        for row in rows:
            table.add_row(
                row.get("index", ""),
                row.get("season", ""),
                row.get("pass", ""),
                row.get("is_net", ""),
                row.get("is_mdd", ""),
                row.get("is_trades", ""),
                row.get("oos_net", ""),
                row.get("oos_mdd", ""),
                row.get("oos_trades", ""),
                row.get("fail_reason", ""),
            )
        self._update_detail_if_open(force=True)

    def _update_detail_if_open(self, force: bool = False) -> None:
        if not self._detail_open and not force:
            return
        detail = self.query_one("#window_detail", Static)
        if not self._detail_open:
            detail.update("")
            return
        table = self.query_one("#windows_table", DataTable)
        try:
            row_key = table.cursor_row
        except Exception:
            row_key = None
        if row_key is None or row_key < 0 or row_key >= len(self._filtered_rows):
            detail.update("Window detail: N/A")
            return
        row = self._filtered_rows[row_key]
        detail.update(self._fmt_kv(row.items()))

    def _set_footer(self, text: str) -> None:
        self.query_one("#footer", Static).update(text)

    def _footer_text(self) -> str:
        if not self._report_path:
            return "No report loaded."
        try:
            ts = datetime.fromtimestamp(self._report_path.stat().st_mtime).isoformat(timespec="seconds")
        except Exception:
            ts = "unknown"
        return f"Source: {self._report_path}  |  Updated: {ts}  |  Keys: r reload / j k move / enter detail / / filter / o open"

    @staticmethod
    def _pick(source: dict, keys: list[str]) -> Any:
        for k in keys:
            if k in source and source[k] is not None:
                return source[k]
        return None

    @staticmethod
    def _fmt(value: Any) -> str:
        if value is None or value == "":
            return "N/A"
        if isinstance(value, bool):
            return "True" if value else "False"
        if isinstance(value, float):
            abs_v = abs(value)
            if abs_v >= 1000:
                return f"{value:,.2f}"
            if abs_v >= 1:
                return f"{value:.4f}".rstrip("0").rstrip(".")
            return f"{value:.6f}".rstrip("0").rstrip(".")
        return str(value)

    @classmethod
    def _fmt_kv(cls, items: Any) -> str:
        lines = []
        for key, value in items:
            lines.append(f"{key}: {cls._fmt(value)}")
        return "\n".join(lines)

    @classmethod
    def _fmt_list(cls, items: list[str], empty_text: str = "N/A") -> str:
        if not items:
            return empty_text
        return "\n".join(f"- {item}" for item in items)

    @staticmethod
    def _season_range(meta: dict) -> str:
        start = meta.get("start_season") or meta.get("season")
        end = meta.get("end_season") or meta.get("season")
        if not start and not end:
            return "N/A"
        if start and end and start != end:
            return f"{start} → {end}"
        return str(start or end)

    @classmethod
    def _extract_flags(cls, metrics: dict) -> list[str]:
        flags: list[str] = []
        hard = metrics.get("hard_gates_triggered")
        if isinstance(hard, list):
            flags.extend([str(x) for x in hard])
        elif isinstance(hard, dict):
            flags.extend([str(k) for k, v in hard.items() if v])
        elif isinstance(hard, str):
            flags.append(hard)
        return flags

    @classmethod
    def _pass_rate_text(cls, raw: dict, windows: list[dict]) -> str:
        if "pass_rate" in raw and raw["pass_rate"] is not None:
            return cls._fmt(raw["pass_rate"])
        total = len(windows)
        if total == 0:
            return "N/A"
        passed = sum(1 for w in windows if bool(w.get("pass_")))
        pct = passed / total if total else 0
        return f"{passed}/{total} ({cls._fmt(pct)})"

    @staticmethod
    def _top_fail_reason(windows: list[dict]) -> str:
        counts: dict[str, int] = {}
        for w in windows:
            reasons = w.get("fail_reasons") or []
            if isinstance(reasons, str):
                reasons = [reasons]
            for r in reasons:
                counts[str(r)] = counts.get(str(r), 0) + 1
        if not counts:
            return "N/A"
        return max(counts.items(), key=lambda x: x[1])[0]

    @staticmethod
    def _fmt_fail_reasons(windows: list[dict]) -> str:
        counts: dict[str, int] = {}
        for w in windows:
            reasons = w.get("fail_reasons") or []
            if isinstance(reasons, str):
                reasons = [reasons]
            for r in reasons:
                counts[str(r)] = counts.get(str(r), 0) + 1
        if not counts:
            return "N/A"
        lines = [f"{k}: {v}" for k, v in sorted(counts.items(), key=lambda x: (-x[1], x[0]))]
        return "\n".join(lines)

    @classmethod
    def _build_windows_rows(cls, windows: list[dict]) -> list[dict]:
        rows = []
        for idx, w in enumerate(windows, start=1):
            is_metrics = w.get("is_metrics") or {}
            oos_metrics = w.get("oos_metrics") or {}
            rows.append(
                {
                    "index": str(idx),
                    "season": str(w.get("season") or ""),
                    "pass": "True" if w.get("pass_") else "False",
                    "is_net": cls._fmt(cls._pick(is_metrics, ["net_profit", "net", "pnl", "profit"])),
                    "is_mdd": cls._fmt(cls._pick(is_metrics, ["max_drawdown", "mdd", "max_dd"])),
                    "is_trades": cls._fmt(cls._pick(is_metrics, ["trades", "total_trades"])),
                    "oos_net": cls._fmt(cls._pick(oos_metrics, ["net_profit", "net", "pnl", "profit"])),
                    "oos_mdd": cls._fmt(cls._pick(oos_metrics, ["max_drawdown", "mdd", "max_dd"])),
                    "oos_trades": cls._fmt(cls._pick(oos_metrics, ["trades", "total_trades"])),
                    "fail_reason": ", ".join(w.get("fail_reasons") or []) if w.get("fail_reasons") else "",
                }
            )
        return rows
