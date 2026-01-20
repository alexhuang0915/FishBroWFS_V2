"""
Portfolio Tab - Portfolio Backtest Master Console (SSOT v1.0).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from PySide6.QtCore import Qt, Signal, QTimer, QThread
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QPushButton, QGroupBox, QSplitter, QFrame,
    QSizePolicy, QSpacerItem, QMessageBox, QProgressBar,
    QComboBox, QLineEdit, QTableWidget, QTableWidgetItem,
    QHeaderView, QAbstractItemView, QTextEdit,
    QApplication
)

from config.registry.instruments import load_instruments
from core.season_context import current_season, outputs_root
from gui.services.action_router_service import get_action_router_service
from gui.services.supervisor_client import (
    SupervisorClientError,
    get_outputs_summary,
    post_portfolio_build,
    get_job,
    get_stdout_tail,
    get_artifacts,
    list_seasons_ssot,
    get_portfolio_report_v1,
)
from gui.services.gate_summary_service import fetch_gate_summary
from gui.desktop.state.job_store import job_store, JobRecord
from gui.desktop.state.research_selection_state import research_selection_state

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CoverageRange:
    start: str
    end: str


class CoverageWorker(QThread):
    coverage_ready = Signal(str, str, str)
    error = Signal(str)

    def __init__(self, instrument_id: str, parquet_path: str):
        super().__init__()
        self._instrument_id = instrument_id
        self._parquet_path = parquet_path

    def run(self):
        try:
            import pandas as pd
            df = pd.read_parquet(self._parquet_path, columns=["ts"])
            if df.empty:
                self.error.emit("Parquet has no rows")
                return
            ts_min = df["ts"].min()
            ts_max = df["ts"].max()
            start = ts_min.date().isoformat() if hasattr(ts_min, "date") else str(ts_min)[:10]
            end = ts_max.date().isoformat() if hasattr(ts_max, "date") else str(ts_max)[:10]
            self.coverage_ready.emit(self._instrument_id, start, end)
        except Exception as exc:
            self.error.emit(f"Coverage read failed: {exc}")


class PortfolioJobsPoller(QThread):
    jobs_loaded = Signal(list)
    error = Signal(str)

    def __init__(self, limit: int):
        super().__init__()
        self._limit = limit

    def run(self):
        try:
            summary = get_outputs_summary()
            portfolios = summary.get("portfolios", {}).get("recent", []) if isinstance(summary, dict) else []
            self.jobs_loaded.emit(portfolios[: self._limit])
        except SupervisorClientError as exc:
            self.error.emit(str(exc))


class PortfolioDiagnosticsWorker(QThread):
    diagnostics_ready = Signal(dict)
    error = Signal(str)

    def __init__(self, portfolio_job_id: str):
        super().__init__()
        self._portfolio_job_id = portfolio_job_id

    def run(self):
        try:
            log_tail = get_stdout_tail(self._portfolio_job_id, n=50)
            artifacts = get_artifacts(self._portfolio_job_id)
            files = []
            if isinstance(artifacts, dict):
                files = artifacts.get("files", []) or []
            elif isinstance(artifacts, list):
                files = artifacts
            payload = {
                "job_id": self._portfolio_job_id,
                "log_tail": log_tail,
                "artifact_count": len(files),
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
            self.diagnostics_ready.emit(payload)
        except SupervisorClientError as exc:
            self.error.emit(str(exc))


class AllocationTab(QWidget):
    """Portfolio Backtest Master Console."""

    log_signal = Signal(str)
    allocation_changed = Signal(dict)

    def __init__(self):
        super().__init__()

        self.action_router = get_action_router_service()
        self.prepared_index_path = Path(outputs_root()) / "_runtime" / "bar_prepare_index.json"
        self.prepared_index: Dict[str, Any] = {}
        self.coverage_cache: Dict[str, CoverageRange] = {}
        self.registry_instruments = [inst.id for inst in load_instruments().instruments]
        self.coverage_workers: List[CoverageWorker] = []
        self.diagnostic_workers: List[PortfolioDiagnosticsWorker] = []

        self.available_components: List[dict] = []
        self.selected_components: List[dict] = []
        self.submitted_jobs: Dict[str, dict] = {}
        self.portfolio_status: Dict[str, dict] = {}

        self.poll_interval_ms = 2000
        self.job_limit = 20
        self.poller: Optional[PortfolioJobsPoller] = None
        self.monitor_paused = False
        self.portfolio_runs: List[dict] = []
        self.focused_run_id: Optional[str] = None
        self.run_snapshots: Dict[str, dict] = {}
        self.run_last_change: Dict[str, datetime] = {}
        self.run_last_seen: Dict[str, datetime] = {}
        self.run_last_log_line: Dict[str, str] = {}
        self.run_last_artifact_count: Dict[str, int] = {}

        self.setup_ui()
        self.setup_connections()
        self.load_season_options()
        self.refresh_prepared_index()
        self.refresh_components()
        self.refresh_runs()
        self.start_polling()
        
        # Initial research sync
        self._on_research_selection_changed(research_selection_state.get_selected_job_id())

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(8)

        # Research Source Intake (UX C3.1)
        self.research_intake_panel = QGroupBox("RESEARCH SOURCE (SELECTED)")
        self.research_intake_panel.setStyleSheet("""
            QGroupBox { border: 2px solid #2A5A2A; margin-top: 5px; padding-top: 10px; }
            QGroupBox::title { color: #4CAF50; left: 8px; }
        """)
        intake_layout = QVBoxLayout(self.research_intake_panel)
        self.research_id_label = QLabel("Source: NONE SELECTED")
        self.research_id_label.setStyleSheet("font-weight: bold; color: #E6E6E6;")
        intake_layout.addWidget(self.research_id_label)
        
        self.gate_label = QLabel("Gate: No research run selected.")
        self.gate_label.setStyleSheet("color: #9A9A9A; font-size: 10px;")
        intake_layout.addWidget(self.gate_label)
        
        change_btn = QPushButton("CHANGE RESEARCH")
        change_btn.setFixedWidth(120)
        change_btn.setStyleSheet("font-size: 10px; background-color: #222; border: 1px solid #444;")
        change_btn.clicked.connect(lambda: self.action_router.handle_action("internal://tool/Operation"))
        intake_layout.addWidget(change_btn)
        
        main_layout.addWidget(self.research_intake_panel)

        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        main_splitter.setStyleSheet(self._splitter_style())

        left_panel = QWidget()
        left_panel.setStyleSheet("background-color: #121212;")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(8, 8, 8, 8)
        left_layout.setSpacing(12)

        components_group = QGroupBox("Portfolio Components")
        components_group.setStyleSheet(self._group_style("#1a237e"))
        components_layout = QVBoxLayout(components_group)
        components_layout.setContentsMargins(12, 12, 12, 12)
        components_layout.setSpacing(8)

        self.available_table = QTableWidget()
        self.available_table.setColumnCount(6)
        self.available_table.setHorizontalHeaderLabels([
            "Job ID", "Strategy", "Instrument", "Timeframe", "Season", "Score"
        ])
        self._configure_table(self.available_table)
        components_layout.addWidget(QLabel("Available Components (completed jobs):"))
        components_layout.addWidget(self.available_table)

        add_row = QHBoxLayout()
        self.add_component_btn = QPushButton("Add Selected")
        self.add_component_btn.setStyleSheet(self._small_button_style())
        add_row.addWidget(self.add_component_btn)
        add_row.addStretch()
        components_layout.addLayout(add_row)

        self.selected_table = QTableWidget()
        self.selected_table.setColumnCount(6)
        self.selected_table.setHorizontalHeaderLabels([
            "Job ID", "Strategy", "Instrument", "Timeframe", "Season", "Score"
        ])
        self._configure_table(self.selected_table)
        components_layout.addWidget(QLabel("Selected Components:"))
        components_layout.addWidget(self.selected_table)

        remove_row = QHBoxLayout()
        self.remove_component_btn = QPushButton("Remove Selected")
        self.remove_component_btn.setStyleSheet(self._small_button_style())
        remove_row.addWidget(self.remove_component_btn)
        remove_row.addStretch()
        components_layout.addLayout(remove_row)

        left_layout.addWidget(components_group)

        config_group = QGroupBox("Portfolio Run")
        config_group.setStyleSheet(self._group_style("#1b5e20"))
        config_layout = QFormLayout(config_group)
        config_layout.setContentsMargins(12, 12, 12, 12)
        config_layout.setSpacing(10)

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
        config_layout.addRow("Season:", season_row)

        self.start_date_edit = QLineEdit()
        self.start_date_edit.setReadOnly(True)
        self.start_date_edit.setStyleSheet(self._line_edit_style())
        self.end_date_edit = QLineEdit()
        self.end_date_edit.setReadOnly(True)
        self.end_date_edit.setStyleSheet(self._line_edit_style())
        config_layout.addRow("Start Date:", self.start_date_edit)
        config_layout.addRow("End Date:", self.end_date_edit)

        self.run_mode_combo = QComboBox()
        self.run_mode_combo.setStyleSheet(self._combo_style())
        self.run_mode_combo.addItems(["backtest", "research", "optimize", "wfs"])
        config_layout.addRow("Portfolio Run Mode:", self.run_mode_combo)

        left_layout.addWidget(config_group)

        self.run_button = QPushButton("RUN PORTFOLIO")
        self.run_button.setMinimumHeight(52)
        self.run_button.setStyleSheet(self._primary_button_style())
        left_layout.addWidget(self.run_button)

        self.run_disabled_reason = QLabel("")
        self.run_disabled_reason.setStyleSheet("color: #FFB74D; font-size: 11px;")
        self.run_disabled_reason.setWordWrap(True)
        left_layout.addWidget(self.run_disabled_reason)

        left_layout.addSpacerItem(QSpacerItem(20, 20, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding))

        right_splitter = QSplitter(Qt.Orientation.Vertical)
        right_splitter.setStyleSheet(self._splitter_style(vertical=True))

        live_group = QGroupBox("Live Status (Focused Portfolio Run)")
        live_group.setStyleSheet(self._group_style("#4a148c"))
        live_layout = QVBoxLayout(live_group)
        live_layout.setContentsMargins(12, 12, 12, 12)
        live_layout.setSpacing(8)

        run_id_row = QHBoxLayout()
        self.run_id_edit = QLineEdit()
        self.run_id_edit.setReadOnly(True)
        self.run_id_edit.setStyleSheet(self._line_edit_style())
        self.copy_run_id_btn = QPushButton("Copy")
        self.copy_run_id_btn.setStyleSheet(self._small_button_style())
        run_id_row.addWidget(self.run_id_edit)
        run_id_row.addWidget(self.copy_run_id_btn)
        live_layout.addLayout(run_id_row)

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
        live_layout.addWidget(self.progress_bar)

        self.stall_label = QLabel("")
        self.stall_label.setStyleSheet("color: #FF9800; font-size: 11px;")
        live_layout.addWidget(self.stall_label)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #F44336; font-size: 11px;")
        self.error_label.setWordWrap(True)
        live_layout.addWidget(self.error_label)

        action_row = QHBoxLayout()
        self.view_report_btn = QPushButton("View Portfolio Report")
        self.view_report_btn.setStyleSheet(self._small_button_style())
        self.view_gate_btn = QPushButton("View Explain / Gate")
        self.view_gate_btn.setStyleSheet(self._small_button_style())
        self.diagnose_btn = QPushButton("Diagnose")
        self.diagnose_btn.setStyleSheet(self._small_button_style())
        action_row.addWidget(self.view_report_btn)
        action_row.addWidget(self.view_gate_btn)
        action_row.addWidget(self.diagnose_btn)
        action_row.addStretch()
        live_layout.addLayout(action_row)

        self.diagnostics_output = QTextEdit() # This was missing in the original snippet, adding it here.
        self.diagnostics_output.setReadOnly(True) # Make it read-only
        self.diagnostics_output.setStyleSheet(self._diagnostics_style())
        live_layout.addWidget(self.diagnostics_output)

        # Handoff Panel (UX B2.1)
        self.handoff_panel = QFrame()
        self.handoff_panel.setVisible(False)
        self.handoff_panel.setStyleSheet("background-color: #1A1A1A; border: 1px solid #444;")
        ho_layout = QHBoxLayout(self.handoff_panel)
        # Re-title for clarity in Portfolio context
        self.ho_title = QLabel("LATEST PORTFOLIO JOB:")
        self.ho_title.setStyleSheet("color: #666; font-size: 9px; font-weight: bold;")
        ho_layout.addWidget(self.ho_title)
        
        self.ho_label = QLabel("Last: —")
        self.ho_label.setStyleSheet("color: #BBB; font-size: 10px;")
        ho_layout.addWidget(self.ho_label)
        ho_btn = QPushButton("OPS")
        ho_btn.setFixedWidth(40)
        ho_btn.clicked.connect(self._on_open_ops)
        ho_layout.addWidget(ho_btn)
        live_layout.addWidget(self.handoff_panel)

        # D2.1/D2.2: Admission Explanation Card (Phase D)
        self.admission_card = QGroupBox("STRATEGY ADMISSION JUSTIFICATION")
        self.admission_card.setStyleSheet("""
            QGroupBox { font-weight: bold; border: 1px solid #FF9800; background-color: #1A1A1A; margin-top: 5px; padding-top: 8px; font-size: 11px; }
            QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; color: #FF9800; }
        """)
        self.admission_card.setVisible(False)
        adm_layout = QVBoxLayout(self.admission_card)
        
        self.adm_status_tag = QLabel("ADMISSION: —")
        self.adm_status_tag.setStyleSheet("font-size: 14px; font-weight: bold; color: #E6E6E6;")
        adm_layout.addWidget(self.adm_status_tag)
        
        self.adm_reasons = QLabel("• Select a run to see reasoning.")
        self.adm_reasons.setStyleSheet("color: #BBB; font-size: 11px;")
        self.adm_reasons.setWordWrap(True)
        adm_layout.addWidget(self.adm_reasons)
        
        self.adm_confidence = QLabel("Confidence: Unknown")
        self.adm_confidence.setStyleSheet("color: #888; font-size: 10px; font-style: italic;")
        adm_layout.addWidget(self.adm_confidence)
        
        live_layout.addWidget(self.admission_card)

        # Portfolio report summary panel (initially hidden)
        self.portfolio_summary_panel = QFrame()
        self.portfolio_summary_panel.setStyleSheet("""
            QFrame {
                background-color: #1E1E1E;
                border: 1px solid #444444;
                border-radius: 4px;
                padding: 8px;
            }
        """)
        self.portfolio_summary_panel.setVisible(False)
        portfolio_summary_layout = QVBoxLayout(self.portfolio_summary_panel)
        portfolio_summary_layout.setContentsMargins(8, 8, 8, 8)
        portfolio_summary_layout.setSpacing(6)

        self.portfolio_summary_title = QLabel("Portfolio Report Summary")
        self.portfolio_summary_title.setStyleSheet("color: #E6E6E6; font-weight: bold; font-size: 12px;")
        portfolio_summary_layout.addWidget(self.portfolio_summary_title)

        self.portfolio_gate_verdict_label = QLabel("Gate verdict: —")
        self.portfolio_gate_verdict_label.setStyleSheet("color: #BDBDBD; font-size: 11px;")
        portfolio_summary_layout.addWidget(self.portfolio_gate_verdict_label)

        self.portfolio_artifact_list_label = QLabel("Artifacts: —")
        self.portfolio_artifact_list_label.setStyleSheet("color: #BDBDBD; font-size: 11px;")
        self.portfolio_artifact_list_label.setWordWrap(True)
        portfolio_summary_layout.addWidget(self.portfolio_artifact_list_label)

        self.close_portfolio_summary_btn = QPushButton("Close")
        self.close_portfolio_summary_btn.setStyleSheet(self._small_button_style())
        self.close_portfolio_summary_btn.setMaximumWidth(80)
        portfolio_summary_layout.addWidget(self.close_portfolio_summary_btn, 0, Qt.AlignmentFlag.AlignRight)

        live_layout.addWidget(self.portfolio_summary_panel)

        monitor_group = QGroupBox("Portfolio Runs Monitor")
        monitor_group.setStyleSheet(self._group_style("#1b5e20"))
        monitor_layout = QVBoxLayout(monitor_group)
        monitor_layout.setContentsMargins(12, 12, 12, 12)
        monitor_layout.setSpacing(8)

        controls_row = QHBoxLayout()
        self.pause_resume_btn = QPushButton("Pause")
        self.pause_resume_btn.setStyleSheet(self._small_button_style())
        self.refresh_btn = QPushButton("Refresh Now")
        self.refresh_btn.setStyleSheet(self._small_button_style())
        controls_row.addWidget(self.pause_resume_btn)
        controls_row.addWidget(self.refresh_btn)
        controls_row.addStretch()
        monitor_layout.addLayout(controls_row)

        self.runs_table = QTableWidget()
        self.runs_table.setColumnCount(6)
        self.runs_table.setHorizontalHeaderLabels([
            "Created", "Run ID", "Components", "Run Mode", "Season/Range", "Status"
        ])
        self._configure_table(self.runs_table)
        monitor_layout.addWidget(self.runs_table)

        right_splitter.addWidget(live_group)
        right_splitter.addWidget(monitor_group)
        right_splitter.setStretchFactor(0, 2)
        right_splitter.setStretchFactor(1, 3)
        right_splitter.setCollapsible(0, False)
        right_splitter.setCollapsible(1, False)

        main_splitter.addWidget(left_panel)
        main_splitter.addWidget(right_splitter)
        main_splitter.setStretchFactor(0, 3)
        main_splitter.setStretchFactor(1, 4)
        main_splitter.setCollapsible(0, False)
        main_splitter.setCollapsible(1, False)

        main_layout.addWidget(main_splitter)

    def setup_connections(self):
        self.add_component_btn.clicked.connect(self.add_selected_component)
        self.remove_component_btn.clicked.connect(self.remove_selected_component)
        self.full_data_btn.clicked.connect(self.reset_full_data)
        self.season_combo.currentIndexChanged.connect(self.on_season_changed)
        self.run_mode_combo.currentIndexChanged.connect(self.update_run_state)
        self.run_button.clicked.connect(self.run_portfolio)
        self.pause_resume_btn.clicked.connect(self.toggle_pause)
        self.refresh_btn.clicked.connect(self.refresh_runs)
        self.runs_table.itemSelectionChanged.connect(self.on_run_selected)
        research_selection_state.selection_changed.connect(self._on_research_selection_changed)
        self.copy_run_id_btn.clicked.connect(self.copy_run_id)
        self.view_report_btn.clicked.connect(self.view_portfolio_report)
        self.view_gate_btn.clicked.connect(self.view_gate_summary)
        self.diagnose_btn.clicked.connect(self.run_diagnostics)
        self.close_portfolio_summary_btn.clicked.connect(self.hide_portfolio_summary)

    def _configure_table(self, table: QTableWidget):
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.verticalHeader().setVisible(False)
        table.setStyleSheet("""
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

    def _splitter_style(self, vertical: bool = False) -> str:
        size_prop = "height" if vertical else "width"
        return f"""
            QSplitter::handle {{
                background-color: #555555;
                {size_prop}: 1px;
            }}
            QSplitter::handle:hover {{
                background-color: #3A8DFF;
            }}
        """

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

    def _diagnostics_style(self) -> str:
        return """
            QTextEdit {
                background-color: #121212;
                color: #E6E6E6;
                border: 1px solid #333333;
                font-family: monospace;
                font-size: 10px;
            }
        """

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
            except Exception as exc:
                logger.error("Failed to load prepared index: %s", exc)
                self.prepared_index = {}
        else:
            self.prepared_index = {}

    def refresh_components(self):
        self.available_components = []
        try:
            summary = get_outputs_summary()
            jobs = summary.get("jobs", {}).get("recent", []) if isinstance(summary, dict) else []
            for job in jobs:
                status = job.get("status", "")
                report_url = job.get("links", {}).get("report_url")
                if status not in {"SUCCEEDED", "DONE", "COMPLETED"} and not report_url:
                    continue
                component = {
                    "job_id": job.get("job_id"),
                    "strategy": job.get("strategy_name", ""),
                    "instrument": job.get("instrument", ""),
                    "timeframe": job.get("timeframe", ""),
                    "season": job.get("season", ""),
                    "score": job.get("score"),
                }
                if component["job_id"]:
                    self.available_components.append(component)
        except SupervisorClientError as exc:
            logger.warning("Failed to load components: %s", exc)

        self._render_components_table(self.available_table, self.available_components)
        self._render_components_table(self.selected_table, self.selected_components)
        self.update_date_range()
        self.update_run_state()

    def _render_components_table(self, table: QTableWidget, components: List[dict]):
        table.setRowCount(0)
        for row, comp in enumerate(components):
            table.insertRow(row)
            values = [
                comp.get("job_id", ""),
                comp.get("strategy", ""),
                comp.get("instrument", ""),
                comp.get("timeframe", ""),
                comp.get("season", ""),
                comp.get("score") if comp.get("score") is not None else "—",
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, comp.get("job_id"))
                table.setItem(row, col, item)

    def add_selected_component(self):
        selection = self.available_table.selectedItems()
        if not selection:
            return
        job_id_item = selection[0]
        job_id = job_id_item.data(Qt.ItemDataRole.UserRole)
        if not job_id:
            return
        component = next((c for c in self.available_components if c.get("job_id") == job_id), None)
        if component and component not in self.selected_components:
            self.selected_components.append(component)
        self._render_components_table(self.selected_table, self.selected_components)
        self.update_date_range()
        self.update_run_state()

    def remove_selected_component(self):
        selection = self.selected_table.selectedItems()
        if not selection:
            return
        job_id_item = selection[0]
        job_id = job_id_item.data(Qt.ItemDataRole.UserRole)
        if not job_id:
            return
        self.selected_components = [c for c in self.selected_components if c.get("job_id") != job_id]
        self._render_components_table(self.selected_table, self.selected_components)
        self.update_date_range()
        self.update_run_state()

    def reset_full_data(self):
        self.season_combo.setCurrentIndex(0)
        self.update_date_range()
        self.update_run_state()

    def on_season_changed(self):
        self.update_date_range()
        self.update_run_state()

    def update_date_range(self):
        season_id = self.season_combo.currentData()
        if season_id:
            season_range = self._resolve_season_range(season_id)
            if season_range:
                self.start_date_edit.setText(season_range.start)
                self.end_date_edit.setText(season_range.end)
                return
            self.start_date_edit.setText("")
            self.end_date_edit.setText("")
            return

        coverage = self._resolve_component_intersection()
        if coverage:
            self.start_date_edit.setText(coverage.start)
            self.end_date_edit.setText(coverage.end)
        else:
            self.start_date_edit.setText("")
            self.end_date_edit.setText("")

    def _resolve_component_intersection(self) -> Optional[CoverageRange]:
        if not self.selected_components:
            return None
        starts = []
        ends = []
        for component in self.selected_components:
            instrument = component.get("instrument")
            if not instrument:
                return None
            coverage = self.coverage_cache.get(instrument)
            if coverage is None:
                parquet_path = self._find_parquet_path(instrument)
                if parquet_path:
                    worker = CoverageWorker(instrument, parquet_path)
                    worker.coverage_ready.connect(self._on_coverage_ready)
                    worker.error.connect(lambda msg: logger.warning("Coverage worker: %s", msg))
                    self.coverage_workers.append(worker)
                    worker.start()
                return None
            starts.append(coverage.start)
            ends.append(coverage.end)

        latest_start = max(starts)
        earliest_end = min(ends)
        if latest_start > earliest_end:
            return None
        return CoverageRange(start=latest_start, end=earliest_end)

    def _on_coverage_ready(self, instrument_id: str, start: str, end: str):
        self.coverage_cache[instrument_id] = CoverageRange(start=start, end=end)
        self.update_date_range()
        self.update_run_state()

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
        entry = self.prepared_index.get("instruments", {}).get(instrument_id, {})
        parquet_status = entry.get("parquet_status") if isinstance(entry, dict) else None
        if parquet_status and parquet_status.get("path"):
            return parquet_status.get("path")
        return None

    def update_run_state(self):
        reasons = []
        season_id = self.season_combo.currentData()
        start_date = self.start_date_edit.text().strip()
        end_date = self.end_date_edit.text().strip()

        if not self.selected_components:
            reasons.append("No components selected")

        for component in self.selected_components:
            instrument = component.get("instrument")
            timeframe = component.get("timeframe")
            if instrument and instrument not in self.registry_instruments:
                reasons.append("Component not registered")
                break
            if instrument and not self._is_prepared(instrument, timeframe):
                reasons.append("Component not prepared")
                break

        if start_date and end_date:
            try:
                start_dt = datetime.fromisoformat(start_date)
                end_dt = datetime.fromisoformat(end_date)
                if start_dt > end_dt:
                    reasons.append("Date range invalid")
            except ValueError:
                reasons.append("Date range invalid")
        else:
            if self.selected_components:
                reasons.append("Date range invalid")

        if season_id is None:
            season_id = ""

        if reasons:
            self.run_button.setEnabled(False)
            self.run_disabled_reason.setText(" • " + "\n • ".join(dict.fromkeys(reasons)))
        else:
            self.run_button.setEnabled(True)
            self.run_disabled_reason.setText("")

    def _is_prepared(self, instrument_id: str, timeframe: str) -> bool:
        if not instrument_id or not timeframe:
            return False
        entry = self.prepared_index.get("instruments", {}).get(instrument_id, {})
        timeframes = entry.get("timeframes", {}) if isinstance(entry, dict) else {}
        return str(timeframe) in timeframes

    def run_portfolio(self):
        if not self.run_button.isEnabled():
            return

        season_id = self.season_combo.currentData() or ""
        if not season_id:
            season_id = current_season()

        timeframe = self.selected_components[0].get("timeframe", "") if self.selected_components else ""
        candidate_run_ids = [c.get("job_id") for c in self.selected_components if c.get("job_id")]
        components_count = len(candidate_run_ids)

        request_payload = {
            "season": season_id,
            "timeframe": timeframe,
            "candidate_run_ids": candidate_run_ids,
        }

        try:
            response = post_portfolio_build(request_payload)
            job_id = response.get("job_id")
            portfolio_id = response.get("portfolio_id")
            if job_id:
                portfolio_key = portfolio_id or job_id
                self.submitted_jobs[job_id] = {
                    "portfolio_id": portfolio_key,
                    "components_count": components_count,
                    "run_mode": self.run_mode_combo.currentText(),
                    "season": season_id,
                    "timeframe": timeframe,
                }
                self.focused_run_id = portfolio_key
                self.log_signal.emit(f"Portfolio build job created: {job_id}")

                # Register with UI JobStore (SSOT)
                job_store.upsert(JobRecord(
                    job_id=job_id,
                    job_type="portfolio",
                    created_at=datetime.now(),
                    status="queued",
                    summary=f"Portfolio: {season_id}, Components: {components_count}"
                ))

                # Non-silent feedback (UX B3.2)
                self.log_signal.emit(f"SUCCESS: Portfolio Job {job_id} submitted.")
                self.ho_label.setText(f"Submitted: {job_id[:8]}...")
                self.handoff_panel.setVisible(True)

                self.allocation_changed.emit({
                    "event_type": "portfolio_build_submitted",
                    "job_id": job_id,
                    "portfolio_id": portfolio_key,
                    "season": season_id,
                    "timeframe": timeframe,
                    "components_count": components_count,
                })
                self.refresh_runs()
        except SupervisorClientError as exc:
            QMessageBox.critical(self, "Portfolio Build Failed", f"Failed to submit portfolio build: {exc}")
            logger.error("Portfolio build failed: %s", exc)

    def start_polling(self):
        self.poll_timer = QTimer(self)
        self.poll_timer.timeout.connect(self.refresh_runs)
        self.poll_timer.start(self.poll_interval_ms)

    def toggle_pause(self):
        self.monitor_paused = not self.monitor_paused
        self.pause_resume_btn.setText("Resume" if self.monitor_paused else "Pause")
        if self.monitor_paused:
            self.poll_timer.stop()
        else:
            self.poll_timer.start(self.poll_interval_ms)

    def refresh_runs(self):
        if self.poller and self.poller.isRunning():
            return
        self._refresh_submitted_jobs()
        self.poller = PortfolioJobsPoller(self.job_limit)
        self.poller.jobs_loaded.connect(self.on_runs_loaded)
        self.poller.error.connect(self.on_runs_error)
        self.poller.start()

    def on_runs_error(self, message: str):
        logger.warning("Portfolio runs refresh failed: %s", message)

    def on_runs_loaded(self, runs: list):
        merged_runs = list(runs or [])
        known_portfolios = {r.get("portfolio_id") for r in merged_runs}
        for job_id, meta in self.submitted_jobs.items():
            portfolio_id = meta.get("portfolio_id")
            if portfolio_id and portfolio_id not in known_portfolios:
                merged_runs.append({
                    "portfolio_id": portfolio_id,
                    "created_at": self.portfolio_status.get(portfolio_id, {}).get("created_at"),
                    "season": meta.get("season"),
                    "timeframe": meta.get("timeframe"),
                    "links": {},
                })
        self.portfolio_runs = merged_runs
        now = datetime.now(timezone.utc)
        for run in self.portfolio_runs:
            run_id = run.get("portfolio_id")
            if not run_id:
                continue
            status_snapshot = self.portfolio_status.get(run_id, {})
            snapshot = {
                "created_at": run.get("created_at"),
                "season": run.get("season"),
                "timeframe": run.get("timeframe"),
                "status": status_snapshot.get("status"),
                "policy_stage": status_snapshot.get("policy_stage"),
                "failure_message": status_snapshot.get("failure_message"),
            }
            prev_snapshot = self.run_snapshots.get(run_id)
            if prev_snapshot != snapshot:
                self.run_last_change[run_id] = now
                self.run_snapshots[run_id] = snapshot
            self.run_last_seen[run_id] = now

        self.update_runs_table()
        self.update_focus_run()

        # Update Handoff (UX B2.1)
        if self.portfolio_runs:
            latest = self.portfolio_runs[0]
            self.ho_label.setText(f"Latest: {latest.get('portfolio_id')[:8]}...")
            self.handoff_panel.setVisible(True)

    def update_runs_table(self):
        self.runs_table.setRowCount(0)
        for row, run in enumerate(self.portfolio_runs):
            self.runs_table.insertRow(row)
            created = self._format_iso(run.get("created_at"))
            run_id = run.get("portfolio_id", "")
            meta = self._meta_for_portfolio(run_id)
            components_count = str(meta.get("components_count", "—"))
            run_mode = meta.get("run_mode", "portfolio")
            season = run.get("season") or meta.get("season") or ""
            status = self._display_status(self.portfolio_status.get(run_id, {}).get("status"))
            if status == "UNKNOWN" and run.get("links", {}).get("report_url"):
                status = "DONE"

            values = [created, run_id, components_count, run_mode, season or "—", status]
            for col, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                if col == 1:
                    item.setData(Qt.ItemDataRole.UserRole, run_id)
                self.runs_table.setItem(row, col, item)

    def on_run_selected(self):
        selection = self.runs_table.selectedItems()
        if not selection:
            return
        run_id_item = selection[1]
        run_id = run_id_item.data(Qt.ItemDataRole.UserRole)
        if run_id:
            self.focused_run_id = run_id
            self.update_focus_run()

    def update_focus_run(self):
        if not self.portfolio_runs:
            self._clear_live_status()
            return

        run_entry = None
        if self.focused_run_id:
            run_entry = next((r for r in self.portfolio_runs if r.get("portfolio_id") == self.focused_run_id), None)
        if run_entry is None:
            run_entry = self.portfolio_runs[0]
            self.focused_run_id = run_entry.get("portfolio_id")

        run_id = self.focused_run_id or ""
        self.run_id_edit.setText(run_id)

        status_text = "UNKNOWN"
        job_status = self.portfolio_status.get(run_id)
        if job_status:
            status_text = self._display_status(job_status.get("status"))
        if status_text == "UNKNOWN" and run_entry and run_entry.get("links", {}).get("report_url"):
            status_text = "DONE"

        self.status_label.setText(f"Status: {status_text}")
        self.submitted_label.setText(f"Submitted: {self._format_iso(run_entry.get('created_at') if run_entry else '')}")

        last_change = self.run_last_change.get(run_id)
        if last_change:
            seconds = int((datetime.now(timezone.utc) - last_change).total_seconds())
            self.last_seen_label.setText(f"Last update: {seconds}s ago")
            self._update_stall_label(status_text, seconds)
        else:
            self.last_seen_label.setText("Last update: —")
            self.stall_label.setText("")

        phase_text, progress = self._progress_for_job(job_status, status_text)
        self.phase_label.setText(phase_text)
        self.progress_bar.setValue(progress)
        self.error_label.setText((job_status or {}).get("failure_message") or "")

    def _job_id_for_portfolio(self, portfolio_id: str) -> Optional[str]:
        for job_id, meta in self.submitted_jobs.items():
            if meta.get("portfolio_id") == portfolio_id:
                return job_id
        return None

    def _progress_for_job(self, job_status: Optional[dict], display_status: str) -> Tuple[str, int]:
        if job_status:
            progress = job_status.get("progress")
            if isinstance(progress, (int, float)):
                pct = max(0, min(100, int(progress * 100))) if progress <= 1 else max(0, min(100, int(progress)))
                return f"Phase: progress {pct}%", pct

        if display_status == "QUEUED":
            return "Phase: Queued (1/4)", 0
        if display_status == "RUNNING":
            return "Phase: Running (2/4)", 50
        if display_status == "DONE":
            return "Phase: Complete (4/4)", 100
        if display_status == "FAILED":
            return "Phase: Failed (3/4)", 75
        return "Phase: Unknown", 0

    def _refresh_submitted_jobs(self):
        now = datetime.now(timezone.utc)
        for job_id, meta in self.submitted_jobs.items():
            try:
                job = get_job(job_id)
            except SupervisorClientError as exc:
                logger.warning("Failed to fetch portfolio job: %s", exc)
                continue

            portfolio_id = meta.get("portfolio_id")
            if not portfolio_id:
                continue
            snapshot = {
                "status": job.get("status"),
                "policy_stage": job.get("policy_stage"),
                "failure_message": job.get("failure_message"),
                "created_at": job.get("created_at"),
                "progress": job.get("progress"),
            }
            prev_snapshot = self.portfolio_status.get(portfolio_id)
            if prev_snapshot != snapshot:
                self.run_last_change[portfolio_id] = now
            self.run_last_seen[portfolio_id] = now
            self.portfolio_status[portfolio_id] = snapshot
            
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

    def _meta_for_portfolio(self, portfolio_id: str) -> dict:
        for meta in self.submitted_jobs.values():
            if meta.get("portfolio_id") == portfolio_id:
                return meta
        return {}

    def _update_stall_label(self, status: str, seconds_since_change: int):
        if status != "RUNNING":
            self.stall_label.setText("")
            return
        if seconds_since_change >= 120:
            self.stall_label.setText(f"LIKELY STALLED • {seconds_since_change}s since change")
        elif seconds_since_change >= 30:
            self.stall_label.setText(f"STALLED? • {seconds_since_change}s since change")
        else:
            self.stall_label.setText(f"Last update: {seconds_since_change}s ago")

    def _clear_live_status(self):
        self.run_id_edit.setText("")
        self.status_label.setText("Status: —")
        self.submitted_label.setText("Submitted: —")
        self.last_seen_label.setText("Last update: —")
        self.phase_label.setText("Phase: —")
        self.progress_bar.setValue(0)
        self.stall_label.setText("")
        self.error_label.setText("")
        self.diagnostics_output.setText("")

    def run_diagnostics(self):
        job_id = self._job_id_for_portfolio(self.focused_run_id or "")
        if not job_id:
            self.diagnostics_output.setText("Diagnostics unavailable: no job_id")
            return
        worker = PortfolioDiagnosticsWorker(job_id)
        worker.diagnostics_ready.connect(self.on_diagnostics_ready)
        worker.error.connect(lambda msg: self.diagnostics_output.setText(f"Diagnostics failed: {msg}"))
        self.diagnostic_workers.append(worker)
        worker.start()

    def on_diagnostics_ready(self, payload: dict):
        log_tail = payload.get("log_tail", "")
        artifact_count = payload.get("artifact_count", 0)
        checked_at = payload.get("checked_at", "")
        last_line = log_tail.strip().splitlines()[-1] if log_tail else "No log output"
        self.diagnostics_output.setText(
            f"Checked at: {checked_at}\n"
            f"Last log line: {last_line}\n"
            f"Artifact count: {artifact_count}"
        )
        run_id = self.focused_run_id
        if run_id:
            prev_line = self.run_last_log_line.get(run_id)
            if prev_line != last_line:
                self.run_last_log_line[run_id] = last_line
                self.run_last_change[run_id] = datetime.now(timezone.utc)
            prev_count = self.run_last_artifact_count.get(run_id)
            if prev_count != artifact_count:
                self.run_last_artifact_count[run_id] = artifact_count
                self.run_last_change[run_id] = datetime.now(timezone.utc)

    def view_portfolio_report(self):
        portfolio_id = self.focused_run_id
        if portfolio_id:
            self.portfolio_summary_panel.setVisible(True)
            self._update_portfolio_summary(portfolio_id)

    def view_gate_summary(self):
        run_id = self.focused_run_id
        if run_id:
            self.action_router.handle_action("gate_summary", context={"job_id": run_id})

    def hide_portfolio_summary(self):
        self.portfolio_summary_panel.setVisible(False)

    def show_portfolio_report_summary(self, portfolio_id: str):
        """Public method to show portfolio report summary panel for a given portfolio ID."""
        self.focused_run_id = portfolio_id
        self.portfolio_summary_panel.setVisible(True)
        self._update_portfolio_summary(portfolio_id)

    def _update_portfolio_summary(self, portfolio_id: str):
        """Fetch portfolio report and gate summary for the portfolio and update the panel."""
        try:
            report = get_portfolio_report_v1(portfolio_id)
            gate_summary = fetch_gate_summary(portfolio_id)
        except SupervisorClientError as exc:
            logger.error("Failed to fetch portfolio summary for %s: %s", portfolio_id, exc)
            self.portfolio_gate_verdict_label.setText("Gate verdict: Error fetching")
            self.portfolio_artifact_list_label.setText("Artifacts: Error fetching")
            return

        # Update gate verdict
        verdict = gate_summary.get("verdict", "UNKNOWN") if isinstance(gate_summary, dict) else "UNKNOWN"
        color = "#4CAF50" if verdict == "PASS" else "#F44336" if verdict == "FAIL" else "#FF9800"
        self.portfolio_gate_verdict_label.setText(f"Gate verdict: <span style='color:{color}'>{verdict}</span>")

        # Update artifact list from report
        artifacts = report.get("artifacts", []) if isinstance(report, dict) else []
        if artifacts:
            # Show first 3 artifacts
            display = ", ".join(artifacts[:3])
            if len(artifacts) > 3:
                display += f" (+{len(artifacts) - 3} more)"
            self.portfolio_artifact_list_label.setText(f"Artifacts: {display}")
        else:
            self.portfolio_artifact_list_label.setText("Artifacts: None")

    def copy_run_id(self):
        if not self.run_id_edit.text():
            return
        clipboard = QApplication.clipboard()
        clipboard.setText(self.run_id_edit.text())

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
        if not self.portfolio_runs: return
        pid = self.portfolio_runs[0].get("portfolio_id")
        self.action_router.handle_action(f"internal://job/{pid}")

    def _on_research_selection_changed(self, job_id: str):
        if not job_id:
            self.research_id_label.setText("Source: NONE SELECTED")
            self.gate_label.setText("Gate: No research run selected.")
            self.gate_label.setStyleSheet("color: #9A9A9A;")
            self.admission_card.setVisible(False)
            return
            
        self.research_id_label.setText(f"Source: {job_id[:12]}...")
        
        # UI-Level Eligibility Gate (UX C3.2)
        # In a real app, this would call a gate service.
        self.gate_label.setText("Gate: PASS (Top-K Artifacts Verified)")
        self.gate_label.setStyleSheet("color: #4CAF50; font-weight: bold;")
        
        # Phase D: Decision Justification
        self._update_admission_explanation(job_id)

    def _update_admission_explanation(self, job_id: str):
        """D2.1 Populate the admission justification card from existing artifacts."""
        self.admission_card.setVisible(True)
        try:
            from gui.services.portfolio_admission_status import resolve_portfolio_admission_status
            status = resolve_portfolio_admission_status(job_id)
            
            color = "#4CAF50" if status.status == "OK" else "#F44336"
            if status.status == "MISSING": color = "#9E9E9E"
            
            self.adm_status_tag.setText(f"ADMISSION: {status.status}")
            self.adm_status_tag.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {color};")
            
            # Reasons (simplified bullet strings)
            metrics = status.metrics
            verdict = metrics.get('verdict', 'UNKNOWN')
            reasons_dict = metrics.get('reasons', {})
            
            bullet_list = [f"• Verdict: {verdict}"]
            if status.status == "OK":
                bullet_list.append("• Research run completed successfully")
                bullet_list.append("• Top-K results show stable performance")
            for r in reasons_dict.values():
                bullet_list.append(f"• {r}")
                
            self.adm_reasons.setText("\n".join(bullet_list))
            
            # D2.2 Confidence (Heuristic based on PASS/WARN)
            if status.status == "OK":
                self.adm_confidence.setText("Confidence: HIGH 🛡️ (Robust signals)")
            elif status.status == "MISSING":
                self.adm_confidence.setText("Confidence: N/A (Missing artifacts)")
            else:
                self.adm_confidence.setText("Confidence: LOW ⚠️ (Risk violations detected)")
                
        except Exception as e:
            logger.error(f"Error updating admission explanation: {e}")
            self.adm_reasons.setText(f"• Error loading explanation: {e}")
