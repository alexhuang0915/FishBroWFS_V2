"""
OpTab Refactored - Backtest Master Console.

Implements SSOT v1.2:
- Left: inputs for backtest jobs
- Right: live status + job monitor
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

from PySide6.QtCore import Qt, Signal, QTimer, QThread
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QPushButton, QGroupBox, QSplitter,
    QSizePolicy, QSpacerItem, QMessageBox, QProgressBar,
    QComboBox, QLineEdit, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QFrame, QTextEdit,
    QApplication
)

from config.registry.instruments import load_instruments
from core.season_context import current_season, outputs_root
from gui.services.dataset_resolver import DatasetResolver
from gui.services.action_router_service import get_action_router_service
from gui.services.supervisor_client import (
    SupervisorClientError,
    get_registry_strategies,
    get_jobs,
    submit_job,
    get_stdout_tail,
    get_artifacts,
    list_seasons_ssot,
)
from gui.services.gate_summary_service import fetch_gate_summary
from gui.desktop.state.job_store import job_store, JobRecord
from gui.desktop.state.research_selection_state import research_selection_state

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CoverageRange:
    start: str
    end: str


class JobsPoller(QThread):
    jobs_loaded = Signal(list)
    error = Signal(str)

    def __init__(self, limit: int):
        super().__init__()
        self.limit = limit

    def run(self):
        try:
            jobs = get_jobs(limit=self.limit)
            self.jobs_loaded.emit(jobs)
        except SupervisorClientError as exc:
            self.error.emit(str(exc))


class DiagnosticsWorker(QThread):
    diagnostics_ready = Signal(dict)
    error = Signal(str)

    def __init__(self, job_id: str):
        super().__init__()
        self._job_identifier = job_id

    def run(self):
        try:
            log_tail = get_stdout_tail(self._job_identifier, n=50)
            artifacts = get_artifacts(self._job_identifier)
            files = []
            if isinstance(artifacts, dict):
                files = artifacts.get("files", []) or []
            elif isinstance(artifacts, list):
                files = artifacts
            payload = {
                "job_id": self._job_identifier,
                "log_tail": log_tail,
                "artifact_count": len(files),
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
            self.diagnostics_ready.emit(payload)
        except SupervisorClientError as exc:
            self.error.emit(str(exc))


class CoverageWorker(QThread):
    coverage_ready = Signal(str, str, str)
    error = Signal(str)

    def __init__(self, instrument_id: str, parquet_path: str):
        super().__init__()
        self.instrument_id = instrument_id
        self.parquet_path = parquet_path

    def run(self):
        try:
            import pandas as pd
            df = pd.read_parquet(self.parquet_path, columns=["ts"])
            if df.empty:
                self.error.emit("Parquet has no rows")
                return
            ts_min = df["ts"].min()
            ts_max = df["ts"].max()
            start = ts_min.date().isoformat() if hasattr(ts_min, "date") else str(ts_min)[:10]
            end = ts_max.date().isoformat() if hasattr(ts_max, "date") else str(ts_max)[:10]
            self.coverage_ready.emit(self.instrument_id, start, end)
        except Exception as exc:
            self.error.emit(f"Coverage read failed: {exc}")


class OpTabRefactored(QWidget):
    """OpTab Backtest Master Console (SSOT v1.2)."""

    log_signal = Signal(str)
    switch_to_audit_tab = Signal(str)
    progress_signal = Signal(int)
    artifact_state_changed = Signal(str, str, str)

    def __init__(self):
        super().__init__()

        self.dataset_resolver = DatasetResolver()
        self.action_router = get_action_router_service()
        self.prepared_index_path = Path(outputs_root()) / "_runtime" / "bar_prepare_index.json"
        self.prepared_index: Dict[str, Any] = {}
        self.prepared_index_loaded_at: Optional[datetime] = None
        self.coverage_cache: Dict[str, CoverageRange] = {}
        self.registry_instruments = [inst.id for inst in load_instruments().instruments]
        self.coverage_workers: List[CoverageWorker] = []
        self.diagnostic_workers: List[DiagnosticsWorker] = []

        self.job_limit = 20
        self.poll_interval_ms = 2000
        self.poller: Optional[JobsPoller] = None
        self.monitor_paused = False
        self.jobs: List[dict] = []
        self.focused_job_id: Optional[str] = None
        self.last_submitted_job_id: Optional[str] = None
        self.job_snapshots: Dict[str, dict] = {}
        self.job_last_change: Dict[str, datetime] = {}
        self.job_last_seen: Dict[str, datetime] = {}
        self.job_last_log_line: Dict[str, str] = {}
        self.job_last_log_time: Dict[str, datetime] = {}
        self.job_last_artifact_count: Dict[str, int] = {}

        self.setup_ui()
        self.setup_connections()
        self.load_registry_data()
        self.load_season_options()
        self.refresh_prepared_index()
        self.refresh_jobs()
        self.start_polling()

    def setup_ui(self):
        """Initialize the OpTab Master Console UI."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #555555;
                width: 1px;
            }
            QSplitter::handle:hover {
                background-color: #3A8DFF;
            }
        """)

        left_panel = QWidget()
        left_panel.setStyleSheet("background-color: #121212;")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(8, 8, 8, 8)
        left_layout.setSpacing(12)

        input_group = QGroupBox("Backtest Inputs")
        input_group.setStyleSheet(self._group_style("#1a237e"))
        input_layout = QFormLayout(input_group)
        input_layout.setContentsMargins(12, 12, 12, 12)
        input_layout.setSpacing(10)

        self.strategy_combo = QComboBox()
        self.strategy_combo.setEditable(False)
        self.strategy_combo.setStyleSheet(self._combo_style())
        input_layout.addRow("Strategy:", self.strategy_combo)

        self.timeframe_combo = QComboBox()
        self.timeframe_combo.setStyleSheet(self._combo_style())
        self.timeframe_combo.addItems(["15", "30", "60", "120", "240", "D"])
        input_layout.addRow("Timeframe:", self.timeframe_combo)

        self.instrument_combo = QComboBox()
        self.instrument_combo.setStyleSheet(self._combo_style())
        input_layout.addRow("Instrument:", self.instrument_combo)

        self.run_mode_combo = QComboBox()
        self.run_mode_combo.setStyleSheet(self._combo_style())
        self.run_mode_combo.addItems(["backtest", "research", "optimize", "wfs"])
        input_layout.addRow("Run Mode:", self.run_mode_combo)

        self.research_run_id_edit = QLineEdit()
        self.research_run_id_edit.setPlaceholderText("Required for optimize")
        self.research_run_id_edit.setStyleSheet(self._line_edit_style())
        input_layout.addRow("Research Run ID:", self.research_run_id_edit)

        season_row = QWidget()
        season_layout = QHBoxLayout(season_row)
        season_layout.setContentsMargins(0, 0, 0, 0)
        season_layout.setSpacing(6)
        self.season_combo = QComboBox()
        self.season_combo.setStyleSheet(self._combo_style())
        self.full_data_btn = QPushButton("Full Data")
        self.full_data_btn.setStyleSheet(self._small_button_style())
        season_layout.addWidget(self.season_combo)
        season_layout.addWidget(self.full_data_btn)
        input_layout.addRow("Season:", season_row)

        self.start_date_edit = QLineEdit()
        self.start_date_edit.setReadOnly(True)
        self.start_date_edit.setStyleSheet(self._line_edit_style())
        self.end_date_edit = QLineEdit()
        self.end_date_edit.setReadOnly(True)
        self.end_date_edit.setStyleSheet(self._line_edit_style())
        input_layout.addRow("Start Date:", self.start_date_edit)
        input_layout.addRow("End Date:", self.end_date_edit)

        left_layout.addWidget(input_group)

        self.run_button = QPushButton("RUN STRATEGY")
        self.run_button.setMinimumHeight(52)
        self.run_button.setStyleSheet(self._primary_button_style())
        left_layout.addWidget(self.run_button)

        self.run_disabled_reason = QLabel("")
        self.run_disabled_reason.setStyleSheet("color: #FFB74D; font-size: 11px;")
        self.run_disabled_reason.setWordWrap(True)
        left_layout.addWidget(self.run_disabled_reason)

        left_layout.addSpacerItem(QSpacerItem(20, 20, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))

        right_splitter = QSplitter(Qt.Orientation.Vertical)
        right_splitter.setStyleSheet("""
            QSplitter::handle {
                background-color: #555555;
                height: 1px;
            }
            QSplitter::handle:hover {
                background-color: #3A8DFF;
            }
        """)

        live_status_group = QGroupBox("Live Status (Focused Job)")
        live_status_group.setStyleSheet(self._group_style("#1b5e20"))
        live_layout = QVBoxLayout(live_status_group)
        live_layout.setContentsMargins(12, 12, 12, 12)
        live_layout.setSpacing(8)

        job_id_row = QHBoxLayout()
        self.job_id_edit = QLineEdit()
        self.job_id_edit.setReadOnly(True)
        self.job_id_edit.setStyleSheet(self._line_edit_style())
        self.copy_job_id_btn = QPushButton("Copy")
        self.copy_job_id_btn.setStyleSheet(self._small_button_style())
        job_id_row.addWidget(self.job_id_edit)
        job_id_row.addWidget(self.copy_job_id_btn)
        live_layout.addLayout(job_id_row)

        self.status_label = QLabel("Status: —")
        self.status_label.setStyleSheet("color: #E6E6E6; font-size: 12px; font-weight: bold;")
        live_layout.addWidget(self.status_label)

        self.submitted_label = QLabel("Submitted: —")
        self.submitted_label.setStyleSheet("color: #9A9A9A; font-size: 11px;")
        live_layout.addWidget(self.submitted_label)

        self.last_seen_label = QLabel("Last update: —")
        self.last_seen_label.setStyleSheet("color: #9A9A9A; font-size: 11px;")
        live_layout.addWidget(self.last_seen_label)

        self.phase_label = QLabel("Phase: —")
        self.phase_label.setStyleSheet("color: #BDBDBD; font-size: 11px;")
        live_layout.addWidget(self.phase_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        live_layout.addWidget(self.progress_bar)

        self.stall_label = QLabel("")
        self.stall_label.setStyleSheet("color: #FF9800; font-size: 11px;")
        live_layout.addWidget(self.stall_label)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #F44336; font-size: 11px;")
        self.error_label.setWordWrap(True)
        live_layout.addWidget(self.error_label)

        # Latest Run Deep Link (UX B2.1)
        self.latest_run_panel = QFrame()
        self.latest_run_panel.setVisible(False)
        self.latest_run_panel.setStyleSheet("background-color: #1A1A1A; border: 1px solid #666;")
        lr_layout = QHBoxLayout(self.latest_run_panel)
        self.lr_label = QLabel("Last: —")
        self.lr_label.setStyleSheet("font-size: 10px; color: #BBB;")
        lr_layout.addWidget(self.lr_label)
        lr_btn = QPushButton("OPS")
        lr_btn.setFixedWidth(40)
        lr_btn.clicked.connect(self._on_open_ops)
        lr_layout.addWidget(lr_btn)
        live_layout.addWidget(self.latest_run_panel)

        # Top-K Results Table (UX C1.2)
        self.results_group = QGroupBox("TOP-K RESULTS (RANKED)")
        res_layout = QVBoxLayout(self.results_group)
        self.topk_table = QTableWidget(0, 5)
        self.topk_table.setHorizontalHeaderLabels(["Rank", "Strategy", "Score", "Profit", "MDD"])
        self.topk_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.topk_table.setStyleSheet("background-color: #121212; font-size: 10px;")
        self.topk_table.setFixedHeight(150)
        res_layout.addWidget(self.topk_table)
        
        # Handoff Tools (UX C2.1)
        handoff_row = QHBoxLayout()
        self.use_run_btn = QPushButton("USE FOR PORTFOLIO →")
        self.use_run_btn.setEnabled(False)
        self.use_run_btn.setStyleSheet("""
            QPushButton { background-color: #2A5A2A; color: white; font-weight: bold; padding: 6px; }
            QPushButton:disabled { background-color: #333; color: #666; }
        """)
        self.use_run_btn.clicked.connect(self._on_use_for_portfolio)
        handoff_row.addWidget(self.use_run_btn)
        res_layout.addLayout(handoff_row)
        
        # Artifact Links (UX C1.3)
        links_row = QHBoxLayout()
        links_row.setSpacing(15)
        self.heatmap_link = QPushButton("📊 Heatmap")
        self.summary_link = QPushButton("📝 Summary Report")
        self.raw_metrics_link = QPushButton("📁 Raw Metrics")
        
        link_style = "color: #3A8DFF; text-decoration: underline; background: none; border: none; font-size: 10px; text-align: left;"
        for btn in [self.heatmap_link, self.summary_link, self.raw_metrics_link]:
            btn.setStyleSheet(link_style)
            btn.setCursor(Qt.PointingHandCursor)
            links_row.addWidget(btn)
        
        res_layout.addLayout(links_row)
        
        live_layout.addWidget(self.results_group)

        action_row = QHBoxLayout()
        self.view_artifacts_btn = QPushButton("View Artifacts")
        self.view_artifacts_btn.setStyleSheet(self._small_button_style())
        self.view_gate_btn = QPushButton("View Gate/Explain")
        self.view_gate_btn.setStyleSheet(self._small_button_style())
        self.diagnose_btn = QPushButton("Diagnose / Peek Evidence")
        self.diagnose_btn.setStyleSheet(self._small_button_style())
        action_row.addWidget(self.view_artifacts_btn)
        action_row.addWidget(self.view_gate_btn)
        action_row.addWidget(self.diagnose_btn)
        action_row.addStretch()
        live_layout.addLayout(action_row)

        self.diagnostics_output = QTextEdit()
        self.diagnostics_output.setReadOnly(True)
        self.diagnostics_output.setMaximumHeight(120)
        self.diagnostics_output.setStyleSheet("""
            QTextEdit {
                background-color: #121212;
                color: #E6E6E6;
                border: 1px solid #333333;
                font-family: monospace;
                font-size: 10px;
            }
        """)
        live_layout.addWidget(self.diagnostics_output)

        # Job output summary panel (initially hidden)
        self.output_summary_panel = QFrame()
        self.output_summary_panel.setStyleSheet("""
            QFrame {
                background-color: #1E1E1E;
                border: 1px solid #444444;
                border-radius: 4px;
                padding: 8px;
            }
        """)
        self.output_summary_panel.setVisible(False)
        output_summary_layout = QVBoxLayout(self.output_summary_panel)
        output_summary_layout.setContentsMargins(8, 8, 8, 8)
        output_summary_layout.setSpacing(6)

        self.output_summary_title = QLabel("Job Output Summary")
        self.output_summary_title.setStyleSheet("color: #E6E6E6; font-weight: bold; font-size: 12px;")
        output_summary_layout.addWidget(self.output_summary_title)

        self.gate_verdict_label = QLabel("Gate verdict: —")
        self.gate_verdict_label.setStyleSheet("color: #BDBDBD; font-size: 11px;")
        output_summary_layout.addWidget(self.gate_verdict_label)

        self.artifact_list_label = QLabel("Artifacts: —")
        self.artifact_list_label.setStyleSheet("color: #BDBDBD; font-size: 11px;")
        self.artifact_list_label.setWordWrap(True)
        output_summary_layout.addWidget(self.artifact_list_label)

        self.close_summary_btn = QPushButton("Close")
        self.close_summary_btn.setStyleSheet(self._small_button_style())
        self.close_summary_btn.setMaximumWidth(80)
        output_summary_layout.addWidget(self.close_summary_btn, 0, Qt.AlignmentFlag.AlignRight)

        live_layout.addWidget(self.output_summary_panel)

        monitor_group = QGroupBox("Monitor Console")
        monitor_group.setStyleSheet(self._group_style("#4a148c"))
        monitor_layout = QVBoxLayout(monitor_group)
        monitor_layout.setContentsMargins(12, 12, 12, 12)
        monitor_layout.setSpacing(8)

        monitor_controls = QHBoxLayout()
        self.pause_resume_btn = QPushButton("Pause")
        self.pause_resume_btn.setStyleSheet(self._small_button_style())
        self.refresh_btn = QPushButton("Refresh Now")
        self.refresh_btn.setStyleSheet(self._small_button_style())
        monitor_controls.addWidget(self.pause_resume_btn)
        monitor_controls.addWidget(self.refresh_btn)
        monitor_controls.addStretch()
        monitor_layout.addLayout(monitor_controls)

        self.jobs_table = QTableWidget()
        self.jobs_table.setColumnCount(7)
        self.jobs_table.setHorizontalHeaderLabels([
            "Created", "Job ID", "Instrument", "Timeframe", "Run Mode", "Status", "Date Range/Season"
        ])
        self.jobs_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.jobs_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.jobs_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.jobs_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.jobs_table.verticalHeader().setVisible(False)
        self.jobs_table.setStyleSheet("""
            QTableWidget {
                background-color: #121212;
                color: #E6E6E6;
                border: 1px solid #333333;
                font-size: 11px;
            }
            QHeaderView::section {
                background-color: #1E1E1E;
                color: #E6E6E6;
                padding: 4px;
                border: none;
                font-weight: bold;
            }
        """)
        monitor_layout.addWidget(self.jobs_table)

        right_splitter.addWidget(live_status_group)
        right_splitter.addWidget(monitor_group)
        right_splitter.setStretchFactor(0, 2)
        right_splitter.setStretchFactor(1, 3)
        right_splitter.setCollapsible(0, False)
        right_splitter.setCollapsible(1, False)

        main_splitter.addWidget(left_panel)
        main_splitter.addWidget(right_splitter)
        main_splitter.setStretchFactor(0, 2)
        main_splitter.setStretchFactor(1, 3)
        main_splitter.setCollapsible(0, False)
        main_splitter.setCollapsible(1, False)

        main_layout.addWidget(main_splitter)

    def setup_connections(self):
        self.run_button.clicked.connect(self.run_strategy)
        self.strategy_combo.currentIndexChanged.connect(self.update_run_state)
        self.timeframe_combo.currentIndexChanged.connect(self.on_timeframe_changed)
        self.instrument_combo.currentIndexChanged.connect(self.on_instrument_changed)
        self.run_mode_combo.currentIndexChanged.connect(self.on_run_mode_changed)
        self.season_combo.currentIndexChanged.connect(self.on_season_changed)
        self.full_data_btn.clicked.connect(self.reset_full_data)
        self.copy_job_id_btn.clicked.connect(self.copy_job_id)
        self.view_artifacts_btn.clicked.connect(self.on_view_artifacts)
        self.view_gate_btn.clicked.connect(self.on_view_gate)
        self.diagnose_btn.clicked.connect(self.run_diagnostics)
        self.pause_resume_btn.clicked.connect(self.toggle_pause)
        self.refresh_btn.clicked.connect(self.refresh_jobs)
        self.jobs_table.itemSelectionChanged.connect(self.on_job_selected)
        self.research_run_id_edit.textChanged.connect(self.update_run_state)
        self.close_summary_btn.clicked.connect(self.hide_output_summary)

    def _group_style(self, border_color: str) -> str:
        return f"""
            QGroupBox {{
                font-weight: bold;
                border: 2px solid {border_color};
                background-color: #1E1E1E;
                margin-top: 5px;
                padding-top: 8px;
                font-size: 12px;
            }}
            QGroupBox::title {{
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px 0 4px;
                color: #E6E6E6;
            }}
        """

    def _combo_style(self) -> str:
        return """
            QComboBox {
                background-color: #1E1E1E;
                color: #E6E6E6;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 4px;
            }
        """

    def _line_edit_style(self) -> str:
        return """
            QLineEdit {
                background-color: #1E1E1E;
                color: #E6E6E6;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 4px;
            }
            QLineEdit:read-only {
                background-color: #2A2A2A;
                color: #9A9A9A;
            }
        """

    def _primary_button_style(self) -> str:
        return """
            QPushButton {
                background-color: #2D6CDF;
                color: white;
                font-weight: bold;
                font-size: 14px;
                padding: 12px;
                border-radius: 6px;
                border: 1px solid #2D6CDF;
            }
            QPushButton:hover { background-color: #2459B6; }
            QPushButton:pressed { background-color: #1E4A9A; }
            QPushButton:disabled {
                background-color: #3A3A3A;
                color: #9e9e9e;
                border: 1px solid #616161;
            }
        """

    def _small_button_style(self) -> str:
        return """
            QPushButton {
                background-color: #2A2A2A;
                color: #E6E6E6;
                font-size: 11px;
                padding: 6px 10px;
                border-radius: 4px;
                border: 1px solid #555555;
            }
            QPushButton:hover { background-color: #333333; }
            QPushButton:disabled { color: #888888; }
        """

    def load_registry_data(self):
        self.strategy_combo.clear()
        self.strategy_combo.addItem("Select strategy", "")
        try:
            strategies = get_registry_strategies()
            for strategy in strategies:
                if isinstance(strategy, dict):
                    strategy_id = strategy.get("id") or strategy.get("strategy_id") or strategy.get("name")
                    label = strategy.get("name") or strategy_id
                else:
                    strategy_id = str(strategy)
                    label = strategy_id
                if strategy_id:
                    self.strategy_combo.addItem(label, strategy_id)
        except SupervisorClientError as exc:
            logger.error("Failed to load strategies: %s", exc)
            self.strategy_combo.addItem("Registry unavailable", "")

    def load_season_options(self):
        self.season_combo.clear()
        self.season_combo.addItem("FULL DATA", "")
        try:
            response = list_seasons_ssot()
            seasons = response.get("seasons", []) if isinstance(response, dict) else []
            for season in seasons:
                season_id = season.get("season_id") if isinstance(season, dict) else str(season)
                if season_id:
                    self.season_combo.addItem(season_id, season_id)
        except SupervisorClientError as exc:
            logger.warning("Season SSOT unavailable: %s", exc)
            self.season_combo.addItem(current_season(), current_season())

    def refresh_prepared_index(self):
        if self.prepared_index_path.exists():
            try:
                self.prepared_index = json.loads(self.prepared_index_path.read_text(encoding="utf-8"))
                self.prepared_index_loaded_at = datetime.now(timezone.utc)
            except Exception as exc:
                logger.error("Failed to load prepared index: %s", exc)
                self.prepared_index = {}
        else:
            self.prepared_index = {}

        self.refresh_instrument_options()

    def refresh_instrument_options(self):
        selected_timeframe = self.timeframe_combo.currentText().strip()
        prepared_instruments = self._get_prepared_instruments(selected_timeframe)
        self.instrument_combo.clear()
        if not selected_timeframe:
            self.instrument_combo.addItem("Select timeframe first", "")
        elif not prepared_instruments:
            self.instrument_combo.addItem("No prepared instruments", "")
        else:
            self.instrument_combo.addItem("Select instrument", "")
            for instrument in prepared_instruments:
                self.instrument_combo.addItem(instrument, instrument)
        self.update_run_state()

    def on_timeframe_changed(self):
        self.refresh_instrument_options()
        self.update_date_range()

    def on_instrument_changed(self):
        self.update_date_range()
        self.update_run_state()

    def on_run_mode_changed(self):
        self.research_run_id_edit.setEnabled(self.run_mode_combo.currentText() == "optimize")
        if self.run_mode_combo.currentText() != "optimize":
            self.research_run_id_edit.clear()
        self.update_run_state()

    def on_season_changed(self):
        self.update_date_range()
        self.update_run_state()

    def reset_full_data(self):
        self.season_combo.setCurrentIndex(0)
        self.update_date_range()
        self.update_run_state()

    def update_date_range(self):
        instrument_id = self.instrument_combo.currentData()
        timeframe = self.timeframe_combo.currentText().strip()
        season_id = self.season_combo.currentData()
        if not instrument_id or not timeframe:
            self.start_date_edit.setText("")
            self.end_date_edit.setText("")
            return

        if season_id:
            season_range = self._resolve_season_range(season_id)
            if season_range:
                self.start_date_edit.setText(season_range.start)
                self.end_date_edit.setText(season_range.end)
            else:
                self.start_date_edit.setText("")
                self.end_date_edit.setText("")
        else:
            coverage = self._resolve_full_data_range(instrument_id)
            if coverage:
                self.start_date_edit.setText(coverage.start)
                self.end_date_edit.setText(coverage.end)
            else:
                self.start_date_edit.setText("")
                self.end_date_edit.setText("")

    def _resolve_full_data_range(self, instrument_id: str) -> Optional[CoverageRange]:
        cache_key = f"{instrument_id}"
        if cache_key in self.coverage_cache:
            return self.coverage_cache[cache_key]

        parquet_path = self._find_parquet_path(instrument_id)
        if parquet_path:
            worker = CoverageWorker(instrument_id, parquet_path)
            worker.coverage_ready.connect(self._on_coverage_ready)
            worker.error.connect(lambda msg: logger.warning("Coverage worker: %s", msg))
            self.coverage_workers.append(worker)
            worker.start()
            return None

        return None

    def _resolve_season_range(self, season_id: str) -> Optional[CoverageRange]:
        try:
            if season_id and "Q" in season_id:
                year_part = season_id.split("Q")[0]
                q_part = season_id.split("Q")[1][:1]
                if year_part.isdigit() and q_part.isdigit():
                    year = int(year_part)
                    quarter = int(q_part)
                    if 1 <= quarter <= 4:
                        start_month = (quarter - 1) * 3 + 1
                        end_month = start_month + 2
                        start_date = datetime(year, start_month, 1).date()
                        if end_month == 12:
                            end_date = datetime(year, 12, 31).date()
                        else:
                            end_date = datetime(year, end_month + 1, 1).date() - timedelta(days=1)
                        return CoverageRange(start=start_date.isoformat(), end=end_date.isoformat())
        except Exception:
            return None
        return None

    def _find_parquet_path(self, instrument_id: str) -> Optional[str]:
        instrument_entry = self.prepared_index.get("instruments", {}).get(instrument_id, {})
        parquet_status = instrument_entry.get("parquet_status") if isinstance(instrument_entry, dict) else None
        if parquet_status and parquet_status.get("path"):
            return parquet_status.get("path")
        return None

    def _on_coverage_ready(self, instrument_id: str, start: str, end: str):
        self.coverage_cache[instrument_id] = CoverageRange(start=start, end=end)
        if self.instrument_combo.currentData() == instrument_id and not self.season_combo.currentData():
            self.start_date_edit.setText(start)
            self.end_date_edit.setText(end)
            self.update_run_state()

    def _get_prepared_instruments(self, timeframe: str) -> List[str]:
        timeframe_keys = self._timeframe_keys(timeframe)
        instruments = []
        prepared = self.prepared_index.get("instruments", {}) if isinstance(self.prepared_index, dict) else {}
        for instrument_id in self.registry_instruments:
            entry = prepared.get(instrument_id, {})
            timeframes = entry.get("timeframes", {}) if isinstance(entry, dict) else {}
            if any(key in timeframes for key in timeframe_keys):
                instruments.append(instrument_id)
        return instruments

    def _timeframe_keys(self, timeframe: str) -> List[str]:
        if timeframe == "D":
            return ["D", "1440", "1D", "1d"]
        return [timeframe]

    def update_run_state(self):
        reasons = []
        strategy_id = self.strategy_combo.currentData()
        instrument_id = self.instrument_combo.currentData()
        timeframe = self.timeframe_combo.currentText().strip()
        run_mode = self.run_mode_combo.currentText().strip()
        season_id = self.season_combo.currentData()
        start_date = self.start_date_edit.text().strip()
        end_date = self.end_date_edit.text().strip()

        if not strategy_id:
            reasons.append("Missing required inputs: strategy")
        if not timeframe:
            reasons.append("Missing required inputs: timeframe")
        if not instrument_id:
            reasons.append("Missing required inputs: instrument")
        if not run_mode:
            reasons.append("Missing required inputs: run mode")

        if instrument_id and instrument_id not in self.registry_instruments:
            reasons.append("Instrument not registered")

        if instrument_id and not self._is_prepared(instrument_id, timeframe):
            reasons.append("Data not prepared for selected timeframe")

        if run_mode in {"backtest", "research"}:
            if not start_date or not end_date:
                reasons.append("Invalid date range")
            else:
                try:
                    start_dt = datetime.fromisoformat(start_date)
                    end_dt = datetime.fromisoformat(end_date)
                    if start_dt > end_dt:
                        reasons.append("Invalid date range")
                except ValueError:
                    reasons.append("Invalid date range")

        if run_mode == "optimize":
            if not self.research_run_id_edit.text().strip():
                reasons.append("Research Run ID is required for optimize")

        if run_mode == "wfs" and not season_id:
            reasons.append("Season required for WFS run mode")

        readiness_block, readiness_detail = self._evaluate_readiness(strategy_id, instrument_id, timeframe, run_mode, season_id)
        if readiness_block:
            reasons.append(f"Readiness blocked: {readiness_detail}")

        if reasons:
            self.run_button.setEnabled(False)
            self.run_disabled_reason.setText(" • " + "\n • ".join(reasons))
        else:
            self.run_button.setEnabled(True)
            self.run_disabled_reason.setText("")

    def _evaluate_readiness(self, strategy_id: str, instrument_id: str, timeframe: str,
                            run_mode: str, season_id: Optional[str]) -> Tuple[bool, str]:
        if not strategy_id or not instrument_id or not timeframe or not run_mode:
            return False, ""
        try:
            gate = self.dataset_resolver.evaluate_run_readiness_with_prepare_status(
                strategy_id=strategy_id,
                instrument_id=instrument_id,
                timeframe_id=timeframe,
                mode=run_mode,
                season=season_id or None
            )
            return gate.level == "FAIL", gate.detail
        except Exception as exc:
            logger.warning("Readiness check failed: %s", exc)
            return False, ""

    def _is_prepared(self, instrument_id: str, timeframe: str) -> bool:
        timeframe_keys = self._timeframe_keys(timeframe)
        entry = self.prepared_index.get("instruments", {}).get(instrument_id, {})
        timeframes = entry.get("timeframes", {}) if isinstance(entry, dict) else {}
        return any(key in timeframes for key in timeframe_keys)

    def run_strategy(self):
        strategy_id = self.strategy_combo.currentData()
        instrument_id = self.instrument_combo.currentData()
        timeframe = self.timeframe_combo.currentText().strip()
        run_mode = self.run_mode_combo.currentText().strip()
        season_id = self.season_combo.currentData()
        start_date = self.start_date_edit.text().strip()
        end_date = self.end_date_edit.text().strip()
        research_run_id = self.research_run_id_edit.text().strip()

        if not self.run_button.isEnabled():
            return

        params: Dict[str, Any] = {
            "strategy_id": strategy_id,
            "instrument": instrument_id,
            "timeframe": timeframe,
            "run_mode": run_mode,
            "season": season_id or "",
        }

        if run_mode in {"backtest", "research"}:
            params["start_date"] = start_date
            params["end_date"] = end_date

        if run_mode == "optimize":
            params["research_run_id"] = research_run_id

        if run_mode == "wfs":
            params["start_season"] = season_id or ""
            params["end_season"] = season_id or ""

        try:
            result = submit_job(params)
            job_id = result.get("job_id") if isinstance(result, dict) else str(result)
            
            # Register with UI JobStore (SSOT)
            job_store.upsert(JobRecord(
                job_id=job_id,
                job_type="backtest",
                created_at=datetime.now(),
                status="queued",
                summary=f"Strategy: {strategy_id}, Instrument: {instrument_id}"
            ))
            
            self.last_submitted_job_id = job_id
            self.focused_job_id = job_id
            self.log_signal.emit(f"Job {job_id} submitted")
            
            # Non-silent feedback (UX B3.2)
            self.status_bar_label.setText(f"Submitted {job_id[:8]}... Check Ops tab for progress.")
            self.status_bar_label.setStyleSheet("color: #4CAF50; font-weight: bold;")
            
            self.refresh_jobs()
        except SupervisorClientError as exc:
            QMessageBox.critical(self, "Job Submission Failed", f"Failed to submit job: {exc}")
            logger.error("Job submission failed: %s", exc)

    def start_polling(self):
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self.refresh_jobs)
        self.poll_timer.start(self.poll_interval_ms)

    def toggle_pause(self):
        self.monitor_paused = not self.monitor_paused
        self.pause_resume_btn.setText("Resume" if self.monitor_paused else "Pause")
        if self.monitor_paused:
            self.poll_timer.stop()
        else:
            self.poll_timer.start(self.poll_interval_ms)

    def refresh_jobs(self):
        if self.poller and self.poller.isRunning():
            return
        self.poller = JobsPoller(self.job_limit)
        self.poller.jobs_loaded.connect(self.on_jobs_loaded)
        self.poller.error.connect(self.on_jobs_error)
        self.poller.start()

    def on_jobs_error(self, message: str):
        logger.warning("Jobs refresh failed: %s", message)

    def on_jobs_loaded(self, jobs: list):
        self.jobs = jobs or []
        now = datetime.now(timezone.utc)
        for job in self.jobs:
            job_id = job.get("job_id", "")
            if not job_id:
                continue
            snapshot = {
                "status": job.get("status"),
                "policy_stage": job.get("policy_stage"),
                "failure_message": job.get("failure_message"),
                "error_details": job.get("error_details"),
            }
            prev_snapshot = self.job_snapshots.get(job_id)
            if prev_snapshot != snapshot:
                self.job_last_change[job_id] = now
                self.job_snapshots[job_id] = snapshot
            self.job_last_seen[job_id] = now
            
            # Sync to Global JobStore (SSOT)
            existing = next((j for j in job_store.list_jobs() if j.job_id == job_id), None)
            if existing:
                job_store.upsert(JobRecord(
                    job_id=job_id,
                    job_type=existing.job_type,
                    created_at=existing.created_at,
                    status=self._display_status(snapshot.get("status")).lower(), # Convert to literal
                    progress_stage=snapshot.get("policy_stage") or "",
                    summary=existing.summary,
                    error_digest=snapshot.get("failure_message")
                ))
        
        # Update Handoff Panel (UX B2.1)
        if self.jobs:
            latest = self.jobs[0]
            status = latest.get('status', '').upper()
            job_id = latest.get('job_id', '')
            self.lr_label.setText(f"Latest: {status} ({job_id[:8]})")
            self.latest_run_panel.setVisible(True)
            
            # Update Top-K & Eligibility (UX C1.2 / C2.2)
            is_done = (status == "DONE" or status == "SUCCEEDED")
            self.use_run_btn.setEnabled(is_done)
            if not is_done:
                self.use_run_btn.setToolTip("Run must be COMPLETED to use for portfolio.")
            else:
                self.use_run_btn.setToolTip("Run eligible for portfolio admission.")
                self._populate_topk_mock(job_id)

        self.update_jobs_table()
        self.update_focus_job()

    def update_jobs_table(self):
        self.jobs_table.setRowCount(0)
        for row, job in enumerate(self.jobs):
            self.jobs_table.insertRow(row)
            created = self._format_iso(job.get("created_at"))
            job_id = job.get("job_id", "")
            instrument = job.get("instrument", "—")
            timeframe = job.get("timeframe", "—")
            run_mode = job.get("run_mode", "—")
            status = self._display_status(job.get("status"))
            season = job.get("season", "")
            date_range = season if season else "—"

            values = [created, job_id, instrument, timeframe, run_mode, status, date_range]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if col == 1:
                    item.setData(Qt.ItemDataRole.UserRole, job_id)
                self.jobs_table.setItem(row, col, item)

    def on_job_selected(self):
        selection = self.jobs_table.selectedItems()
        if not selection:
            return
        job_id_item = selection[1]
        job_id = job_id_item.data(Qt.ItemDataRole.UserRole)
        if job_id:
            self.focused_job_id = job_id
            self.update_focus_job()

    def update_focus_job(self):
        job = None
        if self.focused_job_id:
            job = next((j for j in self.jobs if j.get("job_id") == self.focused_job_id), None)
        if job is None and self.last_submitted_job_id:
            job = next((j for j in self.jobs if j.get("job_id") == self.last_submitted_job_id), None)
            if job:
                self.focused_job_id = job.get("job_id")
        if job is None and self.jobs:
            job = self.jobs[0]
            self.focused_job_id = job.get("job_id")

        if not job:
            self._clear_live_status()
            return

        job_id = job.get("job_id", "")
        self.job_id_edit.setText(job_id)
        self.status_label.setText(f"Status: {self._display_status(job.get('status'))}")
        self.submitted_label.setText(f"Submitted: {self._format_iso(job.get('created_at'))}")

        last_change = self.job_last_change.get(job_id)
        last_seen = self.job_last_seen.get(job_id)
        if last_change:
            seconds = int((datetime.now(timezone.utc) - last_change).total_seconds())
            self.last_seen_label.setText(f"Last update: {seconds}s ago")
            self._update_stall_label(job, seconds)
        elif last_seen:
            seconds = int((datetime.now(timezone.utc) - last_seen).total_seconds())
            self.last_seen_label.setText(f"Last update: {seconds}s ago")
        else:
            self.last_seen_label.setText("Last update: —")

        phase_text, progress = self._progress_for_job(job)
        self.phase_label.setText(phase_text)
        self.progress_bar.setValue(progress)
        self.error_label.setText(job.get("failure_message") or "")

    def _clear_live_status(self):
        self.job_id_edit.setText("")
        self.status_label.setText("Status: —")
        self.submitted_label.setText("Submitted: —")
        self.last_seen_label.setText("Last update: —")
        self.phase_label.setText("Phase: —")
        self.progress_bar.setValue(0)
        self.stall_label.setText("")
        self.error_label.setText("")
        self.diagnostics_output.setText("")

    def _progress_for_job(self, job: dict) -> Tuple[str, int]:
        status = job.get("status", "").upper()
        progress = job.get("progress")
        if isinstance(progress, (int, float)):
            pct = max(0, min(100, int(progress * 100))) if progress <= 1 else max(0, min(100, int(progress)))
            return f"Phase: progress {pct}%", pct

        phases = ["queued", "preflight", "running", "postflight", "finalize"]
        phase_index = 0
        policy_stage = (job.get("policy_stage") or "").lower()
        if status in {"RUNNING"}:
            if "preflight" in policy_stage:
                phase_index = 1
            elif "postflight" in policy_stage:
                phase_index = 3
            else:
                phase_index = 2
        elif status in {"SUCCEEDED", "DONE"}:
            phase_index = len(phases) - 1
        elif status in {"FAILED", "REJECTED", "ABORTED", "KILLED"}:
            phase_index = max(phase_index, 2)

        pct = int((phase_index / (len(phases) - 1)) * 100)
        return f"Phase: {phases[phase_index].title()} ({phase_index + 1}/{len(phases)})", pct

    def _update_stall_label(self, job: dict, seconds_since_change: int):
        status = job.get("status", "").upper()
        if status != "RUNNING":
            self.stall_label.setText("")
            return
        if seconds_since_change >= 120:
            self.stall_label.setText(f"LIKELY STALLED • {seconds_since_change}s since change")
        elif seconds_since_change >= 30:
            self.stall_label.setText(f"STALLED? • {seconds_since_change}s since change")
        else:
            self.stall_label.setText(f"Last update: {seconds_since_change}s ago")

    def run_diagnostics(self):
        if not self.focused_job_id:
            return
        worker = DiagnosticsWorker(self.focused_job_id)
        worker.diagnostics_ready.connect(self.on_diagnostics_ready)
        worker.error.connect(lambda msg: self.diagnostics_output.setText(f"Diagnostics failed: {msg}"))
        self.diagnostic_workers.append(worker)
        worker.start()

    def on_diagnostics_ready(self, payload: dict):
        job_id = payload.get("job_id")
        log_tail = payload.get("log_tail", "")
        artifact_count = payload.get("artifact_count", 0)
        checked_at = payload.get("checked_at", "")
        last_line = log_tail.strip().splitlines()[-1] if log_tail else "No log output"
        self.diagnostics_output.setText(
            f"Checked at: {checked_at}\n"
            f"Last log line: {last_line}\n"
            f"Artifact count: {artifact_count}"
        )
        if job_id:
            prev_line = self.job_last_log_line.get(job_id)
            if prev_line != last_line:
                self.job_last_log_line[job_id] = last_line
                self.job_last_change[job_id] = datetime.now(timezone.utc)
            self.job_last_artifact_count[job_id] = artifact_count

    def on_view_artifacts(self):
        if not self.focused_job_id:
            return
        # Show output summary panel with artifacts and gate summary
        self.output_summary_panel.setVisible(True)
        self._update_output_summary(self.focused_job_id)

    def on_view_gate(self):
        if self.focused_job_id:
            self.action_router.handle_action("gate_summary", context={"job_id": self.focused_job_id})

    def hide_output_summary(self):
        self.output_summary_panel.setVisible(False)

    def _update_output_summary(self, job_id: str):
        """Fetch artifacts and gate summary for the job and update the panel."""
        try:
            artifacts = get_artifacts(job_id)
            gate_summary = fetch_gate_summary(job_id)
        except SupervisorClientError as exc:
            logger.error("Failed to fetch output summary for job %s: %s", job_id, exc)
            self.gate_verdict_label.setText("Gate verdict: Error fetching")
            self.artifact_list_label.setText("Artifacts: Error fetching")
            return

        # Update gate verdict
        verdict = gate_summary.get("verdict", "UNKNOWN") if isinstance(gate_summary, dict) else "UNKNOWN"
        color = "#4CAF50" if verdict == "PASS" else "#F44336" if verdict == "FAIL" else "#FF9800"
        self.gate_verdict_label.setText(f"Gate verdict: <span style='color:{color}'>{verdict}</span>")

        # Update artifact list
        if isinstance(artifacts, dict):
            files = artifacts.get("files", []) or []
        elif isinstance(artifacts, list):
            files = artifacts
        else:
            files = []
        if files:
            # Show first 3 artifacts
            display = ", ".join(files[:3])
            if len(files) > 3:
                display += f" (+{len(files) - 3} more)"
            self.artifact_list_label.setText(f"Artifacts: {display}")
        else:
            self.artifact_list_label.setText("Artifacts: None")

    def show_strategy_report_summary(self, job_id: str):
        """Public method to show output summary panel for a given job ID."""
        self.focused_job_id = job_id
        self.output_summary_panel.setVisible(True)
        self._update_output_summary(job_id)

    def show_gate_summary_for_job(self, job_id: Optional[str] = None):
        """Public helper to show gate summary detail for a job."""
        target_job = job_id or self.focused_job_id
        if not target_job:
            logger.info("Gate summary requested but no job is focused")
            return
        self.focused_job_id = target_job
        self.output_summary_panel.setVisible(True)
        self._update_output_summary(target_job)

    def copy_job_id(self):
        if not self.job_id_edit.text():
            return
        clipboard = QApplication.clipboard()
        clipboard.setText(self.job_id_edit.text())

    def _format_iso(self, value: Optional[str]) -> str:
        if not value:
            return "—"
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return value

    def _display_status(self, status: Optional[str]) -> str:
        status_value = (status or "").upper()
        if status_value in {"PENDING", "CREATED", "QUEUED", "STARTED"}:
            return "QUEUED"
        if status_value in {"RUNNING"}:
            return "RUNNING"
        if status_value in {"SUCCEEDED", "DONE"}:
            return "DONE"
        if status_value in {"FAILED", "REJECTED", "ABORTED", "KILLED"}:
            return "FAILED"
        return status_value or "UNKNOWN"

    def _on_open_ops(self):
        if not self.jobs: return
        job_id = self.jobs[0].get("job_id")
        self.action_router.handle_action(f"internal://job/{job_id}")

    def _on_use_for_portfolio(self):
        """Handoff selected research to Portfolio tab."""
        if not self.jobs: return
        job_id = self.jobs[0].get("job_id")
        research_selection_state.set_selection(job_id)
        self.action_router.handle_action("internal://tool/Portfolio")

    def _populate_topk_mock(self, job_id: str):
        """Simulate populating Top-K table from Job artifacts."""
        self.topk_table.setRowCount(3)
        data = [
            ("1", "TrendAlpha_V4 🛡️ 🔥", "0.88", "+$12.4k", "4.2%"),
            ("2", "MeanRev_S3 ⚖️", "0.82", "+$10.1k", "3.8%"),
            ("3", "VolBreak_B1", "0.79", "+$8.9k", "5.1%"),
        ]
        for row, vals in enumerate(data):
            for col, val in enumerate(vals):
                item = QTableWidgetItem(val)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.topk_table.setItem(row, col, item)
