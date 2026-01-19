"""
OpTab Master Console tests (SSOT v1.2).
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from PySide6.QtWidgets import QApplication
from gui.desktop.tabs.op_tab import OpTab
from gui.desktop.tabs import op_tab_refactored
from gui.services.dataset_resolver import GateStatus


@pytest.fixture
def app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def op_tab(app, monkeypatch, tmp_path):
    monkeypatch.setattr(op_tab_refactored, "get_registry_strategies", lambda: [{"id": "s1", "name": "S1"}])
    monkeypatch.setattr(op_tab_refactored, "list_seasons_ssot", lambda: {"seasons": [{"season_id": "2026Q1"}]})
    monkeypatch.setattr(op_tab_refactored, "get_jobs", lambda limit=50: [])
    tab = OpTab()
    impl = tab._impl
    impl.dataset_resolver.evaluate_run_readiness_with_prepare_status = (
        lambda **kwargs: GateStatus(level="PASS", title="Run Readiness Gate", detail="OK")
    )
    impl.prepared_index_path = tmp_path / "bar_prepare_index.json"
    impl.prepared_index_path.write_text(json.dumps({
        "instruments": {
            "CME.MNQ": {
                "timeframes": {
                    "60": {"status": "built"}
                },
                "parquet_status": {"path": ""}
            }
        }
    }))
    impl.refresh_prepared_index()
    yield tab
    tab.deleteLater()


def test_op_tab_has_master_console_controls(op_tab):
    impl = op_tab._impl
    assert impl.strategy_combo is not None
    assert impl.timeframe_combo is not None
    assert impl.instrument_combo is not None
    assert impl.run_mode_combo is not None
    assert impl.season_combo is not None
    assert impl.run_button.text() == "RUN STRATEGY"


def test_run_gating_requires_prepared_index(op_tab):
    impl = op_tab._impl
    impl.strategy_combo.setCurrentIndex(1)
    impl.timeframe_combo.setCurrentText("60")
    impl.on_timeframe_changed()
    impl.instrument_combo.setCurrentIndex(1)
    impl.run_mode_combo.setCurrentText("backtest")
    impl.coverage_cache["CME.MNQ"] = op_tab_refactored.CoverageRange("2020-01-01", "2020-12-31")
    impl.update_date_range()
    impl.update_run_state()
    assert impl.run_button.isEnabled()

    impl.prepared_index["instruments"]["CME.MNQ"]["timeframes"] = {}
    impl.refresh_instrument_options()
    impl.instrument_combo.setCurrentIndex(0)
    impl.update_run_state()
    assert not impl.run_button.isEnabled()


def test_full_date_range_resolution(op_tab):
    impl = op_tab._impl
    impl.coverage_cache["CME.MNQ"] = op_tab_refactored.CoverageRange("2020-01-01", "2020-12-31")
    impl.timeframe_combo.setCurrentText("60")
    impl.on_timeframe_changed()
    impl.instrument_combo.setCurrentIndex(1)
    impl.update_date_range()
    assert impl.start_date_edit.text() == "2020-01-01"
    assert impl.end_date_edit.text() == "2020-12-31"


def test_season_selection_overrides_date_range(op_tab):
    impl = op_tab._impl
    impl.timeframe_combo.setCurrentText("60")
    impl.on_timeframe_changed()
    impl.instrument_combo.setCurrentIndex(1)
    impl.season_combo.setCurrentIndex(1)
    impl.update_date_range()
    assert impl.start_date_edit.text().startswith("2026-01")
    assert impl.end_date_edit.text().startswith("2026-03")


def test_polling_refresh_updates_job_list(op_tab):
    impl = op_tab._impl
    fake_jobs = [{
        "job_id": "job-123",
        "status": "RUNNING",
        "created_at": "2026-01-01T00:00:00Z",
        "instrument": "CME.MNQ",
        "timeframe": "60",
        "run_mode": "backtest",
        "season": "2026Q1",
    }]
    impl.on_jobs_loaded(fake_jobs)
    assert impl.jobs_table.rowCount() == 1
    assert impl.jobs_table.item(0, 1).text() == "job-123"


def test_stall_detection_labels(op_tab):
    impl = op_tab._impl
    job = {
        "job_id": "job-456",
        "status": "RUNNING",
        "created_at": "2026-01-01T00:00:00Z",
    }
    impl.on_jobs_loaded([job])
    impl.job_last_change["job-456"] = datetime.now(timezone.utc) - timedelta(seconds=40)
    impl.focused_job_id = "job-456"
    impl.update_focus_job()
    assert "STALLED?" in impl.stall_label.text()


def test_progress_bar_phase_mapping(op_tab):
    impl = op_tab._impl
    phase_text, pct = impl._progress_for_job({"status": "RUNNING", "policy_stage": "preflight"})
    assert "Preflight" in phase_text
    assert pct > 0